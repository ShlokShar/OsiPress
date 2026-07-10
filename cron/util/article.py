
from typing import Optional

import trafilatura


def get_article_text(url: str) -> str:
    """
    derives only the article content, ignores navigation bars, footers,
    miscellaneous information in the page.

    :param url: the url of the article
    :return: the content of the article
    """
    full_article = trafilatura.fetch_url(url)
    text = trafilatura.extract(full_article)

    # TODO: if the text is too small (indicates improper content extraction)
    #  then pass the entire response text into the summarizer.

    return text if text else "empty article."
