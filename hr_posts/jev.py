from __future__ import annotations

from typing import Protocol

import httpx

from hr_posts.extract import dedupe_repeated_text
from hr_posts.models import HiringPost

DEFAULT_THRESHOLD = 0.75
HIRING_QUESTION = (
    "Is this an employer or recruiter advertising an open job, not a candidate "
    "seeking work, and not a comment about hiring?"
)


class JevError(RuntimeError):
    pass


class HiringJudge(Protocol):
    def hiring_probability(self, post_text: str) -> float: ...


class TypeSafeHiringJudge:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.typesafe.ai",
        model: str = "jev-latest",
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def hiring_probability(self, post_text: str) -> float:
        try:
            response = self._client.post(
                "/v1/systemone",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "state": post_text,
                    "questions": {
                        "is_hiring": {
                            "type": "noul",
                            "instructions": HIRING_QUESTION,
                        }
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise JevError("The hiring judge request failed.") from exc

        answers = payload.get("answers") if isinstance(payload, dict) else None
        hiring = answers.get("is_hiring") if isinstance(answers, dict) else None
        noul = hiring.get("noul") if isinstance(hiring, dict) else None
        if not isinstance(noul, int | float):
            raise JevError("The hiring judge did not return a valid probability.")
        return float(noul)


def is_hiring_post(
    post: HiringPost,
    judge: HiringJudge,
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> bool:
    cleaned = dedupe_repeated_text(post.text)
    return judge.hiring_probability(cleaned) >= threshold
