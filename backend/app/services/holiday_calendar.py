"""Berechnung der gesetzlichen Feiertage je Bundesland (Gauß'sche Osterformel
+ bundeslandspezifische Zuordnung). Bildet den aktuellen Rechtsstand ab (z.B.
Reformationstag seit 2018 auch in HB/HH/NI/SH, Frauentag in BE seit 2019 und
MV seit 2023) – frühere Jahre werden nicht rückwirkend historisch korrekt
abgebildet, das Tool ist für den Import künftiger/aktueller Jahre gedacht."""

from datetime import date, timedelta
from enum import Enum


class Bundesland(str, Enum):
    BW = "BW"
    BY = "BY"
    BE = "BE"
    BB = "BB"
    HB = "HB"
    HH = "HH"
    HE = "HE"
    MV = "MV"
    NI = "NI"
    NW = "NW"
    RP = "RP"
    SL = "SL"
    SN = "SN"
    ST = "ST"
    SH = "SH"
    TH = "TH"


BUNDESLAND_NAMES: dict[Bundesland, str] = {
    Bundesland.BW: "Baden-Württemberg",
    Bundesland.BY: "Bayern",
    Bundesland.BE: "Berlin",
    Bundesland.BB: "Brandenburg",
    Bundesland.HB: "Bremen",
    Bundesland.HH: "Hamburg",
    Bundesland.HE: "Hessen",
    Bundesland.MV: "Mecklenburg-Vorpommern",
    Bundesland.NI: "Niedersachsen",
    Bundesland.NW: "Nordrhein-Westfalen",
    Bundesland.RP: "Rheinland-Pfalz",
    Bundesland.SL: "Saarland",
    Bundesland.SN: "Sachsen",
    Bundesland.ST: "Sachsen-Anhalt",
    Bundesland.SH: "Schleswig-Holstein",
    Bundesland.TH: "Thüringen",
}


def easter_sunday(year: int) -> date:
    """Gauß'sche Osterformel."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _buss_und_bettag(year: int) -> date:
    """Mittwoch vor dem 23. November – nur noch gesetzlicher Feiertag in Sachsen."""
    day = date(year, 11, 22)
    while day.weekday() != 2:  # Mittwoch
        day -= timedelta(days=1)
    return day


def public_holidays(year: int, bundesland: Bundesland) -> dict[date, str]:
    """Alle gesetzlichen Feiertage eines Jahres für ein Bundesland (Datum -> Name)."""
    ostersonntag = easter_sunday(year)
    holidays: dict[date, str] = {
        date(year, 1, 1): "Neujahr",
        ostersonntag - timedelta(days=2): "Karfreitag",
        ostersonntag + timedelta(days=1): "Ostermontag",
        date(year, 5, 1): "Tag der Arbeit",
        ostersonntag + timedelta(days=39): "Christi Himmelfahrt",
        ostersonntag + timedelta(days=50): "Pfingstmontag",
        date(year, 10, 3): "Tag der Deutschen Einheit",
        date(year, 12, 25): "1. Weihnachtstag",
        date(year, 12, 26): "2. Weihnachtstag",
    }

    if bundesland in (Bundesland.BW, Bundesland.BY, Bundesland.ST):
        holidays[date(year, 1, 6)] = "Heilige Drei Könige"

    if bundesland in (
        Bundesland.BW,
        Bundesland.BY,
        Bundesland.HE,
        Bundesland.NW,
        Bundesland.RP,
        Bundesland.SL,
    ):
        holidays[ostersonntag + timedelta(days=60)] = "Fronleichnam"

    if bundesland in (Bundesland.BY, Bundesland.SL):
        holidays[date(year, 8, 15)] = "Mariä Himmelfahrt"

    if bundesland == Bundesland.TH:
        holidays[date(year, 9, 20)] = "Weltkindertag"

    if bundesland in (
        Bundesland.BB,
        Bundesland.MV,
        Bundesland.SN,
        Bundesland.ST,
        Bundesland.TH,
        Bundesland.HB,
        Bundesland.HH,
        Bundesland.NI,
        Bundesland.SH,
    ):
        holidays[date(year, 10, 31)] = "Reformationstag"

    if bundesland in (Bundesland.BW, Bundesland.BY, Bundesland.NW, Bundesland.RP, Bundesland.SL):
        holidays[date(year, 11, 1)] = "Allerheiligen"

    if bundesland == Bundesland.SN:
        holidays[_buss_und_bettag(year)] = "Buß- und Bettag"

    if bundesland in (Bundesland.BE, Bundesland.MV):
        holidays[date(year, 3, 8)] = "Internationaler Frauentag"

    return holidays
