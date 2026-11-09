"""Organisation einer Firma: Abteilungen als Baum (Department.parent_id) mit Leitungen und
Stellvertretungen (DepartmentLeader) – die einzige Struktur, Teams gibt es nicht mehr (Entscheidungen
vom 09.11.2026).

Führungskräfte einer Person (wirksam, es können mehrere sein):
1. die je Person eingetragene Ausnahme (Employee.supervisor_id), wenn aktiv und nicht die Person selbst,
2. sonst die aktiven Leitungen der eigenen Abteilung („Heimatabteilung“: Employee.department_id, ohne
   Abteilung die erste, die die Person leitet). Ist die Person selbst eine Leitung dieser Abteilung oder
   hat die Abteilung keine aktive Leitung, gelten die Leitungen der nächsten Abteilung darüber,
3. sonst keine.

Stellvertretungen sind keine Führungskräfte im Baum. Sie handeln für die Leitungen ihrer Abteilung –
je nach Rechten (DEPUTY_FULL immer, sonst nur, wenn keine Leitung verfügbar ist, siehe
scope_service und approval_service). Dafür rechnet reports() mit „zusätzlichen Leitungen“.

Eine Führungskraft ist zuständig für alle direkt und indirekt Unterstellten.
"""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.models import Department, DepartmentLeader, Employee
from app.models.department import LEADER_DEPUTY, LEADER_HEAD
from app.services.department_service import subtree_ids

# Abteilung -> zusätzliche (gedachte) Leitungen, z. B. eine Stellvertretung, die gerade handelt
ExtraHeads = dict[int, set[int]]


@dataclass
class OrgSnapshot:
    # Abteilung -> übergeordnete Abteilung
    departments: dict[int, int | None] = field(default_factory=dict)
    # Abteilung -> [(Mitarbeiter, Rolle HEAD/DEPUTY, Rechte)] in Anzeige-Reihenfolge
    leaders: dict[int, list[tuple[int, str, str]]] = field(default_factory=dict)
    # Mitarbeiter -> (Abteilung, Ausnahme-Führungskraft, aktiv)
    employees: dict[int, tuple[int | None, int | None, bool]] = field(default_factory=dict)

    def _active(self, employee_id: int | None) -> bool:
        return employee_id is not None and employee_id in self.employees and self.employees[employee_id][2]

    def heads(self, department_id: int | None, extra: ExtraHeads | None = None) -> list[int]:
        """Aktive Leitungen der Abteilung (Reihenfolge wie eingegeben), plus gedachte aus extra."""
        if department_id is None:
            return []
        result = [e for e, role, _ in self.leaders.get(department_id, []) if role == LEADER_HEAD and self._active(e)]
        for e in sorted((extra or {}).get(department_id, set())):
            if e not in result and self._active(e):
                result.append(e)
        return result

    def deputies(self, department_id: int | None) -> list[tuple[int, str]]:
        """Aktive Stellvertretungen der Abteilung mit ihren Rechten."""
        if department_id is None:
            return []
        return [(e, rights) for e, role, rights in self.leaders.get(department_id, []) if role == LEADER_DEPUTY and self._active(e)]

    def led_departments(self, employee_id: int, role: str = LEADER_HEAD) -> list[int]:
        """Abteilungen, in denen die Person Leitung (bzw. Stellvertretung) ist, nach ID."""
        return sorted(d for d, rows in self.leaders.items() if any(e == employee_id and r == role for e, r, _ in rows))

    def home_department(self, employee_id: int) -> int | None:
        """Eigene Abteilung; ohne Abteilung die erste, die die Person leitet."""
        if employee_id not in self.employees:
            return None
        own = self.employees[employee_id][0]
        if own is not None:
            return own
        led = self.led_departments(employee_id)
        return led[0] if led else None

    def leading_department(self, employee_id: int, extra: ExtraHeads | None = None) -> int | None:
        """Die Abteilung, deren Leitungen für die Person zuständig sind (ohne Ausnahme je Person):
        die eigene oder – leitet die Person sie selbst oder hat sie keine Leitung – die nächste darüber."""
        current = self.home_department(employee_id)
        seen: set[int] = set()
        while current is not None and current in self.departments and current not in seen:
            seen.add(current)
            heads = self.heads(current, extra)
            if heads and employee_id not in heads:
                return current
            current = self.departments[current]
        return None

    def department_supervisors(self, employee_id: int, extra: ExtraHeads | None = None) -> list[int]:
        """Führungskräfte nach Abteilung (ohne Ausnahme je Person)."""
        return self.heads(self.leading_department(employee_id, extra), extra)

    def override(self, employee_id: int) -> int | None:
        """Gültige Ausnahme je Person (aktiv, nicht die Person selbst) oder None."""
        if employee_id not in self.employees:
            return None
        override = self.employees[employee_id][1]
        return override if override is not None and override != employee_id and self._active(override) else None

    def supervisors(self, employee_id: int, extra: ExtraHeads | None = None) -> list[int]:
        """Wirksame Führungskräfte: die Ausnahme oder die Leitungen nach Abteilung."""
        override = self.override(employee_id)
        if override is not None:
            return [override]
        return self.department_supervisors(employee_id, extra)

    def supervisor_source(self, employee_id: int) -> str | None:
        """OVERRIDE (je Person eingetragen), DEPARTMENT (Abteilungsleitung) oder None."""
        if self.override(employee_id) is not None:
            return "OVERRIDE"
        return "DEPARTMENT" if self.department_supervisors(employee_id) else None

    def reports(self, supervisor_id: int, extra: ExtraHeads | None = None) -> set[int]:
        """Alle direkt und indirekt Unterstellten (ohne die Führungskraft selbst). extra: Abteilungen, in
        denen zusätzlich jemand als Leitung gilt (Stellvertretung, die gerade handelt)."""
        children: dict[int, list[int]] = {}
        for employee_id in self.employees:
            for boss in self.supervisors(employee_id, extra):
                children.setdefault(boss, []).append(employee_id)
        result: set[int] = set()
        stack = list(children.get(supervisor_id, []))
        while stack:
            current = stack.pop()
            if current in result or current == supervisor_id:
                continue
            result.add(current)
            stack.extend(children.get(current, []))
        return result

    def find_cycle(self) -> int | None:
        """Eine Person, deren Führungskräfte (direkt oder über mehrere Stufen) wieder bei ihr ankommen –
        etwa A leitet die Abteilung von B und B die von A –, sonst None."""
        edges = {employee_id: self.supervisors(employee_id) for employee_id in self.employees}
        state: dict[int, int] = {}  # 1 = in Arbeit, 2 = fertig

        def visit(node: int) -> int | None:
            state[node] = 1
            for boss in edges.get(node, []):
                if state.get(boss) == 1:
                    return boss
                if state.get(boss) is None:
                    found = visit(boss)
                    if found is not None:
                        return found
            state[node] = 2
            return None

        for start in sorted(self.employees):
            if state.get(start) is None:
                found = visit(start)
                if found is not None:
                    return found
        return None

    def subtree(self, department_id: int) -> set[int]:
        """Die Abteilung und alle darunter."""
        return subtree_ids(dict(self.departments), department_id)


