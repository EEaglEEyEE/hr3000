from datetime import date, timedelta
from typing import Protocol

from app.errors import AppError


class _Period(Protocol):
    valid_from: date
    valid_to: date | None


def apply_new_period(
    existing: list,
    new_from: date,
    new_to: date | None,
    overlap_message: str = "Der Zeitraum überlappt mit einem bestehenden Eintrag.",
) -> None:
    """Effective-Dating für Zeitreihen mit "höchstens ein Eintrag zu jedem
    Zeitpunkt" (Verträge, Vergütung, Standard-Schichten): ein neuer Eintrag, der
    nach dem Start des aktuell offenen beginnt, schließt diesen automatisch zum
    Vortag ab; jede andere Überlappung wird abgelehnt. Mutiert nur die
    übergebenen Objekte, committet nicht."""
    if new_to is not None and new_to < new_from:
        raise AppError(400, "INVALID_RANGE", "'valid_to' darf nicht vor 'valid_from' liegen.")

    open_row = next((row for row in existing if row.valid_to is None), None)
    if open_row is not None and new_from > open_row.valid_from:
        open_row.valid_to = new_from - timedelta(days=1)
        others = [row for row in existing if row is not open_row]
    else:
        others = existing

    new_end = new_to or date.max
    for other in others:
        other_end = other.valid_to or date.max
        if other.valid_from <= new_end and new_from <= other_end:
            raise AppError(400, "OVERLAPPING_PERIOD", overlap_message)
