"""View models for the redesigned pages.

The designs in `osipress-design/pages` compute a specific shape for every
block: an article carries its outlet in both scripts, a local time, a 1-5
position with its label and a five-tick marker; a country carries its axis,
its five position bins and a coverage bar; an event carries its countries and
a count line. These builders produce that shape from the database rows so the
templates stay declarative.

Two values the backend does not store yet are derived here, and this is where
they should be replaced:

* a subhead, taken from the article's stored reference lines or its summary;
* an edition label, taken from the hour an ingestion run started.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from shared.countries import (
    COUNTRIES,
    LIVE_COUNTRY_KEYS,
    country_key,
    outlet_native_name,
    outlet_position,
    position_label,
)

POSITIONS = (1, 2, 3, 4, 5)
SUBHEAD_LIMIT = 150


def plural(count: int, word: str) -> str:
    """Return "1 article" or "2 articles", including for "country"."""

    if count == 1:
        return f"{count} {word}"
    if word == "country":
        return f"{count} countries"
    return f"{count} {word}s"


def country_view(key: str) -> dict:
    """Return a country's axis and identity for the templates."""

    country = COUNTRIES[key]
    return {
        "key": key,
        "name": country["name"],
        "native": country["native_name"],
        "lang": country["lang"],
        "dir": country["dir"],
        "colour": country["colour"],
        "chart_colour": country["chart_colour"],
        "left_label": country["axis_left_label"],
        "right_label": country["axis_right_label"],
        "labels": list(country["position_labels"]),
        "status": country["status"],
        "is_live": country["status"] == "live",
        "atlas_id": country["atlas_id"],
        "capital": list(country["capital"]),
        "city": country["city"],
    }


def live_countries() -> list[dict]:
    return [country_view(key) for key in LIVE_COUNTRY_KEYS]


def all_countries() -> list[dict]:
    return [country_view(key) for key in COUNTRIES]


def ticks(position: int) -> list[dict]:
    """Return the five-tick position marker."""

    return [{"on": slot == position, "off": slot != position}
            for slot in POSITIONS]


def local_time(published_at: Optional[datetime], key: str) -> str:
    """Return "06:40 Tehran", or the design's undated label."""

    if not published_at:
        return "Time not published"
    country = COUNTRIES[key]
    moment = published_at
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(ZoneInfo(country["timezone"]))
    return f"{local:%H:%M} {country['city']}"


def _subhead(row: dict) -> tuple[str, str]:
    """Return an (original, English) subhead for a row.

    Placeholder: the schema has no subhead column, so the stored reference
    lines stand in for one. Articles without them show no subhead, which is
    how the designs read: the second line is an editorial extra, not a
    summary printed under every headline.
    """

    original = (row.get("references_original") or [""])[0] or ""
    english = (row.get("references_translated") or [""])[0] or ""
    if len(english) > SUBHEAD_LIMIT:
        english = english[:SUBHEAD_LIMIT].rstrip() + "…"
    return original.strip(), english.strip()


def _sort_key(row: dict):
    """Newest first, with undated articles last."""

    published = row.get("published_at")
    return (0 if published else 1, -(published.timestamp() if published else 0))


def article_view(row: dict, key: str) -> dict:
    """Return one article in the shape every page renders it."""

    position = outlet_position(row["outlet"], row.get("leaning", ""))
    country = COUNTRIES[key]
    sub_original, sub_english = _subhead(row)

    return {
        "id": row.get("article_id"),
        "outlet": row["outlet"],
        "outlet_id": row.get("outlet_id"),
        "outlet_native": outlet_native_name(row["outlet"]),
        "lang": country["lang"],
        "dir": country["dir"],
        "time": local_time(row.get("published_at"), key),
        "published_at": row.get("published_at"),
        "english": row.get("translated_headline") or row.get("headline") or "",
        "original": row.get("headline") or "",
        "sub_original": sub_original,
        "sub_english": sub_english,
        "has_sub": bool(sub_english),
        "position": position,
        "position_label": position_label(key, position),
        "ticks": ticks(position),
        "link": row.get("link") or "",
        "event_title": row.get("event_title"),
        "latest_run": row.get("latest_run", False),
    }


