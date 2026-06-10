"""URL identity helpers for crawling, dedupe, and monitoring."""

from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from core_export import clean_text


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "gbraid",
    "wbraid",
    "msclkid",
    "yclid",
    "_hsenc",
    "_hsmi",
    "mc_cid",
    "mc_eid",
    "igshid",
}


def normalize_url(url, base_url=""):
    url = clean_text(url, 2000)
    if not url:
        return ""
    lower_url = url.lower()
    if lower_url.startswith(("javascript:", "mailto:", "tel:")):
        return ""
    if base_url:
        url = urljoin(base_url, url)
    parsed = urlparse(url)
    if not parsed.scheme and not base_url:
        if url.startswith("//"):
            url = "https:" + url
        elif "." in url and not url.lower().startswith(("javascript:", "mailto:", "tel:")):
            url = "https://" + url
        parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        return ""
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return ""
    netloc = hostname
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{netloc}:{port}"
    path = parsed.path or ""
    if path == "/":
        path = ""
    elif path:
        path = path.rstrip("/")
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lower_key = key.lower()
        if lower_key.startswith("utm_") or lower_key in TRACKING_QUERY_KEYS:
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items), doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def url_domain(url):
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def site_root_url(url):
    parsed = urlparse(normalize_url(url))
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"
