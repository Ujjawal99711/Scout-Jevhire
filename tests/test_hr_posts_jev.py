from __future__ import annotations

import httpx
import pytest

from hr_posts.jev import JevError, TypeSafeHiringJudge, is_hiring_post
from hr_posts.models import HiringPost


class FakeJudge:
    def __init__(self, probability: float | None = 0.9, error: Exception | None = None) -> None:
        self.probability = probability
        self.error = error
        self.seen: list[str] = []

    def hiring_probability(self, post_text: str) -> float:
        self.seen.append(post_text)
        if self.error is not None:
            raise self.error
        assert self.probability is not None
        return self.probability


def _post(text: str = "We're hiring an AI Engineer") -> HiringPost:
    return HiringPost("Ada", None, None, "https://linkedin.com/posts/ada-1", text, 0, 0)


def test_is_hiring_post_keeps_above_threshold() -> None:
    judge = FakeJudge(0.75)
    assert is_hiring_post(_post(), judge) is True
    assert judge.seen


def test_is_hiring_post_drops_below_threshold() -> None:
    assert is_hiring_post(_post(), FakeJudge(0.74)) is False


def test_is_hiring_post_sends_deduped_text_not_url() -> None:
    block = (
        "We are hiring a Civil Engineer in Pune for site supervision "
        "and AutoCAD drawings on residential projects."
    )
    judge = FakeJudge(0.9)
    post = _post(f"{block} {block} {block}")
    assert is_hiring_post(post, judge) is True
    assert judge.seen == [block]
    assert "linkedin.com" not in judge.seen[0]


def test_typesafe_judge_reads_noul_probability() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/systemone"
        assert request.headers["authorization"] == "Bearer test-key"
        body = request.content.decode()
        assert "We're hiring" in body
        assert "linkedin.com" not in body
        return httpx.Response(200, json={"answers": {"is_hiring": {"type": "noul", "noul": 0.88}}})

    transport = httpx.MockTransport(handler)
    judge = TypeSafeHiringJudge(
        "test-key",
        client=httpx.Client(transport=transport, base_url="https://api.typesafe.ai"),
    )
    assert judge.hiring_probability("We're hiring an AI Engineer") == 0.88


def test_typesafe_judge_rejects_missing_probability() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answers": {}})

    judge = TypeSafeHiringJudge(
        "test-key",
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://api.typesafe.ai",
        ),
    )
    with pytest.raises(JevError, match="valid probability"):
        judge.hiring_probability("hiring text")


def test_typesafe_judge_wraps_http_errors() -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "nope"})

    judge = TypeSafeHiringJudge(
        "test-key",
        client=httpx.Client(
            transport=httpx.MockTransport(boom),
            base_url="https://api.typesafe.ai",
        ),
    )
    with pytest.raises(JevError, match="request failed"):
        judge.hiring_probability("hiring text")