def outlet_views(rows: Iterable[dict], key: str) -> list[dict]:
    """Group a country's articles by outlet, ordered along its axis.

    Each outlet keeps every article, newest first, and `pick` is the one the
    overview shows, carrying a "+N earlier" label for the rest.
    """

    by_outlet: defaultdict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_outlet[row["outlet"]].append(row)

    outlets = []
    for name, outlet_rows in by_outlet.items():
        ordered = sorted(outlet_rows, key=_sort_key)
        articles = [article_view(row, key) for row in ordered]
        for index, article in enumerate(articles):
            article["latest"] = index == 0 and len(articles) > 1
        newest = articles[0]
        more = len(articles) - 1

        outlets.append({
            "name": name,
            "native": newest["outlet_native"],
            "lang": newest["lang"],
            "dir": newest["dir"],
            "position": newest["position"],
            "position_label": newest["position_label"],
            "ticks": newest["ticks"],
            "count": len(articles),
            "count_label": plural(len(articles), "article"),
            "articles": articles,
            "pick": {
                **newest,
                "more": more,
                "has_more": more > 0,
                "more_label": f"+{more} earlier",
            },
        })

    return sorted(outlets, key=lambda outlet: (outlet["position"], outlet["name"]))


def country_block(key: str, rows: Iterable[dict]) -> dict:
    """Return one country's coverage of an event: bins, outlets, coverage."""

    rows = list(rows)
    outlets = outlet_views(rows, key)
    picks = [outlet["pick"] for outlet in outlets]
    country = country_view(key)

    bins = []
    for position in POSITIONS:
        items = [pick for pick in picks if pick["position"] == position]
        bins.append({
            "position": position,
            "label": country["labels"][position - 1],
            "items": items,
            "has": bool(items),
            "empty": not items,
        })

    return {
        **country,
        "articles": picks,
        "outlets": outlets,
        "bins": bins,
        "coverage": [{"on": slot["has"], "off": slot["empty"]} for slot in bins],
        "count": len(rows),
        "outlet_count": len(outlets),
        "count_label": (
            f"{plural(len(rows), 'article')}, "
            f"{plural(len(outlets), 'outlet')}"
        ),
        "anchor": f"country-{key}",
    }


def event_view(event: dict, keys: Optional[Iterable[str]] = None) -> dict:
    """Return an event with a country block for each covering country."""

    by_country: defaultdict[str, list[dict]] = defaultdict(list)
    for row in event["articles"]:
        key = country_key(row["country"])
        if key:
            by_country[key].append(row)

    wanted = list(keys) if keys is not None else list(COUNTRIES)
    blocks = [
        country_block(key, by_country[key])
        for key in wanted
        if by_country.get(key)
    ]

    total = sum(block["count"] for block in blocks)
    outlets = sum(block["outlet_count"] for block in blocks)

    return {
        "id": event["id"],
        "title": event["title"],
        "topic": event.get("topic"),
        "href": f"/event/{event['id']}",
        "countries": blocks,
        "country_keys": [block["key"] for block in blocks],
        "total": total,
        "outlet_count": outlets,
        "country_count": len(blocks),
        "last_seen": event.get("last_seen"),
        "first_published_at": event.get("first_published_at"),
        "meta": (
            f"{plural(total, 'article')} from {plural(outlets, 'outlet')} "
            f"in {plural(len(blocks), 'country')}"
        ),
        "view_all": f"View all {plural(total, 'article')} →",
        "missing": [],
    }


def _breadth_key(view: dict):
    """Coverage breadth: most countries, then most outlets, then newest."""

    last_seen = view.get("last_seen")
    return (
        view["country_count"],
        view["outlet_count"],
        last_seen.timestamp() if last_seen else 0,
    )


def today_view(events: Iterable[dict]) -> dict:
    """Rank a day's events by breadth and choose the featured lead.

    The lead treatment only applies when the top event clearly leads: it
    covers at least two countries and has more outlets than the next event.
    """

    views = sorted(
        (event_view(event) for event in events),
        key=_breadth_key,
        reverse=True,
    )
    if not views:
        return {"lead": None, "events": [], "all_events": []}

    lead, rest = views[0], views[1:]
    clearly_leads = lead["country_count"] >= 2 and (
        not rest or lead["outlet_count"] > rest[0]["outlet_count"]
    )

    return {
        "lead": lead if clearly_leads else None,
        "events": rest if clearly_leads else views,
        "all_events": views,
    }


def compare_columns(view: dict, keys: Iterable[str]) -> list[dict]:
    """Return an event's countries as compare columns, in the picked order.

    Columns are never aligned position to position across countries, because
    each country's axis means something different.
    """

    blocks = {block["key"]: block for block in view["countries"]}
    return [blocks[key] for key in keys if key in blocks]


