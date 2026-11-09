"""Test-Helfer für die Organisation ohne Teams: Abteilung mit Leitungen und Stellvertretungen
(Führungskraft mit Login).

Eine Führungskraft ist ein Mitarbeiter mit Konto (Rolle SUPERVISOR) und Leitung einer Abteilung; sie
sieht sich selbst und alle direkt und indirekt Unterstellten (app/services/scope_service.py)."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Department, DepartmentLeader, Employee, HrRole, Location
from app.services.auth_service import hash_password


async def supervisor_with_department(
    db_session: AsyncSession,
    location: Location,
    *,
    email: str = "lead@example.com",
    password: str = "pw",
    department_name: str = "Team Nord",
    members: tuple[Employee, ...] = (),
    first_name: str = "Sam",
    last_name: str = "Leitung",
    employee_number: str | None = None,
    role: HrRole = HrRole.SUPERVISOR,
    parent: Department | None = None,
) -> tuple[Department, Employee, Account]:
    """Legt eine Abteilung (optional unter parent) an, deren Leitung ein neuer Mitarbeiter mit Login
    ist, und ordnet members (bereits gespeicherte Mitarbeiter) dieser Abteilung zu."""
    head = Employee(
        location_id=location.id,
        first_name=first_name,
        last_name=last_name,
        employee_number=employee_number or f"L-{department_name}",
    )
    db_session.add(head)
    await db_session.flush()
    # Über die Beziehung (nicht nur employee_id) verknüpfen: Die Tests teilen sich die Session mit der
    # App, head.account muss deshalb auch im Speicher gesetzt sein (sonst sähe die App die Leitung
    # ohne Konto, z. B. bei Genehmigung und Benachrichtigung).
    account = Account(email=email, password_hash=hash_password(password), role=role, employee=head)
    department = Department(name=department_name, parent_id=parent.id if parent is not None else None)
    db_session.add_all([account, department])
    await db_session.flush()
    db_session.add(DepartmentLeader(department_id=department.id, employee_id=head.id, role="HEAD"))
    head.department_id = department.id
    for member in members:
        member.department_id = department.id
    await db_session.commit()
    return department, head, account


async def department(
    db_session: AsyncSession,
    name: str,
    *members: Employee,
    head: Employee | None = None,
    parent: Department | None = None,
    heads: tuple[Employee, ...] = (),
    deputies: tuple[tuple[Employee, str], ...] = (),
) -> Department:
    """Abteilung (optional mit Leitung(en), Stellvertretungen (Person, Rechte) und unter parent) und
    ihre Mitglieder."""
    row = Department(name=name, parent_id=parent.id if parent is not None else None)
    db_session.add(row)
    await db_session.flush()
    await set_leaders(db_session, row, heads=((head,) if head is not None else ()) + tuple(heads), deputies=deputies)
    for member in members:
        member.department_id = row.id
    await db_session.commit()
    return row


async def set_leaders(
    db_session: AsyncSession,
    department: Department,
    *,
    heads: tuple[Employee, ...] = (),
    deputies: tuple[tuple[Employee, str], ...] = (),
) -> None:
    """Ersetzt Leitungen und Stellvertretungen (Person, Rechte STANDBY/FULL/ABSENCE) der Abteilung."""
    from sqlalchemy import delete

    await db_session.execute(delete(DepartmentLeader).where(DepartmentLeader.department_id == department.id))
    position = 0
    for person in heads:
        db_session.add(DepartmentLeader(department_id=department.id, employee_id=person.id, role="HEAD", position=position))
        position += 1
    for person, rights in deputies:
        db_session.add(
            DepartmentLeader(department_id=department.id, employee_id=person.id, role="DEPUTY", deputy_rights=rights, position=position)
        )
        position += 1
    await db_session.flush()
