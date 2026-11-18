"""Unit-Tests für app/metrics.py (Prometheus-Textformat ohne Zusatzpaket) und die reinen Helfer
in app/services/monitoring.py und app/api/metrics.py."""
from datetime import UTC, datetime, timedelta, timezone

import pytest
from starlette.requests import Request

from app import metrics
from app.api.metrics import came_through_proxy, token_ok
from app.metrics import (
    Counter,
    Histogram,
    escape_help,
    escape_label_value,
    format_labels,
    format_value,
    gauge_lines,
    render,
)
from app.services.monitoring import naive_utc, seconds_since, up_lines


# --- Escaping -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("plain", "plain"),
        ("", ""),
        ('a"b', 'a\\"b'),
        ("a\\b", "a\\\\b"),
        ("a\nb", "a\\nb"),
        ('\\"\n', '\\\\\\"\\n'),
        ("ümlaut-ß", "ümlaut-ß"),
        ("{x}", "{x}"),
    ],
)
def test_escape_label_value(raw: str, escaped: str) -> None:
    assert escape_label_value(raw) == escaped


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [("Text", "Text"), ('mit "Zitat"', 'mit "Zitat"'), ("a\\b", "a\\\\b"), ("zwei\nZeilen", "zwei\\nZeilen")],
)
def test_escape_help_keeps_quotes(raw: str, escaped: str) -> None:
    assert escape_help(raw) == escaped


def test_format_labels_empty() -> None:
    assert format_labels((), ()) == ""


def test_format_labels_order_and_escaping() -> None:
    assert format_labels(("a", "b"), ("1", 'x"y')) == '{a="1",b="x\\"y"}'


def test_format_labels_extra_appended() -> None:
    assert format_labels(("route",), ("/x",), (("le", "0.5"),)) == '{route="/x",le="0.5"}'


def test_format_labels_only_extra() -> None:
    assert format_labels((), (), (("le", "+Inf"),)) == '{le="+Inf"}'


def test_format_labels_length_mismatch() -> None:
    with pytest.raises(ValueError):
        format_labels(("a", "b"), ("1",))


# --- Zahlen ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (0, "0"),
        (1, "1"),
        (-3, "-3"),
        (2.0, "2"),
        (0.25, "0.25"),
        (1e-9, "1e-09"),
        (float("inf"), "+Inf"),
        (float("-inf"), "-Inf"),
        (float("nan"), "NaN"),
        (10**12, "1000000000000"),
    ],
)
def test_format_value(value: float, text: str) -> None:
    assert format_value(value) == text


# --- Namen und Labels -----------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["", "1abc", "a-b", "a b", "ä"])
def test_invalid_metric_name(name: str) -> None:
    with pytest.raises(ValueError):
        Counter(name, "x")
    with pytest.raises(ValueError):
        gauge_lines(name, "x", (), [])


@pytest.mark.parametrize("label", ["le", "1a", "a-b", "__reserved", ""])
def test_invalid_label_name(label: str) -> None:
    with pytest.raises(ValueError):
        Counter("ok_total", "x", (label,))
    with pytest.raises(ValueError):
        gauge_lines("ok", "x", (label,), [])


def test_duplicate_label_rejected() -> None:
    with pytest.raises(ValueError):
        Counter("ok_total", "x", ("a", "a"))


@pytest.mark.parametrize("name", ["hr_up", "a:b", "_x", "x1"])
def test_valid_metric_names(name: str) -> None:
    assert Counter(name, "x").name == name


# --- Counter --------------------------------------------------------------------------------------


def test_counter_without_labels_reports_zero_initially() -> None:
    c = Counter("c_total", "Hilfe")
    assert c.collect() == ["# HELP c_total Hilfe", "# TYPE c_total counter", "c_total 0"]


def test_counter_with_labels_empty_has_only_header() -> None:
    c = Counter("c_total", "Hilfe", ("a",))
    assert c.collect() == ["# HELP c_total Hilfe", "# TYPE c_total counter"]


def test_counter_inc_and_value() -> None:
    c = Counter("c_total", "x", ("route", "status"))
    c.inc(route="/a", status="200")
    c.inc(2, route="/a", status="200")
    c.inc(route="/b", status="404")
    assert c.value(route="/a", status="200") == 3
    assert c.value(route="/b", status="404") == 1
    assert c.value(route="/c", status="200") == 0


def test_counter_collect_sorted_and_escaped() -> None:
    c = Counter("c_total", "x", ("route",))
    c.inc(route="/z")
    c.inc(0.5, route='/a"b')
    assert c.collect()[2:] == ['c_total{route="/a\\"b"} 0.5', 'c_total{route="/z"} 1']


def test_counter_rejects_negative() -> None:
    c = Counter("c_total", "x")
    with pytest.raises(ValueError):
        c.inc(-1)


def test_counter_zero_increment_allowed() -> None:
    c = Counter("c_total", "x")
    c.inc(0)
    assert c.value() == 0
    assert c.collect()[-1] == "c_total 0"


