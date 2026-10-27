from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from hr_posts.extract import (
    ExtractError,
    ModelHiringFields,
    OpenAIHiringParser,
    classify_contact_kind,
    dedupe_repeated_text,
    extract_hiring_fields,
    first_apply_url,
    first_email,
)
from hr_posts.models import HiringPost

SAMPLE_ANALYST_POST = """
We are hiring a Data Analyst in Bengaluru.

Skills: SQL, Python, Tableau
Requirements: 2+ years of analytics experience and a statistics degree.
You will build dashboards and support weekly stakeholder reviews.

Email jobs@acme.com or apply at https://acme.com/careers/apply
https://www.linkedin.com/posts/acme-analyst-1
""".strip()

SAMPLE_UNSTATED_POST = """
We're hiring. Reach out if this sounds interesting.
https://www.linkedin.com/feed/update/urn:li:activity:123
""".strip()


class FakeParser:
    def __init__(self, result: ModelHiringFields) -> None:
        self.result = result
        self.seen: list[str] = []

    def parse(self, post_text: str) -> ModelHiringFields:
        self.seen.append(post_text)
        return self.result


def _post(text: str, url: str | None = "https://www.linkedin.com/posts/acme-1") -> HiringPost:
    return HiringPost(
        author_name="Ada",
        author_headline="Recruiter",
        timestamp="2026-09-24",
        post_url=url,
        text=text,
        likes=1,
        comments=0,
    )


def test_first_email_returns_first_valid_address() -> None:
    text = "Write to team@acme.com or later to jobs@acme.com. Ignore not-an-email@"
    assert first_email(text) == "team@acme.com"
    assert first_email("no contact listed") is None


def test_first_apply_url_accepts_apply_form_and_job_pages() -> None:
    text = (
        "See https://www.linkedin.com/posts/ada-1 first, "
        "then https://acme.com/about, then https://acme.com/careers/apply"
    )
    assert first_apply_url(text) == "https://acme.com/careers/apply"
    assert first_apply_url("Apply: https://docs.google.com/forms/d/e/abc") == (
        "https://docs.google.com/forms/d/e/abc"
    )
    assert first_apply_url("https://jobs.lever.co/acme/role-1") == "https://jobs.lever.co/acme/role-1"


def test_first_apply_url_accepts_lnkd_and_apply_here_links() -> None:
    source = "https://www.linkedin.com/feed/update/urn:li:activity:7508880735068397568"
    assert first_apply_url(
        "Apply here: https://lnkd.in/gYFqpuZ7",
        source_url=source,
    ) == "https://lnkd.in/gYFqpuZ7"
    assert first_apply_url("https://lnkd.in/gYFqpuZ7", source_url=source) == (
        "https://lnkd.in/gYFqpuZ7"
    )
    assert first_apply_url("Apply at https://acme.com/about", source_url=source) == (
        "https://acme.com/about"
    )
    assert (
        classify_contact_kind("Apply here: https://lnkd.in/gYFqpuZ7", source_url=source)
        == "hiring_with_apply_url"
    )


def test_classify_contact_kind_covers_all_four_labels() -> None:
    source = "https://www.linkedin.com/posts/ada-1"
    assert (
        classify_contact_kind(
            "Email jobs@acme.com or apply at https://acme.com/careers/apply",
            source_url=source,
        )
        == "hiring_with_email_and_apply_url"
    )
    assert classify_contact_kind("Email jobs@acme.com", source_url=source) == "hiring_with_email"
    assert (
        classify_contact_kind("Apply at https://acme.com/careers/apply", source_url=source)
        == "hiring_with_apply_url"
    )
    assert classify_contact_kind("We're hiring an AI Engineer.", source_url=source) == (
        "just_hiring"
    )
    assert classify_contact_kind(f"Apply here {source}", source_url=source) == "just_hiring"


def test_first_apply_url_rejects_linkedin_feed_and_source_url() -> None:
    source = "https://www.linkedin.com/posts/ada-1"
    assert first_apply_url(f"Apply here {source}", source_url=source) is None
    assert first_apply_url("https://www.linkedin.com/feed/update/urn:li:activity:9") is None
    assert first_apply_url("https://www.linkedin.com/posts/someone-hiring-jobs") is None
    assert first_apply_url("Homepage https://acme.com/about") is None


def test_dedupe_repeated_text_collapses_tripled_body() -> None:
    block = (
        "We are hiring a Civil Engineer in Pune for site supervision "
        "and AutoCAD drawings on residential projects."
    )
    repeated = f"{block} {block} {block}"
    assert dedupe_repeated_text(repeated) == block
    assert dedupe_repeated_text(f"{block}\n\n{block}\n\n{block}") == block


def test_extract_null_role_and_location() -> None:
    parser = FakeParser(
        ModelHiringFields(
            hiring_role=None,
            location=None,
            skills=[],
            requirements=None,
            job_description=None,
        )
    )

    result = extract_hiring_fields(_post(SAMPLE_UNSTATED_POST), parser)

    assert result.hiring_role is None
    assert result.location is None
    assert result.skills == []
    assert result.requirements is None
    assert result.job_description is None
    assert result.email is None
    assert result.apply_url is None
    assert result.post_kind == "just_hiring"
    assert result.source_url == "https://www.linkedin.com/posts/acme-1"


def test_extract_skills_requirements_and_job_description() -> None:
    parser = FakeParser(
        ModelHiringFields(
            hiring_role="Data Analyst",
            location="Bengaluru",
            skills=["SQL", "Python", "Tableau"],
            requirements="2+ years of analytics experience and a statistics degree.",
            job_description="You will build dashboards and support weekly stakeholder reviews.",
        )
    )

    result = extract_hiring_fields(_post(SAMPLE_ANALYST_POST), parser)

    assert result.hiring_role == "Data Analyst"
    assert result.location == "Bengaluru"
    assert result.skills == ["SQL", "Python", "Tableau"]
    assert result.requirements == "2+ years of analytics experience and a statistics degree."
    assert result.job_description == (
        "You will build dashboards and support weekly stakeholder reviews."
    )
    assert result.email == "jobs@acme.com"
    assert result.apply_url == "https://acme.com/careers/apply"
    assert result.post_kind == "hiring_with_email_and_apply_url"
    assert result.source_url == "https://www.linkedin.com/posts/acme-1"
    assert result.source_url != result.apply_url
    assert parser.seen


def test_openai_parser_rejects_empty_structured_output() -> None:
    parser = object.__new__(OpenAIHiringParser)
    parser._client = SimpleNamespace(  # type: ignore[attr-defined]
        responses=SimpleNamespace(parse=lambda **_: SimpleNamespace(output_parsed=None))
    )
    parser._model = "gpt-5-mini"

    with pytest.raises(ExtractError, match="valid hiring fields"):
        parser.parse("hiring text")


def test_openai_parser_wraps_provider_errors() -> None:
    def boom(**_: Any) -> None:
        raise RuntimeError("timeout")

    parser = object.__new__(OpenAIHiringParser)
    parser._client = SimpleNamespace(responses=SimpleNamespace(parse=boom))  # type: ignore[attr-defined]
    parser._model = "gpt-5-mini"

    with pytest.raises(ExtractError, match="provider request failed"):
        parser.parse("hiring text")
