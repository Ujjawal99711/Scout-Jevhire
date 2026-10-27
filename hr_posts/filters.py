from __future__ import annotations

import re
from typing import Any

from hr_posts.models import HiringPost

HIRING_SIGNALS = (
    "hiring",
    "we're hiring",
    "we are hiring",
    "looking for",
    "open role",
    "open roles",
    "job opening",
    "job openings",
    "join our team",
    "now hiring",
    "we’re hiring",
)

_PUNCTUATION_RE = re.compile(r"[–—\-,/|]+")


def combined_post_text(post: dict[str, Any]) -> str:
    parts = [
        post.get("text"),
        post.get("content"),
        post.get("userCommentary"),
    ]
    return "\n".join(str(part) for part in parts if isinstance(part, str) and part.strip())


def has_hiring_signal(text: str) -> bool:
    lowered = text.casefold()
    return any(signal in lowered for signal in HIRING_SIGNALS)


def _normalize_text(text: str) -> str:
    lowered = _PUNCTUATION_RE.sub(" ", text.casefold())
    return " ".join(lowered.split())


def role_phrases(job_role: str) -> list[str]:
    words = _normalize_text(job_role).split()
    if not words:
        return []

    phrases = {" ".join(words)}
    if len(words) >= 3 and words[-2:] == ["product", "manager"]:
        qualifier = " ".join(words[:-2])
        phrases.update(
            {
                f"product manager {qualifier}",
                f"{qualifier} pm",
            }
        )
    return sorted(phrases)


def matches_role(text: str, job_role: str) -> bool:
    normalized = _normalize_text(text)
    return any(phrase in normalized for phrase in role_phrases(job_role))


def normalize_post(post: dict[str, Any], job_role: str) -> HiringPost | None:
    text = combined_post_text(post)
    if not text or not has_hiring_signal(text) or not matches_role(text, job_role):
        return None

    likes = post.get("likes")
    comments = post.get("comments")
    return HiringPost(
        author_name=_optional_str(post.get("authorName")),
        author_headline=_optional_str(post.get("authorHeadline")),
        timestamp=_optional_str(post.get("timestamp")),
        post_url=_optional_str(post.get("postUrl")),
        text=text,
        likes=likes if isinstance(likes, int) else 0,
        comments=comments if isinstance(comments, int) else 0,
    )


def filter_hiring_posts(posts: list[dict[str, Any]], job_role: str) -> list[HiringPost]:
    results: list[HiringPost] = []
    seen_urls: set[str] = set()
    for post in posts:
        normalized = normalize_post(post, job_role)
        if normalized is None:
            continue
        if normalized.post_url:
            if normalized.post_url in seen_urls:
                continue
            seen_urls.add(normalized.post_url)
        results.append(normalized)
    return results


def _optional_str(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None
