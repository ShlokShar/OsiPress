from urllib.parse import (
    parse_qsl,
    urlencode,
    urlsplit,
    urlunsplit,
)


TRACKING_QUERY_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def normalize_article_url(url: str) -> str:
    """Return a stable URL key without fragments or common tracking data."""

    parsed = urlsplit((url or "").strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()

    if scheme not in {"http", "https"} or not hostname:
        raise ValueError("Article URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("Article URL must not include credentials")

    try:
        port = parsed.port
    except ValueError as exception:
        raise ValueError("Article URL has an invalid port") from exception

    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")

    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
            and key.lower() not in TRACKING_QUERY_PARAMETERS
        ],
        doseq=True,
    )

    return urlunsplit((scheme, netloc, path, query, ""))
