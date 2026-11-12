"""Mehrwöchiger Turnus eines Arbeitszeitmodells (z.B. Woche 1 Mo–Mi, Woche 2 Do–Fr): gemeinsame
Auswertung für die Fassung der Arbeitszeit eines Mitarbeiters (EmployeeDefaultShift) und die Fassung
eines Arbeitszeitmodells (WorkTimeProfileVersion).

Gespeichert wird der Turnus als Text in rotation_minutes – Wochen durch ";" getrennt, darin die
Soll-Minuten Mo..So durch "," (z.B. "480,480,480,0,0,0,0;0,0,0,480,480,0,0") – und der Montag der
Woche 1 in rotation_start. Der Startpunkt ist ein festes Datum (nicht "relativ zum Gültig-ab"),
damit das Teilen einer Fassung, das Nachziehen aus einem Modell und spätere Fassungen den Rhythmus
nicht verschieben. Der Turnus wiederholt sich fortlaufend – auch rückwärts vor dem Startpunkt."""
from datetime import date, timedelta

ROTATION_MIN_WEEKS = 2
ROTATION_MAX_WEEKS = 4


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def serialize_rotation(weeks: list[list[int]]) -> str:
    return ";".join(",".join(str(minutes) for minutes in week) for week in weeks)


def parse_rotation(value: str | None) -> list[list[int]] | None:
    if not value:
        return None
    return [[int(minutes) for minutes in week.split(",")] for week in value.split(";")]


def rotation_week_index(start: date, weeks: int, day: date) -> int:
    """0-basierte Turnus-Woche eines Tages: Wochen seit dem Montag der Woche 1, modulo Turnuslänge
    (Python-Modulo: auch vor dem Startpunkt richtig herum)."""
    return ((monday_of(day) - monday_of(start)).days // 7) % weeks


class RotationMixin:
    """Auswertung von rotation_minutes/rotation_start und day_minutes (Spalten in der Klasse)."""

    day_minutes: str | None
    rotation_minutes: str | None
    rotation_start: date | None
    valid_from: date

    @property
    def day_minutes_list(self) -> list[int] | None:
        return [int(v) for v in self.day_minutes.split(",")] if self.day_minutes else None

    @property
    def rotation_weeks(self) -> list[list[int]] | None:
        """Soll-Minuten je Turnus-Woche (je 7 Werte Mo..So), None = kein mehrwöchiges Modell."""
        return parse_rotation(self.rotation_minutes)

    def rotation_week_on(self, day: date) -> int | None:
        """0-basierte Turnus-Woche an diesem Tag (None = kein mehrwöchiges Modell)."""
        weeks = self.rotation_weeks
        if weeks is None:
            return None
        return rotation_week_index(self.rotation_start or self.valid_from, len(weeks), day)

    def day_minutes_on(self, day: date) -> list[int] | None:
        """Soll-Minuten Mo..So der Woche, in der dieser Tag liegt: beim mehrwöchigen Modell die der
        jeweiligen Turnus-Woche, sonst die Stunden je Wochentag (None = gleichmäßig verteilt)."""
        weeks = self.rotation_weeks
        if weeks is None:
            return self.day_minutes_list
        return weeks[rotation_week_index(self.rotation_start or self.valid_from, len(weeks), day)]

    @property
    def average_workdays(self) -> float | None:
        """Durchschnittliche Arbeitstage je Woche über den Turnus (None = kein mehrwöchiges Modell)."""
        weeks = self.rotation_weeks
        if weeks is None:
            return None
        return sum(1 for week in weeks for minutes in week if minutes > 0) / len(weeks)
