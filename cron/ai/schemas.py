
from pydantic import (
    BaseModel,
    Field
)

from cron.ai.tags import ALLOWED_TAGS


class IranianDate(BaseModel):
    year: int = Field(description="the date's year in the Persian Calendar.")
    month: int = Field(description="the date's month in the Persian Calendar.")
    day: int = Field(description="the date's day in the Persian Calendar.")


class DateModel(BaseModel):
    dates: list[IranianDate] = Field(
        description=(
            "Solar Hijri dates mentioned in the article, ordered to match "
            "DATE_0, DATE_1, and subsequent placeholders."
        )
    )


class HeadlineClassifier(BaseModel):
    political: bool = Field(description="whether a headline is political")


class Parsed(DateModel):
    references: list[str] = Field(
        description="a list of quotes from the article that are used for the summary"
    )
    references_for_translation: list[str] = Field(
        description=(
            "Copies of the references in the same order, with complete Solar "
            "Hijri dates replaced by placeholders for translation. "
            "Placeholder numbering restarts at DATE_0 in each reference."
        )
    )
    references_dates: list[list[IranianDate]] = Field(
        description=(
            "One date list per item in references_for_translation. Each inner "
            "list is ordered to match that reference's DATE_0, DATE_1, and "
            "subsequent placeholders."
        )
    )
    tags: list[ALLOWED_TAGS] = Field(
        description="a list of tags from the article"
    )
    summary: str = Field(description="Summary of the article")


class TranslatedHeadline(DateModel):
    translated_headline: str = Field(
        description="headline translated verbatim to English"
    )
