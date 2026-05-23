# Agentic Acquisition Platform

AI-powered outbound acquisition system by Ascentir. Two fully independent systems sharing a common infrastructure layer and dashboard.

---

## Systems

### ✉️  AI Cold Email — `src/ai_cold_email/`
Personalized cold email + video pipeline at 30K leads/month.
- Scrapes each lead's website → AI generates a personalized 55-sec scroll video
- 9 A/B variant email frameworks running simultaneously (Berman, AIDA, PAS, BAB, etc.)
- Pushes to Smartlead campaigns with motion-aware copy
- Target cost: ~$0.024/lead

**Entry point:** `python -m src.ai_cold_email.orchestrator`

### 📱  SMS — `src/sms/`
Personalized outbound SMS with 3-number rotation and two-way inbox.
- 6 reply-optimized variants (under 160 chars, no opener filler)
- Deterministic number assignment — same lead always texts same number
- Inbound webhook → reply directly from the dashboard
- Completely separate database and analytics from email

**Entry point:** managed via Dashboard

---

## Shared Infrastructure

| Module | Purpose |
|---|---|
| `src/analysis/` | Lead fit analysis — used by both pipelines |
| `src/analytics/` | A/B stats, variant assignment, significance testing |
| `src/dashboard/` | FastAPI + React web dashboard |
| `src/enrichment/` | Website scraper + LinkedIn enrichment |
| `src/hosting/` | Cloudflare R2 video upload + landing pages |
| `src/ingestion/` | CSV reader for lead lists |
| `src/utils/` | Settings, ledger, cost tracker, template store |
| `src/webhooks/` | Smartlead + Calendly inbound webhooks |

---

## Dashboard

```bash
python -m src.dashboard
# Open http://localhost:8000
```

Pages: Email Dashboard · Leads · Pipeline · Cost Tracker · SMS Dashboard · SMS Conversations · Playbook

---

## Quick Start

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env          # fill in API keys
python -m src.dashboard       # launch dashboard
```

---

## Structure

```
agentic-acquisition-platform/
├── src/
│   ├── ai_cold_email/       ← Email + video pipeline
│   │   ├── email/           · AI generator (9 variants)
│   │   ├── video/           · Scroll recorder + FFmpeg + TTS
│   │   ├── smartlead/       · Smartlead API client
│   │   └── orchestrator/    · Async pipeline runner
│   ├── sms/                 ← SMS pipeline
│   │   ├── generator.py     · AI SMS (6 variants)
│   │   ├── sender.py        · Twilio + number rotation
│   │   ├── ledger.py        · SMS-only SQLite
│   │   └── conversation.py  · Inbound + dashboard replies
│   ├── analysis/            ← Shared
│   ├── analytics/           ← Shared
│   ├── dashboard/           ← Shared
│   ├── enrichment/          ← Shared
│   ├── hosting/             ← Shared
│   ├── ingestion/           ← Shared
│   ├── utils/               ← Shared
│   └── webhooks/            ← Shared
├── prompts/
│   ├── ai_cold_email/       ← analysis.md, email.md, script.md
│   └── sms/                 ← sms.md
├── config/
│   ├── settings.yaml        ← All config + A/B test definitions
│   └── templates.yaml       ← Playbook editor writes here
├── frontend/            ← React dashboard source
├── tests/
│   ├── ai_cold_email/       ← Email system tests
│   └── sms/                 ← SMS system tests
└── data/
    ├── input/               ← Drop lead CSVs here
    └── output/              ← Generated videos
```