def country_picker(
    selected: Iterable[str],
    limit: int = 3,
    available: Optional[Iterable[str]] = None,
) -> dict:
    """Return the country buttons for the compare picker."""

    selected = list(selected)
    available = set(available) if available is not None else None
    full = len(selected) >= limit

    buttons = []
    for key, country in COUNTRIES.items():
        live = country["status"] == "live"
        on = key in selected
        present = available is None or key in available
        buttons.append({
            "key": key,
            "name": country["name"],
            "native": country["native_name"],
            "colour": country["colour"],
            "on": on,
            "off": not on,
            "soon": not live,
            "disabled": not live or not present or (full and not on),
        })

    hint = (
        f"Pick up to {limit} countries"
        if not full
        else f"{limit} countries picked. Unpick one to swap."
    )
    return {"buttons": buttons, "selected": selected, "hint": hint}


def event_detail_view(event: dict, keys: Optional[Iterable[str]] = None) -> dict:
    """Return an event detail page's view model."""

    view = event_view(event, keys)
    view["jump"] = [
        {
            "key": block["key"],
            "name": block["name"],
            "native": block["native"],
            "colour": block["colour"],
            "anchor": f"#{block['anchor']}",
            "count": block["count"],
            "count_label": plural(block["count"], "article"),
        }
        for block in view["countries"]
    ]
    view["grouping_note"] = "Grouped by country, then outlet, newest first."
    return view


def mobile_event_view(view: dict, keys: Iterable[str]) -> dict:
    """Add the mobile "No coverage from X" lines for the picked countries."""

    keys = list(keys)
    present = {block["key"] for block in view["countries"]}
    shown = [block for block in view["countries"] if block["key"] in keys]
    missing = [
        {"key": key, "text": (
            f"No coverage from {COUNTRIES[key]['name']} for this event."
        )}
        for key in keys
        if key not in present
    ]
    return {**view, "shown": shown, "missing": missing}


def day_line(day) -> str:
    """Return "Wednesday 25 November 2026"."""

    return f"{day:%A %-d %B %Y}" if day else ""


def all_today_view(rows: Iterable[dict]) -> list[dict]:
    """Return every outlet's coverage for a day, grouped by country."""

    by_country: defaultdict[str, list[dict]] = defaultdict(list)
    for row in rows:
        key = country_key(row["country"])
        if key:
            by_country[key].append(row)

    return [
        country_block(key, by_country[key])
        for key in COUNTRIES
        if by_country.get(key)
    ]


def switch_options(current: str, options: Iterable[tuple[str, str]]) -> list[dict]:
    """Return segmented-control options with the current one pressed."""

    return [
        {"value": value, "name": name, "on": value == current}
        for value, name in options
    ]


def globe_events(views: Iterable[dict], limit: int = 4) -> list[dict]:
    """Return today's events as globe entries, keyed to the countries that
    covered them.

    An event has no location of its own in the schema, so the globe marks the
    countries whose outlets covered it rather than where the story happened.
    """

    events = []
    for index, view in enumerate(list(views)[:limit], start=1):
        blocks = [block for block in view["countries"] if block["articles"]]
        if not blocks:
            continue
        events.append({
            "number": index,
            "id": view["id"],
            "title": view["title"],
            "href": view["href"],
            "countries": [
                {
                    "key": block["key"],
                    "name": block["name"],
                    "colour": block["colour"],
                    "capital": block["capital"],
                    "atlas_id": block["atlas_id"],
                }
                for block in blocks
            ],
            "headlines": [
                {
                    "country": block["name"],
                    "colour": block["colour"],
                    "outlet": block["articles"][0]["outlet"],
                    "english": block["articles"][0]["english"],
                }
                for block in blocks
            ],
        })
    return events


def ticker_items(rows: Iterable[dict], limit: int = 8) -> list[dict]:
    """Return original-language headlines with their English underneath."""

    items = []
    for row in rows:
        key = country_key(row["country"])
        if not key:
            continue
        original = (row.get("headline") or "").strip()
        english = (row.get("translated_headline") or "").strip()
        if not original or original == english:
            continue
        country = COUNTRIES[key]
        items.append({
            "lang": country["lang"],
            "dir": country["dir"],
            "colour": country["colour"],
            "outlet": row["outlet"],
            "original": original,
            "english": english,
        })
        if len(items) >= limit:
            break
    return items


