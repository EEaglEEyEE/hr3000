"""Abteilungen als Baum (Department.parent_id): Teilbäume für Filter und Organigramm."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Department


def subtree_ids(parents: dict[int, int | None], root_id: int) -> set[int]:
    """root_id und alle Abteilungen darunter. Robust gegen Zyklen (jede Abteilung höchstens einmal)."""
    children: dict[int, list[int]] = {}
    for department_id, parent_id in parents.items():
        if parent_id is not None:
            children.setdefault(parent_id, []).append(department_id)
    result: set[int] = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(children.get(current, []))
    return result


async def department_subtree_ids(db: AsyncSession, tenant_id: int, root_id: int) -> set[int]:
    rows = (await db.execute(select(Department.id, Department.parent_id).where(Department.tenant_id == tenant_id))).all()
    return subtree_ids({department_id: parent_id for department_id, parent_id in rows}, root_id)
