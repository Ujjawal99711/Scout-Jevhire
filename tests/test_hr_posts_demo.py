from __future__ import annotations

import json
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from hr_posts.demo import classify_post, format_summary, load_posts, run
from hr_posts.jev import JevError
from hr_posts.models import HiringPost


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


def _write_posts(path: Path, posts: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps(posts), encoding="utf-8")
    return path


def test_load_posts_defaults_id_and_ignores_source_url_for_text() -> None:
    posts = load_posts(
        Path(__file__).resolve().parents[1] / "demo_posts.example.json"
    )
    assert [post_id for post_id, _ in posts] == ["1", "2"]
    assert "We're hiring a Product Manager" in posts[0][1].text


def test_classify_post_hiring_at_threshold() -> None:
    post = HiringPost(None, None, None, None, "We're hiring a PM", 0, 0)
    result = classify_post("1", post, FakeJudge(0.75), threshold=0.75)
    assert result == {"id": "1", "verdict": "hiring", "probability": 0.75}


def test_classify_post_not_hiring_below_threshold() -> None:
    post = HiringPost(None, None, None, None, "Open to PM roles", 0, 0)
    result = classify_post("2", post, FakeJudge(0.74), threshold=0.75)
    assert result == {"id": "2", "verdict": "not_hiring", "probability": 0.74}


def test_classify_post_skips_jev_error(capsys: CaptureFixture[str]) -> None:
    post = HiringPost(None, None, None, None, "We're hiring a PM", 0, 0)
    result = classify_post("3", post, FakeJudge(error=JevError("judge failed")), threshold=0.75)
    assert result == {"id": "3", "verdict": "skipped", "probability": None}
    assert "Skipped post 3: judge failed" in capsys.readouterr().err


def test_demo_cli_prints_verdicts(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    posts_path = _write_posts(
        tmp_path / "posts.json",
        [
            {"id": "keep", "text": "We're hiring a Product Manager"},
            {"text": "Open to roles, please DM me"},
        ],
    )
    monkeypatch.setattr("hr_posts.demo.load_dotenv", lambda: None)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("DEMO_JEV_HIRING_THRESHOLD", raising=False)

    class ThresholdJudge:
        def hiring_probability(self, post_text: str) -> float:
            return 0.75 if "hiring" in post_text.casefold() else 0.1

    exit_code = run(["--posts", str(posts_path)], judge=ThresholdJudge())
    output = capsys.readouterr().out

    assert exit_code == 0
    lines = output.strip().splitlines()
    assert json.loads(lines[0]) == {"id": "keep", "verdict": "hiring", "probability": 0.75}
    assert json.loads(lines[1]) == {"id": "2", "verdict": "not_hiring", "probability": 0.1}
    assert lines[-1] == "hiring: 1, not_hiring: 1, skipped: 0"
    assert format_summary([json.loads(lines[0]), json.loads(lines[1])]) == lines[-1]


def test_demo_cli_treats_below_075_as_not_hiring(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    posts_path = _write_posts(
        tmp_path / "posts.json",
        [{"id": "border", "text": "We're hiring a Product Manager"}],
    )
    monkeypatch.setattr("hr_posts.demo.load_dotenv", lambda: None)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("DEMO_JEV_HIRING_THRESHOLD", raising=False)

    exit_code = run(["--posts", str(posts_path)], judge=FakeJudge(0.74))
    lines = capsys.readouterr().out.strip().splitlines()

    assert exit_code == 0
    assert json.loads(lines[0]) == {
        "id": "border",
        "verdict": "not_hiring",
        "probability": 0.74,
    }


def test_demo_missing_typesafe_key(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    posts_path = _write_posts(
        tmp_path / "posts.json",
        [{"text": "We're hiring a Product Manager"}],
    )
    monkeypatch.setattr("hr_posts.demo.load_dotenv", lambda: None)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    exit_code = run(["--posts", str(posts_path)])

    assert exit_code == 1
    assert "TYPESAFE_API_KEY is not configured" in capsys.readouterr().err
