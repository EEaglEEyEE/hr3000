"""Unit-Tests für app/services/role_permissions.py (ohne Datenbank)."""
import json

import pytest

from app.models import Account, HrRole, Role
from app.api.deps import Actor, account_custom_permissions
from app.services import role_permissions as rp
from app.services.role_permissions import Area, Decision, Level, Rule, RuleKind


def _perms(**levels: str) -> rp.Permissions:
    return rp.normalize(levels)


# --- normalize / parse / dump ------------------------------------------------------------------


def test_normalize_fills_all_areas_with_none() -> None:
    result = rp.normalize({})
    assert set(result) == set(Area)
    assert all(level == Level.NONE for level in result.values())


def test_normalize_keeps_known_values_and_drops_unknown() -> None:
    result = rp.normalize({"PAYROLL": "VIEW", "FOO": "EDIT", "TIME": "SUPER"})
    assert result[Area.PAYROLL] == Level.VIEW
    assert result[Area.TIME] == Level.NONE
    assert "FOO" not in {a.value for a in result}


def test_normalize_accepts_enum_keys() -> None:
    assert rp.normalize({Area.TIME: Level.EDIT})[Area.TIME] == Level.EDIT


@pytest.mark.parametrize("raw", [None, "", "kaputt{", "[1, 2]", "42", "null"])
def test_parse_invalid_means_no_access(raw) -> None:
    result = rp.parse_permissions(raw)
    assert all(level == Level.NONE for level in result.values())


def test_dump_and_parse_round_trip() -> None:
    perms = _perms(PAYROLL="VIEW", EMPLOYEES="EDIT")
    raw = rp.dump_permissions(perms)
    assert json.loads(raw)["PAYROLL"] == "VIEW"
    assert len(json.loads(raw)) == len(Area)
    assert rp.parse_permissions(raw) == perms


# --- Stufen -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("have", "need", "ok"),
    [
        ("NONE", Level.VIEW, False),
        ("VIEW", Level.VIEW, True),
        ("VIEW", Level.EDIT, False),
        ("EDIT", Level.VIEW, True),
        ("EDIT", Level.EDIT, True),
        ("NONE", Level.NONE, True),
    ],
)
def test_has_level(have, need, ok) -> None:
    assert rp.has_level(_perms(TIME=have), Area.TIME, need) is ok


def test_lookup_access_needs_any_area() -> None:
    assert rp.has_lookup_access(_perms()) is False
    assert rp.has_lookup_access(_perms(CHECKLISTS="VIEW")) is True


def test_lookup_access_payroll_only_from_edit() -> None:
    """Das Lohnbüro (nur ansehen) bekommt keine Live-Mitarbeiterliste."""
    assert rp.has_lookup_access(_perms(PAYROLL="VIEW")) is False
    assert rp.has_lookup_access(_perms(PAYROLL="EDIT")) is True


# --- route_key ---------------------------------------------------------------------------------------


def test_route_key_maps_head_to_get_and_uppercases() -> None:
    assert rp.route_key("head", "/x") == "GET /x"
    assert rp.route_key("post", "/x") == "POST /x"


# --- rule_allows -------------------------------------------------------------------------------------


def test_area_rule_uses_method_level() -> None:
    rule = rp.area(Area.TIME)
    assert rp.rule_allows(rule, "GET", _perms(TIME="VIEW"))
    assert not rp.rule_allows(rule, "POST", _perms(TIME="VIEW"))
    assert rp.rule_allows(rule, "DELETE", _perms(TIME="EDIT"))
    assert rp.rule_allows(rule, "HEAD", _perms(TIME="VIEW"))


def test_area_rule_explicit_level_overrides_method() -> None:
    rule = rp.area((Area.PAYROLL, Level.EDIT))
    assert not rp.rule_allows(rule, "GET", _perms(PAYROLL="VIEW"))
    assert rp.rule_allows(rule, "GET", _perms(PAYROLL="EDIT"))


