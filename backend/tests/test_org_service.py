"""Führungskräfte und Zuständigkeit aus Abteilungsbaum, Leitungen und Stellvertretungen (ohne Datenbank)."""
from app.services.org_service import OrgSnapshot

# Abteilungen: 1 Vertrieb → 2 Innendienst → 3 Angebote; 4 Lager; 5 IT; 6 Projekt (unter 1)
DEPARTMENTS = {1: None, 2: 1, 3: 2, 4: None, 5: None, 6: 1}
LEADERS = {
    1: [(10, "HEAD", "STANDBY"), (12, "HEAD", "STANDBY"), (13, "DEPUTY", "FULL")],  # zwei Leitungen + Stellv.
    2: [(20, "HEAD", "STANDBY"), (22, "DEPUTY", "STANDBY")],
    # 3 Angebote: ohne Leitung
    4: [(42, "DEPUTY", "ABSENCE")],  # Lager: nur Stellvertretung, keine Leitung
    5: [(50, "HEAD", "STANDBY")],  # IT: Leitung inaktiv
    6: [(70, "HEAD", "STANDBY")],  # Projekt: Leitung 70 ohne eigene Abteilung
}
EMPLOYEES = {
    10: (1, None, True),   # Leitung Vertrieb
    11: (1, None, True),   # Vertrieb
    12: (1, None, True),   # zweite Leitung Vertrieb
    13: (1, None, True),   # Stellvertretung Vertrieb
    20: (2, None, True),   # Leitung Innendienst
    21: (2, None, True),   # Innendienst
    22: (2, None, True),   # Stellvertretung Innendienst
    30: (3, None, True),   # Angebote – Leitung darüber: 20
    31: (3, 10, True),     # Angebote, Ausnahme: direkt an 10
    40: (4, None, True),   # Lager ohne Leitung
    41: (4, 11, True),     # Lager, Ausnahme: 11
    42: (4, None, True),   # Stellvertretung Lager
    50: (5, None, False),  # inaktive Leitung IT
    51: (5, None, True),   # IT – keine aktive Leitung
    60: (None, None, True),  # ohne Abteilung
    61: (None, 61, True),    # Ausnahme auf sich selbst wird ignoriert
    62: (2, 50, True),       # Ausnahme auf Inaktive: Abteilungsleitung gilt
    70: (None, None, True),  # leitet Projekt, ohne eigene Abteilung
    71: (6, None, True),     # Projekt
}


def org(**changes) -> OrgSnapshot:
    snapshot = OrgSnapshot(
        departments=dict(DEPARTMENTS),
        leaders={d: list(rows) for d, rows in LEADERS.items()},
        employees=dict(EMPLOYEES),
    )
    for key, value in changes.items():
        getattr(snapshot, key).update(value)
    return snapshot


def test_heads_and_deputies() -> None:
    o = org()
    assert o.heads(1) == [10, 12]  # Reihenfolge wie eingetragen
    assert o.heads(5) == []  # inaktive Leitung zählt nicht
    assert o.heads(3) == []
    assert o.heads(None) == []
    assert o.heads(4, extra={4: {42}}) == [42]  # gedachte Leitung (handelnde Stellvertretung)
    assert o.heads(1, extra={1: {13, 10}}) == [10, 12, 13]  # keine doppelt
    assert o.heads(1, extra={1: {50}}) == [10, 12]  # inaktive auch nicht als gedachte
    assert o.deputies(1) == [(13, "FULL")]
    assert o.deputies(4) == [(42, "ABSENCE")]
    assert o.deputies(None) == []
    assert o.led_departments(10) == [1]
    assert o.led_departments(13, role="DEPUTY") == [1]
    assert o.led_departments(11) == []


def test_supervisors_from_department() -> None:
    o = org()
    assert o.supervisors(11) == [10, 12]  # beide Leitungen
    assert o.supervisors(13) == [10, 12]  # Stellvertretung ist keine Leitung
    assert o.supervisors(21) == [20]
    assert o.supervisors(30) == [20]  # Abteilung ohne Leitung: nächste darüber
    assert o.supervisors(20) == [10, 12]  # Leitung selbst: Leitungen darüber
    assert o.supervisors(10) == []  # oberste Leitung – die zweite Leitung ist nicht ihre Führungskraft
    assert o.supervisors(12) == []
    assert o.supervisors(40) == []  # Lager: nur Stellvertretung, niemand darüber
    assert o.supervisors(51) == []  # Leitung inaktiv
    assert o.supervisors(60) == []
    assert o.supervisors(999) == []  # unbekannt


