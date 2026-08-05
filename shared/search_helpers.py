
import re
from functools import cache
from itertools import zip_longest
from urllib.parse import urlparse

from shared.models import Articles
from shared.search_service import SearchService


ARCHIVE_START_LABEL = "March 2026"
SEARCH_PAGE_SIZE = 6

LEANING_CLASSES = (
    ("left", "left"),
    ("right", "right"),
    ("center", "center"),
    ("centre", "center"),
)

APOLOGY = re.compile(
    r"^(i can'?t|no content|the provided article content is empty)",
    re.IGNORECASE
)


@cache
def get_search_service() -> SearchService:
    return SearchService()


def leaning_class(political_leaning: str) -> str:
    label = (political_leaning or "").lower()
    for needle, class_name in LEANING_CLASSES:
        if needle in label:
            return class_name
    return "unknown"


def clean_summary(summary: str) -> str:
    text = (summary or "").strip()
    return "" if not text or APOLOGY.match(text) else text


def source_domain(link: str) -> str:
    try:
        hostname = urlparse(link or "").hostname or ""
    except ValueError:
        return "source"

    return hostname.removeprefix("www.") or "source"


def build_quotes(article: Articles) -> list[dict[str, str]]:
    translated = list(article.references_translated or [])
    original = list(article.references_original or [])
    if translated == original:
        original = []

    return [
        {"translated": translated_quote, "original": original_quote}
        for translated_quote, original_quote in zip_longest(
            translated, original, fillvalue=""
        )
        if translated_quote or original_quote
    ]


def build_result(rank: int, article: Articles,
                 sources: dict[int, dict[str, str]]) -> dict:
    source = sources.get(article.source_id, {})
    headline = (article.headline or "").strip()
    translated_headline = (article.translated_headline or "").strip()

    return {
        "rank": rank,
        "outlet": source.get("outlet") or "Unknown outlet",
        "country": source.get("country") or "",
        "leaning": source.get("political_leaning") or "",
        "leaning_class": leaning_class(source.get("political_leaning")),
        "published": (article.captured_at.strftime("%d %b %Y")
                      if article.captured_at else ""),
        "title": translated_headline or headline,
        "title_original": headline if headline != translated_headline else "",
        "summary": clean_summary(article.summary),
        "tags": list(article.tags or []),
        "link": article.link,
        "domain": source_domain(article.link),
        "quotes": build_quotes(article),
    }
