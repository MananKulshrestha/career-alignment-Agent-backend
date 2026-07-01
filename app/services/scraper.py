from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.core.errors import BlockedWorkflowError

logger = logging.getLogger(__name__)

NOISE_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "footer",
    "header",
    "form",
    "button",
    "input",
    "select",
    "option",
}
BLOCK_TAGS = {"article", "section", "div", "p", "li", "br", "h1", "h2", "h3", "h4", "tr"}
NOISE_ATTRIBUTE_RE = re.compile(
    r"\b(cookie|consent|banner|navbar|footer|header|modal|popup|subscribe|"
    r"social|share|advertisement|ads|tracking|privacy-preferences)\b",
    re.IGNORECASE,
)
HIDDEN_STYLE_RE = re.compile(r"\b(display\s*:\s*none|visibility\s*:\s*hidden)\b", re.IGNORECASE)
LOW_VALUE_LINE_RE = re.compile(
    r"^(apply now|save job|share|share this job|accept cookies|cookie settings|"
    r"privacy preferences|sign in|log in|create job alert|job alert|back to jobs)$",
    re.IGNORECASE,
)
JOB_SIGNAL_TERMS = {
    "responsibilities",
    "requirements",
    "qualifications",
    "experience",
    "skills",
    "about the role",
    "what you will do",
    "what you'll do",
    "we are looking",
    "you will",
}
ROLE_SIGNAL_TERMS = {
    "engineer",
    "developer",
    "manager",
    "analyst",
    "intern",
    "specialist",
    "consultant",
    "designer",
    "scientist",
    "architect",
}


@dataclass(frozen=True)
class TextExtractionAssessment:
    is_usable: bool
    confidence: Literal["low", "medium", "high"]
    reason: str
    character_count: int
    signal_count: int


def html_to_markdownish_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(tuple(NOISE_TAGS)):
        tag.decompose()

    for element in list(soup.find_all(True)):
        if _is_decomposed_tag(element):
            continue
        attributes = " ".join(
            _attribute_text(element.get(attribute_name))
            for attribute_name in ("id", "class", "role", "aria-label")
        )
        if _is_hidden_element(element) or (attributes and NOISE_ATTRIBUTE_RE.search(attributes)):
            element.decompose()

    for tag in list(soup.find_all(tuple(BLOCK_TAGS))):
        if _is_decomposed_tag(tag):
            continue
        tag.insert_before("\n")
        tag.insert_after("\n")

    return _normalize_readable_text(soup.get_text("\n"))


def assess_text_extraction_quality(text: str) -> TextExtractionAssessment:
    normalized = text.strip()
    lower_text = normalized.lower()
    character_count = len(normalized)
    signal_count = sum(1 for term in JOB_SIGNAL_TERMS if term in lower_text)
    has_role_signal = any(term in lower_text for term in ROLE_SIGNAL_TERMS)
    has_requirement_signal = any(
        term in lower_text for term in {"requirements", "qualifications", "skills", "experience"}
    )

    if character_count < 80:
        return TextExtractionAssessment(
            is_usable=False,
            confidence="low",
            reason="readable job text is too short",
            character_count=character_count,
            signal_count=signal_count,
        )
    if character_count < 240 and not (has_role_signal and has_requirement_signal):
        return TextExtractionAssessment(
            is_usable=False,
            confidence="low",
            reason="short text is missing role and requirement signals",
            character_count=character_count,
            signal_count=signal_count,
        )
    if signal_count == 0 and not has_role_signal:
        return TextExtractionAssessment(
            is_usable=False,
            confidence="low",
            reason="readable text does not look like a job posting",
            character_count=character_count,
            signal_count=signal_count,
        )

    if signal_count >= 4 and character_count >= 800:
        confidence: Literal["low", "medium", "high"] = "high"
    elif signal_count >= 2 or (has_role_signal and has_requirement_signal):
        confidence = "medium"
    else:
        confidence = "low"
    return TextExtractionAssessment(
        is_usable=True,
        confidence=confidence,
        reason="job-like readable text extracted",
        character_count=character_count,
        signal_count=signal_count,
    )


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
    assessment = assess_text_extraction_quality(text)
    logger.info(
        "job page extraction quality: confidence=%s chars=%s signals=%s reason=%s",
        assessment.confidence,
        assessment.character_count,
        assessment.signal_count,
        assessment.reason,
    )
    if not assessment.is_usable:
        raise BlockedWorkflowError(
            f"job page extraction failed quality checks: {assessment.reason}"
        )
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


def _normalize_readable_text(text: str) -> str:
    normalized_lines: list[str] = []
    seen_recent: set[str] = set()
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line:
            continue
        if len(line) < 80 and LOW_VALUE_LINE_RE.match(line):
            continue
        lowered = line.lower()
        if lowered in seen_recent:
            continue
        normalized_lines.append(line)
        seen_recent.add(lowered)
        if len(seen_recent) > 200:
            seen_recent.clear()
    return "\n".join(normalized_lines)


def _attribute_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _is_hidden_element(element) -> bool:
    if _is_decomposed_tag(element):
        return True
    if element.has_attr("hidden"):
        return True
    if str(element.get("aria-hidden", "")).lower() == "true":
        return True
    style = _attribute_text(element.get("style"))
    return bool(style and HIDDEN_STYLE_RE.search(style))


def _is_decomposed_tag(element: object) -> bool:
    return getattr(element, "name", None) is None or getattr(element, "attrs", None) is None
