"""Positivliste des Berichts-Builders und Pydantic-Validierung der Definitionen (ohne Datenbank)."""
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.personal_data import PAYROLL_FIELDS
from app.schemas.report_builder import (
    ReportDefinition,
    ReportPeriod,
    ReportPreviewRequest,
    SavedReportRequest,
)
from app.schemas.reports import AbsenceRateQuery, HeadcountQuery
from app.services import report_catalog as catalog

EMP = catalog.STATIC_COLUMNS[catalog.SOURCE_EMPLOYEES]


# --- Katalog ----------------------------------------------------------------------------------------


def test_sources_and_time_based():
    assert set(catalog.SOURCES) == {"employees", "absences", "time_months", "project_times"}
    assert catalog.TIME_BASED_SOURCES == {"absences", "time_months", "project_times"}


def test_person_columns_in_every_source():
    for columns in catalog.STATIC_COLUMNS.values():
        assert {"employee_number", "last_name", "first_name", "department", "location"} <= set(columns)


def test_payroll_columns_are_exactly_the_payroll_fields_plus_compensation():
    payroll = {k for k, spec in EMP.items() if spec.access == catalog.ACCESS_PAYROLL}
    assert payroll == set(PAYROLL_FIELDS) | catalog.COMPENSATION_KEYS


def test_personal_data_without_payroll_needs_hr():
    for key in catalog.PERSONAL_DATA_KEYS - PAYROLL_FIELDS:
        assert EMP[key].access == catalog.ACCESS_HR, key
    assert EMP["birth_date"].access == catalog.ACCESS_HR
    assert EMP["contract_type"].access == catalog.ACCESS_HR


def test_other_sources_have_no_restricted_columns():
    for source in (catalog.SOURCE_ABSENCES, catalog.SOURCE_TIME_MONTHS):
        assert all(spec.access == catalog.ACCESS_ALL for spec in catalog.STATIC_COLUMNS[source].values())


def test_summable_columns_are_numbers():
    for columns in catalog.STATIC_COLUMNS.values():
        for spec in columns.values():
            if spec.summable:
                assert spec.type == catalog.NUMBER


def test_enum_columns_have_options_and_labels():
    status = EMP["status"]
    assert status.type == catalog.ENUM and status.option_label("LEAVE") == "Auszeit"
    assert status.option_label("UNBEKANNT") == "UNBEKANNT"
    assert status.operators == ("eq", "ne", "in", "is_empty", "is_not_empty")


def test_operators_by_type():
    assert "contains" in EMP["last_name"].operators
    assert "gt" in EMP["hire_date"].operators and "contains" not in EMP["hire_date"].operators
    assert catalog.STATIC_COLUMNS["absences"]["half_day"].operators == ("eq",)


@pytest.mark.parametrize(
    "source,key,known",
    [
        ("employees", "last_name", True),
        ("employees", "attr_1", True),
        ("employees", "attr_9999999999", True),
        ("employees", "attr_0", False),
        ("employees", "attr_01", False),
        ("employees", "attr_12345678901", False),
        ("employees", "attr_x", False),
        ("absences", "attr_1", False),
        ("absences", "days", True),
        ("employees", "days", False),
        ("time_months", "balance_hours", True),
        ("employees", "password_hash", False),
    ],
)
def test_is_known_key(source, key, known):
    assert catalog.is_known_key(source, key) is known


# --- Filterwerte ------------------------------------------------------------------------------------


def test_normalize_text():
    assert catalog.normalize_filter_value(EMP["last_name"], "contains", "  Mu ") == "Mu"
    for bad in ("", "   ", 5, None, True):
        with pytest.raises(ValueError):
            catalog.normalize_filter_value(EMP["last_name"], "eq", bad)
    with pytest.raises(ValueError, match="200"):
        catalog.normalize_filter_value(EMP["last_name"], "eq", "x" * 201)
    assert catalog.normalize_filter_value(EMP["last_name"], "eq", "x" * 200) == "x" * 200


def test_normalize_number():
    spec = EMP["weekly_hours"]
    assert catalog.normalize_filter_value(spec, "gte", 20) == 20.0
    assert catalog.normalize_filter_value(spec, "lt", 7.5) == 7.5
    assert catalog.normalize_filter_value(spec, "eq", catalog.MAX_NUMBER) == float(catalog.MAX_NUMBER)
    for bad in ("20", True, catalog.MAX_NUMBER + 1, float("inf"), float("nan")):
        with pytest.raises(ValueError):
            catalog.normalize_filter_value(spec, "eq", bad)


def test_normalize_date():
    assert catalog.normalize_filter_value(EMP["hire_date"], "gte", "2024-02-29") == date(2024, 2, 29)
    for bad in ("2023-02-29", "01.01.2024", 2024):
        with pytest.raises(ValueError):
            catalog.normalize_filter_value(EMP["hire_date"], "gte", bad)


