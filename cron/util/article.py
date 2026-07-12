
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests
import trafilatura


MAX_REDIRECTS = 5
MAX_ARTICLE_BYTES = 5 * 1024 * 1024
REQUEST_TIMEOUT = (5, 20)

def is_safe_article_url(url: str) -> bool:
    """Return whether a URL is a public HTTP(S) destination."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False

        addresses = socket.getaddrinfo(parsed.hostname, parsed.port)
        if not addresses:
            return False

        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                return False
    except (OSError, TypeError, ValueError):
        return False

    return True


def fetch_safe_article(url: str) -> bytes:
    """Download an article while validating every redirect destination."""
    current_url = url
    headers = {"User-Agent": "OsiPress/1.0"}

    with requests.Session() as session:
        for _ in range(MAX_REDIRECTS + 1):
            if not is_safe_article_url(current_url):
                raise ValueError(
                    "Article URL must resolve to a public HTTP(S) host"
                )

            response = session.get(
                current_url,
                allow_redirects=False,
                headers=headers,
                stream=True,
                timeout=REQUEST_TIMEOUT,
            )

            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise ValueError("Article redirect has no destination")
                current_url = urljoin(current_url, location)
                continue

            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                content.extend(chunk)
                if len(content) > MAX_ARTICLE_BYTES:
                    raise ValueError("Article response exceeds size limit")
            return bytes(content)

    raise ValueError("Article exceeded redirect limit")


def get_article_text(url: str) -> str:
    """
    derives only the article content, ignores navigation bars, footers,
    miscellaneous information in the page.

    :param url: the url of the article
    :return: the content of the article
    """
    full_article = fetch_safe_article(url)
    text = trafilatura.extract(full_article)

    # TODO: if the text is too small (indicates improper content extraction)
    #  then pass the entire response text into the summarizer.

    return text if text else "empty article."
