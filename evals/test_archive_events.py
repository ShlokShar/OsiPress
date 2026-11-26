from datetime import date

from shared.presenters import archive_view


def test_multiday_event_counts_daily_coverage_and_ranks_once():
    days = [date(2026, 11, 22), date(2026, 11, 23)]
    events = []
    for day, article_id in zip(days, (1, 2)):
        article = {"article_id": article_id, "country": "Iran", "outlet": "Shargh", "leaning": "Left"}
        events.append({"id": 1, "title": "Ongoing event", "topic": None,
                       "day": day, "articles": [article], "by_country": {"Iran": [article]}})

    view = archive_view(days, {}, events, 2, ["ir"], None, None)
    assert [day["meta"] for day in view["list_days"]] == ["1 event, 1 article", "1 event, 1 article"]
    assert len(view["ranked"]) == 1
    assert view["ranked"][0]["count"] == "2 articles"
    assert view["stats"][0]["big"] == "1"
