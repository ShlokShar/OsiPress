from datetime import date, datetime, timedelta, timezone
from typing import Optional

import flask


from shared.countries import (
    COUNTRIES,
    LIVE_COUNTRY_KEYS,
    outlet_native_name,
    outlet_position,
    position_label,
)
from shared.models import (
    get_archive_daily_counts,
    get_archive_events,
    get_day_articles,
    get_edition_count,
    get_event_by_id,
    get_events_for_day,
    get_headlines_by_country,
    get_latest_headline_by_outlet,
    get_outlets_by_country,
    get_topic_names,
    get_sources_by_ids,
)
from shared.search_helpers import get_search_service
from shared.presenters import (
    all_today_view,
    globe_events,
    country_view,
    ticks,
    archive_view,
    search_view,
    compare_columns,
    country_picker,
    day_line,
    event_detail_view,
    spectrum_explorer,
    switch_options,
    ticker_items,
    today_view,
)


app = flask.Flask(__name__)


@app.context_processor
def footer_context():
    return {"current_year": datetime.now(timezone.utc).year}

MAX_FALLBACK_DAYS = 3
ARCHIVE_MIN_DATE = date(2026, 7, 9)
MAX_COMPARE_COUNTRIES = 3
DEFAULT_COMPARE = list(LIVE_COUNTRY_KEYS)[:2]

STORY_OPTIONS = (("top", "Top stories"), ("all", "All today"))
RANGE_OPTIONS = (
    ("30", "Last 30 days"),
    ("90", "Last 90 days"),
    ("all", "Since launch"),
)
ARCHIVE_START_LABEL_LONG = "9 July 2026"
SORT_OPTIONS = (("relevance", "Most relevant"), ("new", "Newest first"), ("old", "Oldest first"))
MAX_QUERY = 200
VIEW_OPTIONS = (("spectrum", "Spectrum"), ("compare", "Compare countries"))
EVENT_VIEW_OPTIONS = (
    ("spectrum", "All countries"),
    ("compare", "Compare countries"),
)


def _picked_countries() -> list[str]:
    """Read the compare selection from the URL, keeping it shareable."""

    raw = flask.request.args.get("countries") or ""
    picked = [key for key in raw.split(",") if key in COUNTRIES]
    deduplicated = list(dict.fromkeys(picked))
    return deduplicated[:MAX_COMPARE_COUNTRIES] or list(DEFAULT_COMPARE)


def _archive_date(name: str, today: date) -> Optional[date]:
    """Read one end of the archive's date range, ignoring junk and outliers."""

    raw = flask.request.args.get(name)
    if not raw:
        return None
    try:
        picked = date.fromisoformat(raw)
    except ValueError:
        return None
    return min(max(picked, ARCHIVE_MIN_DATE), today)


def _one_of(name: str, options: tuple, default: str) -> str:
    value = flask.request.args.get(name)
    allowed = {value for value, _ in options}
    return value if value in allowed else default


@app.route("/")
def home():
    _, events = get_events_for_day(fallback_days=MAX_FALLBACK_DAYS)
    globe = globe_events(today_view(events)["all_events"])

    day, rows = get_day_articles(fallback_days=MAX_FALLBACK_DAYS)

    spectrum = flask.request.args.get("spectrum")
    if spectrum not in COUNTRIES:
        spectrum = DEFAULT_COMPARE[0]

    return flask.render_template(
        "home.html",
        nav_current=None,
        globe=globe,
        ticker=ticker_items(rows),
        explorer=spectrum_explorer(
            get_outlets_by_country(),
            get_latest_headline_by_outlet(fallback_days=MAX_FALLBACK_DAYS),
            spectrum,
        ),
        globe_data={
            "events": [
                {
                    "number": event["number"],
                    "title": event["title"],
                    "countries": [
                        {
                            "key": country["key"],
                            "name": country["name"],
                            "atlas_id": country["atlas_id"],
                            "capital": country["capital"],
                        }
                        for country in event["countries"]
                    ],
                }
                for event in globe
            ],
            "live": [
                COUNTRIES[key]["atlas_id"] for key in LIVE_COUNTRY_KEYS
            ],
            "next": [
                country["atlas_id"]
                for country in COUNTRIES.values()
                if country["status"] != "live"
            ],
        },
    )


