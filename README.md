# Scout-Jevhire

Scout-Jevhire finds real open roles on LinkedIn and filters out the noise. Point it at a job title; it scouts recent posts, uses **Jev** to keep only true employer and recruiter hiring ads, and surfaces what teams need to act on hiring opportunities faster.

## Why Jev

Keyword search on LinkedIn is loud. A query like `AI Engineer hiring` mixes:

- employers and recruiters posting open roles
- candidates looking for work
- people talking *about* hiring

**Jev** is the judgment layer. It scores each post against a clear question and keeps only real job ads. That is what makes Scout-Jevhire useful: less noise, more signal, before any extraction runs.

Question Jev answers:

> Is this an employer or recruiter advertising an open job, not a candidate seeking work, and not a comment about hiring?

Default keep line: probability **≥ 0.75**.

## How it works

```text
job role + LinkedIn account
        │
        ▼
ConnectSafely search  (last 24 hours, then last 7 days)
        │
        ▼
Role filter  (title + close variants)
        │
        ▼
Jev gate  ← keep true hiring ads
        │
        ▼
Contact tags + GPT field extract
        │
        ▼
Structured hiring opportunities
```

## What you get

For each kept post:

| Field | Meaning |
|---|---|
| `source_url` | LinkedIn post URL |
| `post_kind` | email, apply link, both, or none |
| `hiring_role` | Role being hired |
| `location` | Where the role is |
| `skills` | Skills called out in the post |
| `requirements` | Experience / must-haves |
| `job_description` | Short description |
| `email` / `apply_url` | How to apply, when present |

## Setup

Requires Python 3.11+.

```bash
git clone https://github.com/Ujjawal99711/Scout-Jevhire.git
cd Scout-Jevhire
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env
```

Fill `.env` locally. **Never commit `.env` or real API keys.**

| Variable | Used for |
|---|---|
| `CONNECTSAFELY_API_KEY` | LinkedIn post search |
| `TYPESAFE_API_KEY` | Jev hiring judge |
| `OPENAI_API_KEY` | Field extraction |

## Run

Live scout (ConnectSafely + Jev + GPT):

```bash
python -m hr_posts --account-id YOUR_ACCOUNT_ID --job-role "AI Engineer"
```

Optional flags: `--limit` (posts per window, default 20), `--start` (pagination offset).

Jev-only demo (no ConnectSafely or OpenAI — great for showing the filter):

```bash
cp demo_posts.example.json demo_posts.json
python -m hr_posts.demo --posts demo_posts.json
```

## Security

- Secrets stay in local `.env` or your own secret store
- `.env` is gitignored; only `.env.example` (placeholders) is in the repo
- The CLI does not log API keys
- `source_url` is never sent to Jev as content for scoring

## Tests

```bash
pytest
```

Tests mock providers and do not call live APIs.

## Docs

See [HIRING_POSTS_PRD.md](HIRING_POSTS_PRD.md) for the full live pipeline (search → filter → Jev → extract).
