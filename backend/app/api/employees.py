from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    Actor,
    get_current_actor,
    get_current_admin_principal,
    get_current_full_hr_principal,
    get_current_hr_or_self,
    get_current_hr_principal,
)
from app.db import get_db
from app.errors import AppError
from app.models import AuditAction, Employee, EmployeeLocationPeriod, HrRole, Location, Team
from app.schemas.work_time_model import WorkTimeModelInput, WorkTimeModelSetRequest
from app.schemas.employee import (
    BulkImportResult,
    BulkImportRowError,
    EmployeeCreateRequest,
    EmployeeHrRoleUpdateRequest,
    EmployeePasswordResetRequest,
    EmployeePasswordResetResponse,
    EmployeeResponse,
    EmployeeUpdateRequest,
    LocationEmployeeResponse,
)
from app.services.admin_service import ensure_not_last_admin
from app.services.audit_service import log_action
from app.services.auth_service import generate_one_time_password, hash_password
from app.services.document_service import delete_employee_documents
from app.services.credentials_mail import login_url, send_credentials_email
from app.services.email_service import describe_smtp_error, resolve_smtp_config
from app.services.employee_import_service import ParsedEmployeeRow, parse_bulk_import_csv
from app.services.team_scope_service import ensure_employee_visible, supervisor_team_ids
from app.services.timesheet_service import calculate_day, employee_timezone, local_date
from app.services.timesheet_service import invalidate_balance
from app.services.period_service import ensure_open_from
from app.services.settings_service import get_or_create_settings
from app.services.plan_service import ensure_can_activate, limit_error, plan_status


async def _record_location_change(db: AsyncSession, employee: Employee, new_location_id: int, effective: date) -> None:
    """Standort-Historie fortschreiben (für Feiertage je Tag, siehe timesheet_service.location_on)."""
    existing = (
        await db.execute(select(EmployeeLocationPeriod).where(EmployeeLocationPeriod.employee_id == employee.id))
    ).scalars().all()
    if not existing:
        db.add(EmployeeLocationPeriod(employee_id=employee.id, location_id=employee.location_id, valid_from=date(2000, 1, 1)))
    for period in existing:
        if period.valid_from >= effective:
            await db.delete(period)
    db.add(EmployeeLocationPeriod(employee_id=employee.id, location_id=new_location_id, valid_from=effective))


router = APIRouter(tags=["employees"])


@router.get("/employees", response_model=list[EmployeeResponse])
async def list_employees(
    location_id: int | None = Query(default=None),
    active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    actor: Actor = Depends(get_current_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> list[EmployeeResponse]:
    stmt = select(Employee).where(Employee.tenant_id == actor.tenant_id)
    if location_id is not None:
        stmt = stmt.where(Employee.location_id == location_id)
    if active is not None:
        stmt = stmt.where(Employee.active == active)
    if actor.is_supervisor_level:
        team_ids = await supervisor_team_ids(db, actor)
        stmt = stmt.where(Employee.team_id.in_(team_ids or set()))
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Employee.first_name.ilike(pattern),
                Employee.last_name.ilike(pattern),
                Employee.employee_number.ilike(pattern),
            )
        )
    stmt = stmt.order_by(Employee.last_name.asc(), Employee.first_name.asc())

    result = await db.execute(stmt)
    return [EmployeeResponse.model_validate(e) for e in result.scalars().all()]