def _explorer_outlets(
    key: str,
    entries: Iterable[dict],
    latest_by_outlet: dict[int, dict],
) -> list[dict]:
    """Return one country's outlets placed along its axis."""

    outlets = []
    for outlet in entries:
        position = outlet_position(outlet["outlet"], outlet.get("leaning", ""))
        latest = latest_by_outlet.get(outlet["id"])
        outlets.append({
            "name": outlet["outlet"],
            "native": outlet_native_name(outlet["outlet"]),
            "position": position,
            "position_label": position_label(key, position),
            "offset": round((position - 1) / 4 * 100, 1),
            "english": (latest or {}).get("translated_headline", ""),
            "original": (latest or {}).get("headline", ""),
            "link": (latest or {}).get("link", ""),
            "has_today": bool(latest),
        })

    outlets.sort(key=lambda item: (item["position"], item["name"]))

    # Outlets sharing a position would sit on the same point of the axis, so
    # spread them inside their slot. A finer-grained lean would remove this.
    grouped: defaultdict[int, list[dict]] = defaultdict(list)
    for outlet in outlets:
        grouped[outlet["position"]].append(outlet)
    for group in grouped.values():
        size = len(group)
        if size == 1:
            continue
        half = min(6.0, 2.0 * size)
        base = group[0]["offset"]
        start, end = base - half, base + half
        if start < 2.0:
            start, end = 2.0, 2.0 + 2 * half
        if end > 98.0:
            start, end = 98.0 - 2 * half, 98.0
        step = (end - start) / (size - 1)
        for index, outlet in enumerate(group):
            outlet["offset"] = round(start + index * step, 1)

    for index, outlet in enumerate(outlets):
        outlet["above"] = index % 2 == 0

    return outlets


def spectrum_explorer(
    outlets_by_country: dict[str, list[dict]],
    latest_by_outlet: dict[int, dict],
    selected: str,
) -> dict:
    """Return the country tabs and every country's outlet axis.

    All panels are rendered so switching country is a local toggle rather
    than a page load, which would jump the reader down the page.
    """

    tabs = []
    panels = []
    for key, country in COUNTRIES.items():
        tabs.append({
            "key": key,
            "name": country["name"],
            "colour": country["colour"],
            "note": "" if country["status"] == "live" else "Coming next",
            "on": key == selected,
            "live": country["status"] == "live",
        })
        panels.append({
            **country_view(key),
            "on": key == selected,
            "outlets": _explorer_outlets(
                key,
                outlets_by_country.get(country["name"], []),
                latest_by_outlet,
            ),
        })

    return {"tabs": tabs, "panels": panels, "selected": selected}


CHART_HEIGHT = 96
SPIKE_FACTOR = 1.8


