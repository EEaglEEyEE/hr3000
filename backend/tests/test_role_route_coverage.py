"""Pflicht-Test zu eigenen Rollen: JEDE registrierte Route der App muss in
app/services/role_permissions.ROUTE_RULES stehen (deny by default) – sonst wäre eine neue
Verwaltungsfunktion für Konten mit eigener Rolle stillschweigend gesperrt bzw. nie bewusst
eingeordnet. Zusätzlich wird geprüft, dass die Einordnung zur tatsächlichen Absicherung passt."""
from fastapi.routing import APIRoute, APIWebSocketRoute

from app.api import deps
from app.main import app
from app.services.role_permissions import ROUTE_RULES, Rule, RuleKind, route_key


def _walk(routes):
    # FastAPI kapselt eingebundene Router (_IncludedRouter); app.routes enthält sie nicht direkt.
    for route in routes:
        if isinstance(route, (APIRoute, APIWebSocketRoute)):
            yield route
        elif hasattr(route, "original_router"):
            yield from _walk(route.original_router.routes)
        elif hasattr(route, "routes"):
            yield from _walk(route.routes)


def _api_routes() -> list[APIRoute]:
    return [r for r in _walk(app.routes) if isinstance(r, APIRoute)]


def _dependency_calls(dependant, acc=None) -> set:
    acc = set() if acc is None else acc
    for sub in dependant.dependencies:
        if sub.call is not None:
            acc.add(sub.call)
        _dependency_calls(sub, acc)
    return acc


def _keys() -> dict[str, APIRoute]:
    result = {}
    for route in _api_routes():
        for method in route.methods - {"HEAD", "OPTIONS"}:
            result[route_key(method, route.path)] = route
    return result


_ACCOUNT_DEPS = {
    deps.get_current_actor,
    deps.get_current_hr_principal,
    deps.get_current_admin_principal,
    deps.get_current_payroll_principal,
    deps.get_current_full_hr_principal,
    deps.get_current_super_admin_principal,
    deps.get_current_hr_or_self,
}


def test_walker_finds_the_routes() -> None:
    keys = _keys()
    assert len(keys) > 250
    assert "GET /employees" in keys
    assert "GET /roles" in keys


def test_every_registered_route_has_a_rule() -> None:
    missing = sorted(set(_keys()) - set(ROUTE_RULES))
    assert not missing, (
        "Route(n) ohne Einordnung für eigene Rollen – in app/services/role_permissions.ROUTE_RULES "
        f"einem Bereich zuordnen (oder bewusst ALWAYS/ADMIN/NEVER/PUBLIC): {missing}"
    )


def test_no_stale_rules() -> None:
    stale = sorted(set(ROUTE_RULES) - set(_keys()))
    assert not stale, f"Regeln für Routen, die es nicht (mehr) gibt: {stale}"


def test_admin_rules_really_require_admin() -> None:
    """ADMIN heißt: die Route selbst verlangt Admin bzw. Super-Admin – die Regel ersetzt das nicht."""
    keys = _keys()
    admin_deps = {deps.get_current_admin_principal, deps.get_current_super_admin_principal}
    wrong = [
        key for key, rule in ROUTE_RULES.items()
        if rule.kind == RuleKind.ADMIN and not (_dependency_calls(keys[key].dependant) & admin_deps)
    ]
    assert not wrong, f"Als ADMIN eingeordnet, aber ohne Admin-Prüfung: {wrong}"


def test_public_rules_have_no_account_check() -> None:
    """PUBLIC: Endpoints ohne Konto-Anmeldung über get_current_actor (dort greift die Prüfung nicht)."""
    keys = _keys()
    wrong = [
        key for key, rule in ROUTE_RULES.items()
        if rule.kind == RuleKind.PUBLIC and (_dependency_calls(keys[key].dependant) & _ACCOUNT_DEPS)
    ]
    assert not wrong, f"Als PUBLIC eingeordnet, nutzt aber eine Konto-Anmeldung: {wrong}"


def test_area_rules_have_requirements() -> None:
    empty = [
        key for key, rule in ROUTE_RULES.items()
        if rule.kind in (RuleKind.AREA, RuleKind.MIXED) and not rule.alternatives and not rule.lookup
        and not rule.without_employee
    ]
    assert not empty, f"Bereichsregel ohne Bereich: {empty}"


def test_admin_dependency_routes_are_never_area_rules() -> None:
    """Admin-only Endpoints bleiben Admin: eine Bereichsregel würde suggerieren, sie seien freigebbar."""
    keys = _keys()
    admin_deps = {deps.get_current_admin_principal, deps.get_current_super_admin_principal}
    wrong = [
        key for key, route in keys.items()
        if _dependency_calls(route.dependant) & admin_deps and ROUTE_RULES.get(key, Rule(RuleKind.ADMIN)).kind != RuleKind.ADMIN
    ]
    assert not wrong, wrong


def test_me_routes_are_always_allowed() -> None:
    """„Mein Bereich“ eines verknüpften Mitarbeiters bleibt von eigenen Rollen unberührt."""
    wrong = [key for key, rule in ROUTE_RULES.items() if key.split(" ", 1)[1].startswith("/me/") and rule.kind != RuleKind.ALWAYS]
    assert not wrong, wrong
