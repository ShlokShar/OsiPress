import main


def test_archive_edition_uses_existing_history_query(monkeypatch):
    seen = []
    monkeypatch.setattr(main, "get_headlines_by_country", lambda day: seen.append(day) or {})
    response = main.app.test_client().get("/archive/edition/2026-07-10")
    assert response.status_code == 200
    assert seen[0].isoformat() == "2026-07-10"
    assert b"10 July 2026" in response.data


def test_archive_edition_rejects_invalid_date():
    assert main.app.test_client().get("/archive/edition/not-a-date").status_code == 404
