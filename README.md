# Agentic Acquisition Platform (AAP)
### AI-Powered Cold Outbound System — Built for Ascentir

> **Current status — June 2026:** Phase 1 (personalisation) is fully working and actively processing leads. Phase 2 (Smartlead push) is ready but **requires Smartlead campaign setup before activating** — see [Smartlead Setup](#smartlead-setup) below.

---

## What This System Does

AAP automates the entire cold outbound pipeline from CSV → personalised email → Smartlead:

1. **Ingests** a CSV of leads (skiptrace exports or any source)
2. **Enriches** each lead — scrapes their website, pulls LinkedIn data
3. **Analyses** fit, detects market/vertical/acquisition mode, scores intent 1–10
4. **Routes** based on intent score:
   - **Score 8–10** → Full video pipeline (ElevenLabs cloned Frank voice + personalised screen-recording video)
   - **Score 1–7** → Email-only (no video, no TTS cost — just a personalised cold email)
5. **Generates** a personalised cold email using one of 9 variants × 5 market templates (Dan Kennedy copywriting)
6. **Pushes** to Smartlead campaign for automated multi-step follow-up sending

**The offer in every email:** 120 qualified appointments in 90 days. Done-for-you. Pay on results only.

**The CTA in every email:**
> *Reply VIDEO and I'll send you a personalized demo of the AI Client Acquisition System showing exactly how we'll book {company} 120 appointments in 90 days. No call, no pitch. Just the demo.*

---

## Architecture Overview

```
CSV Upload
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 1 — Personalise (dry_run=True)                   │
│                                                         │
│  1. Website scrape (Playwright)                         │
│  2. LinkedIn enrichment                                 │
│  3. AI Analysis (Claude) → market, intent score, hook   │
│  4. Variant assignment (deterministic hash-based A/B)   │
│  5. Email generation (Claude Sonnet) — 9 variants       │
│  6. [Score ≥8 only] TTS — ElevenLabs cloned Frank voice │
│  7. [Score ≥8 only] Scroll recording (Playwright)       │
│  8. [Score ≥8 only] Video composite (FFmpeg)            │
│  9. [Score ≥8 only] Upload to Cloudflare R2             │
│  10. Save all stages to ledger.sqlite                   │
└─────────────────────────────────────────────────────────┘
    │
    ▼  (review in Leads dashboard, delete any unwanted)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 2 — Push to Smartlead (dry_run=False)            │
│                                                         │
│  Reads cached stages from ledger.sqlite (no AI calls)   │
│  Video leads: injects thumbnail image into email body   │
│  Email-only: injects Reply VIDEO CTA block              │
│  Pushes personalised email to Smartlead campaign        │
│  Smartlead handles send scheduling + follow-up sequence │
└─────────────────────────────────────────────────────────┘
```

### Key Design Principles
- **Stage caching** — every AI/generation stage is stored in `ledger.sqlite`. Re-running a batch picks up exactly where it left off. No re-billing for completed stages.
- **Lead deduplication** — lead ID is SHA-256 of the email address. Same email across different CSVs = same ID = same cache. Already-personalised leads are never reprocessed.
- **Intent gating** — `video.intent_threshold: 8` in `settings.yaml`. Score <8 skips video/TTS entirely, saving ~$0.162/lead in ElevenLabs costs.
- **Company name cleaning** — legal suffixes (Inc., LLC, Ltd., Corp., etc.) are automatically stripped from company names before any AI stage so emails always read naturally.

---

## Directory Structure

```
/
├── config/
│   ├── settings.yaml          # All system config (thresholds, models, campaigns, A/B test)
│   ├── templates.yaml         # 9 email variants × 5 markets (hand-crafted Kennedy copy)
│   └── video_scripts.yaml     # 4 video script variants for high-intent leads
│
├── prompts/ai_cold_email/
│   ├── analysis.md            # Lead analysis prompt (market detection, intent scoring, skip logic)
│   ├── email.md               # Email generation prompt (9 variants, video vs email-only mode)
│   └── script.md              # Video voiceover script prompt
│
├── src/
│   ├── ai_cold_email/
│   │   ├── email/generator.py       # Claude Sonnet email generation with has_video flag
│   │   ├── orchestrator/pipeline.py # Main pipeline — all stages in order
│   │   ├── smartlead/client.py      # Smartlead API push
│   │   └── video/
│   │       ├── tts/tts_client.py    # ElevenLabs (≥8) / Edge TTS (<8) routing
│   │       ├── scroll/recorder.py   # Playwright website screen recording
│   │       └── composite/           # FFmpeg video assembly + browser frame overlay
│   ├── dashboard/__main__.py        # FastAPI backend — all API endpoints + static serving
│   ├── enrichment/
│   │   ├── website.py               # Playwright website scraper
│   │   └── linkedin.py              # LinkedIn data enrichment
│   ├── analysis/fit_analyzer.py     # Claude Haiku analysis stage
│   └── utils/
│       ├── ledger.py                # SQLite stage cache + lead metadata
│       ├── settings.py              # Pydantic settings loader (.env + settings.yaml)
│       └── cost_tracker.py          # Per-lead cost accounting
│
├── frontend/src/pages/
│   ├── PipelinePage.tsx       # Upload CSV, run Phase 1 & 2, live activity feed, progress bar
│   ├── LeadsPage.tsx          # Browse all leads, preview emails, delete before push
│   ├── PlaybookPage.tsx       # Edit templates per ICP, Video/Email-Only mode toggle
│   ├── DashboardPage.tsx      # Analytics overview
│   └── CostsPage.tsx          # Cost breakdown by provider and stage
│
├── assets/
│   ├── frank.jpg              # Frank's face — used in video corner overlay
│   └── frank_alt.jpg
│
├── tools/                     # One-off setup scripts (R2, Smartlead, voice clone)
├── .env.example               # Copy to .env and fill in API keys
├── .env                       # API keys — NEVER commit this (gitignored)
├── ledger.sqlite              # All lead data and cached stages (gitignored)
└── start.sh                   # Always use this to launch
```

---

## Setup on a New Machine

### 1. Prerequisites
```bash
# macOS
brew install python@3.11 node ffmpeg

# Playwright browser
pip install playwright
playwright install chromium
```

### 2. Clone & Install
```bash
git clone https://github.com/ascentir-dev/AAP.git
cd AAP

# Python dependencies
pip install -r requirements.txt

# Frontend
cd frontend
npm install
npm run build
cd ..
```

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env with your actual API keys
```

**Required keys in `.env`:**
```env
# AI Models
ANTHROPIC_API_KEY=sk-ant-api03-...        # Claude — analysis + email generation
ELEVENLABS_API_KEY=...                     # ElevenLabs — cloned Frank voice (score ≥8 only)
ELEVENLABS_VOICE_ID=...                    # Your cloned voice ID

# Outbound
SMARTLEAD_API_KEY=...                      # Smartlead API key
SMARTLEAD_CAMPAIGN_ID=...                  # Campaign ID (see Smartlead Setup below)

# Hosting (Cloudflare) — for video leads only
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_R2_BUCKET=...
CLOUDFLARE_WORKER_URL=...                  # Video tracking worker URL
BASE_URL=...                               # Landing page base URL

# Calendar
BOOK_A_CALL_URL=https://calendly.com/...   # Frank's Calendly link
```

> ⚠️ **CRITICAL:** Never export API keys in `~/.zshrc` or `~/.bashrc`. Pydantic prioritises real env vars over `.env` — a stale key in your shell profile will silently override `.env`. The `start.sh` script runs `unset ANTHROPIC_API_KEY` to prevent this, but the safest approach is to never set these in your shell profile at all.

### 4. Launch
```bash
bash start.sh
# Dashboard opens at http://localhost:8000
```

---

## The Pipeline in Detail

### Phase 1 — Personalise
Click **"✨ Personalise Leads"** in the Pipeline tab. Runs `dry_run=True` — nothing is sent to Smartlead.

| Stage | What happens | ~Cost |
|-------|-------------|-------|
| Website scrape | Playwright fetches the lead's website | Free |
| LinkedIn enrichment | LinkedIn profile data | Free |
| AI Analysis | Claude scores intent 1–10, detects market, writes personalised hook | ~$0.002 |
| Variant assignment | Deterministic hash assigns 1 of 9 email variants | Free |
| Email generation | Claude writes the full personalised email | ~$0.011 |
| TTS *(score ≥8 only)* | ElevenLabs generates cloned Frank voiceover | ~$0.162 |
| Scroll recording *(score ≥8 only)* | Playwright records 30s of their website | Free |
| Video composite *(score ≥8 only)* | FFmpeg: scroll + face circle + audio + browser frame | Free |
| R2 upload *(score ≥8 only)* | Video + thumbnail → Cloudflare R2 | ~$0.001 |

**Cost per lead:**
- Email-only (score 1–7): **~$0.013**
- Full video (score 8–10): **~$0.176**

### Phase 2 — Push to Smartlead
Click **"🚀 Push to Smartlead"**. Reads cached stages — no new AI calls.
- Video leads: `{VIDEO_LINK}` replaced with clickable thumbnail image linking to the personalised video
- Email-only leads: `{VIDEO_LINK}` replaced with the Reply VIDEO CTA text block
- Each lead pushed to Smartlead with `custom_subject` and `custom_body` set

---

## The 5 Target Markets

| Market key | Business Type | CTA Metric | Core Pain |
|-----------|--------------|-----------|----------|
| `coach` | High-ticket coaches & training firms | Discovery calls | Inconsistent enrollments, launch fatigue |
| `agency` | Marketing & advertising agencies | New-biz calls | Founder-led new biz, feast-or-famine MRR |
| `consultant` | Strategy / ops / fractional advisory | Intro calls | BD falls on principals, referral-dependent |
| `financial_advisor` | Financial advisory / fractional CFO | Prospect meetings | Referral ceiling, compliance constraints |
| `msp` | MSPs & B2B cybersecurity | Prospect calls | Relationship-based, no systematic outbound |

`other` = doesn't fit any market → generic templates, `skip=false`.

### Skip Criteria
**Only 1 hard disqualifier:** confirmed registered nonprofit / government agency / trade association with zero commercial arm.

Everything else gets an email. Current skip rate: ~5%.

---

## The 9 Email Variants

| # | Framework | Words | Character |
|---|-----------|-------|-----------|
| V1 | PPP Full — Praise / Picture / Push | 130–160w | Warm, risk-reversal heavy, "Best part: if calls don't land, you don't pay" |
| V2 | PPP Compact Warm | 70–90w | Opens with personalised hook + pain observation directly |
| V3 | PPP + Average-Lift Proof | 100–130w | "First: {company} looks great" + benchmark number |
| V4 | AIDA — Niche Authority | 80–100w | "Strong ties here" + specific industry pain wall |
| V5 | 3 Cs — Case Studies (Berman) | 90–120w | 3 specific bullet case studies, "qualifies to be next" |
| V6 | QVC — Question / Value / CTA | 45–65w | Shortest possible, one conditional question + CTA |
| V7 | Demand Flip | 85–110w | Frames Frank as having demand to route to partners |
| V8 | Inverted Demand / Scarcity | 85–110w | "2 new [market] partners this quarter — 1 spot open" |
| V9 | PAS — Problem / Agitate / Solve | 95–120w | "Honest observation about {company}:" + agitation |

Variants are assigned by `SHA-256(lead_id) % 9` — deterministic, stable across runs.

### Editing Templates
**Playbook** tab → filter by ICP → expand variant → Edit Template → Save. No restart needed.

---

## Smartlead Setup

> ⚠️ **This must be done before Phase 2. If Step 1 is missing or campaign is not ACTIVE, pushes will appear to succeed but leads will receive the wrong email.**

### Campaign Sequence
1. Open Smartlead → Campaign ID (from `.env`)
2. **Add Step 1 — Day 0:**
   - Subject: `{{custom_subject}}`
   - Body: `{{custom_body}}`
3. **Add Step 2 — Day 4 (follow-up):**
   ```
   Subject: re: {{custom_subject}}

   Hey {{first_name}}, just wanted to bump this up in case it got buried.

   Reply VIDEO and I'll send the demo. Takes 60 seconds.

   Frank
   ```
4. **Add Step 3 — Day 9 (soft exit):**
   ```
   Subject: closing the loop

   Hey {{first_name}}, going to close this out — if the timing isn't right, no hard feelings.

   If {{company}} ever wants to add a systematic outbound engine, you know where to find me.

   Frank
   ```
5. Set campaign to **ACTIVE**
6. Set sending limit: **50 emails/day per email account**

---

## CSV Format

Accepts skiptrace CSV exports. Column mapping (case-insensitive):

| CSV Column | Field | Required |
|-----------|-------|---------|
| `BUSINESS_EMAIL` or `EMAIL` | `email` | ✅ |
| `FIRST_NAME` | `first_name` | ✅ |
| `LAST_NAME` | `last_name` | ✅ |
| `COMPANY_NAME` or `COMPANY` | `company` | ✅ |
| `COMPANY_DOMAIN` or `WEBSITE` | `website` | ✅ |
| `JOB_TITLE` or `ROLE` | `role` | Optional |
| `STATE` | `state` | Optional (V7/V8 territory language) |

---

## Dashboard Reference

| Page | Purpose |
|------|---------|
| **Pipeline** | Upload CSV → Phase 1 → Phase 2. Live activity feed, overall progress bar (X of 6,531) |
| **Leads** | Browse all leads. Filter by Personalised/Skipped/Failed. Click any to preview email. Delete before push. |
| **Playbook** | All 9 email variants, filterable by ICP and Video/Email-Only mode. Edit templates inline. |
| **Analytics** | A/B test results. Variant reply rates. Subject line performance. |
| **Costs** | Per-lead cost breakdown by provider (Claude, ElevenLabs, Cloudflare). |

---

## Cost Summary (Actual — June 2026)

First 100 leads processed:

| Provider | Cost | Share |
|----------|------|-------|
| ElevenLabs (23 video leads) | $3.73 | 91.5% |
| Claude (analysis + email) | $0.34 | 8.4% |
| Cloudflare | $0.01 | <1% |
| **Total** | **$4.07** | |

**Full CSV projection (6,531 leads, ~20% video rate):**
- Claude: ~$85
- ElevenLabs (~1,306 leads): ~$211
- **Total: ~$300 for the full list**

To reduce ElevenLabs cost, raise `elevenlabs_intent_threshold` in `config/settings.yaml` (currently `8`). Setting it to `9` would cut video volume ~50%.

---

## Where I Left Off

### ✅ Completed and working

| Feature | Status |
|---------|--------|
| Two-phase pipeline (personalise → push) | ✅ Working |
| Intent-based routing (video ≥8 / email-only <8) | ✅ Working |
| ElevenLabs / Edge TTS tiering | ✅ Working |
| 45 email templates (9 variants × 5 markets) | ✅ Rewritten with Kennedy copy |
| `Reply VIDEO` CTA in all templates | ✅ Done |
| Company name cleaning (strips Inc., LLC, etc.) | ✅ Done |
| Skip criteria loosened to ~5% (nonprofit/gov only) | ✅ Done |
| All-time progress bar (X of 6,531) | ✅ Done |
| Leads page: "Personalised" label + delete button | ✅ Done |
| Email preview in lead drawer (no raw `{VIDEO_LINK}`) | ✅ Done |
| Playbook: ICP filter + Video/Email-Only toggle | ✅ Done |
| No reprocessing of already-done leads | ✅ Done |
| `{VIDEO_LINK}` removed from all templates | ✅ Done |

### 🔜 Immediate next steps

1. **Fix Smartlead campaign** ← BLOCKING for Phase 2
   - Campaign ID `3379547` is set to COMPLETED and is missing Step 1
   - Add the `{{custom_subject}}` / `{{custom_body}}` sequence (see above)
   - Set to ACTIVE
   - Do 1 test push of a single lead to verify delivery

2. **Process the full 6,531-lead CSV**
   - Upload CSV in Pipeline tab
   - Click "✨ Personalise Leads" in batches of 100
   - Monitor the live feed and progress bar
   - Expected: ~95% personalise, ~5% skip

3. **Review before pushing**
   - Go to Leads tab, filter by "Personalised"
   - Preview a sample of emails — click any lead to open the drawer
   - Delete any that look wrong
   - Then push to Smartlead

4. **Monitor replies**
   - Replies come into Smartlead's inbox
   - Track open/reply rates in the Analytics tab after 50+ sends

### Current DB snapshot
- **54 leads** personalised (ready to push)
- **44 leads** skipped (not a fit)
- **2 leads** failed
- **100 total** processed out of 6,531

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `BadRequestError: credit balance too low` | Stale API key in `~/.zshrc` overriding `.env` | Remove `export ANTHROPIC_API_KEY` from `~/.zshrc`, restart terminal, run `bash start.sh` |
| High skip rate (>10%) | Analysis prompt too aggressive | Edit `prompts/ai_cold_email/analysis.md` Hard Disqualifiers section |
| `{VIDEO_LINK}` showing in emails | Old cached email from before the fix | These get replaced correctly at Phase 2 push time — safe to ignore in preview |
| CSV shows wrong lead count | Embedded newlines in CSV fields | Fixed — system uses `csv.reader`, not `splitlines()` |
| Push returns success but wrong email | Campaign Step 1 not configured | Add `{{custom_subject}}` / `{{custom_body}}` Step 1 in Smartlead |
| ElevenLabs cost too high | Too many leads scoring ≥8 | Raise `elevenlabs_intent_threshold` to `9` in `config/settings.yaml` |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, uvicorn |
| AI | Anthropic Claude Sonnet 4.6 (analysis + email), ElevenLabs (TTS) |
| Browser automation | Playwright (website scraping + video recording) |
| Video | FFmpeg (compositing), Cloudflare R2 (storage + CDN) |
| Frontend | React 18, TypeScript, Vite, Blueprint.js 5 |
| Database | SQLite (`ledger.sqlite`) |
| Email outbound | Smartlead |
| Free TTS fallback | Microsoft Edge Neural TTS (`en-US-AndrewMultilingualNeural`) |
