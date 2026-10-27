from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

from hr_posts.extract import dedupe_repeated_text
from hr_posts.jev import HiringJudge, JevError, TypeSafeHiringJudge
from hr_posts.models import HiringPost

DEMO_THRESHOLD = 0.75
Verdict = dict[str, str | float | None]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify provided LinkedIn posts as hiring vs not hiring using Jev."
    )
    parser.add_argument(
        "--posts",
        required=True,
        help="JSON file with a list of posts: {id?, text, source_url?}",
    )
    return parser


def load_posts(path: Path) -> list[tuple[str, HiringPost]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"Could not read posts file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Posts file is not valid JSON.") from exc

    if not isinstance(payload, list) or not payload:
        raise RuntimeError("Posts file must be a non-empty JSON list.")

    loaded: list[tuple[str, HiringPost]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise RuntimeError(f"Post {index} must be a JSON object.")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(f"Post {index} needs a non-empty text field.")
        raw_id = item.get("id")
        post_id = str(raw_id).strip() if raw_id is not None and str(raw_id).strip() else str(index)
        source_url = item.get("source_url")
        loaded.append(
            (
                post_id,
                HiringPost(
                    author_name=None,
                    author_headline=None,
                    timestamp=None,
                    post_url=source_url if isinstance(source_url, str) else None,
                    text=text,
                    likes=0,
                    comments=0,
                ),
            )
        )
    return loaded


def classify_post(
    post_id: str,
    post: HiringPost,
    judge: HiringJudge,
    *,
    threshold: float,
) -> Verdict:
    try:
        cleaned = dedupe_repeated_text(post.text)
        probability = judge.hiring_probability(cleaned)
    except JevError as exc:
        print(f"Skipped post {post_id}: {exc}", file=sys.stderr)
        return {"id": post_id, "verdict": "skipped", "probability": None}

    verdict = "hiring" if probability >= threshold else "not_hiring"
    return {"id": post_id, "verdict": verdict, "probability": probability}


def format_summary(results: Sequence[Verdict]) -> str:
    counts = {"hiring": 0, "not_hiring": 0, "skipped": 0}
    for item in results:
        verdict = item["verdict"]
        if isinstance(verdict, str) and verdict in counts:
            counts[verdict] += 1
    return (
        f"hiring: {counts['hiring']}, not_hiring: {counts['not_hiring']}, "
        f"skipped: {counts['skipped']}"
    )


def _jev_settings() -> tuple[str, str, str, float, float]:
    api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
    base_url = os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai").rstrip("/")
    model = os.getenv("JEV_MODEL", "jev-latest")
    timeout = float(os.getenv("TYPESAFE_TIMEOUT_SECONDS", "30"))
    threshold = float(os.getenv("DEMO_JEV_HIRING_THRESHOLD", str(DEMO_THRESHOLD)))
    return api_key, base_url, model, timeout, threshold


def run(
    argv: Sequence[str] | None = None,
    *,
    judge: HiringJudge | None = None,
) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)

    try:
        posts = load_posts(Path(args.posts))
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    api_key, base_url, model, timeout, threshold = _jev_settings()
    hiring_judge = judge
    owns_judge = hiring_judge is None
    if hiring_judge is None:
        if not api_key:
            print("TYPESAFE_API_KEY is not configured", file=sys.stderr)
            return 1
        hiring_judge = TypeSafeHiringJudge(
            api_key,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout,
        )

    results: list[Verdict] = []
    try:
        for post_id, post in posts:
            results.append(classify_post(post_id, post, hiring_judge, threshold=threshold))
    finally:
        closer = getattr(hiring_judge, "close", None) if owns_judge else None
        if callable(closer):
            closer()

    for item in results:
        print(json.dumps(item, ensure_ascii=False))
    print(format_summary(results))
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
