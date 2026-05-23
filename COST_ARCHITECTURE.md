# Cost-Optimized Architecture for 30K/month

This document explains the model routing, batching, and caching strategy that brings per-lead Claude cost from ~$0.04 down to ~$0.008.

## Per-Lead Cost Target

| Step | Model / Service | Cost per lead |
|------|------|------|
| Website scrape | Playwright (local) | $0.000 |
| LinkedIn enrichment | Apify | $0.008 |
| Fit analysis (filter step) | **Haiku 4.5 with prompt caching** | $0.0006 |
| Email generation (kept leads) | **Sonnet 4.6 batch API** | $0.0030 |
| Script generation (kept leads) | **Sonnet 4.6 batch API** | $0.0020 |
| TTS | **OpenAI TTS-1 ($15/M chars)** | $0.0090 |
| Cloudflare R2 + Pages | Cloudflare | $0.0010 |
| **Total per processed lead** | | **~$0.025** |
| **Total per kept lead (after filtering)** | | **~$0.024** |

At 30K leads/month with ~85% kept rate (broader ICP, looser filter): **~$720/month** in API costs.

## Why This Is Right for 30K Volume

### 1. Use Haiku for the kill step, not Opus

The fit analysis stage is a **classification task**: skip or keep, score the fit, write a hook. Haiku 4.5 handles this category extremely well. It's 5x cheaper than Opus on input and output. At 30K leads/month, that's the difference between $300/month and $60/month for the same step.

When to use Opus or Sonnet for analysis: never, for cold outreach at this volume. Save the premium models for the writing tasks.

### 2. Use Sonnet 4.6 for email + script generation, not Opus

Cold email writing is well within Sonnet's capability. Sonnet 4.6 is 40% cheaper than Opus per token, generates faster, and produces emails that are essentially indistinguishable in blind A/B tests at this length (under 100 words). For the video script, same story — Sonnet is fine.

When to use Opus: never, for this pipeline. The quality lift on a 90-word email isn't measurable.

### 3. Aggressive prompt caching on the analysis stage

The analysis prompt has a stable ~3,000-token system prompt (business context, ICP rules, vertical detection logic, intent signals). At 30K leads/month, that's 90M input tokens that would be re-read on every call.

With caching:
- First call: pays full price (1.25x for cache write)
- Every subsequent call within 5 minutes: pays 10% of input price
- At cache hit rate >95%, effective input cost drops by ~85%

How to do it: add a single `cache_control: {type: "ephemeral"}` field on the system message in the API call. The Anthropic SDK handles the rest.

### 4. Batch API for email + script generation

The Batch API gives a flat 50% discount on both input and output tokens, in exchange for async processing (results in minutes to hours). For cold outreach, you don't need real-time generation — you queue tonight's batch, it processes overnight, you push to Smartlead in the morning.

This stacks with prompt caching. The combined discount can hit ~80% off the standard rate.

### 5. OpenAI TTS instead of ElevenLabs

ElevenLabs Turbo at $0.18 per 1K chars = $0.05 per 45-second video.
OpenAI TTS-1 at $15 per 1M chars = $0.009 per 45-second video.

At 30K videos/month, that's $1,500 vs $270 — a $1,230/month savings.

Quality difference: ElevenLabs is slightly more natural on edge cases, but for a 50-second cold-outreach script with a stock voice, OpenAI's `alloy`, `echo`, or `onyx` voices are indistinguishable to recipients. We use OpenAI TTS-1 with the "echo" voice (warm, conversational male) by default.

If you want to upgrade specific high-priority leads to ElevenLabs, the system supports per-lead voice override.

## Implementation Notes for Claude Code

When building the modules, the following changes apply vs. the original spec:

1. **`src/analysis/fit_analyzer.py`** — uses `claude-haiku-4-5-20251001`. Always sets `cache_control` on the system prompt block.

2. **`src/email/generator.py`** and **`src/video/script/builder.py`** — use `claude-sonnet-4-6`. For runs >100 leads, queue requests via the Batch API instead of synchronous calls. Build a `BatchRunner` in `src/utils/batch_runner.py` that submits a batch, polls for completion, parses results, retries failures.

3. **`src/video/tts/`** — rename `elevenlabs_client.py` to `tts_client.py` and implement an adapter pattern. Default backend: OpenAI TTS-1. Optional backend: ElevenLabs (for premium leads). Voice config in `settings.yaml`.

4. **Cost ledger** — track which model + which API mode (sync vs batch, cached vs not) produced each cost line. This makes it easy to spot regressions.

5. **Volume-aware orchestrator** — when processing >500 leads in one run, automatically switch from sync to batch mode for email + script. Below 500, sync is fine and faster end-to-end.

## What Doesn't Change

- Playwright website scraping (free, runs locally)
- FFmpeg compositing (free, runs locally)
- Cloudflare R2 for hosting (already cheapest)
- Smartlead for sending (your existing infrastructure)
- The pipeline structure, retry logic, ledger, resume

## What This Buys You

| Volume | Old monthly cost | New monthly cost | Savings |
|--------|------|------|------|
| 2K leads/month | $220 | $50 | $170 |
| 10K leads/month | $1,110 | $250 | $860 |
| 30K leads/month | $3,330 | $720 | **$2,610** |

The savings scale linearly with volume, which is exactly when you need them.