def test_alternatives_any_of() -> None:
    rule = rp.area(Area.ABSENCES, Area.SHIFT_PLANNING)
    assert rp.rule_allows(rule, "GET", _perms(SHIFT_PLANNING="VIEW"))
    assert rp.rule_allows(rule, "GET", _perms(ABSENCES="VIEW"))
    assert not rp.rule_allows(rule, "GET", _perms(TIME="EDIT"))


def test_combined_requirement_needs_all() -> None:
    rule = rp.area(((Area.PAYROLL, None), (Area.EMPLOYEES, Level.VIEW)))
    assert not rp.rule_allows(rule, "GET", _perms(PAYROLL="VIEW"))
    assert not rp.rule_allows(rule, "GET", _perms(EMPLOYEES="EDIT"))
    assert rp.rule_allows(rule, "GET", _perms(PAYROLL="VIEW", EMPLOYEES="VIEW"))
    # Schreiben verlangt Bearbeiten bei Vergütung, Ansehen bei Mitarbeitern genügt
    assert not rp.rule_allows(rule, "POST", _perms(PAYROLL="VIEW", EMPLOYEES="EDIT"))
    assert rp.rule_allows(rule, "POST", _perms(PAYROLL="EDIT", EMPLOYEES="VIEW"))


def test_lookup_rule() -> None:
    assert rp.rule_allows(rp.LOOKUP, "GET", _perms(REPORTS="VIEW"))
    assert not rp.rule_allows(rp.LOOKUP, "GET", _perms(PAYROLL="VIEW"))


# --- decide ------------------------------------------------------------------------------------------


def test_decide_unknown_route_is_denied() -> None:
    assert rp.decide("GET", "/gibt-es-nicht", _perms(TIME="EDIT"), has_employee=True) == Decision.DENY


def test_decide_without_path_is_denied() -> None:
    assert rp.decide("GET", None, _perms(TIME="EDIT"), has_employee=True) == Decision.DENY


@pytest.mark.parametrize("key", ["GET /settings", "GET /hr-users", "GET /roles", "PATCH /employees/{employee_id}/hr-role"])
def test_decide_admin_routes_denied_even_with_everything(key) -> None:
    method, path = key.split(" ", 1)
    everything = {area: Level.EDIT for area in Area}
    assert rp.decide(method, path, everything, has_employee=True) == Decision.DENY


@pytest.mark.parametrize("key", ["GET /audit-log", "GET /employees/{employee_id}/data-export", "POST /migration/employee-values"])
def test_decide_never_routes(key) -> None:
    method, path = key.split(" ", 1)
    assert rp.decide(method, path, {area: Level.EDIT for area in Area}, has_employee=False) == Decision.DENY


@pytest.mark.parametrize("key", ["GET /notifications", "GET /me/personal-data", "POST /auth/change-password", "GET /features"])
def test_decide_always_routes(key) -> None:
    method, path = key.split(" ", 1)
    assert rp.decide(method, path, _perms(), has_employee=False) == Decision.ALLOW


def test_decide_mixed_falls_back_to_self_with_employee() -> None:
    path = "/employees/{employee_id}/absences"
    assert rp.decide("GET", path, _perms(ABSENCES="VIEW"), has_employee=True) == Decision.ALLOW
    assert rp.decide("GET", path, _perms(PAYROLL="VIEW"), has_employee=True) == Decision.SELF
    assert rp.decide("GET", path, _perms(PAYROLL="VIEW"), has_employee=False) == Decision.DENY


def test_decide_dashboard_without_employee_is_self() -> None:
    assert rp.decide("GET", "/dashboard", _perms(PAYROLL="VIEW"), has_employee=False) == Decision.SELF
    assert rp.decide("GET", "/dashboard", _perms(ABSENCES="VIEW"), has_employee=False) == Decision.ALLOW


