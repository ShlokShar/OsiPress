from types import SimpleNamespace

import pytest

from cron.util.translation import translate_references


class FakeTranslationClient:
    def __init__(self, translations: list[str]):
        self.translations = translations
        self.request = None

    def translate_text(self, request):
        self.request = request
        return SimpleNamespace(
            translations=[
                SimpleNamespace(translated_text=text)
                for text in self.translations
            ]
        )


def test_translate_references_batches_quotes_in_one_request():
    client = FakeTranslationClient(["First quote", "Second quote"])

    result = translate_references(
        ["نقل اول", "ציטוט שני"],
        client=client,
        project_id="osipress-production",
    )

    assert result == ["First quote", "Second quote"]
    assert client.request == {
        "parent": "projects/osipress-production/locations/global",
        "contents": ["نقل اول", "ציטוט שני"],
        "mime_type": "text/plain",
        "target_language_code": "en",
    }


def test_translate_references_skips_empty_batches():
    assert translate_references([], project_id="osipress-production") == []


def test_translate_references_omits_empty_quotes_and_preserves_positions():
    client = FakeTranslationClient(["First quote", "Third quote"])

    result = translate_references(
        ["نقل اول", "", "نقل سوم"],
        client=client,
        project_id="osipress-production",
    )

    assert result == ["First quote", "", "Third quote"]
    assert client.request["contents"] == ["نقل اول", "نقل سوم"]


def test_translate_references_requires_project_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT"):
        translate_references(["نقل"], client=FakeTranslationClient([]))


def test_translate_references_rejects_incomplete_responses():
    client = FakeTranslationClient(["Only one"])

    with pytest.raises(ValueError, match="unexpected number"):
        translate_references(
            ["نقل اول", "نقل دوم"],
            client=client,
            project_id="osipress-production",
        )