@app.route("/today")
def today():
    view = _one_of("view", VIEW_OPTIONS, "spectrum")
    stories = _one_of("stories", STORY_OPTIONS, "top")
    countries = _picked_countries()

    day, events = get_events_for_day(fallback_days=MAX_FALLBACK_DAYS)
    ranked = today_view(events)
    lead = ranked["lead"]

    all_today = []
    if stories == "all":
        day_for_articles, rows = get_day_articles(
            fallback_days=MAX_FALLBACK_DAYS
        )
        day = day_for_articles
        all_today = all_today_view(rows)

    lead_columns = compare_columns(lead, countries) if lead else []
    covered = {column["key"] for column in lead_columns}
    lead_missing = [
        {"text": f"No coverage from {COUNTRIES[key]['name']} for this event."}
        for key in countries
        if key not in covered
    ]

    return flask.render_template(
        "today.html",
        nav_current="today",
        day_line=day_line(day),
        view=view,
        stories=stories,
        countries=countries,
        countries_param=",".join(countries),
        view_switch=switch_options(view, VIEW_OPTIONS),
        story_switch=switch_options(stories, STORY_OPTIONS),
        picker=country_picker(countries, MAX_COMPARE_COUNTRIES),
        lead=lead,
        lead_columns=lead_columns,
        lead_missing=lead_missing,
        events=ranked["events"],
        all_today=all_today,
    )


@app.route("/event/<int:event_id>")
def event(event_id: int):
    record = get_event_by_id(event_id)
    if not record:
        flask.abort(404)

    view = _one_of("view", EVENT_VIEW_OPTIONS, "spectrum")
    countries = _picked_countries()
    detail = event_detail_view(record)
    columns = compare_columns(detail, countries)
    covered = {column["key"] for column in columns}

    return flask.render_template(
        "event.html",
        nav_current="today",
        view=view,
        countries=countries,
        countries_param=",".join(countries),
        view_switch=switch_options(view, EVENT_VIEW_OPTIONS),
        picker=country_picker(
            countries,
            MAX_COMPARE_COUNTRIES,
            available=detail["country_keys"],
        ),
        event=detail,
        columns=columns,
        missing=[
            {"text": (
                f"No coverage from {COUNTRIES[key]['name']} for this event."
            )}
            for key in countries
            if key not in covered
        ],
    )


@app.route("/all-today")
def all_today():
    today_utc = datetime.now(timezone.utc).date()
    shown_date = today_utc
    data = get_headlines_by_country(shown_date)

    offset = 1
    while not data and offset <= MAX_FALLBACK_DAYS:
        shown_date = today_utc - timedelta(days=offset)
        data = get_headlines_by_country(shown_date)
        offset += 1

    return flask.render_template(
        "index.html",
        data=data,
        shown_date=shown_date,
        is_today=(shown_date == today_utc),
    )


@app.route("/about")
def about():
    outlets = get_outlets_by_country()

    countries = []
    for key, meta in COUNTRIES.items():
        entries = [
            {
                "name": entry["outlet"],
                "native": outlet_native_name(entry["outlet"]),
                "position": outlet_position(entry["outlet"], entry["leaning"]),
            }
            for entry in outlets.get(meta["name"], [])
        ]
        for entry in entries:
            entry["position_label"] = position_label(key, entry["position"])
            entry["ticks"] = ticks(entry["position"])
        entries.sort(key=lambda entry: (entry["position"], entry["name"]))
        countries.append({**country_view(key), "outlets": entries})

    return flask.render_template(
        "about.html", nav_current="about", countries=countries
    )


