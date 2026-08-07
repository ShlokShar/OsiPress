
import re

from persiantools.jdatetime import JalaliDate

from cron.ai.schemas import IranianDate


DATE_PLACEHOLDER_PATTERN = re.compile(
    r"(?<![A-Z0-9_])DATE_\d+(?![A-Z0-9_])"
)


def convert_iranian_date(year: int, month: int, day: int) -> str:
    """
    Converts a complete Solar Hijri date to the Gregorian calendar.

    :param year: the Solar Hijri year
    :param month: the Solar Hijri month, from 1 through 12
    :param day: the day of the Solar Hijri month
    :return: the Gregorian date formatted as Month D, YYYY
    """

    iranian_date = JalaliDate(year, month, day)
    return iranian_date.to_gregorian().strftime("%B %-d, %Y")


def handle_iranian_date_text(dates: list[IranianDate], text: str) -> str:
    """
    Replaces ordered DATE_0, DATE_1, and subsequent placeholders with their
    converted or transliterated date values.

    :param dates: a list of Solar Hijri dates ordered to match the placeholders
    :param text: the translated text containing the date placeholders
    :return: the text with each placeholder replaced by its formatted date
    :raises ValueError: if placeholders do not exactly match the date list
    """

    placeholders = DATE_PLACEHOLDER_PATTERN.findall(text)
    expected_placeholders = [
        f"DATE_{index}" for index in range(len(dates))
    ]

    if placeholders != expected_placeholders:
        raise ValueError(
            f"Expected placeholders {expected_placeholders} but received "
            f"{placeholders}"
        )

    for i, date in enumerate(dates):
        date_year, date_month, date_day = date.year, date.month, date.day
        formatted_date = convert_iranian_date(
            month=date_month,
            day=date_day,
            year=date_year,
        )

        text = text.replace(
            f"DATE_{i}",
            formatted_date
        )

    return text


def handle_iranian_date_references(
    dates: list[IranianDate],
    text: str
) -> str:
    """
    Replaces reference date placeholders by their order in the text, ignoring
    each placeholder's numeric suffix.

    :param dates: Solar Hijri dates ordered by occurrence in the reference
    :param text: reference text containing DATE_<number> placeholders
    :return: the reference with its placeholders replaced by Gregorian dates
    :raises ValueError: if the placeholder and date counts do not match
    """

    placeholders = DATE_PLACEHOLDER_PATTERN.findall(text)

    if len(placeholders) != len(dates):
        raise ValueError(
            f"Reference contains {len(placeholders)} date placeholders but "
            f"received {len(dates)} dates"
        )

    formatted_dates = iter(
        convert_iranian_date(
            month=date.month,
            day=date.day,
            year=date.year,
        )
        for date in dates
    )

    return DATE_PLACEHOLDER_PATTERN.sub(
        lambda _: next(formatted_dates),
        text,
    )