def test_normalize_bool():
    spec = catalog.STATIC_COLUMNS["absences"]["half_day"]
    assert catalog.normalize_filter_value(spec, "eq", True) is True
    with pytest.raises(ValueError):
        catalog.normalize_filter_value(spec, "eq", "true")
    with pytest.raises(ValueError):
        catalog.normalize_filter_value(spec, "ne", True)


def test_normalize_enum_and_in():
    spec = EMP["status"]
    assert catalog.normalize_filter_value(spec, "eq", "ACTIVE") == "ACTIVE"
    assert catalog.normalize_filter_value(spec, "in", ["ACTIVE", "LEAVE"]) == ["ACTIVE", "LEAVE"]
    for bad in ("aktiv", ["ACTIVE", "X"], [], ["ACTIVE"] * (catalog.MAX_IN_VALUES + 1)):
        with pytest.raises(ValueError):
            catalog.normalize_filter_value(spec, "in" if isinstance(bad, list) else "eq", bad)
    assert catalog.normalize_filter_value(EMP["city"], "in", ["Ulm", " Bonn "]) == ["Ulm", "Bonn"]


def test_normalize_valueless_and_operator_mismatch():
    assert catalog.normalize_filter_value(EMP["hire_date"], "is_empty", None) is None
    with pytest.raises(ValueError, match="keinen Wert"):
        catalog.normalize_filter_value(EMP["hire_date"], "is_empty", "2024-01-01")
    with pytest.raises(ValueError, match="enthält"):
        catalog.normalize_filter_value(EMP["hire_date"], "contains", "2024")
    with pytest.raises(ValueError, match="genau einen"):
        catalog.normalize_filter_value(EMP["last_name"], "eq", ["a"])
    with pytest.raises(ValueError, match="genau einen"):
        catalog.normalize_filter_value(EMP["last_name"], "eq", None)


# --- Definition -------------------------------------------------------------------------------------


def test_definition_minimal_and_full():
    definition = ReportDefinition(source="employees", columns=["last_name"])
    assert definition.filters == [] and definition.sort == [] and definition.group_by is None
    full = ReportDefinition.model_validate(
        {
            "source": "absences",
            "columns": ["last_name", "days"],
            "filters": [{"column": "category", "operator": "in", "value": ["SICK"]}],
            "sort": [{"column": "days", "direction": "desc"}],
            "group_by": "department",
        }
    )
    assert full.sort[0].direction == "desc"


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"source": "employees", "columns": []}, "at least 1"),
        ({"source": "employees", "columns": ["last_name"] * 2}, "nur einmal"),
        ({"source": "employees", "columns": [f"attr_{i}" for i in range(1, 32)]}, "at most 30"),
        ({"source": "employees", "columns": ["days"]}, "gibt es in dieser Datenquelle nicht"),
        ({"source": "salaries", "columns": ["last_name"]}, "literal_error"),
        ({"source": "employees", "columns": ["Last_Name"]}, "string_pattern_mismatch"),
        ({"source": "employees", "columns": ["last_name; DROP TABLE"]}, "string_pattern_mismatch"),
        ({"source": "employees", "columns": ["last_name"], "sql": "SELECT 1"}, "extra_forbidden"),
        ({"source": "employees", "columns": ["last_name"], "group_by": "nope"}, "gibt es"),
        ({"source": "employees", "columns": ["last_name"], "sort": [{"column": "nope"}]}, "gibt es"),
        (
            {"source": "employees", "columns": ["last_name"], "sort": [{"column": "last_name"}, {"column": "last_name"}]},
            "nur einmal sortiert",
        ),
        ({"source": "employees", "columns": ["last_name"], "sort": [{"column": "last_name", "direction": "up"}]}, "literal_error"),
        ({"source": "employees", "columns": ["last_name"], "filters": [{"column": "hire_date", "operator": "like"}]}, "literal_error"),
        (
            {"source": "employees", "columns": ["last_name"], "filters": [{"column": "hire_date", "operator": "gt", "value": "gestern"}]},
            "JJJJ-MM-TT",
        ),
        (
            {"source": "employees", "columns": ["last_name"], "filters": [{"column": "weekly_hours", "operator": "gt", "value": "20"}]},
            "Zahl",
        ),
        ({"source": "employees", "columns": ["last_name"], "filters": [{"column": "x", "operator": "eq", "value": {"a": 1}}]}, "Input should be"),
        (
            {"source": "employees", "columns": ["last_name"], "filters": [{"column": "last_name", "operator": "eq", "value": "a"}] * 11},
            "at most 10",
        ),
    ],
)
def test_definition_rejects(payload, message):
    with pytest.raises(ValidationError, match=message):
        ReportDefinition.model_validate(payload)