def test_head_without_own_department_uses_the_led_one() -> None:
    o = org()
    assert o.home_department(70) == 6
    assert o.supervisors(70) == [10, 12]  # Projekt hängt unter Vertrieb
    assert o.supervisors(71) == [70]
    assert o.home_department(60) is None
    assert o.home_department(999) is None


def test_override_wins_unless_self_or_inactive() -> None:
    o = org()
    assert o.supervisors(31) == [10]
    assert o.supervisors(41) == [11]
    assert o.supervisors(61) == []
    assert o.supervisors(62) == [20]
    assert o.override(31) == 10 and o.override(62) is None and o.override(999) is None
    assert o.department_supervisors(31) == [20]  # ohne Ausnahme wäre es die Abteilung
    assert o.supervisor_source(31) == "OVERRIDE"
    assert o.supervisor_source(30) == "DEPARTMENT"
    assert o.supervisor_source(62) == "DEPARTMENT"
    assert o.supervisor_source(10) is None


def test_leading_department() -> None:
    o = org()
    assert o.leading_department(11) == 1
    assert o.leading_department(30) == 2
    assert o.leading_department(20) == 1
    assert o.leading_department(10) is None
    assert o.leading_department(40) is None
    assert o.leading_department(40, extra={4: {42}}) == 4  # handelnde Stellvertretung macht das Lager „geleitet“
    assert o.leading_department(42, extra={4: {42}}) is None  # für sich selbst nicht


def test_reports_are_direct_and_indirect() -> None:
    o = org()
    # Vertrieb: Mitglieder, Innendienst-Leitung und alles darunter, Ausnahme 31, Projekt
    assert o.reports(10) == {11, 13, 20, 21, 22, 30, 31, 41, 62, 70, 71}
    assert o.reports(12) == {11, 13, 20, 21, 22, 30, 41, 62, 70, 71}  # 31 per Ausnahme nur an 10; 41 über 11
    assert o.reports(20) == {21, 22, 30, 62}
    assert o.reports(11) == {41}
    assert o.reports(21) == set()
    assert o.reports(13) == set()  # Stellvertretung ohne Handeln: keine Unterstellten


def test_reports_of_an_acting_deputy() -> None:
    o = org()
    assert o.reports(13, extra={1: {13}}) == {11, 20, 21, 22, 30, 41, 62, 70, 71}  # wie eine Leitung, ohne die Leitungen
    assert o.reports(42, extra={4: {42}}) == {40}  # 41 hat eine Ausnahme
    assert o.reports(22, extra={2: {22}}) == {21, 30, 62}


def test_find_cycle() -> None:
    assert org().find_cycle() is None
    # 10 bekommt eine Ausnahme auf 21 (unter ihr): 21 → 20 → 10 → 21
    assert org(employees={10: (1, 21, True)}).find_cycle() in {10, 20, 21}
    # 70 leitet Projekt und gehört selbst ins Projekt: kein Kreis (geht eine Ebene höher)
    assert org(employees={70: (6, None, True)}).find_cycle() is None
    # A leitet die Abteilung von B und umgekehrt
    crossed = OrgSnapshot(
        departments={1: None, 2: None},
        leaders={1: [(1, "HEAD", "STANDBY")], 2: [(2, "HEAD", "STANDBY")]},
        employees={1: (2, None, True), 2: (1, None, True)},
    )
    assert crossed.find_cycle() in {1, 2}
    # Stellvertretungen erzeugen keine Kreise
    deputy_loop = OrgSnapshot(
        departments={1: None},
        leaders={1: [(1, "HEAD", "STANDBY"), (2, "DEPUTY", "FULL")]},
        employees={1: (None, 2, True), 2: (1, None, True)},
    )
    assert deputy_loop.find_cycle() in {1, 2}  # aber eine Ausnahme 1 → 2 bei 2 → 1 schon


def test_subtree() -> None:
    o = org()
    assert o.subtree(1) == {1, 2, 3, 6}
    assert o.subtree(4) == {4}
