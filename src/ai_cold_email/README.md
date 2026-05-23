# AI Cold Email System

Part of the Agentic Acquisition Platform. Generates personalized cold emails + videos at scale.

## How it works

1. **Ingest** — reads lead CSV (`src/ingestion/`)
2. **Enrich** — scrapes lead's website for company signals (`src/enrichment/`)
3. **Analyze** — Claude Haiku classifies fit, motion, and personalization hook (`src/analysis/`)
4. **Assign** — selects one of 9 A/B variant arms (`src/analytics/`)
5. **Generate email** — Claude Sonnet writes variant-specific copy (`email/`)
6. **Generate video** — records scroll of lead's website, adds TTS voiceover + CTA overlay (`video/`)
7. **Host** — uploads video to Cloudflare R2, generates landing page (`src/hosting/`)
8. **Push** — adds lead to the correct Smartlead campaign (`smartlead/`)

## Entry point

```bash
python -m src.ai_cold_email.orchestrator --csv data/input/leads.csv
python -m src.ai_cold_email.orchestrator --csv data/input/leads.csv --dry-run
python -m src.ai_cold_email.orchestrator --csv data/input/leads.csv --single-lead 0
```

## A/B Test Variants

9 variants running in `config/settings.yaml` under `variants.framework_tournament_v1`:

| ID | Framework | Description |
|---|---|---|
| Variant 1 | PPP — Warm + Risk Reversal | Long form, pay-on-results |
| Variant 2 | PPP — Compact | Under 80 words, senior buyers |
| Variant 3 | PPP + Social Proof | Average lift stat injected |
| Variant 4 | AIDA | Niche authority + direct ask |
| Variant 5 | Berman 3Cs | Compliment + case study + CTA |
| Variant 6 | QVC | Shortest — under 65 words |
| Variant 7 | Suby Authority | Aggregate proof numbers |
| Variant 8 | Inverted Demand | Scarcity / heads-up framing |
| Variant 9 | PAS | Problem / agitate / solve |

## Prompts

All AI prompts live in `prompts/ai_cold_email/`:
- `analysis.md` — lead fit + hook generation instructions
- `email.md` — email generation with all 9 variant templates
- `script.md` — video voiceover script generation
