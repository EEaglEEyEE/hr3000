from datetime import date

from app.services.holiday_calendar import Bundesland, easter_sunday, public_holidays


def test_easter_sunday_known_dates() -> None:
    assert easter_sunday(2024) == date(2024, 3, 31)
    assert easter_sunday(2025) == date(2025, 4, 20)
    assert easter_sunday(2026) == date(2026, 4, 5)


def test_bayern_includes_catholic_holidays() -> None:
    holidays = public_holidays(2026, Bundesland.BY)

    assert holidays[date(2026, 1, 6)] == "Heilige Drei Könige"
    assert holidays[date(2026, 8, 15)] == "Mariä Himmelfahrt"
    assert holidays[date(2026, 11, 1)] == "Allerheiligen"
    assert date(2026, 10, 31) not in holidays  # Reformationstag nicht in Bayern


def test_all_states_share_the_common_holidays() -> None:
    for bundesland in Bundesland:
        holidays = public_holidays(2026, bundesland)
        assert holidays[date(2026, 1, 1)] == "Neujahr"
        assert holidays[date(2026, 5, 1)] == "Tag der Arbeit"
        assert holidays[date(2026, 10, 3)] == "Tag der Deutschen Einheit"
        assert holidays[date(2026, 12, 25)] == "1. Weihnachtstag"
        assert holidays[date(2026, 12, 26)] == "2. Weihnachtstag"


def test_sachsen_has_buss_und_bettag_and_reformationstag() -> None:
    holidays = public_holidays(2026, Bundesland.SN)

    assert holidays[date(2026, 10, 31)] == "Reformationstag"
    # Buß- und Bettag 2026: Mittwoch vor dem 23.11. -> 18.11.2026
    assert holidays[date(2026, 11, 18)] == "Buß- und Bettag"


def test_thueringen_has_weltkindertag_but_no_fronleichnam() -> None:
    holidays = public_holidays(2026, Bundesland.TH)

    assert holidays[date(2026, 9, 20)] == "Weltkindertag"
    assert "Fronleichnam" not in holidays.values()