@pytest.mark.parametrize("labels", [{}, {"a": "1", "b": "2"}, {"b": "1"}])
def test_counter_wrong_labels(labels: dict) -> None:
    c = Counter("c_total", "x", ("a",))
    with pytest.raises(ValueError):
        c.inc(**labels)


def test_counter_clear() -> None:
    c = Counter("c_total", "x", ("a",))
    c.inc(a="1")
    c.clear()
    assert c.value(a="1") == 0


def test_counter_label_value_converted_to_str() -> None:
    c = Counter("c_total", "x", ("status",))
    c.inc(status=200)  # type: ignore[arg-type]
    assert c.value(status="200") == 1


# --- Histogram ------------------------------------------------------------------------------------


def test_histogram_requires_buckets() -> None:
    with pytest.raises(ValueError):
        Histogram("h", "x", (), buckets=())
    with pytest.raises(ValueError):
        Histogram("h", "x", (), buckets=(float("inf"),))


def test_histogram_duplicate_buckets() -> None:
    with pytest.raises(ValueError):
        Histogram("h", "x", (), buckets=(1, 1.0))


def test_histogram_buckets_sorted() -> None:
    assert Histogram("h", "x", (), buckets=(5, 0.1, 1)).buckets == (0.1, 1.0, 5.0)


def test_histogram_empty_has_only_header() -> None:
    assert Histogram("h", "x", ("a",)).collect() == ["# HELP h x", "# TYPE h histogram"]


def test_histogram_cumulative_buckets_sum_count() -> None:
    h = Histogram("h", "Dauer", ("route",), buckets=(0.1, 0.5, 1))
    for value in (0.05, 0.1, 0.3, 2.0):
        h.observe(value, route="/a")
    assert h.collect() == [
        "# HELP h Dauer",
        "# TYPE h histogram",
        'h_bucket{route="/a",le="0.1"} 2',
        'h_bucket{route="/a",le="0.5"} 3',
        'h_bucket{route="/a",le="1"} 3',
        'h_bucket{route="/a",le="+Inf"} 4',
        'h_sum{route="/a"} 2.45',
        'h_count{route="/a"} 4',
    ]
    assert h.count(route="/a") == 4
    assert h.count(route="/b") == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, [1, 1, 1]), (0.1, [1, 1, 1]), (0.1000001, [0, 1, 1]), (1, [0, 0, 1]), (1.5, [0, 0, 0])],
)
def test_histogram_bucket_edges_inclusive(value: float, expected: list[int]) -> None:
    h = Histogram("h", "x", (), buckets=(0.1, 0.5, 1))
    h.observe(value)
    lines = h.collect()[2:]
    assert [int(line.rsplit(" ", 1)[1]) for line in lines[:3]] == expected
    assert lines[3] == 'h_bucket{le="+Inf"} 1'


def test_histogram_without_labels_format() -> None:
    h = Histogram("h", "x", (), buckets=(1,))
    h.observe(0.5)
    assert h.collect()[2:] == ['h_bucket{le="1"} 1', 'h_bucket{le="+Inf"} 1', "h_sum 0.5", "h_count 1"]


def test_histogram_series_sorted() -> None:
    h = Histogram("h", "x", ("route",), buckets=(1,))
    h.observe(1, route="/b")
    h.observe(1, route="/a")
    bucket_lines = [line for line in h.collect() if line.startswith("h_count")]
    assert bucket_lines == ['h_count{route="/a"} 1', 'h_count{route="/b"} 1']


def test_histogram_wrong_labels() -> None:
    h = Histogram("h", "x", ("route",))
    with pytest.raises(ValueError):
        h.observe(1)


def test_histogram_clear() -> None:
    h = Histogram("h", "x", ())
    h.observe(1)
    h.clear()
    assert h.count() == 0


def test_default_buckets_ascending() -> None:
    assert list(metrics.DEFAULT_BUCKETS) == sorted(metrics.DEFAULT_BUCKETS)


# --- Gauges und Gesamtausgabe ---------------------------------------------------------------------


def test_gauge_lines_empty_rows() -> None:
    assert gauge_lines("g", "Hilfe", ("tenant",), []) == ["# HELP g Hilfe", "# TYPE g gauge"]


def test_gauge_lines_values() -> None:
    lines = gauge_lines("g", "x", ("tenant", "device"), [(("a", 7), 1.5), (("b\n", "8"), 0)])
    assert lines[2:] == ['g{tenant="a",device="7"} 1.5', 'g{tenant="b\\n",device="8"} 0']


def test_gauge_lines_help_escaped() -> None:
    assert gauge_lines("g", "a\nb", (), [])[0] == "# HELP g a\\nb"


