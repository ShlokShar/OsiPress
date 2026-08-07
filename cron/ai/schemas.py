
from pydantic import (
    BaseModel,
    Field
)

from cron.ai.tags import ALLOWED_TAGS


class IranianDate(BaseModel):
    year: int = Field(
        ge=1,
        description="Solar Hijri year from a complete date.",
    )
    month: int = Field(
        ge=1,
        le=12,
        description="Numeric Solar Hijri month from 1 through 12.",
    )
    day: int = Field(
        ge=1,
        le=31,
        description="Day from a complete Solar Hijri date.",
    )


class DateModel(BaseModel):
    dates: list[IranianDate] = Field(
        description=(
            "Only Solar Hijri dates whose year, month, and day are explicitly "
            "present in one non-range expression; never infer a component. "
            "Ordered to match DATE_0, DATE_1, and subsequent placeholders."
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
            "One list per translated reference containing only complete, "
            "non-range Solar Hijri dates with three explicit components. Each "
            "inner list matches that reference's ordered placeholders."
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