def test_decide_payroll_office_template() -> None:
    perms = rp.normalize(rp.TEMPLATES["PAYROLL_OFFICE_READONLY"][2])
    assert rp.decide("GET", "/wage-types", perms, has_employee=False) == Decision.ALLOW
    assert rp.decide("PUT", "/wage-types", perms, has_employee=False) == Decision.DENY
    assert rp.decide("GET", "/payroll-export", perms, has_employee=False) == Decision.DENY
    assert rp.decide("GET", "/employees", perms, has_employee=False) == Decision.DENY


def test_template_payroll_office_only_payroll_view() -> None:
    name, _, perms = rp.TEMPLATES["PAYROLL_OFFICE_READONLY"]
    assert name == "Lohnbüro (nur lesen)"
    assert {a: l for a, l in rp.normalize(perms).items() if l != Level.NONE} == {Area.PAYROLL: Level.VIEW}


def test_area_info_covers_every_area() -> None:
    assert set(rp.AREA_INFO) == set(Area)


def test_rule_helpers() -> None:
    assert rp.mixed(Area.TIME).kind == RuleKind.MIXED
    assert rp.mixed(lookup=True).lookup is True
    assert Rule(RuleKind.NEVER).alternatives == ()


# --- Actor / Konto -----------------------------------------------------------------------------------


def _account(role: HrRole | None, perms: dict | None = None, payroll: bool = False) -> Account:
    custom = Role(id=7, tenant_id=1, name="R", permissions=json.dumps(perms)) if perms is not None else None
    return Account(
        id=1, tenant_id=1, role=role, payroll_access=payroll, custom_role=custom, custom_role_id=7 if custom else None
    )


def test_custom_permissions_only_for_hr() -> None:
    assert account_custom_permissions(_account(HrRole.HR, {"TIME": "VIEW"}))[Area.TIME] == Level.VIEW
    assert account_custom_permissions(_account(HrRole.ADMIN, {"TIME": "VIEW"})) is None
    assert account_custom_permissions(_account(HrRole.SUPERVISOR, {"TIME": "VIEW"})) is None
    assert account_custom_permissions(_account(None, {"TIME": "VIEW"})) is None
    assert account_custom_permissions(_account(HrRole.HR)) is None
    assert account_custom_permissions(None) is None


def test_custom_permissions_dangling_reference_means_no_access() -> None:
    account = Account(id=1, tenant_id=1, role=HrRole.HR, custom_role_id=99, custom_role=None)
    perms = account_custom_permissions(account)
    assert perms is not None and all(level == Level.NONE for level in perms.values())


@pytest.mark.parametrize(
    ("role", "perms", "payroll", "view", "edit"),
    [
        (HrRole.ADMIN, None, False, True, True),
        (HrRole.HR, None, False, False, False),
        (HrRole.HR, None, True, True, True),
        (HrRole.HR, {"PAYROLL": "VIEW"}, False, True, False),
        (HrRole.HR, {"PAYROLL": "EDIT"}, False, True, True),
        # Mit eigener Rolle zählt der Haken „Vergütung & Lohn-Export“ nicht
        (HrRole.HR, {"TIME": "EDIT"}, True, False, False),
        (HrRole.SUPERVISOR, None, True, False, False),
        (None, None, False, False, False),
    ],
)
def test_payroll_access(role, perms, payroll, view, edit) -> None:
    actor = Actor(account=_account(role, perms, payroll))
    assert actor.has_payroll_access is view
    assert actor.can_edit_payroll is edit


def test_self_only_actor_loses_role_and_areas() -> None:
    actor = Actor(account=_account(HrRole.HR, {"TIME": "EDIT"}))
    assert actor.has_area(Area.TIME, Level.EDIT)
    actor.self_only = True
    assert actor.role is None
    assert not actor.is_hr_level
    assert not actor.has_area(Area.TIME)


def test_has_area_without_custom_role_is_true() -> None:
    assert Actor(account=_account(HrRole.HR)).has_area(Area.PAYROLL, Level.EDIT)