def test_render_ends_with_newline_and_orders_extra_first() -> None:
    c = Counter("c_total", "x")
    text = render(["# HELP g x", "# TYPE g gauge", "g 1"], registry=(c,))
    assert text == "# HELP g x\n# TYPE g gauge\ng 1\n# HELP c_total x\n# TYPE c_total counter\nc_total 0\n"


def test_render_empty() -> None:
    assert render([], registry=()) == "\n"


def test_registry_names_and_reset() -> None:
    names = {m.name for m in metrics.REGISTRY}
    assert names == {"hr_http_requests_total", "hr_http_request_duration_seconds", "hr_mail_failures_total"}
    metrics.MAIL_FAILURES.inc()
    metrics.HTTP_REQUESTS.inc(route="/x", method="GET", status="200")
    metrics.HTTP_SECONDS.observe(0.1, route="/x", method="GET")
    metrics.reset()
    assert metrics.MAIL_FAILURES.value() == 0
    assert metrics.HTTP_REQUESTS.value(route="/x", method="GET", status="200") == 0
    assert metrics.HTTP_SECONDS.count(route="/x", method="GET") == 0


def test_every_sample_line_belongs_to_declared_type() -> None:
    """Grobe Formatprüfung der Gesamtausgabe: jede Zeile ist Kommentar oder Messwert mit Zahl."""
    h = Histogram("h_seconds", "x", ("route",), buckets=(1,))
    h.observe(0.2, route="/a")
    c = Counter("c_total", "x", ("a",))
    c.inc(a="1")
    text = render(gauge_lines("g", "x", (), [((), 3)]), registry=(h, c))
    for line in text.strip().split("\n"):
        if line.startswith("#"):
            assert line.split(" ")[1] in {"HELP", "TYPE"}
            continue
        name, value = line.rsplit(" ", 1)
        float(value.replace("+Inf", "inf"))
        assert name.split("{")[0] in {"g", "h_seconds_bucket", "h_seconds_sum", "h_seconds_count", "c_total"}


# --- Helfer aus monitoring ------------------------------------------------------------------------


def test_up_lines() -> None:
    assert up_lines(True)[-1] == "hr_up 1"
    assert up_lines(False)[-1] == "hr_up 0"
    assert up_lines(False)[1] == "# TYPE hr_up gauge"


def test_naive_utc_keeps_naive() -> None:
    value = datetime(2026, 11, 18, 12, 0)
    assert naive_utc(value) == value


def test_naive_utc_converts_aware() -> None:
    value = datetime(2026, 11, 18, 13, 0, tzinfo=timezone(timedelta(hours=1)))
    assert naive_utc(value) == datetime(2026, 11, 18, 12, 0)
    assert naive_utc(value).tzinfo is None


@pytest.mark.parametrize(
    ("seen", "now", "seconds"),
    [
        (datetime(2026, 1, 1, 12, 0), datetime(2026, 1, 1, 12, 1), 60.0),
        (datetime(2026, 1, 1, 12, 0, tzinfo=UTC), datetime(2026, 1, 1, 12, 0, 30), 30.0),
        (datetime(2026, 1, 1, 12, 0), datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC), 30.0),
        (datetime(2026, 1, 1, 12, 5), datetime(2026, 1, 1, 12, 0), 0.0),  # Uhr des Tablets voraus
        (datetime(2026, 1, 1, 12, 0), datetime(2026, 1, 1, 12, 0), 0.0),
    ],
)
def test_seconds_since(seen: datetime, now: datetime, seconds: float) -> None:
    assert seconds_since(seen, now) == seconds


# --- Helfer aus api/metrics -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("authorization", "token", "ok"),
    [
        (None, None, True),
        (None, "", True),
        ("Bearer egal", None, True),
        (None, "geheim", False),
        ("", "geheim", False),
        ("Bearer geheim", "geheim", True),
        ("bearer geheim", "geheim", False),
        ("Bearer geheim ", "geheim", False),
        ("Bearer falsch", "geheim", False),
        ("geheim", "geheim", False),
        ("Bearer gehei", "geheim", False),
        ("Bearer ä", "ä", True),
    ],
)
def test_token_ok(authorization: str | None, token: str | None, ok: bool) -> None:
    assert token_ok(authorization, token) is ok


def _request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]
    return Request({"type": "http", "method": "GET", "path": "/metrics", "headers": raw, "query_string": b""})


@pytest.mark.parametrize(
    ("headers", "proxied"),
    [
        ({}, False),
        ({"Host": "backend:8000"}, False),
        ({"X-Forwarded-For": "203.0.113.5"}, True),
        ({"X-Forwarded-Host": "firma.hr3000.de"}, True),
        ({"X-Forwarded-Proto": "https"}, True),
        ({"Forwarded": "for=203.0.113.5"}, True),
        ({"X-Real-IP": "203.0.113.5"}, True),
        ({"X-Forwarded-For": ""}, False),
    ],
)
def test_came_through_proxy(headers: dict[str, str], proxied: bool) -> None:
    assert came_through_proxy(_request(headers)) is proxied
