from __future__ import annotations

from pytest import CaptureFixture, MonkeyPatch

from hr_posts.cli import extract_window, format_posts, gate_window, run
from hr_posts.client import ConnectSafelyError
from hr_posts.config import Settings
from hr_posts.extract import ExtractError, HiringFields, ModelHiringFields
from hr_posts.jev import JevError
from hr_posts.models import HiringPost


class FakeClient:
    def __init__(
        self,
        payload: dict[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.payload = payload or {"success": True, "posts": []}
        self.error = error
        self.closed = False
        self.calls: list[dict[str, object]] = []

    def search_posts(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if "past-24h" in self.payload and "past-week" in self.payload:
            window_payload = self.payload[str(kwargs["date_posted"])]
            assert isinstance(window_payload, dict)
            return window_payload
        return self.payload

    def close(self) -> None:
        self.closed = True


class FakeParser:
    def parse(self, post_text: str) -> ModelHiringFields:
        role = "AI Engineer" if "AI Engineer" in post_text else None
        return ModelHiringFields(
            hiring_role=role,
            location=None,
            skills=["Python"] if role else [],
            requirements=None,
            job_description=post_text,
        )


class FakeJudge:
    def __init__(self, probability: float = 0.9, error: Exception | None = None) -> None:
        self.probability = probability
        self.error = error
        self.seen: list[str] = []

    def hiring_probability(self, post_text: str) -> float:
        self.seen.append(post_text)
        if self.error is not None:
            raise self.error
        return self.probability


def _stub_env(monkeypatch: MonkeyPatch, fake: FakeClient) -> None:
    monkeypatch.setattr(
        "hr_posts.cli.Settings.from_env",
        lambda: Settings(api_key="test-key"),
    )
    monkeypatch.setattr("hr_posts.cli.ConnectSafelyClient", lambda settings: fake)
    monkeypatch.setattr("hr_posts.cli.load_dotenv", lambda: None)


def test_format_empty_results() -> None:
    assert format_posts(
        {"last 24 hours": [], "last 7 days": []},
        job_role="AI Engineer",
    ) == ("No hiring posts found for 'AI Engineer' in the last 24 hours or last 7 days.")


def test_format_includes_extracted_json_fields() -> None:
    output = format_posts(
        {
            "last 24 hours": [
                HiringFields(
                    source_url="https://linkedin.com/posts/ada-1",
                    post_kind="hiring_with_email_and_apply_url",
                    hiring_role="AI Engineer",
                    location="Delhi",
                    skills=["Python", "LLMs"],
                    requirements="3+ years building AI products",
                    job_description="Own the AI product roadmap.",
                    email="jobs@acme.com",
                    apply_url="https://acme.com/careers/apply",
                )
            ],
            "last 7 days": [],
        },
        job_role="AI Engineer",
    )

    assert "Last 24 hours: 1 hiring post(s) for 'AI Engineer'" in output
    assert '"source_url": "https://linkedin.com/posts/ada-1"' in output
    assert '"post_kind": "hiring_with_email_and_apply_url"' in output
    assert '"hiring_role": "AI Engineer"' in output
    assert '"location": "Delhi"' in output
    assert '"skills": [' in output
    assert '"requirements": "3+ years building AI products"' in output
    assert '"job_description": "Own the AI product roadmap."' in output
    assert '"email": "jobs@acme.com"' in output
    assert '"apply_url": "https://acme.com/careers/apply"' in output
    assert "Last 7 days: no hiring posts found" in output


def test_cli_success(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    shared_post = {
        "authorName": "Ada",
        "authorHeadline": "TA",
        "timestamp": "2026-09-24",
        "postUrl": "https://linkedin.com/posts/ada-1",
        "text": "We're hiring an AI Engineer",
        "likes": 2,
        "comments": 0,
    }
    fake = FakeClient(
        {
            "past-24h": {"success": True, "posts": [shared_post]},
            "past-week": {
                "success": True,
                "posts": [
                    shared_post,
                    {
                        "authorName": "Sam",
                        "authorHeadline": "Recruiter",
                        "timestamp": "2026-09-20",
                        "postUrl": "https://linkedin.com/posts/sam-1",
                        "text": "Hiring an AI Engineer this week. Email jobs@acme.com",
                        "likes": 1,
                        "comments": 0,
                    },
                ],
            },
        }
    )
    _stub_env(monkeypatch, fake)

    exit_code = run(
        ["--account-id", "acc_12345", "--job-role", "AI Engineer"],
        parser=FakeParser(),
        judge=FakeJudge(),
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert fake.closed is True
    assert [call["date_posted"] for call in fake.calls] == ["past-24h", "past-week"]
    assert fake.calls[0]["keywords"] == "AI Engineer hiring"
    assert fake.calls[0]["account_id"] == "acc_12345"
    assert '"source_url": "https://linkedin.com/posts/ada-1"' in output
    assert '"source_url": "https://linkedin.com/posts/sam-1"' in output
    assert '"post_kind": "just_hiring"' in output
    assert '"post_kind": "hiring_with_email"' in output
    assert '"hiring_role": "AI Engineer"' in output
    assert '"email": "jobs@acme.com"' in output
    assert output.index("ada-1") < output.index("sam-1")


def test_cli_empty_results(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    fake = FakeClient({"success": True, "posts": []})
    _stub_env(monkeypatch, fake)

    exit_code = run(["--account-id", "acc_12345", "--job-role", "AI Engineer"])

    assert exit_code == 0
    assert [call["date_posted"] for call in fake.calls] == ["past-24h", "past-week"]
    assert "No hiring posts found" in capsys.readouterr().out


def test_cli_missing_typesafe_key(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    fake = FakeClient(
        {
            "success": True,
            "posts": [
                {
                    "authorName": "Ada",
                    "text": "We're hiring an AI Engineer",
                    "postUrl": "https://linkedin.com/posts/ada-1",
                }
            ],
        }
    )
    _stub_env(monkeypatch, fake)

    exit_code = run(["--account-id", "acc_12345", "--job-role", "AI Engineer"])

    assert exit_code == 1
    assert "TYPESAFE_API_KEY is not configured" in capsys.readouterr().err


def test_cli_missing_openai_key(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    fake = FakeClient(
        {
            "success": True,
            "posts": [
                {
                    "authorName": "Ada",
                    "text": "We're hiring an AI Engineer",
                    "postUrl": "https://linkedin.com/posts/ada-1",
                }
            ],
        }
    )
    _stub_env(monkeypatch, fake)

    exit_code = run(
        ["--account-id", "acc_12345", "--job-role", "AI Engineer"],
        judge=FakeJudge(),
    )

    assert exit_code == 1
    assert "OPENAI_API_KEY is not configured" in capsys.readouterr().err


def test_cli_maps_api_error(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    fake = FakeClient(error=ConnectSafelyError("account_not_found", "missing account"))
    _stub_env(monkeypatch, fake)

    exit_code = run(["--account-id", "acc_12345", "--job-role", "AI Engineer"])

    assert exit_code == 1
    assert "missing account" in capsys.readouterr().err


def test_cli_jev_drop_skips_openai(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    fake = FakeClient(
        {
            "success": True,
            "posts": [
                {
                    "authorName": "Ada",
                    "text": "We're hiring an AI Engineer",
                    "postUrl": "https://linkedin.com/posts/ada-1",
                }
            ],
        }
    )
    _stub_env(monkeypatch, fake)

    exit_code = run(
        ["--account-id", "acc_12345", "--job-role", "AI Engineer"],
        judge=FakeJudge(0.1),
    )

    assert exit_code == 0
    assert "No hiring posts found" in capsys.readouterr().out


def test_extract_window_skips_failed_posts(capsys: CaptureFixture[str]) -> None:
    class BoomThenOk:
        def parse(self, post_text: str) -> ModelHiringFields:
            if "broken" in post_text:
                raise ExtractError("model failed")
            return ModelHiringFields(
                hiring_role="AI Engineer",
                location=None,
                skills=[],
                requirements=None,
                job_description=None,
            )

    posts = [
        HiringPost(
            "Ada", None, None, "https://linkedin.com/posts/bad", "broken hiring post", 0, 0
        ),
        HiringPost(
            "Sam", None, None, "https://linkedin.com/posts/ok", "hiring an AI Engineer", 0, 0
        ),
    ]

    extracted = extract_window(posts, BoomThenOk())
    err = capsys.readouterr().err

    assert [item.source_url for item in extracted] == ["https://linkedin.com/posts/ok"]
    assert "Skipped a post: model failed" in err


def test_gate_window_skips_failed_judge(capsys: CaptureFixture[str]) -> None:
    class SelectiveJudge:
        def hiring_probability(self, post_text: str) -> float:
            if "broken" in post_text:
                raise JevError("judge failed")
            return 0.9

    posts = [
        HiringPost(
            "Ada", None, None, "https://linkedin.com/posts/bad", "broken hiring post", 0, 0
        ),
        HiringPost(
            "Sam", None, None, "https://linkedin.com/posts/ok", "hiring an AI Engineer", 0, 0
        ),
    ]

    kept = gate_window(posts, SelectiveJudge(), threshold=0.75)
    err = capsys.readouterr().err

    assert [item.post_url for item in kept] == ["https://linkedin.com/posts/ok"]
    assert "Skipped a post: judge failed" in err
