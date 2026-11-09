"""iCalendar (RFC 5545) für das Kalender-Abo: ganztägige Termine, CRLF, Zeilen gefaltet."""
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    start: date
    end: date  # letzter Tag (einschließlich)
    summary: str


def _escape(text: str) -> str:
    """Sonderzeichen in Textwerten (RFC 5545, 3.3.11)."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Zeilen über 75 Oktette falten (Fortsetzung mit führendem Leerzeichen)."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += encoded
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def build_ics(name: str, events: list[CalendarEvent], host: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//HR3000//Kalender//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
    ]
    for event in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{event.uid}@{host}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{event.start:%Y%m%d}",
            f"DTEND;VALUE=DATE:{event.end + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(event.summary)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
