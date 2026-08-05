
from persiantools.jdatetime import JalaliDate

from cron.ai.schemas import IranianDate


def convert_iranian_date(year: int, month: int, day: int) -> str:
    """
    Converts a date from the Iranian calendar to the Gregorian calendar.

    :param year: the Solar Hijri year
    :param month: the Solar Hijri month, from 1 through 12
    :param day: the day of the Solar Hijri month
    :return: the Gregorian date formatted as MM DD, YYYY
    """
    iranian_date = JalaliDate(year, month, day)
    return iranian_date.to_gregorian().strftime("%B %-d, %Y")


def handle_iranian_date(dates: list[IranianDate], text: str) -> str:
    """
    Replaces ordered DATE_0, DATE_1, and subsequent placeholders with their
    Gregorian equivalents.

    :param dates: a list of Solar Hijri dates ordered to match the placeholders
    :param text: the translated text containing the date placeholders
    :return: the text with each placeholder replaced by its Gregorian date
    """

    if len(dates) < 1:
        return text

    for i, date in enumerate(dates):
        date_year, date_month, date_day = date.year, date.month, date.day
        gregorian_date = convert_iranian_date(
            date_year,
            date_month,
            date_day
        )

        text = text.replace(
            f"DATE_{i}",
            gregorian_date
        )

    return text