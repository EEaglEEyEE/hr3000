"""Unit-Tests der Hilfsfunktionen der Lohnbuchhaltung (ohne HTTP)."""
from datetime import date

import pytest

from app.services.payroll_accounting_service import _euro_de, _in, changed_employees, month_bounds, parse_month


@pytest.mark.parametrize(
    ("year", "month", "last"),
    [(2026, 2, 28), (2028, 2, 29), (2026, 12, 31), (2026, 4, 30), (2026, 1, 31)],
)
def test_month_bounds(year: int, month: int, last: int) -> None:
    assert month_bounds(year, month) == (date(year, month, 1), date(year, month, last))


def test_parse_month() -> None:
    assert parse_month("2026-10") == (2026, 10)
    assert parse_month("1999-01") == (1999, 1)


def test_in_range() -> None:
    first, last = date(2026, 10, 1), date(2026, 10, 31)
    assert _in(date(2026, 10, 1), first, last)
    assert _in(date(2026, 10, 31), first, last)
    assert not _in(date(2026, 9, 30), first, last)
    assert not _in(date(2026, 11, 1), first, last)
    assert not _in(None, first, last)


def _snap(*rows: dict) -> dict:
    return {"employees": list(rows)}


def test_changed_employees_detects_changes_additions_and_removals() -> None:
    a, b, c = {"employee_id": 1, "x": 1}, {"employee_id": 2, "x": 1}, {"employee_id": 3, "x": 1}
    assert changed_employees(_snap(a, b), _snap(a, b)) == []
    assert changed_employees(_snap(a, b), _snap(a, {"employee_id": 2, "x": 2})) == [2]
    assert changed_employees(_snap(a, b), _snap(a, b, c)) == [3]
    assert changed_employees(_snap(a, b), _snap(a)) == [2]
    assert changed_employees({}, {}) == []


def test_changed_employees_ignores_key_order() -> None:
    assert changed_employees(_snap({"employee_id": 1, "a": 1, "b": 2}), _snap({"b": 2, "a": 1, "employee_id": 1})) == []


@pytest.mark.parametrize(
    ("value", "text"),
    [(3500, "3.500,00"), (0, "0,00"), (20.5, "20,50"), (1234567.891, "1.234.567,89"), (999.999, "1.000,00")],
)
def test_euro_de(value, text: str) -> None:
    assert _euro_de(value) == text
