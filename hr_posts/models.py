from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HiringPost:
    author_name: str | None
    author_headline: str | None
    timestamp: str | None
    post_url: str | None
    text: str
    likes: int
    comments: int
