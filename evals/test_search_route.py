from datetime import datetime, timezone
from types import SimpleNamespace

import main


def _row(index: int) -> dict:
    return {
        "article_id": index,
        "country": "Iran",
        "outlet": "Kayhan",
        "outlet_id": 1,
        "leaning": "Right",
        "headline": f"Original headline {index}",
        "translated_headline": f"Headline {index} about energy",
        "link": f"https://example.com/articles/{index}",
        "published_at": datetime(2026, 11, 10, 8, index, tzinfo=timezone.utc),
        "captured_at": datetime(2026, 11, 10, 9, index, tzinfo=timezone.utc),
        "event_title": "An event",
    }


def _patch(monkeypatch, rows, calls):
    def hybrid_search(query):
        calls.append(query)
        return [(index, SimpleNamespace(
            id=row["article_id"], source_id=row["outlet_id"],
            headline=row["headline"], translated_headline=row["translated_headline"],
            link=row["link"], published_at=row["published_at"],
            captured_at=row["captured_at"],
        )) for index, row in enumerate(rows)]

    monkeypatch.setattr(main, "get_search_service", lambda: SimpleNamespace(hybrid_search=hybrid_search))
    monkeypatch.setattr(main, "get_sources_by_ids", lambda ids: {
        1: {"country": "Iran", "outlet": "Kayhan", "political_leaning": "Right"}
    })
    monkeypatch.setattr(
        main, "get_topic_names", lambda: ["Nuclear programme", "Gaza"]
    )
    monkeypatch.setattr(
        main,
        "get_outlets_by_country",
        lambda: {
            "Iran": [
                {"id": 1, "outlet": "Kayhan", "leaning": "Right",
                 "link": "https://example.com"},
                {"id": 2, "outlet": "Shargh", "leaning": "Left",
                 "link": "https://example.com"},
            ]
        },
    )


def test_search_renders_every_match(monkeypatch):
    rows = [_row(index) for index in range(1, 8)]
    calls = []
    _patch(monkeypatch, rows, calls)

    response = main.app.test_client().get("/search?q=energy&countries=ir")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert calls == ["energy"]
    assert page.count('class="osi-result"') == 7
    assert "7 articles from 1 outlet" in page


def test_search_highlights_the_query(monkeypatch):
    _patch(monkeypatch, [_row(1)], [])

    page = main.app.test_client().get(
        "/search?q=energy&countries=ir"
    ).get_data(as_text=True)

    assert "<mark>energy</mark>" in page


def test_search_defaults_to_relevance_order(monkeypatch):
    _patch(monkeypatch, [_row(1), _row(2)], [])
    page = main.app.test_client().get(
        "/search?q=energy&countries=ir"
    ).get_data(as_text=True)
    assert page.index("Headline 1 about") < page.index("Headline 2 about")


def test_search_keeps_outlets_without_a_match_visible(monkeypatch):
    _patch(monkeypatch, [_row(1)], [])

    page = main.app.test_client().get(
        "/search?q=energy&countries=ir"
    ).get_data(as_text=True)

    assert "Shargh" in page


def test_search_opens_empty_without_a_query(monkeypatch):
    calls = []
    _patch(monkeypatch, [_row(1)], calls)

    page = main.app.test_client().get("/search").get_data(as_text=True)

    assert calls == []
    assert "Search the archive." in page


def test_search_rejects_a_very_long_query(monkeypatch):
    calls = []
    _patch(monkeypatch, [_row(1)], calls)

    page = main.app.test_client().get(
        "/search?q=" + "x" * 201
    ).get_data(as_text=True)

    assert calls == []
    assert "too long" in page
