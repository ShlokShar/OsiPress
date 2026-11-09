
import os
from functools import lru_cache
from typing import Optional

from google.cloud import translate_v3


@lru_cache(maxsize=1)
def _translation_client() -> translate_v3.TranslationServiceClient:
    """Builds one authenticated client for the lifetime of an ingestion run."""

    return translate_v3.TranslationServiceClient()

def translate_references(
    references: list[str],
    client: Optional[translate_v3.TranslationServiceClient] = None,
    project_id: Optional[str] = None,
) -> list[str]:
    """
    Translates an article's supporting quotes to English in one authenticated
    Google Cloud Translation request.

    :param references: the list of quotes from the article in its original
    language
    :param client: optional client override used by tests
    :param project_id: optional Google Cloud project override used by tests
    :return: a list of the original quotes in English
    """

    if not references:
        return []

    non_empty_references = [
        (index, reference)
        for index, reference in enumerate(references)
        if reference.strip()
    ]
    if not non_empty_references:
        return references.copy()

    resolved_project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not resolved_project_id:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is not configured")

    translation_client = client or _translation_client()
    response = translation_client.translate_text(
        request={
            "parent": f"projects/{resolved_project_id}/locations/global",
            "contents": [
                reference for _, reference in non_empty_references
            ],
            "mime_type": "text/plain",
            "target_language_code": "en",
        }
    )
    translations = [item.translated_text for item in response.translations]

    if len(translations) != len(non_empty_references):
        raise ValueError(
            "Google Cloud Translation returned an unexpected number of "
            "translations"
        )

    translated_references = references.copy()
    for (index, _), translation in zip(
        non_empty_references,
        translations,
        strict=True,
    ):
        translated_references[index] = translation

    return translated_references
