"""Prometheus-Metriken ohne Zusatzpaket (Textformat 0.0.4).

Zähler und Histogramme leben im Speicher des Backend-Prozesses (ein Uvicorn-Prozess, siehe
docker-compose.yml) und beginnen nach einem Neustart bei 0 – Prometheus erkennt das an den
``_total``-Zählern selbst. Momentwerte (Mandanten, Mitarbeiter, offene Anträge, Tablets) liest
``GET /metrics`` bei jedem Abruf aus der Datenbank, siehe app/services/monitoring.py.

Bewusst nur Zählwerte: keine Namen, E-Mail-Adressen oder Inhalte in Labels.
"""

from __future__ import annotations

import math
import re
import threading
from collections.abc import Iterable

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

_NAME = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
_LABEL = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)


def escape_label_value(value: str) -> str:
    """Escaping für Labelwerte laut Textformat: Backslash, Zeilenumbruch, Anführungszeichen."""
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def escape_help(text: str) -> str:
    """Escaping für HELP-Texte: nur Backslash und Zeilenumbruch."""
    return text.replace("\\", "\\\\").replace("\n", "\\n")


def format_labels(names: tuple[str, ...], values: tuple[str, ...], extra: tuple[tuple[str, str], ...] = ()) -> str:
    pairs = list(zip(names, values, strict=True)) + list(extra)
    if not pairs:
        return ""
    return "{" + ",".join(f'{k}="{escape_label_value(str(v))}"' for k, v in pairs) + "}"


def format_value(value: float) -> str:
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


def _check_name(name: str) -> None:
    if not _NAME.match(name):
        raise ValueError(f"Ungültiger Metrikname {name!r}")


def _check_labels(labelnames: tuple[str, ...]) -> None:
    for label in labelnames:
        if not _LABEL.match(label) or label == "le" or label.startswith("__"):
            raise ValueError(f"Ungültiges Label {label!r}")
    if len(set(labelnames)) != len(labelnames):
        raise ValueError("Label doppelt")


def header(name: str, help_text: str, kind: str) -> list[str]:
    return [f"# HELP {name} {escape_help(help_text)}", f"# TYPE {name} {kind}"]


class _Metric:
    kind = ""

    def __init__(self, name: str, help_text: str, labels: Iterable[str] = ()):
        _check_name(name)
        self.name, self.help, self.labelnames = name, help_text, tuple(labels)
        _check_labels(self.labelnames)
        self._lock = threading.Lock()

    def _key(self, labels: dict[str, str]) -> tuple[str, ...]:
        if set(labels) != set(self.labelnames):
            raise ValueError(f"{self.name}: Labels {sorted(labels)} statt {sorted(self.labelnames)}")
        return tuple(str(labels[n]) for n in self.labelnames)

    def header(self) -> list[str]:
        return header(self.name, self.help, self.kind)

    def clear(self) -> None:
        raise NotImplementedError


class Counter(_Metric):
    kind = "counter"

    def __init__(self, name: str, help_text: str, labels: Iterable[str] = ()):
        super().__init__(name, help_text, labels)
        self._values: dict[tuple[str, ...], float] = {}

    def inc(self, amount: float = 1, **labels: str) -> None:
        if amount < 0:
            raise ValueError("Zähler können nur steigen")
        key = self._key(labels)
        with self._lock:
            self._values[key] = self._values.get(key, 0) + amount

    def value(self, **labels: str) -> float:
        return self._values.get(self._key(labels), 0)

    def collect(self) -> list[str]:
        with self._lock:
            items = sorted(self._values.items())
        if not items and not self.labelnames:
            # Zähler ohne Labels immer ausgeben (0), damit rate()/increase() von Anfang an Werte haben.
            items = [((), 0)]
        return self.header() + [f"{self.name}{format_labels(self.labelnames, k)} {format_value(v)}" for k, v in items]

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


class Histogram(_Metric):
    kind = "histogram"

    def __init__(
        self, name: str, help_text: str, labels: Iterable[str] = (), buckets: Iterable[float] = DEFAULT_BUCKETS
    ):
        super().__init__(name, help_text, labels)
        self.buckets = tuple(sorted(float(b) for b in buckets if not math.isinf(b)))
        if not self.buckets:
            raise ValueError("Histogramm ohne Grenzen")
        if len(set(self.buckets)) != len(self.buckets):
            raise ValueError("Histogramm-Grenzen doppelt")
        # Schlüssel -> [Anzahl je Grenze (kumulativ), Summe, Anzahl gesamt]
        self._data: dict[tuple[str, ...], list] = {}

    def observe(self, value: float, **labels: str) -> None:
        key = self._key(labels)
        with self._lock:
            counts, total, n = self._data.get(key, ([0] * len(self.buckets), 0.0, 0))
            counts = [c + (1 if value <= b else 0) for c, b in zip(counts, self.buckets)]
            self._data[key] = [counts, total + value, n + 1]

    def count(self, **labels: str) -> int:
        entry = self._data.get(self._key(labels))
        return entry[2] if entry else 0

    def collect(self) -> list[str]:
        with self._lock:
            items = sorted((k, (list(v[0]), v[1], v[2])) for k, v in self._data.items())
        lines = self.header()
        for key, (counts, total, n) in items:
            for bound, c in zip(self.buckets, counts):
                lines.append(f"{self.name}_bucket{format_labels(self.labelnames, key, (('le', format_value(bound)),))} {c}")
            lines.append(f"{self.name}_bucket{format_labels(self.labelnames, key, (('le', '+Inf'),))} {n}")
            lines.append(f"{self.name}_sum{format_labels(self.labelnames, key)} {format_value(total)}")
            lines.append(f"{self.name}_count{format_labels(self.labelnames, key)} {n}")
        return lines

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


def gauge_lines(
    name: str, help_text: str, labelnames: tuple[str, ...], rows: Iterable[tuple[tuple[str, ...], float]]
) -> list[str]:
    """Momentwerte (z. B. aus der Datenbank) als Gauge."""
    _check_name(name)
    _check_labels(labelnames)
    lines = header(name, help_text, "gauge")
    lines += [f"{name}{format_labels(labelnames, tuple(str(x) for x in key))} {format_value(value)}" for key, value in rows]
    return lines


HTTP_REQUESTS = Counter(
    "hr_http_requests_total", "HTTP-Anfragen nach Routenvorlage, Methode und Status", ("route", "method", "status")
)
HTTP_SECONDS = Histogram(
    "hr_http_request_duration_seconds", "Antwortzeit nach Routenvorlage und Methode", ("route", "method")
)
MAIL_FAILURES = Counter(
    "hr_mail_failures_total", "Fehlgeschlagene E-Mail-Versuche (SMTP-Fehler) seit dem Start des Prozesses"
)

REGISTRY: tuple[_Metric, ...] = (HTTP_REQUESTS, HTTP_SECONDS, MAIL_FAILURES)


def render(extra: Iterable[str] = (), registry: Iterable[_Metric] = REGISTRY) -> str:
    """Momentwerte (``extra``) zuerst, dann die Prozesszähler; endet mit Zeilenumbruch."""
    lines: list[str] = list(extra)
    for metric in registry:
        lines += metric.collect()
    return "\n".join(lines) + "\n"


def reset() -> None:
    """Nur für Tests."""
    for metric in REGISTRY:
        metric.clear()
