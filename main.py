
import re
from datetime import date, datetime, timedelta, timezone
from functools import cache
from itertools import zip_longest
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