@router.get("/locations/{location_id}/employees", response_model=list[LocationEmployeeResponse])
async def list_location_employees(
    location_id: int,
    actor: Actor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> list[LocationEmployeeResponse]:
    """Für den Kiosk: Mitarbeiterliste eines Standorts inkl. aktuellem
    Anwesenheitsstatus (Farbcodierung der Kachel) und PIN-Hinterlegung."""
    location = await db.get(Location, location_id)
    if location is None or location.tenant_id != actor.tenant_id:
        raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")
    if actor.device is not None and actor.device.location_id != location_id:
        raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")
    if actor.device is None and not actor.is_hr_level:
        # Die Liste enthält NFC-UIDs und Anwesenheitsstatus – nichts für Kollegen im Self-Service.
        raise AppError(403, "FORBIDDEN", "Keine Berechtigung.")

    stmt = select(Employee).where(Employee.location_id == location_id, Employee.active.is_(True))
    # Teamleader sehen nur ihre Teams und keine Chip-Nummern (die braucht nur das Tablet bzw. HR).
    limited = actor.device is None and actor.is_supervisor_level
    if limited:
        stmt = stmt.where(Employee.team_id.in_(await supervisor_team_ids(db, actor) or set()))
    result = await db.execute(stmt.order_by(Employee.last_name.asc(), Employee.first_name.asc()))
    employees = result.scalars().all()

    responses = []
    for employee in employees:
        tz = await employee_timezone(db, employee)
        today = local_date(datetime.now(UTC), tz)
        calculation = await calculate_day(db, employee, today, tz)
        responses.append(
            LocationEmployeeResponse(
                id=employee.id,
                first_name=employee.first_name,
                last_name=employee.last_name,
                employee_number=employee.employee_number,
                has_pin=employee.has_pin,
                nfc_uid=None if limited else employee.nfc_uid,
                today_status=calculation.status,
                today_flags=calculation.flags,
            )
        )
    return responses


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    actor: Actor = Depends(get_current_hr_or_self),
    db: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if actor.is_hr_level:
        await ensure_employee_visible(db, actor, employee)
    return EmployeeResponse.model_validate(employee)


@router.post("/employees", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    payload: EmployeeCreateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    location = await db.get(Location, payload.location_id)
    if location is None or location.tenant_id != actor.tenant_id:
        raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")
    if payload.work_time_model is not None and payload.work_time_model.exceeds_daily_maximum:
        raise AppError(
            400,
            "MAX_DAILY_WORKING_TIME_EXCEEDED",
            "Das Arbeitszeitmodell ergibt mehr als 10 Stunden pro Arbeitstag (§3 ArbZG).",
        )
    if payload.team_id is not None:
        team = await db.get(Team, payload.team_id)
        if team is None or team.tenant_id != actor.tenant_id:
            raise AppError(404, "TEAM_NOT_FOUND", "Team nicht gefunden.")

    if payload.active:
        await ensure_can_activate(db, actor.tenant_id)

    defaults = await get_or_create_settings(db, actor.tenant_id)
    employee = Employee(
        tenant_id=actor.tenant_id,
        location_id=payload.location_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        employee_number=payload.employee_number,
        active=payload.active,
        login_email=payload.login_email,
        password_hash=hash_password(payload.password) if payload.password else None,
        auto_break_enabled=defaults.default_auto_break if payload.auto_break_enabled is None else payload.auto_break_enabled,
        pin_hash=hash_password(payload.pin) if payload.pin else None,
        nfc_uid=payload.nfc_uid or None,
        hire_date=payload.hire_date,
        termination_date=payload.termination_date,
        birth_date=payload.birth_date,
        show_birthday_in_calendar=(
            defaults.default_show_birthday if payload.show_birthday_in_calendar is None else payload.show_birthday_in_calendar
        ),
        team_id=payload.team_id,
    )
    db.add(employee)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict_error(exc)

    await db.refresh(employee)

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.EMPLOYEE_CREATED,
        entity_type="employee",
        entity_id=employee.id,
        detail=f"{employee.first_name} {employee.last_name} ({employee.employee_number})",
    )
    await db.commit()

    model = payload.work_time_model
    if model is None and defaults.default_day_minutes and not payload.no_work_time_model:
        # Standard-Arbeitszeitmodell des Mandanten (Einstellungen)
        model = WorkTimeModelInput(daily_hours=[int(m) / 60 for m in defaults.default_day_minutes.split(",")])
    if model is not None:
        from app.api.work_time_model import set_work_time_model

        await set_work_time_model(
            employee.id,
            WorkTimeModelSetRequest.from_input(model, employee.hire_date or date.today()),
            actor,
            db,
        )
        await db.refresh(employee)

    return EmployeeResponse.model_validate(employee)


@router.post("/employees/bulk-import", response_model=BulkImportResult)
async def bulk_import_employees(
    file: UploadFile = File(...),
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> BulkImportResult:
    """CSV-Import für Mitarbeiterstammdaten (Semikolon-getrennt, UTF-8).
    Zeilen werden unabhängig voneinander validiert: fehlerhafte Zeilen werden
    übersprungen und im Ergebnis gemeldet, gültige Zeilen trotzdem angelegt –
    kein Alles-oder-Nichts-Import."""
    raw = await file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError(400, "INVALID_ENCODING", "Die Datei muss UTF-8-kodiert sein.") from exc

    locations_result = await db.execute(select(Location).where(Location.tenant_id == actor.tenant_id))
    teams_result = await db.execute(select(Team).where(Team.tenant_id == actor.tenant_id))
    existing_numbers_result = await db.execute(
        select(Employee.employee_number).where(Employee.tenant_id == actor.tenant_id)
    )
    existing_emails_result = await db.execute(
        select(Employee.login_email).where(
            Employee.tenant_id == actor.tenant_id, Employee.login_email.is_not(None)
        )
    )

    rows, errors = parse_bulk_import_csv(
        content,
        locations=list(locations_result.scalars().all()),
        teams=list(teams_result.scalars().all()),
        existing_employee_numbers=set(existing_numbers_result.scalars().all()),
        existing_login_emails=set(existing_emails_result.scalars().all()),
    )

    # Tarifgrenze: aktive Zeilen nur bis zur verbleibenden Anzahl, der Rest wird als Fehler gemeldet
    # (inaktive Mitarbeiter zählen nicht).
    status = await plan_status(db, actor.tenant_id)
    remaining = status.remaining
    if remaining is not None:
        allowed: list[ParsedEmployeeRow] = []
        for parsed in rows:
            if parsed.active and remaining <= 0:
                errors.append(BulkImportRowError(row=parsed.line, message=limit_error(status.limit).message))
                continue
            remaining -= 1 if parsed.active else 0
            allowed.append(parsed)
        rows = allowed
        errors.sort(key=lambda error: error.row)

    defaults = await get_or_create_settings(db, actor.tenant_id)
    created: list[tuple[Employee, ParsedEmployeeRow]] = []
    for parsed in rows:
        new_employee = Employee(
                tenant_id=actor.tenant_id,
                location_id=parsed.location_id,
                team_id=parsed.team_id,
                first_name=parsed.first_name,
                last_name=parsed.last_name,
                employee_number=parsed.employee_number,
                active=parsed.active,
                login_email=parsed.login_email,
                hire_date=parsed.hire_date,
                birth_date=parsed.birth_date,
                auto_break_enabled=defaults.default_auto_break,
                show_birthday_in_calendar=defaults.default_show_birthday,
            )
        db.add(new_employee)
        created.append((new_employee, parsed))

    if rows:
        log_action(
            db,
            tenant_id=actor.tenant_id,
            actor_hr_user_id=actor.audit_hr_user_id,
            actor_employee_id=actor.audit_employee_id,
            action=AuditAction.EMPLOYEES_BULK_IMPORTED,
            entity_type="employee",
            entity_id=0,
            detail=f"{len(rows)} Mitarbeiter importiert, {len(errors)} Zeile(n) mit Fehler übersprungen",
        )

    await db.commit()

    from app.api.work_time_model import set_work_time_model

    default_daily = [int(m) / 60 for m in defaults.default_day_minutes.split(",")] if defaults.default_day_minutes else None
    for new_employee, parsed in created:
        has_model = (
            parsed.on_demand
            or parsed.flexible
            or (parsed.weekly_hours is not None and parsed.weekdays)
            or parsed.daily_hours
        )
        if not has_model and default_daily:
            parsed.daily_hours = default_daily  # Standard-Arbeitszeitmodell des Mandanten
            has_model = True
        if has_model:
            await set_work_time_model(
                new_employee.id,
                WorkTimeModelSetRequest(
                    weekly_hours=parsed.weekly_hours,
                    weekdays=parsed.weekdays,
                    daily_hours=parsed.daily_hours,
                    flexible=parsed.flexible,
                    on_demand=parsed.on_demand,
                    monthly_cap_hours=parsed.monthly_cap_hours,
                    valid_from=parsed.hire_date or date.today(),
                ),
                actor,
                db,
            )

    return BulkImportResult(created=len(rows), errors=errors)


@router.patch("/employees/{employee_id}/hr-role", response_model=EmployeeResponse)
async def update_employee_hr_role(
    employee_id: int,
    payload: EmployeeHrRoleUpdateRequest,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """Vergibt oder entzieht die HR-Berechtigung eines Mitarbeiters – mit
    gesetztem hr_role bekommt der Mitarbeiter mit seinem eigenen Login vollen
    HR-Webapp-Zugriff, siehe app/api/deps.py get_current_hr_principal."""
    if payload.hr_role == HrRole.SUPER_ADMIN:
        # Plattformweite Rolle ohne Mandantenbezug – nie einem Mitarbeiter zuweisbar
        # (gleiche Regel wie beim Anlegen von HR-Usern, siehe app/api/hr_users.py).
        raise AppError(403, "FORBIDDEN", "Diese Rolle kann hier nicht vergeben werden.")

    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")

    if employee.hr_role == HrRole.ADMIN and payload.hr_role != HrRole.ADMIN:
        await ensure_not_last_admin(db, actor.tenant_id, exclude_employee_id=employee.id)

    old_role = employee.hr_role.value if employee.hr_role else "keine"
    new_role = payload.hr_role.value if payload.hr_role else "keine"
    old_payroll = employee.hr_payroll_access
    employee.hr_role = payload.hr_role
    if payload.payroll_access is not None:
        employee.hr_payroll_access = payload.payroll_access
    if employee.hr_role != HrRole.HR:
        employee.hr_payroll_access = False  # Admins haben sie immer, Teamleader und Mitarbeiter nie
    if employee.hr_payroll_access != old_payroll:
        new_role += ", Vergütung & Lohn-Export " + ("an" if employee.hr_payroll_access else "aus")

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.EMPLOYEE_HR_ROLE_CHANGED,
        entity_type="employee",
        entity_id=employee.id,
        detail=f"Rolle geändert: {old_role} -> {new_role}",
    )

    await db.commit()
    await db.refresh(employee)
    return EmployeeResponse.model_validate(employee)


@router.post("/employees/{employee_id}/reset-password", response_model=EmployeePasswordResetResponse)
async def reset_employee_password(
    employee_id: int,
    payload: EmployeePasswordResetRequest,
    request: Request,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> EmployeePasswordResetResponse:
    """Setzt das Passwort eines Mitarbeiter-Logins auf ein neues Einmalpasswort –
    wahlweise per E-Mail (über den SMTP des Mandanten) oder zur einmaligen
    Anzeige. Bewusst nur für Admins: ein HR-Reset könnte sonst ein Admin-Konto
    übernehmen."""
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if employee.login_email is None:
        raise AppError(400, "NO_LOGIN", "Der Mitarbeiter hat keine Login-E-Mail hinterlegt.")
    if employee.anonymized_at is not None:
        raise AppError(400, "ALREADY_ANONYMIZED", "Mitarbeiter ist anonymisiert.")

    config = None
    if payload.send_email:
        config = await resolve_smtp_config(db, actor.tenant_id)
        if config is None:
            raise AppError(400, "EMAIL_NOT_CONFIGURED", "Es ist kein SMTP-Server konfiguriert.")

    new_password = generate_one_time_password()
    employee.password_hash = hash_password(new_password)

    if payload.send_email:
        try:
            await send_credentials_email(
                to=employee.login_email,
                organisation=f"{employee.first_name} {employee.last_name}",
                url=login_url(request),
                login_email=employee.login_email,
                password=new_password,
                config=config,
                raise_errors=True,
            )
        except Exception as exc:
            await db.rollback()
            raise AppError(400, "EMAIL_SEND_FAILED", describe_smtp_error(exc)) from exc

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.EMPLOYEE_PASSWORD_RESET,
        entity_type="employee",
        entity_id=employee.id,
        detail=f"{employee.first_name} {employee.last_name} ({employee.employee_number}) – "
        + ("per E-Mail gesendet" if payload.send_email else "einmalig angezeigt"),
    )
    await db.commit()
    return EmployeePasswordResetResponse(
        emailed=payload.send_email, new_password=None if payload.send_email else new_password
    )


@router.post("/employees/{employee_id}/anonymize", response_model=EmployeeResponse)
async def anonymize_employee(
    employee_id: int,
    actor: Actor = Depends(get_current_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """DSGVO-Anonymisierung: überschreibt die personenbezogenen Stammdaten
    eines ausgeschiedenen Mitarbeiters unwiderruflich (Name, Login,
    Zugangsdaten, Geburtsdatum) – Stempelungen und Abwesenheiten bleiben für
    die gesetzliche Aufbewahrungsfrist unverändert bestehen, da sie sich nach
    der Anonymisierung nicht mehr auf eine identifizierbare Person beziehen.
    Nur für vollwertige Admins, analog zu HR-Rollen-Änderungen."""
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if employee.anonymized_at is not None:
        raise AppError(400, "ALREADY_ANONYMIZED", "Mitarbeiter ist bereits anonymisiert.")
    if employee.termination_date is None:
        raise AppError(
            400,
            "EMPLOYEE_NOT_TERMINATED",
            "Nur ausgeschiedene Mitarbeiter (mit Austrittsdatum) können anonymisiert werden.",
        )

    if employee.hr_role == HrRole.ADMIN:
        await ensure_not_last_admin(db, actor.tenant_id, exclude_employee_id=employee.id)

    original_label = f"{employee.first_name} {employee.last_name} ({employee.employee_number})"

    # Personalakte: Dokumente entfernen, außer solchen unter Aufbewahrungsfrist.
    removed_documents = await delete_employee_documents(db, employee.id)

    employee.first_name = "Anonymisiert"
    employee.last_name = f"Mitarbeiter {employee.id}"
    employee.login_email = None
    employee.password_hash = None
    employee.pin_hash = None
    employee.nfc_uid = None
    employee.birth_date = None
    employee.hr_role = None
    employee.active = False
    employee.anonymized_at = datetime.now(UTC)

    log_action(
        db,
        tenant_id=actor.tenant_id,
        actor_hr_user_id=actor.audit_hr_user_id,
        actor_employee_id=actor.audit_employee_id,
        action=AuditAction.EMPLOYEE_ANONYMIZED,
        entity_type="employee",
        entity_id=employee.id,
        detail=f"{original_label}; {removed_documents} Dokument(e) gelöscht",
    )

    await db.commit()
    await db.refresh(employee)
    return EmployeeResponse.model_validate(employee)


def _conflict_error(exc: IntegrityError) -> AppError:
    message = str(exc.orig).lower()
    if "login_email" in message:
        return AppError(409, "LOGIN_EMAIL_TAKEN", "Diese Login-E-Mail wird bereits verwendet.")
    if "nfc_uid" in message:
        return AppError(409, "NFC_UID_TAKEN", "Diese Karte ist bereits einem anderen Mitarbeiter zugeordnet.")
    return AppError(409, "EMPLOYEE_NUMBER_TAKEN", "Personalnummer wird bereits verwendet.")


@router.patch("/employees/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    payload: EmployeeUpdateRequest,
    actor: Actor = Depends(get_current_full_hr_principal),
    db: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    employee = await db.get(Employee, employee_id)
    if employee is None or employee.tenant_id != actor.tenant_id:
        raise AppError(404, "EMPLOYEE_NOT_FOUND", "Mitarbeiter nicht gefunden.")
    if employee.anonymized_at is not None:
        raise AppError(400, "ALREADY_ANONYMIZED", "Anonymisierte Mitarbeiter können nicht mehr bearbeitet werden.")

    # Konten mit HR-Berechtigung sind Zugänge zur Verwaltung: Login, Passwort und
    # Aktiv-Status darf nur ein Admin ändern – sonst könnte ein HR-Nutzer per
    # Passwort-Änderung ein Admin-Konto übernehmen (siehe auch reset-password).
    # Unverändert mitgeschickte Werte (der Dialog sendet die Login-E-Mail immer) zählen nicht.
    email_changed = payload.login_email is not None and payload.login_email.lower() != (employee.login_email or "").lower()
    touches_access = (
        payload.password is not None
        or email_changed
        or (payload.active is not None and payload.active != employee.active)
    )
    if employee.hr_role is not None and touches_access and not actor.is_admin_level:
        raise AppError(
            403,
            "ADMIN_PERMISSION_REQUIRED",
            "Zugangsdaten und Aktiv-Status von Mitarbeitern mit HR-Berechtigung dürfen nur Administratoren ändern.",
        )
    if employee.hr_role == HrRole.ADMIN and payload.active is False and employee.active:
        await ensure_not_last_admin(db, actor.tenant_id, exclude_employee_id=employee.id)

    # Ein- und Austritt bestimmen den Kontozeitraum des Gleitzeitkontos.
    balance_relevant = (employee.hire_date, employee.termination_date)
    if payload.location_id is not None and payload.location_id != employee.location_id:
        location = await db.get(Location, payload.location_id)
        if location is None or location.tenant_id != actor.tenant_id:
            raise AppError(404, "LOCATION_NOT_FOUND", "Standort nicht gefunden.")
        effective = payload.location_valid_from or date.today()
        await ensure_open_from(db, employee.id, effective)
        await _record_location_change(db, employee, payload.location_id, effective)
        await invalidate_balance(db, employee.id, effective)
        employee.location_id = payload.location_id
    if payload.first_name is not None:
        employee.first_name = payload.first_name
    if payload.last_name is not None:
        employee.last_name = payload.last_name
    if payload.employee_number is not None:
        employee.employee_number = payload.employee_number
    if payload.active is not None:
        if payload.active and not employee.active:
            await ensure_can_activate(db, actor.tenant_id)
        employee.active = payload.active
    if payload.login_email is not None:
        employee.login_email = payload.login_email
    if payload.password is not None:
        employee.password_hash = hash_password(payload.password)
    if payload.auto_break_enabled is not None:
        employee.auto_break_enabled = payload.auto_break_enabled
    if payload.pin is not None:
        employee.pin_hash = hash_password(payload.pin) if payload.pin else None
    if payload.nfc_uid is not None:
        employee.nfc_uid = payload.nfc_uid or None
    if payload.hire_date is not None:
        employee.hire_date = payload.hire_date
    elif payload.clear_hire_date:
        employee.hire_date = None
    if payload.termination_date is not None:
        employee.termination_date = payload.termination_date
    elif payload.clear_termination_date:
        employee.termination_date = None
    if payload.birth_date is not None:
        employee.birth_date = payload.birth_date
    elif payload.clear_birth_date:
        employee.birth_date = None
    if payload.show_birthday_in_calendar is not None:
        employee.show_birthday_in_calendar = payload.show_birthday_in_calendar
    if payload.team_id is not None:
        team = await db.get(Team, payload.team_id)
        if team is None or team.tenant_id != actor.tenant_id:
            raise AppError(404, "TEAM_NOT_FOUND", "Team nicht gefunden.")
        employee.team_id = payload.team_id
    elif payload.clear_team_id:
        employee.team_id = None
    if (employee.hire_date, employee.termination_date) != balance_relevant:
        await invalidate_balance(db, employee.id, None)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict_error(exc)

    await db.refresh(employee)
    return EmployeeResponse.model_validate(employee)
