"""Berichts-Builder ohne HTTP: Filtern, Sortieren, Formatieren, CSV, Zeitraum, Rechte je Spalte."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.errors import AppError
from app.models import AttributeDefinition
from app.schemas.report_builder import ReportPeriod
from app.services import report_builder_service as builder
from app.services import report_catalog as catalog

EMP = catalog.STATIC_COLUMNS["employees"]
ABS = catalog.STATIC_COLUMNS["absences"]
TIME = catalog.STATIC_COLUMNS["time_months"]


def actor(full_hr: bool = True, payroll: bool = False) -> SimpleNamespace:
    return SimpleNamespace(is_full_hr_level=full_hr, has_payroll_access=payroll)


def test_can_use_by_access():
    assert builder.can_use(actor(full_hr=False), EMP["last_name"])
    assert not builder.can_use(actor(full_hr=False), EMP["birth_date"])
    assert builder.can_use(actor(), EMP["birth_date"])
    assert not builder.can_use(actor(), EMP["iban"])
    assert not builder.can_use(actor(), EMP["pay_amount"])
    assert builder.can_use(actor(payroll=True), EMP["pay_amount"])


@pytest.mark.parametrize(
    "spec,operator,expected,raw,result",
    [
        (EMP["last_name"], "eq", "müller", "Müller", True),
        (EMP["last_name"], "eq", "Meier", "Müller", False),
        (EMP["last_name"], "ne", "Meier", "Müller", True),
        (EMP["last_name"], "ne", "Meier", None, True),
        (EMP["last_name"], "ne", "müller", "Müller", False),
        (EMP["last_name"], "contains", "ÜLL", "Müller", True),
        (EMP["last_name"], "contains", "x", None, False),
        (EMP["last_name"], "starts_with", "mü", "Müller", True),
        (EMP["last_name"], "starts_with", "ller", "Müller", False),
        (EMP["city"], "in", ["ulm", "Bonn"], "Ulm", True),
        (EMP["city"], "in", ["Bonn"], "Ulm", False),
        (EMP["status"], "in", ["ACTIVE", "LEAVE"], "LEAVE", True),
        (EMP["weekly_hours"], "gt", 20.0, 20.0, False),
        (EMP["weekly_hours"], "gte", 20.0, 20.0, True),
        (EMP["weekly_hours"], "lt", 20.0, 19.5, True),
        (EMP["weekly_hours"], "lte", 20.0, 20.5, False),
        (EMP["weekly_hours"], "gt", 20.0, None, False),
        (EMP["hire_date"], "gte", date(2024, 1, 1), date(2024, 1, 1), True),
        (EMP["hire_date"], "lt", date(2024, 1, 1), date(2024, 1, 1), False),
        (EMP["hire_date"], "is_empty", None, None, True),
        (EMP["hire_date"], "is_empty", None, date(2024, 1, 1), False),
        (EMP["position"], "is_empty", None, "", True),
        (EMP["position"], "is_not_empty", None, "Lager", True),
        (ABS["half_day"], "eq", True, True, True),
        (ABS["half_day"], "eq", True, False, False),
        (EMP["weekly_hours"], "gt", 20.0, "zwanzig", False),  # Typfehler im Wert: kein Treffer statt Absturz
        (EMP["weekly_hours"], "unknown", 20.0, 20.0, False),
    ],
)
def test_matches(spec, operator, expected, raw, result):
    assert builder.matches(spec, operator, expected, raw) is result


def test_sort_rows_multi_key_stable_and_empty_last():
    rows = [
        {"last_name": "b", "weekly_hours": 10.0, "status": "ACTIVE"},
        {"last_name": "A", "weekly_hours": None, "status": "INACTIVE"},
        {"last_name": "c", "weekly_hours": 10.0, "status": "LEAVE"},
        {"last_name": None, "weekly_hours": 40.0, "status": "ONBOARDING"},
    ]
    by_name = builder.sort_rows(rows, [(EMP["last_name"], False)])
    assert [r["last_name"] for r in by_name] == ["A", "b", "c", None]
    by_name_desc = builder.sort_rows(rows, [(EMP["last_name"], True)])
    assert [r["last_name"] for r in by_name_desc] == ["c", "b", "A", None]
    combined = builder.sort_rows(rows, [(EMP["weekly_hours"], True), (EMP["last_name"], False)])
    assert [r["last_name"] for r in combined] == [None, "b", "c", "A"]
    # Auswahlwerte nach Anzeige: Aktiv, Auszeit, Inaktiv, Onboarding
    by_status = builder.sort_rows(rows, [(EMP["status"], False)])
    assert [r["status"] for r in by_status] == ["ACTIVE", "LEAVE", "INACTIVE", "ONBOARDING"]
    assert builder.sort_rows(rows, []) == rows


@pytest.mark.parametrize(
    "value,text",
    [(1.0, "1"), (7.5, "7,5"), (7.25, "7,25"), (-3.1, "-3,1"), (0.0, "0"), (1234.567, "1234,57"), (2.10, "2,1")],
)
def test_german_number(value, text):
    assert builder.german_number(value) == text


def test_text_of_and_cell_of():
    assert builder.text_of(EMP["last_name"], None) == ""
    assert builder.text_of(EMP["status"], "LEAVE") == "Auszeit"
    assert builder.text_of(ABS["half_day"], True) == "Ja" and builder.text_of(ABS["half_day"], False) == "Nein"
    assert builder.text_of(EMP["hire_date"], date(2025, 3, 1)) == "01.03.2025"
    assert builder.text_of(EMP["weekly_hours"], 38.5) == "38,5"
    assert builder.text_of(EMP["last_name"], "Muster") == "Muster"
    assert builder.cell_of(EMP["last_name"], "") is None
    assert builder.cell_of(EMP["status"], "ACTIVE") == "Aktiv"
    assert builder.cell_of(ABS["half_day"], False) is False
    assert builder.cell_of(EMP["hire_date"], date(2025, 3, 1)) == "2025-03-01"
    assert builder.cell_of(EMP["weekly_hours"], 1 / 3) == 0.33
    assert builder.cell_of(EMP["last_name"], "Muster") == "Muster"


@pytest.mark.parametrize(
    "value,safe",
    [("=SUM(A1)", "'=SUM(A1)"), ("+1", "'+1"), ("-1", "'-1"), ("@x", "'@x"), ("\tx", "'\tx"), ("\rx", "'\rx"), ("Müller", "Müller"), ("", "")],
)
def test_csv_safe(value, safe):
    assert builder.csv_safe(value) == safe


def _outcome(rows, columns, group=None, source="employees", omitted=None, first=None, last=None):
    plan = builder.Plan(source, columns, omitted or [], [], [], group)
    groups = []
    if group is not None:
        for row in rows:
            label = builder.text_of(group, row.get(group.key))
            if groups and groups[-1][0] == label:
                groups[-1][1].append(row)
            else:
                groups.append((label, [row]))
    return builder.Outcome(plan, rows, groups, first, last)


def test_to_csv_plain_and_injection():
    rows = [{"last_name": "=HACK()", "hire_date": date(2025, 1, 2), "weekly_hours": 38.5, "status": "ACTIVE"}]
    content = builder.to_csv(_outcome(rows, [EMP["last_name"], EMP["hire_date"], EMP["weekly_hours"], EMP["status"]]))
    assert content.startswith("﻿")
    lines = content[1:].split("\r\n")
    assert lines[0] == "Nachname;Eintritt;Wochenstunden;Status"
    assert lines[1] == "'=HACK();02.01.2025;38,5;Aktiv"
    assert lines[2] == ""  # keine Summenzeilen ohne summierbare Spalte und Gruppe


def test_to_csv_with_groups_and_sums():
    rows = [
        {"department": "Lager", "days": 2.0, "category": "SICK"},
        {"department": "Lager", "days": 1.5, "category": "SICK"},
        {"department": None, "days": 1.0, "category": "VACATION"},
    ]
    content = builder.to_csv(_outcome(rows, [ABS["department"], ABS["days"]], group=ABS["department"], source="absences"))
    lines = content[1:].strip().split("\r\n")
    assert lines[:4] == ["Abteilung;Tage (im Zeitraum)", "Lager;2", "Lager;1,5", ";1"]
    assert lines[4] == ""
    assert lines[5] == "Abteilung;Anzahl;Tage (im Zeitraum)"
    assert lines[6:] == ["Lager;2;3,5", "(leer);1;1", "Gesamt;3;4,5"]


def test_to_csv_sums_without_group():
    content = builder.to_csv(_outcome([{"days": 1.0}, {"days": None}], [ABS["days"]], source="absences"))
    assert content[1:].strip().split("\r\n")[-2:] == [";Anzahl;Tage (im Zeitraum)", "Gesamt;2;1"]


def test_to_result_pagination_totals_groups():
    rows = [{"department": "A" if i < 3 else "B", "days": float(i)} for i in range(5)]
    outcome = _outcome(rows, [ABS["department"], ABS["days"]], group=ABS["department"], source="absences", omitted=["IBAN"],
                       first=date(2025, 1, 1), last=date(2025, 1, 31))
    result = builder.to_result(outcome, ReportPeriod(page=2, page_size=2))
    assert result.total_rows == 5 and result.rows == [["A", 2.0], ["B", 3.0]]
    assert result.totals == {"days": 10.0}
    assert [(g.label, g.count, g.sums) for g in result.groups] == [("A", 3, {"days": 3.0}), ("B", 2, {"days": 7.0})]
    assert result.omitted_columns == ["IBAN"] and result.group_by == "department" and result.group_by_label == "Abteilung"
    assert builder.to_result(outcome, ReportPeriod(page=4, page_size=2)).rows == []


def test_audit_detail_has_no_content():
    rows = [{"last_name": "Geheim"}]
    detail = builder.audit_detail(_outcome(rows, [EMP["last_name"]], omitted=["IBAN"], source="absences",
                                           first=date(2025, 1, 1), last=date(2025, 1, 31)), "Krank Q1")
    assert "Geheim" not in detail
    assert detail == "Bericht „Krank Q1“, Quelle Abwesenheiten, 1 Spalten, 1 Zeilen, Zeitraum 01.01.2025–31.01.2025, 1 Spalten ausgelassen"
    assert builder.audit_detail(_outcome([], [EMP["last_name"]])).startswith("Ad-hoc-Bericht, Quelle Mitarbeitende")
    assert len(builder.audit_detail(_outcome([], [EMP["last_name"]]), "x" * 600)) == 500


def test_resolve_period():
    assert builder.resolve_period("employees", ReportPeriod()) == (None, None)
    assert builder.resolve_period("employees", ReportPeriod(date_from=date(2025, 1, 1), date_to=date(2025, 1, 2))) == (None, None)
    with pytest.raises(AppError) as error:
        builder.resolve_period("absences", ReportPeriod())
    assert error.value.status_code == 400 and error.value.code == "REPORT_PERIOD_REQUIRED"
    assert builder.resolve_period("absences", ReportPeriod(date_from=date(2025, 1, 5), date_to=date(2025, 2, 3))) == (date(2025, 1, 5), date(2025, 2, 3))
    assert builder.resolve_period("time_months", ReportPeriod(date_from=date(2024, 1, 5), date_to=date(2024, 2, 3))) == (date(2024, 1, 1), date(2024, 2, 29))


def test_attribute_raw_conversion():
    def definition(kind):
        return AttributeDefinition(field_type=kind, label="X")

    assert builder._attribute_raw(definition("NUMBER"), "12.50", {}) == 12.5
    assert builder._attribute_raw(definition("NUMBER"), "abc", {}) is None
    assert builder._attribute_raw(definition("DATE"), "2025-01-31", {}) == date(2025, 1, 31)
    assert builder._attribute_raw(definition("DATE"), "31.01.2025", {}) is None
    assert builder._attribute_raw(definition("BOOLEAN"), "true", {}) is True
    assert builder._attribute_raw(definition("BOOLEAN"), "false", {}) is False
    assert builder._attribute_raw(definition("EMPLOYEE"), "7", {7: "Max Muster"}) == "Max Muster"
    assert builder._attribute_raw(definition("EMPLOYEE"), "x", {7: "Max Muster"}) is None
    assert builder._attribute_raw(definition("SELECT"), "Rot", {}) == "Rot"
    assert builder._attribute_raw(definition("TEXT"), None, {}) is None


def test_model_name():
    templates = {5: SimpleNamespace(name="Früh")}
    assert builder.model_name(None, templates, {}) is None
    assert builder.model_name(SimpleNamespace(profile_id=3, on_demand=False, flexible=False, shift_template_id=None), templates, {3: "Teilzeit 20"}) == "Teilzeit 20"
    assert builder.model_name(SimpleNamespace(profile_id=None, on_demand=True, flexible=False, shift_template_id=None), templates, {}) == "Nach Aufwand"
    assert builder.model_name(SimpleNamespace(profile_id=None, on_demand=False, flexible=True, shift_template_id=None), templates, {}) == "Flexibel"
    assert builder.model_name(SimpleNamespace(profile_id=None, on_demand=False, flexible=False, shift_template_id=5), templates, {}) == "Früh"
    assert builder.model_name(SimpleNamespace(profile_id=9, on_demand=False, flexible=False, shift_template_id=None), templates, {}) == "Individuell"


def test_current_row_at_reference_day():
    rows = [
        SimpleNamespace(id=1, valid_from=date(2024, 1, 1), valid_to=date(2024, 12, 31)),
        SimpleNamespace(id=2, valid_from=date(2025, 1, 1), valid_to=None),
        SimpleNamespace(id=3, valid_from=date(2026, 1, 1), valid_to=None),
    ]
    assert builder._current(rows, date(2025, 6, 1)).id == 2
    assert builder._current(rows, date(2024, 6, 1)).id == 1
    assert builder._current(rows, date(2023, 6, 1)) is None
    assert builder._current(rows, date(2026, 6, 1)).id == 3