async def load_org(db: AsyncSession, tenant_id: int) -> OrgSnapshot:
    departments = (
        await db.execute(select(Department.id, Department.parent_id).where(Department.tenant_id == tenant_id))
    ).all()
    leaders = (
        await db.execute(
            select(DepartmentLeader.department_id, DepartmentLeader.employee_id, DepartmentLeader.role, DepartmentLeader.deputy_rights)
            .join(Department, Department.id == DepartmentLeader.department_id)
            .where(Department.tenant_id == tenant_id)
            .order_by(DepartmentLeader.department_id, DepartmentLeader.position, DepartmentLeader.id)
        )
    ).all()
    employees = (
        await db.execute(
            select(Employee.id, Employee.department_id, Employee.supervisor_id, Employee.active).where(
                Employee.tenant_id == tenant_id
            )
        )
    ).all()
    snapshot = OrgSnapshot(
        departments={d_id: parent for d_id, parent in departments},
        employees={e_id: (department, supervisor, bool(active)) for e_id, department, supervisor, active in employees},
    )
    for department_id, employee_id, role, rights in leaders:
        snapshot.leaders.setdefault(department_id, []).append((employee_id, role, rights))
    return snapshot


async def supervisor_ids(db: AsyncSession, employee: Employee) -> list[int]:
    return (await load_org(db, employee.tenant_id)).supervisors(employee.id)


async def check_no_supervisor_cycle(db: AsyncSession, tenant_id: int) -> None:
    """Nach einer Änderung an Abteilung, Leitungen oder abweichender Führungskraft (bereits geflusht):
    kein Kreis in den Führungskräften – sonst 400, die Änderung wird nicht gespeichert."""
    person_id = (await load_org(db, tenant_id)).find_cycle()
    if person_id is not None:
        person = await db.get(Employee, person_id)
        name = f"{person.first_name} {person.last_name}" if person is not None else "einer Person"
        raise AppError(
            400,
            "SUPERVISOR_CYCLE",
            f"Damit wäre {name} (indirekt) die eigene Führungskraft. Bitte Leitung oder abweichende Führungskraft "
            "anders wählen.",
        )
