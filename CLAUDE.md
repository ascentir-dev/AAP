# CLAUDE.md — Project Context for Claude Code

You are Claude Code, helping Frank build a cold-outreach pipeline for Ascentir.

## What This Project Is

Cold-email + personalized-video outbound system. Reads a CSV of high-intent leads
(companies that signaled interest in AI automation, 100+ employees), generates
a personalized cold email + 55-second video for each one, pushes to Smartlead.

Volume target: 30,000/month with phased ramp (5K → 12K → 30K over 3 months).
Per-lead cost target: ~$0.024.

## What's Already Built (Don't Modify These)

- `src/orchestrator/` — async pipeline with retries and resume logic
- `src/video/composite/compositor.py` — FFmpeg layering with circular mask + CTA overlay
- `src/video/scroll/recorder.py` — Playwright smooth scroll capture
- `src/smartlead/client.py` — Smartlead API push
- `src/analytics/` — framework-aware analytics CLI, queries, insights generator, variant assigner
- `src/dashboard/` — FastAPI dashboard at localhost:8000 with HTMX + Chart.js
- `src/webhooks/server.py` — Smartlead + Calendly webhook receiver

## What You Need to Build

12 stub modules. Listed in `MASTER_CLAUDE_CODE_PROMPT.md` with the exact build order.
Build them one at a time, write a pytest test for each, verify the test passes
before moving to the next.

## Critical Files to Read First

In this order, before writing any code:

1. `MASTER_CLAUDE_CODE_PROMPT.md` — your build instructions
2. `PLAYBOOK.md` — the business strategy
3. `FRAMEWORK_RESEARCH.md` — why the email variants are structured the way they are
4. `ANALYTICS.md` — how A/B testing works in this system
5. `COST_ARCHITECTURE.md` — model routing rationale
6. `prompts/analysis.md`, `prompts/email.md`, `prompts/script.md` — the AI prompts the modules call

## Style Rules

- Type hints everywhere
- `httpx` for HTTP, not `requests`
- `tenacity` retries on every external API call (3 attempts, exponential backoff)
- Every API call logs cost via `cost_tracker.log()`
- No `print()` statements — use the `logging` module
- `pytest` tests in `tests/` for every module you build, mirror the source structure

## When You Finish

Report back with:
- Confirmation all 12 modules build and tests pass
- Output of `python -m src.orchestrator --csv data/input/sample_leads.csv --single-lead 0 --dry-run`
- Any decisions you had to make that weren't obvious from the spec