@app.route("/archive")
def archive():
    today_utc = datetime.now(timezone.utc).date()
    countries = _picked_countries()
    range_key = _one_of("range", RANGE_OPTIONS, "30")
    topic = flask.request.args.get("topic") or None

    picked_from = _archive_date("from", today_utc)
    picked_to = _archive_date("to", today_utc)
    custom_range = bool(picked_from or picked_to)

    if custom_range:
        start = picked_from or ARCHIVE_MIN_DATE
        end = picked_to or today_utc
        if start > end:
            start, end = end, start
    else:
        end = today_utc
        start = ARCHIVE_MIN_DATE
        if range_key in ("30", "90"):
            start = max(
                ARCHIVE_MIN_DATE, end - timedelta(days=int(range_key) - 1)
            )

    days = [
        start + timedelta(days=offset)
        for offset in range((end - start).days + 1)
    ]

    selected_day = flask.request.args.get("day")
    if selected_day not in {day.isoformat() for day in days}:
        selected_day = None

    date_args = {}
    if custom_range:
        date_args = {"from": start.isoformat(), "to": end.isoformat()}

    return flask.render_template(
        "archive.html",
        nav_current="archive",
        launch_label=ARCHIVE_START_LABEL_LONG,
        countries=countries,
        countries_param=",".join(countries),
        range_key=range_key,
        topic=topic,
        range_from=start.isoformat() if custom_range else "",
        range_to=end.isoformat() if custom_range else "",
        min_date=ARCHIVE_MIN_DATE.isoformat(),
        max_date=today_utc.isoformat(),
        custom_range=custom_range,
        date_args=date_args,
        picker=country_picker(countries, MAX_COMPARE_COUNTRIES),
        range_switch=switch_options(range_key, RANGE_OPTIONS),
        archive=archive_view(
            days,
            get_archive_daily_counts(start, end),
            get_archive_events(start, end),
            get_edition_count(start, end),
            countries,
            topic,
            selected_day,
        ),
    )


@app.route("/archive/edition/<day>")
def archive_edition(day):
    try:
        selected = date.fromisoformat(day)
    except ValueError:
        flask.abort(404)
    if not ARCHIVE_MIN_DATE <= selected <= datetime.now(timezone.utc).date():
        flask.abort(404)
    return flask.render_template(
        "index.html",
        data=get_headlines_by_country(selected),
        shown_date=selected,
        is_today=False,
    )


@app.route("/search")
def search():
    query = (flask.request.args.get("q") or "").strip()
    countries = _picked_countries()
    sort = _one_of("sort", SORT_OPTIONS, "relevance")

    context = {
        "nav_current": "search",
        "query": query,
        "countries": countries,
        "countries_param": ",".join(countries),
        "sort": sort,
        "launch_label": ARCHIVE_START_LABEL_LONG,
        "picker": country_picker(countries, MAX_COMPARE_COUNTRIES),
        "sort_switch": switch_options(sort, SORT_OPTIONS),
        "suggestions": get_topic_names()[:6],
        "search": None,
    }

    if not query:
        return flask.render_template("search.html", state="empty", **context)
    if len(query) > MAX_QUERY:
        return flask.render_template("search.html", state="too_long", **context)

    try:
        ranked = get_search_service().hybrid_search(query)
        sources = get_sources_by_ids([article.source_id for _, article in ranked])
        rows = [
            {
                "article_id": article.id,
                "country": sources.get(article.source_id, {}).get("country", ""),
                "outlet": sources.get(article.source_id, {}).get("outlet", "Unknown outlet"),
                "outlet_id": article.source_id,
                "leaning": sources.get(article.source_id, {}).get("political_leaning", ""),
                "headline": article.headline,
                "translated_headline": article.translated_headline,
                "link": article.link,
                "published_at": article.published_at,
                "captured_at": article.captured_at,
            }
            for _, article in ranked
        ]
    except Exception:
        app.logger.exception("Search failed for query %r", query)
        return flask.render_template("search.html", state="error", **context)

    context["search"] = search_view(
        query, rows, get_outlets_by_country(), countries, sort
    )
    if not context["search"]["has_results"]:
        return flask.render_template("search.html", state="none", **context)

    return flask.render_template("search.html", state="results", **context)


if __name__ == '__main__':
    app.run(debug=False)
