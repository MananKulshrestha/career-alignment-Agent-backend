from __future__ import annotations

from html.parser import HTMLParser

import httpx

from app.core.config import settings
from app.core.errors import BlockedWorkflowError


class ReadableTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._blocked_depth += 1
        if tag in {"p", "div", "li", "br", "section", "article", "h1", "h2", "h3"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._blocked_depth:
            self._blocked_depth -= 1
        if tag in {"p", "div", "li", "section", "article", "h1", "h2", "h3"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._blocked_depth and data.strip():
            self._chunks.append(data.strip())
            self._chunks.append(" ")

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._chunks).splitlines()]
        return "\n".join(line for line in lines if line)


def html_to_markdownish_text(html: str) -> str:
    parser = ReadableTextExtractor()
    parser.feed(html)
    return parser.text()


async def fetch_job_text(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 CareerAlignmentAgent/0.1 "
            "(job ingestion; contact configured by deployment owner)"
        )
    }
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds, follow_redirects=True
    ) as client:
        response = await client.get(url, headers=headers)
    if response.status_code >= 400:
        raise BlockedWorkflowError(f"job page fetch failed with HTTP {response.status_code}")
    text = html_to_markdownish_text(response.text)
    if len(text.strip()) < 80:
        raise BlockedWorkflowError("job page did not contain enough readable text")
    return text[: settings.max_job_text_chars]


async def fetch_first_job_for_query(query: str) -> tuple[str, str]:
    if not settings.job_search_api_url or not settings.job_search_api_key:
        raise BlockedWorkflowError(
            "query ingestion requires JOB_SEARCH_API_URL and JOB_SEARCH_API_KEY; "
            "URL/text ingestion is ready"
        )
    headers = {"Authorization": f"Bearer {settings.job_search_api_key.get_secret_value()}"}
    params = {"q": query}
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        response = await client.get(settings.job_search_api_url, headers=headers, params=params)
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") or payload.get("jobs") or []
    if not results:
        raise BlockedWorkflowError("job search returned no results")
    first = results[0]
    url = first.get("url") or first.get("apply_url") or first.get("job_url")
    description = first.get("description") or first.get("text") or ""
    if not url or not description:
        raise BlockedWorkflowError("job search provider response is missing url or description")
    return url, description[: settings.max_job_text_chars]
