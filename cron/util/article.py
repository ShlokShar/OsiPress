from typing import Optional

import trafilatura


def get_article_text(url: str) -> str:
    full_article = trafilatura.fetch_url(url)
    text = trafilatura.extract(full_article)

    # TODO: if the text is too small (indicates improper content extraction)
    #  then pass the entire response text into the summarizer.

    return text if text else "empty article."
