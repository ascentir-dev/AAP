# THE PLAYBOOK — Best-Case Strategy for High-Intent AI-Automation Leads

This is the canonical "how this system works and why it's structured this way" doc. Read this before doing anything else.

## Your Setup (What's True About Your Pipeline)

- **Lead source:** High-intent database (companies that signaled interest in AI automation, AI integration, AI sales integration)
- **Pre-filter:** 100+ employees, AI-automation interest
- **Volume target:** 30,000/month (with phased ramp — see below)
- **Sending infrastructure:** 40-60 warmed inboxes across multiple domains, via Smartlead
- **Offer:** 14-Day Command Brief (refundable, board-ready operational diagnostic)
- **Underlying product:** Ascentir (Atlas + AAP + AROS + Sentinel)

## The Core Strategic Choice

Your leads are pre-qualified for AI-automation interest, BUT the Ascentir document is positioned for $200K-$450K Operating Partnerships sold to CROs at $200M companies. Most of your 30K leads won't fit that exact ICP shape — but they ALL fit the broader "we want AI automation that works" intent.

**The resolution:** Don't pitch Ascentir in the cold email/video. Pitch the **14-Day Command Brief** — a refundable, board-ready operational diagnostic. Refundable in full if it isn't the most useful document they've read in 12 months (this is already in your Ascentir Triple Guarantee).

This works because:
1. **It's a real deliverable, not a demo request.** "Get a board-ready diagnostic" is concrete and valuable.
2. **It's refundable.** Risk-free for the buyer is a power move at this volume.
3. **It pre-qualifies the buyer.** Someone willing to engage on a Brief is closer to platform-buying readiness than someone who clicked "schedule demo."
4. **It scales across verticals.** A B2B SaaS Brief and a Manufacturing Brief look different in content but identical in structure — same offer, different examples.
5. **It bridges to the platform sale.** After the Brief, those who fit Ascentir's ICP convert to the full Operating Partnership. Those who don't, you've still made money on the Brief and gotten a customer who will refer.

## The Volume Ramp (Critical — Do Not Skip)

### Month 1: 5,000 leads
**Goal:** Validate the whole pipeline end-to-end on real leads with real replies.
- Run on 100 leads first, manually review every email + video before pushing to Smartlead. Iterate prompts until 80%+ feel right.
- Run on 500 leads next, push live, measure: open rate, reply rate, video click-through, booked call rate.
- Run remaining 4,400 leads with adjustments based on what you learn.
- Cost: ~$120 in API + Smartlead subscription.

**Decision gate at end of month 1:** Did it produce booked calls? If yes → scale. If no → debug before scaling.

### Month 2: 12,000 leads
**Goal:** Scale what works, kill what doesn't.
- Identify which verticals replied best, which angles worked, which hooks landed. Lean into them.
- A/B test subject lines, video CTA timing, the fixed second half wording.
- Cost: ~$290 in API + Smartlead subscription.

### Month 3+: 30,000 leads
**Goal:** Steady-state operation.
- Cost: ~$720 in API + Smartlead subscription.
- Expected output (industry benchmarks for high-intent + personalized video at this scale):
  - Open rate: 35-50%
  - Reply rate: 1.5-3%
  - Booked-call rate of replies: 20-30%
  - Booked calls/month: ~150-300
  - Brief conversions of calls: ~30-50%
  - Briefs sold/month: ~50-150
  - Brief → Platform conversions: ~10-25%
  - **New Ascentir Operating Partnerships/month: ~5-15**

At Ascentir's $75K-$450K price point, even 3 new partnerships/month is an extraordinary outcome at $720 in monthly API costs.

## How the Personalization Works (The Why Behind Every Beat)

The personalized video is doing 4 jobs in 55 seconds:

1. **Prove I'm not mass-blasting** — by showing their website on screen and saying so out loud (Beat 2). Without this, the video format wastes its main psychological asset.
2. **Prove I actually looked at their stuff** — by referencing something specific to THEM in Beat 3 (the hook from analysis).
3. **Connect their situation to a real problem AI automation solves** — Beat 3 also does this, by tying the observation to a likely pain.
4. **Make the offer impossible to lose on** — refundable Brief, "leave your card at home," low-pressure call (in the fixed second half).

Every beat does specific work. The script prompt encodes this explicitly so the AI can't accidentally skip a beat.

## Vertical-Aware Personalization

The analysis stage detects 13 possible verticals (B2B SaaS, Cybersecurity, FinTech, E-commerce, Agency, Professional Services, Manufacturing, Healthcare, PropTech, EdTech, Logistics, Other B2B, Other). The script prompt has tuned proof-points and observation-pattern examples for each major vertical.

