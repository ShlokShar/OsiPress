from datetime import datetime, timezone
from types import SimpleNamespace

import main


def _article(index: int) -> SimpleNamespace:
    return SimpleNamespace(
        source_id=1,
        headline=f"Original headline {index}",
        translated_headline=f"Headline {index}",
        summary=f"Summary {index}",
        references_original=[],
        references_translated=[],
        tags=[],
        link=f"https://example.com/articles/{index}",
        captured_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
    )


def test_search_renders_all_ranked_results_once(monkeypatch):
    ranked = [(index, _article(index)) for index in range(1, 8)]
    calls = []

    class FakeSearchService:
        def hybrid_search(self, query):
            calls.append(query)
            return ranked

    monkeypatch.setattr(main, "get_search_service", lambda: FakeSearchService())
    monkeypatch.setattr(
        main,
        "get_sources_by_ids",
        lambda _: {
            1: {
                "outlet": "Example Press",
                "country": "Example",
                "political_leaning": "Center",
            }
        },
    )

    response = main.app.test_client().get("/search?q=energy&limit=1")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert calls == ["energy"]
    assert page.count('class="story"') == 7
    assert 'id="show-more-results"' in page
    assert "limit=" not in page
