
from datetime import date, datetime, timedelta, timezone

import flask

from shared.models import (
    get_visible_events,
    get_headlines_by_country,
    get_sources_by_ids
)
from shared.search_helpers import (
    ARCHIVE_START_LABEL,
    build_result,
    get_search_service
)

app = flask.Flask(__name__)

MAX_FALLBACK_DAYS = 3
ARCHIVE_MIN_DATE = date(2026, 7, 9)

@app.route("/")
def all_today():
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

@app.route("/today")
def today():
    return flask.render_template("events.html", events=get_visible_events())


@app.route("/about")
def about():
    return flask.render_template("landing.html")


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

@app.route("/search")
def search():
    query = (flask.request.args.get("q") or "").strip()

    context = {
        "query": query,
        "archive_start": ARCHIVE_START_LABEL,
        "results": [],
        "total": 0,
        "suggestions": [],
    }

    if not query:
        return flask.render_template("search.html", state="empty", **context)
    if len(query) > 200:
        return flask.render_template("search.html", state="error", **context)

    try:
        ranked = get_search_service().hybrid_search(query)
    except Exception:
        app.logger.exception("Search failed for query %r", query)
        return flask.render_template(
            "search.html", state="error", error_ref="SRCH-500", **context
        )

    if not ranked:
        return flask.render_template("search.html", state="none", **context)

    sources = get_sources_by_ids([article.source_id for _, article in ranked])

    context["results"] = [
        build_result(rank, article, sources) for rank, article in ranked
    ]

    return flask.render_template("search.html", state="results", **context)


if __name__ == '__main__':
    app.run(debug=False)
