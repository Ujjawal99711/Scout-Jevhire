from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence

from dotenv import load_dotenv

from hr_posts.client import ConnectSafelyClient, ConnectSafelyError, build_search_keywords
from hr_posts.config import Settings
from hr_posts.extract import (
    ExtractError,
    HiringFieldParser,
    HiringFields,
    OpenAIHiringParser,
    extract_hiring_fields,
)
from hr_posts.filters import filter_hiring_posts
from hr_posts.jev import HiringJudge, JevError, TypeSafeHiringJudge, is_hiring_post
from hr_posts.models import HiringPost

SEARCH_WINDOWS = (
    ("past-24h", "last 24 hours"),
    ("past-week", "last 7 days"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Find LinkedIn hiring posts for a job role from the last 24 hours and last 7 days."
        )
    )
    parser.add_argument("--account-id", required=True, help="ConnectSafely LinkedIn account ID")
    parser.add_argument("--job-role", required=True, help="Job role to search for")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Number of posts to request from ConnectSafely (default 20)",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Pagination offset for the ConnectSafely search (default 0)",
    )
    return parser


def _post_key(post: HiringPost) -> str:
    return post.post_url or f"{post.author_name}:{post.text}"


def format_window(posts: Sequence[HiringFields], *, job_role: str, window: str) -> str:
    if not posts:
        return f"{window.capitalize()}: no hiring posts found for '{job_role}'."

    blocks = [f"{window.capitalize()}: {len(posts)} hiring post(s) for '{job_role}':"]
    for post in posts:
        blocks.append(json.dumps(post.model_dump(), indent=2, ensure_ascii=False))
    return "\n".join(blocks)


def format_posts(
    grouped: Mapping[str, Sequence[HiringFields]],
    *,
    job_role: str,
) -> str:
    if not any(grouped.values()):
        return f"No hiring posts found for '{job_role}' in the last 24 hours or last 7 days."
    return "\n\n".join(
        format_window(posts, job_role=job_role, window=window) for window, posts in grouped.items()
    )


def gate_window(
    posts: Sequence[HiringPost],
    judge: HiringJudge,
    *,
    threshold: float,
) -> list[HiringPost]:
    kept: list[HiringPost] = []
    for post in posts:
        try:
            if is_hiring_post(post, judge, threshold=threshold):
                kept.append(post)
        except JevError as exc:
            print(f"Skipped a post: {exc}", file=sys.stderr)
    return kept


def extract_window(
    posts: Sequence[HiringPost],
    parser: HiringFieldParser,
) -> list[HiringFields]:
    extracted: list[HiringFields] = []
    for post in posts:
        try:
            extracted.append(extract_hiring_fields(post, parser))
        except ExtractError as exc:
            print(f"Skipped a post: {exc}", file=sys.stderr)
    return extracted


def run(
    argv: Sequence[str] | None = None,
    *,
    parser: HiringFieldParser | None = None,
    judge: HiringJudge | None = None,
) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)

    try:
        settings = Settings.from_env()
        keywords = build_search_keywords(args.job_role)
        count = args.limit if args.limit is not None else settings.default_count
        if count < 1:
            raise ConnectSafelyError("invalid_limit", "--limit must be at least 1.")
        if args.start < 0:
            raise ConnectSafelyError("invalid_start", "--start cannot be negative.")

        job_role = " ".join(args.job_role.split())
        grouped_raw: dict[str, list[HiringPost]] = {}
        client = ConnectSafelyClient(settings)
        try:
            seen: set[str] = set()
            for date_posted, window in SEARCH_WINDOWS:
                payload = client.search_posts(
                    account_id=args.account_id.strip(),
                    keywords=keywords,
                    count=count,
                    start=args.start,
                    date_posted=date_posted,
                )
                raw_posts = payload.get("posts")
                filtered = filter_hiring_posts(
                    raw_posts if isinstance(raw_posts, list) else [],
                    job_role,
                )
                unique: list[HiringPost] = []
                for post in filtered:
                    key = _post_key(post)
                    if key in seen:
                        continue
                    seen.add(key)
                    unique.append(post)
                grouped_raw[window] = unique
        finally:
            client.close()
    except (ConnectSafelyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not any(grouped_raw.values()):
        print(format_posts({"last 24 hours": [], "last 7 days": []}, job_role=job_role))
        return 0

    hiring_judge = judge
    owns_judge = hiring_judge is None
    if hiring_judge is None:
        if not settings.typesafe_api_key:
            print("TYPESAFE_API_KEY is not configured", file=sys.stderr)
            return 1
        hiring_judge = TypeSafeHiringJudge(
            settings.typesafe_api_key,
            base_url=settings.typesafe_base_url,
            model=settings.jev_model,
            timeout_seconds=settings.typesafe_timeout_seconds,
        )

    try:
        grouped_kept = {
            window: gate_window(posts, hiring_judge, threshold=settings.jev_threshold)
            for window, posts in grouped_raw.items()
        }
    finally:
        closer = getattr(hiring_judge, "close", None) if owns_judge else None
        if callable(closer):
            closer()

    if not any(grouped_kept.values()):
        print(format_posts({"last 24 hours": [], "last 7 days": []}, job_role=job_role))
        return 0

    field_parser = parser
    if field_parser is None:
        if not settings.openai_api_key:
            print("OPENAI_API_KEY is not configured", file=sys.stderr)
            return 1
        field_parser = OpenAIHiringParser(settings.openai_api_key, settings.openai_model)

    grouped = {
        window: extract_window(posts, field_parser) for window, posts in grouped_kept.items()
    }
    print(format_posts(grouped, job_role=job_role))
    return 0


def main() -> None:
    raise SystemExit(run())
