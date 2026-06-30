from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.core.errors import BlockedWorkflowError

TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def canonicalize_url(url: str) -> str:
    candidate = url.strip()
    preliminary_parts = urlsplit(candidate)
    if preliminary_parts.scheme and "://" not in candidate:
        raise BlockedWorkflowError("job URL must use http or https")
    if not preliminary_parts.scheme:
        candidate = f"https://{candidate}"
    parts = urlsplit(candidate)
    scheme = (parts.scheme or "https").lower()
    if scheme not in {"http", "https"}:
        raise BlockedWorkflowError("job URL must use http or https")
    netloc = parts.netloc.lower()
    if not netloc:
        raise BlockedWorkflowError("job URL is missing a hostname")
    path = parts.path.rstrip("/") or "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_pairs), doseq=True)
    return urlunsplit((scheme, netloc, path, query, ""))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