What this means in practice: a CRO at a B2B SaaS company gets "your post about pipeline + we cut SDR ramp time" — a COO at a manufacturing company gets "your new facility + multi-site ops visibility gap." Same structure, different content.

The email prompt has matching vertical awareness via the `recommended_angle` field — which Ascentir capability to lead with (AAP outbound, AAP inbound, AAP sales ops, AROS, Atlas, Full platform).

## The Cost Architecture (~$720/month at 30K)

| Step | Service | Cost/lead | 30K/month |
|------|---------|-----------|-----------|
| Website scrape | Playwright (local) | $0 | $0 |
| LinkedIn enrichment | Apify | $0.008 | $240 |
| Fit + hook analysis | Claude Haiku 4.5 (cached) | $0.0006 | $18 |
| Email generation | Claude Sonnet 4.6 (batch) | $0.0030 | $90 |
| Script generation | Claude Sonnet 4.6 (batch) | $0.0020 | $60 |
| Voiceover | OpenAI TTS-1 (echo voice) | $0.0090 | $270 |
| Video hosting | Cloudflare R2 + Pages | $0.0010 | $30 |
| **Total** | | **$0.024** | **~$708** |

Plus Smartlead subscription (~$200/month at this volume).

## What's Different vs. The First Version of This System

1. **Models routed by task** — Haiku for cheap classification, Sonnet for quality writing. Opus is gone.
2. **OpenAI TTS instead of ElevenLabs** — same quality on stock voices, 70% cheaper.
3. **Prompt caching + Batch API** — 80% cheaper at scale.
4. **No hard ICP gate** — leads come pre-qualified, so analysis focuses on personalization quality, not fit gating.
5. **Vertical-aware prompts** — same structure, vertical-tuned proof points.
6. **Frank Frederico Loom beats encoded** — Beat 1-4 explicit in the script prompt. Beat 2 (the "real human" line) is non-negotiable because it's why the video format works.
7. **Offer changed from full Ascentir platform to 14-Day Command Brief** — better cold-email offer, scales across the broader ICP.
8. **Video duration bumped from 38s to 55s** — Frank's pattern needs the room.
9. **CTA color is red** — script literally says "click the red button," visual must match.
10. **Volume ramp documented** — don't blast 30K in month 1.

## What You Need to Do Before Running

1. **Replace "Frank" with your real name** in `settings.yaml > your_identity` if it isn't Frank.
2. **Replace "Ascentir" with your company name** if needed (in `settings.yaml`, in the prompts, in the example sign-offs).
3. **Read the fixed_second_half** in `settings.yaml` aloud. If a single word doesn't sound like you'd actually say it, change it. This is your pitch — it needs to be in your voice.
4. **Review the proof points** in `prompts/email.md` — the percentages and claims (50% below mid-market, 17 hours speed-to-lead, 5% retention = 25-95% profit) come from your Ascentir master document. Confirm they're accurate to what you can deliver.
5. **Drop your headshot** at `assets/corner_image.png` (square, 512x512 PNG, looking at camera, smiling).
6. **Set up Cloudflare R2 + Pages** for video hosting (~10 min one-time).
7. **Set up your Smartlead campaign** with `{{custom_subject}}` and `{{custom_body}}` template variables.
8. **Get all API keys** in `.env.example`.
9. **Open Claude Code in the project folder** and paste the prompt from `MASTER_CLAUDE_CODE_PROMPT.md` — this builds out the 11 stub modules.
10. **Run on 1 test lead with `--dry-run`** before anything else.

## A Final Honest Note

This system, executed well, will produce real results. It will not produce miracles. The ceiling of cold outreach to senior buyers is real — even with perfect personalization, you'll get a 1-3% reply rate. The math works because of cost discipline and volume, not because of magic conversion rates.

The biggest risks at 30K/month:
1. **Domain reputation burn** if you skip the warm-up period or send too fast per inbox. Stick to 20-30 sends/inbox/day max.
2. **Hallucinated facts** if the analysis prompt fails on edge cases. Spot-check the first 100-200 leads' generated emails before going wide.
3. **Smartlead deliverability flagging unique URLs.** Mitigation: Cloudflare R2 + custom subdomain (e.g., go.yourdomain.com) is a single domain that all unique paths live under — looks much cleaner than 30K random URLs to spam filters.

You'll know the system is working when: replies are coming in within 24 hours of send batches, reply tone is "interested" not "unsubscribe," and a meaningful fraction of replies turn into booked calls.

Ramp slowly. Read the outputs. Iterate the prompts. The prompts are the source of all quality.
