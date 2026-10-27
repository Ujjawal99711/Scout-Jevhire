from __future__ import annotations

from hr_posts.client import ConnectSafelyError, build_search_keywords
from hr_posts.filters import filter_hiring_posts, has_hiring_signal, matches_role
from hr_posts.models import HiringPost


def test_keywords_quote_the_role() -> None:
    assert build_search_keywords("  AI Product Manager  ") == "AI Product Manager hiring"


def test_blank_job_role_is_rejected() -> None:
    try:
        build_search_keywords("   ")
    except ConnectSafelyError as exc:
        assert exc.code == "invalid_job_role"
    else:
        raise AssertionError("expected invalid_job_role")


def test_hiring_signals_are_detected() -> None:
    assert has_hiring_signal("We are hiring an AI Engineer")
    assert has_hiring_signal("Looking for a backend developer")
    assert not has_hiring_signal("Great article about AI engineering")


def test_role_match_accepts_close_title_variants() -> None:
    assert matches_role("We're hiring an AI Product Manager", "AI Product Manager")
    assert matches_role("Hiring: Product Manager – AI", "AI Product Manager")
    assert matches_role("Open role: Product Manager, AI", "AI Product Manager")
    assert matches_role("Looking for an AI PM", "AI Product Manager")
    assert not matches_role("Hiring QA Automation Engineer", "AI Product Manager")
    assert not matches_role("More engineering openings: SDE 1 Python", "AI Product Manager")


def test_filter_keeps_only_role_hiring_posts() -> None:
    posts = [
        {
            "authorName": "Ada",
            "authorHeadline": "Recruiter",
            "timestamp": "2026-09-24",
            "postUrl": "https://linkedin.com/posts/ada-1",
            "text": "We are hiring an AI Product Manager",
            "likes": 4,
            "comments": 1,
        },
        {
            "authorName": "Ada",
            "postUrl": "https://linkedin.com/posts/ada-1",
            "text": "We are hiring an AI Product Manager again",
        },
        {
            "authorName": "Radancy",
            "text": (
                "We're Hiring at Radancy | Bangalore across Engineering, QA, Data, Analytics, AI"
            ),
            "postUrl": "https://linkedin.com/posts/radancy-1",
        },
        {
            "authorName": "Manikanta",
            "text": "Hiring: QA Automation Engineer | AI-Driven Testing",
            "postUrl": "https://linkedin.com/posts/qa-1",
        },
        {
            "authorName": "Vas",
            "text": "More Engineering Openings at M2P Fintech. Here's what we're hiring for: SDE 1",
            "postUrl": "https://linkedin.com/posts/m2p-1",
        },
        {
            "authorName": "Sam",
            "content": "Thoughts on prompt engineering",
            "postUrl": "https://linkedin.com/posts/sam-1",
        },
    ]

    results = filter_hiring_posts(posts, "AI Product Manager")

    assert results == [
        HiringPost(
            author_name="Ada",
            author_headline="Recruiter",
            timestamp="2026-09-24",
            post_url="https://linkedin.com/posts/ada-1",
            text="We are hiring an AI Product Manager",
            likes=4,
            comments=1,
        )
    ]
