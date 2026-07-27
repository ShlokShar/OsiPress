
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import flask

from shared.models import (
    Countries,
    Sources,
    Articles,
    get_headlines_by_country,
    get_sources_by_ids
)
from shared.search_service import SearchService

app = flask.Flask(__name__)

MAX_FALLBACK_DAYS = 3


VISITED_COOKIE = "visited"

@app.route("/")
def landing():
    # First-time visitors see the landing page; returning visitors (who already
    # carry the cookie) are sent straight to today's edition.
    if flask.request.cookies.get(VISITED_COOKIE):
        return flask.redirect(flask.url_for("today"))

    response = flask.make_response(flask.render_template("landing.html"))
    response.set_cookie(
        VISITED_COOKIE, "1",
        max_age=60 * 60 * 24 * 365,  # remember for a year
        samesite="Lax",
    )
    return response

@app.route("/today")
def today():
    today = datetime.now(timezone.utc).date()
    shown_date = today
    data = get_headlines_by_country(shown_date)

    offset = 1
    while not data and offset <= MAX_FALLBACK_DAYS:
        shown_date = today - timedelta(days=offset)
        data = get_headlines_by_country(shown_date)
        offset += 1

    return flask.render_template(
        "index.html",
        data=data,
        shown_date=shown_date,
        is_today=(shown_date == today),
    )


ARCHIVE_MIN_DATE = date(2026, 7, 9)

@app.route("/archive")
def archive():
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    shown_date = yesterday
    date_param = flask.request.args.get("date")
    if date_param:
        try:
            parsed = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            parsed = None
        if parsed and ARCHIVE_MIN_DATE <= parsed <= yesterday:
            shown_date = parsed

    data = get_headlines_by_country(shown_date)
    return flask.render_template(
        "archive.html",
        data=data,
        date=shown_date.isoformat(),
        min_date=ARCHIVE_MIN_DATE.isoformat(),
    )

ARCHIVE_START_LABEL = "March 2026"
SEARCH_PAGE_SIZE = 6

# Mirrors normalizeLean() in static/js/osipress.js so a leaning renders with
# the same .tag colour here as it does on the today and archive boards.
LEANING_CLASSES = (
    ("left", "left"),
    ("right", "right"),
    ("center", "center"),
    ("centre", "center"),
)

# Summaries occasionally come back as a model apology rather than a summary.
# Same guard as cleanSummary() in static/js/osipress.js.
APOLOGY = re.compile(
    r"^(i can'?t|no content|the provided article content is empty)",
    re.IGNORECASE
)

_search_service = None


def get_search_service() -> SearchService:
    """
    Returns the shared search service, building it on first use so that a
    missing embedding credential fails on request rather than at import.

    :return: the search service
    """

    global _search_service
    if _search_service is None:
        _search_service = SearchService()
    return _search_service


def leaning_class(political_leaning: str) -> str:
    """
    Maps a political leaning onto one of the .tag classes in the stylesheet.

    :param political_leaning: the leaning as stored on the source
    :return: the matching tag class name
    """

    label = (political_leaning or "").lower()
    for needle, class_name in LEANING_CLASSES:
        if needle in label:
            return class_name
    return "unknown"


def clean_summary(summary: str) -> str:
    """
    Drops summaries that are a refusal rather than a description.

    :param summary: the stored article summary
    :return: the summary, or an empty string if it is unusable
    """

    text = (summary or "").strip()
    return "" if not text or APOLOGY.match(text) else text


def source_domain(link: str) -> str:
    """
    Extracts the display domain from an article link.

    :param link: the article's source url
    :return: the hostname without a www prefix
    """

    try:
        hostname = urlparse(link or "").hostname or ""
    except ValueError:
        return "source"

    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname or "source"


def build_quotes(article: Articles) -> list[dict[str, str]]:
    """
    Pairs each translated quotation with its original by position. Where the
    two arrays are identical the translation added nothing, so the original
    is dropped to avoid printing the same line twice.

    :param article: the article holding the quotation arrays
    :return: the quotations as translated and original pairs
    """

    translated = list(article.references_translated or [])
    original = list(article.references_original or [])
    identical = translated == original

    quotes = []
    for index in range(max(len(translated), len(original))):
        quote = {
            "translated": translated[index] if index < len(translated) else "",
            "original": original[index] if index < len(original) else "",
        }
        if identical:
            quote["original"] = ""
        if quote["translated"] or quote["original"]:
            quotes.append(quote)

    return quotes


def build_result(rank: int, article: Articles,
                 sources: dict[int, dict[str, str]]) -> dict:
    """
    Maps a ranked search hit onto the shape search.html renders.

    :param rank: the article's position in the ranked results
    :param article: the matching article
    :param sources: the outlet details keyed by source id
    :return: a single renderable search result
    """

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


@app.route("/search")
def search():
    query = (flask.request.args.get("q") or "").strip()

    context = {
        "query": query,
        "archive_start": ARCHIVE_START_LABEL,
        "results": [],
        "total": 0,
        "suggestions": [],
        "next_limit": SEARCH_PAGE_SIZE,
    }

    if not query:
        return flask.render_template("search.html", state="empty", **context)

    try:
        ranked = get_search_service().hybrid_search(query)
    except Exception:
        app.logger.exception("Search failed for query %r", query)
        return flask.render_template(
            "search.html", state="error", error_ref="SRCH-500", **context
        )

    if not ranked:
        return flask.render_template("search.html", state="none", **context)

    limit = flask.request.args.get("limit", type=int) or SEARCH_PAGE_SIZE
    limit = max(1, min(limit, len(ranked)))

    sources = get_sources_by_ids([article.source_id for _, article in ranked])

    context["results"] = [
        build_result(rank, article, sources) for rank, article in ranked[:limit]
    ]
    context["total"] = len(ranked)
    context["next_limit"] = min(limit + SEARCH_PAGE_SIZE, len(ranked))

    return flask.render_template("search.html", state="results", **context)


if __name__ == '__main__':
    app.run(debug=False)