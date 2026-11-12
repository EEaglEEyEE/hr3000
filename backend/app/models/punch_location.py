import enum


class PunchLocationCheck(str, enum.Enum):
    """Ergebnis der Standortprüfung beim Stempeln im Web-Login (A18). Gespeichert wird nur dieses
    Ergebnis, nie die Position selbst – siehe app/services/punch_location_service.py."""

    INSIDE = "INSIDE"
    OUTSIDE = "OUTSIDE"
    UNKNOWN = "UNKNOWN"