def archive_view(
    days: list,
    counts: dict,
    events: Iterable[dict],
    editions: int,
    keys: Iterable[str],
    topic: Optional[str],
    selected_day: Optional[str],
) -> dict:
    """Return the archive chart, topic list, day list and ranking.

    `counts` is keyed by (ISO day, country name); `days` is every day in the
    chosen range, oldest first.
    """

    keys = [key for key in keys if key in COUNTRIES]
    names = {key: COUNTRIES[key]["name"] for key in keys}

    events = [
        event for event in events
        if topic in (None, event.get("topic"))
    ]
    events_by_day: defaultdict[str, list[dict]] = defaultdict(list)
    for event in events:
        events_by_day[event["day"].isoformat()].append(event)

    totals = []
    for day in days:
        iso = day.isoformat()
        per_country = {
            key: counts.get((iso, names[key]), 0) for key in keys
        }
        totals.append(per_country)

    ceiling = max(
        [4] + [value for row in totals for value in row.values()]
    )
    average = (
        sum(value for row in totals for value in row.values())
        / max(1, len(totals))
    )

    chart = []
    spikes = []
    for index, day in enumerate(days):
        iso = day.isoformat()
        row = totals[index]
        total = sum(row.values())
        left = (index + 0.5) / max(1, len(days)) * 100
        chart.append({
            "iso": iso,
            "label": f"{day:%-d %b}",
            "long": f"{day:%A %-d %B}",
            "selected": iso == selected_day,
            "dim": bool(selected_day) and iso != selected_day,
            "bars": [
                {
                    "key": key,
                    "colour": COUNTRIES[key]["chart_colour"],
                    "count": row[key],
                    "height": round(row[key] / ceiling * CHART_HEIGHT),
                }
                for key in keys
            ],
            "total": total,
            "aria": f"{day:%A %-d %B}: " + ", ".join(
                f"{names[key]} {row[key]}" for key in keys
            ),
            "top": (
                max(
                    events_by_day.get(iso, []),
                    key=lambda event: len(event["articles"]),
                )["title"]
                if events_by_day.get(iso) else ""
            ),
            "more": max(0, len(events_by_day.get(iso, [])) - 1),
        })
        if total >= average * SPIKE_FACTOR and total >= 8:
            spikes.append({
                "left": round(left, 2),
                "shift": "-100%" if left > 70 else "0%" if left < 30 else "-50%",
                "label": chart[-1]["top"][:38] or f"{day:%-d %b}",
            })

    step = max(1, len(days) // 6)
    ticks = [
        {"left": round((index + 0.5) / max(1, len(days)) * 100, 2),
         "label": f"{day:%-d %b}" if len(days) <= 90 else f"{day:%b}"}
        for index, day in enumerate(days)
        if index % step == 0
    ]

    topic_totals: defaultdict[str, int] = defaultdict(int)
    for event in events:
        name = event.get("topic") or "Untagged"
        topic_totals[name] += sum(
            len(event["by_country"].get(names[key], [])) for key in keys
        )
    topic_ceiling = max([1] + list(topic_totals.values()))
    topics = sorted(
        (
            {
                "name": name,
                "count": count,
                "width": round(count / topic_ceiling * 100, 1),
                "on": name == topic,
            }
            for name, count in topic_totals.items()
        ),
        key=lambda item: -item["count"],
    )

    def article_total(event):
        return sum(
            len(event["by_country"].get(names[key], [])) for key in keys
        )

    unique_events = {}
    for event in events:
        item = unique_events.setdefault(event["id"], {
            **event, "articles": {}, "by_country": defaultdict(list),
        })
        item["day"] = max(item["day"], event["day"])
        for row in event["articles"]:
            item["articles"][row["article_id"]] = row
    for item in unique_events.values():
        for row in item["articles"].values():
            item["by_country"][row["country"]].append(row)

    ranked_events = sorted(unique_events.values(), key=article_total, reverse=True)[:5]
    rank_ceiling = max(
        [1] + [article_total(event) for event in ranked_events]
    )
    ranked = [
        {
            "number": index,
            "title": event["title"],
            "date": f"{event['day']:%-d %b}",
            "count": plural(article_total(event), "article"),
            "width": round(article_total(event) / rank_ceiling * 100, 1),
            "href": f"/event/{event['id']}",
        }
        for index, event in enumerate(ranked_events, start=1)
    ]

    if selected_day:
        listed = [day for day in days if day.isoformat() == selected_day]
    else:
        listed = list(reversed(days))[:4]

    list_days = []
    for day in listed:
        iso = day.isoformat()
        day_events = sorted(
            events_by_day.get(iso, []),
            key=article_total,
            reverse=True,
        )
        visible = [event for event in day_events if article_total(event)]
        article_count = sum(article_total(event) for event in visible)
        list_days.append({
            "iso": iso,
            "long": f"{day:%A %-d %B}",
            "day": f"{day:%-d}",
            "month": f"{day:%b}",
            "meta": (
                f"{plural(len(visible), 'event')}, "
                f"{plural(article_count, 'article')}"
            ),
            "empty": not visible,
            "events": [
                {
                    "title": event["title"],
                    "topic": event.get("topic"),
                    "href": f"/event/{event['id']}",
                    "rows": [
                        _coverage_row(event, key, names[key])
                        for key in keys
                    ],
                }
                for event in visible
            ],
        })

    article_grand_total = sum(
        value for row in totals for value in row.values()
    )
    return {
        "chart": chart,
        "ticks": ticks,
        "spikes": spikes,
        "ceiling": ceiling,
        "keys": keys,
        "stats": [
            {"big": str(len([e for e in unique_events.values() if article_total(e)])),
             "small": "events"},
            {"big": str(article_grand_total), "small": "article appearances"},
            {"big": str(editions), "small": "editions"},
        ],
        "topics": topics,
        "ranked": ranked,
        "list_days": list_days,
        "topic_name": topic or "All topics",
        "has_topic": topic is not None,
        "selected_day": selected_day,
        "selected_label": next(
            (row["long"] for row in chart if row["selected"]), ""
        ),
    }


def _coverage_row(event: dict, key: str, country_name: str) -> dict:
    """Return one country's strip for an event in the archive day list."""

    rows = event["by_country"].get(country_name, [])
    positions = {
        outlet_position(row["outlet"], row.get("leaning", ""))
        for row in rows
    }
    return {
        "key": key,
        "name": country_name,
        "colour": COUNTRIES[key]["chart_colour"],
        "count": plural(len(rows), "article") if rows else "Not covered",
        "has": bool(rows),
        "cells": [
            {"on": slot in positions, "off": slot not in positions}
            for slot in POSITIONS
        ],
    }


def _highlight(text: str, needle: str) -> list[dict]:
    """Split a headline into matched and unmatched parts for <mark>."""

    if not needle:
        return [{"text": text, "hit": False}]

    parts = []
    lowered, target = text.lower(), needle.lower()
    index = 0
    while True:
        found = lowered.find(target, index)
        if found == -1:
            break
        if found > index:
            parts.append({"text": text[index:found], "hit": False})
        parts.append({"text": text[found:found + len(target)], "hit": True})
        index = found + len(target)
    if index < len(text):
        parts.append({"text": text[index:], "hit": False})
    return parts or [{"text": text, "hit": False}]


def search_view(
    query: str,
    rows: Iterable[dict],
    outlets_by_country: dict[str, list[dict]],
    keys: Iterable[str],
    sort: str,
) -> dict:
    """Return the search results with their counts, months and spectrum."""

    keys = [key for key in keys if key in COUNTRIES]
    names = {COUNTRIES[key]["name"]: key for key in keys}

    matched = [row for row in rows if row["country"] in names]
    if sort in ("new", "old"):
        matched.sort(key=_sort_key, reverse=(sort == "old"))

    results = []
    for row in matched:
        key = names[row["country"]]
        article = article_view(row, key)
        english = article["english"]
        results.append({
            **article,
            "country": row["country"],
            "country_colour": COUNTRIES[key]["chart_colour"],
            "date": (
                f"{row['published_at']:%-d %b %Y}"
                if row.get("published_at") else "Date not published"
            ),
            "parts": _highlight(english, query),
            "event_title": row.get("event_title"),
        })

    dated = [row for row in matched if row.get("published_at")]
    outlet_total = len({row["outlet"] for row in matched})
    summary = (
        f"{plural(len(matched), 'article')} from "
        f"{plural(outlet_total, 'outlet')}"
    )
    if dated:
        first = min(row["published_at"] for row in dated)
        last = max(row["published_at"] for row in dated)
        summary += f", {first:%-d %b %Y} to {last:%-d %b %Y}"

    months: dict[str, dict] = {}
    for row in dated:
        stamp = row["published_at"].astimezone(timezone.utc)
        bucket = months.setdefault(
            f"{stamp:%Y-%m}",
            {"label": f"{stamp:%b}", "counts": {key: 0 for key in keys}},
        )
        bucket["counts"][names[row["country"]]] += 1

    ordered_months = [months[month] for month in sorted(months)]
    month_ceiling = max(
        [1] + [
            count
            for bucket in ordered_months
            for count in bucket["counts"].values()
        ]
    )
    timeline = [
        {
            "label": bucket["label"],
            "bars": [
                {
                    "key": key,
                    "colour": COUNTRIES[key]["chart_colour"],
                    "count": bucket["counts"][key],
                    "height": round(
                        bucket["counts"][key] / month_ceiling * 110
                    ),
                }
                for key in keys
            ],
        }
        for bucket in ordered_months
    ]

    hits: defaultdict[str, int] = defaultdict(int)
    for row in matched:
        hits[row["outlet"]] += 1

    spectrum = []
    for key in keys:
        country = country_view(key)
        entries = outlets_by_country.get(country["name"], [])
        ceiling = max([1] + [hits[entry["outlet"]] for entry in entries])
        slots = []
        for slot in POSITIONS:
            members = [
                {
                    "name": entry["outlet"],
                    "count": hits[entry["outlet"]],
                    "width": round(hits[entry["outlet"]] / ceiling * 100),
                    "hit": hits[entry["outlet"]] > 0,
                }
                for entry in entries
                if outlet_position(entry["outlet"], entry["leaning"]) == slot
            ]
            members.sort(key=lambda item: (-item["count"], item["name"]))
            slots.append({
                "label": country["labels"][slot - 1],
                "outlets": members,
            })
        spectrum.append({
            **country,
            "slots": slots,
            "total": plural(
                sum(hits[entry["outlet"]] for entry in entries), "article"
            ),
        })

    return {
        "results": results,
        "summary": summary,
        "timeline": timeline,
        "spectrum": spectrum,
        "has_results": bool(results),
    }