def test_definition_attribute_filter_is_checked_later():
    definition = ReportDefinition.model_validate(
        {"source": "employees", "columns": ["attr_3"], "filters": [{"column": "attr_3", "operator": "contains", "value": "x"}]}
    )
    assert definition.filters[0].column == "attr_3"


def test_definition_strict_values_are_not_coerced():
    with pytest.raises(ValidationError):
        ReportDefinition.model_validate(
            {"source": "absences", "columns": ["days"], "filters": [{"column": "half_day", "operator": "eq", "value": 1}]}
        )


# --- Zeitraum und gespeicherte Berichte -------------------------------------------------------------


def test_period_defaults_and_limits():
    period = ReportPeriod()
    assert (period.date_from, period.page, period.page_size) == (None, 1, 50)
    assert ReportPeriod(date_from=date(2024, 1, 1), date_to=date(2025, 1, 1)).date_to == date(2025, 1, 1)  # 366 Tage
    for kwargs, message in (
        ({"date_from": date(2024, 1, 1)}, "Beginn und Ende"),
        ({"date_to": date(2024, 1, 1)}, "Beginn und Ende"),
        ({"date_from": date(2024, 2, 1), "date_to": date(2024, 1, 31)}, "nicht vor dem Beginn"),
        ({"date_from": date(2024, 1, 1), "date_to": date(2025, 1, 2)}, "366 Tage"),
        ({"date_from": date(1999, 12, 31), "date_to": date(2000, 1, 1)}, "außerhalb"),
        ({"page": 0}, "greater than or equal"),
        ({"page_size": 201}, "less than or equal"),
        ({"page_size": 0}, "greater than or equal"),
        ({"unknown": 1}, "extra_forbidden"),
    ):
        with pytest.raises(ValidationError, match=message):
            ReportPeriod(**kwargs)


def test_preview_request_contains_definition():
    request = ReportPreviewRequest.model_validate({"definition": {"source": "employees", "columns": ["last_name"]}, "page_size": 200})
    assert request.page_size == 200


def test_saved_report_request_strips_and_limits():
    request = SavedReportRequest.model_validate(
        {"name": "  Liste  ", "description": "   ", "definition": {"source": "employees", "columns": ["last_name"]}}
    )
    assert request.name == "Liste" and request.description is None and request.shared is False
    for payload in ({"name": "   "}, {"name": "x" * 101}, {"name": "ok", "description": "x" * 501}, {"name": "ok", "owner_account_id": 1}):
        with pytest.raises(ValidationError):
            SavedReportRequest.model_validate({"definition": {"source": "employees", "columns": ["last_name"]}, **payload})
    assert SavedReportRequest.model_validate(
        {"name": "x" * 100, "description": "y" * 500, "definition": {"source": "employees", "columns": ["last_name"]}}
    ).name == "x" * 100


# --- Abfragen der festen Auswertungen ---------------------------------------------------------------


def test_absence_rate_query_defaults_and_limits():
    query = AbsenceRateQuery(date_from=date(2025, 1, 1), date_to=date(2026, 12, 31))  # genau 24 Monate
    assert [c.value for c in query.categories] == ["SICK", "CHILD_SICK"]
    for kwargs, message in (
        ({"date_from": date(2025, 1, 1), "date_to": date(2027, 1, 1)}, "24 Monate"),
        ({"date_from": date(2025, 2, 1), "date_to": date(2025, 1, 1)}, "nicht vor"),
        ({"date_from": date(1999, 1, 1), "date_to": date(1999, 2, 1)}, "außerhalb"),
        ({"date_from": date(2025, 1, 1), "date_to": date(2025, 2, 1), "categories": ["WORK_TIME"]}, "keine Abwesenheiten"),
        ({"date_from": date(2025, 1, 1), "date_to": date(2025, 2, 1), "categories": ["PUBLIC_HOLIDAY"]}, "keine Abwesenheiten"),
        ({"date_from": date(2025, 1, 1), "date_to": date(2025, 2, 1), "categories": ["SICK", "SICK"]}, "nur einmal"),
        ({"date_from": date(2025, 1, 1), "date_to": date(2025, 2, 1), "categories": []}, "at least 1"),
        ({"date_from": date(2025, 1, 1), "date_to": date(2025, 2, 1), "categories": ["KRANK"]}, "Input should be"),
    ):
        with pytest.raises(ValidationError, match=message):
            AbsenceRateQuery(**kwargs)


def test_headcount_query_limits():
    assert HeadcountQuery(date_from=date(2024, 1, 15), date_to=date(2026, 12, 1)).date_to == date(2026, 12, 1)  # 36 Monate
    with pytest.raises(ValidationError, match="36 Monate"):
        HeadcountQuery(date_from=date(2024, 1, 1), date_to=date(2027, 1, 1))
