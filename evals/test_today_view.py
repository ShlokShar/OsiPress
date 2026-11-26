from datetime import date, datetime, timezone

import main


def test_compare_controls_work_without_a_lead(monkeypatch):
    stamp = datetime(2026, 11, 20, tzinfo=timezone.utc)
    articles = [
        {"country": country, "outlet": outlet, "leaning": "Left",
         "headline": outlet, "translated_headline": outlet, "link": "https://example.com",
         "published_at": stamp}
        for country, outlet in (("Iran", "Shargh"), ("Israel", "Haaretz"))
    ]
    events = [
        {"id": index, "title": f"Event {index}", "articles": articles, "last_seen": stamp}
        for index in (1, 2)
    ]
    monkeypatch.setattr(main, "get_events_for_day", lambda **_: (date(2026, 11, 20), events))

    page = main.app.test_client().get("/today?view=compare&countries=ir").get_data(as_text=True)
    assert 'data-action="view"' in page
    assert 'data-action="country"' in page
    assert page.count('class="osi-compare-column"') == 2
    assert "Event 1" in page and "Event 2" in page
