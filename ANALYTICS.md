# Analytics + A/B Testing Playbook (Framework-Grounded)

## What Changed

This system now tests 9 variants, each grounded in a **documented cold-email framework** from the most-cited books and methodologies in B2B sales:

- *Cold Email Manifesto* (Berman, 2022) — 3C framework + tactical one-sentence
- *Predictable Revenue* (Ross, 2011) — Cold Calling 2.0 referral approach
- Classical AIDA / PAS / BAB / 3Ps copywriting frameworks
- Gym-marketing On/Off frameworks (Risk-Reversal, Inverted Demand)

The tournament tells you which framework works for YOUR ICP — not anyone else's. That's the whole value.

## 2026 Cold Email Reality (Calibrate Expectations)

According to Instantly's 2026 cold email benchmark report analyzing billions of interactions, the overall average reply rate is 3.43% with top performers exceeding 10%.

- Optimal first-email length is 50-125 words; top performers in 2026 keep it under 80 words
- 58% of replies come from email #1 — the first touch IS the main event
- 71% of decision-makers cite "lack of relevance" as the #1 reason they don't reply, 43% say the email feels impersonal, 36% don't trust the sender
- Personalized video drives 2-3x more replies than text-only sequences; combined with deep personalization can hit 10-15% reply rates
- Campaigns with advanced signal-specific personalization achieve 18% reply rates — more than 5x the generic average

Your high-intent database + 9 framework-tested variants + personalized video + motion-aware language puts you firmly in elite-sender territory. Realistic targets:

- **Open rate:** 35-50% (Smartlead campaigns with proper warm-up + verified emails)
- **Reply rate:** 5-10% (top quartile, achievable with this stack)
- **Booked-call rate:** 1-3% of sent (industry top performers)

## The 9 Variants and Their Frameworks

| Variant | Framework | Best Use Case |
|---|---|---|
| 1 | 3C (Berman) — Compliment + Case Study + CTA | High-volume default. Works across motions. |
| 2 | Predictable Revenue Referral (Ross) | When unsure of decision-maker. Self-routes. |
| 3 | AIDA — Attention/Interest/Desire/Action | Strong-hook leads with clear pain. |
| 4 | PAS — Problem/Agitate/Solve | Acute, visible pain only. Skip if hook is positive. |
| 5 | BAB — Before/After/Bridge | Prospects in transition (funding, launch). |
| 6 | 3Ps — Praise/Picture/Push | Senior buyers (VP+, 200+ employees). |
| 7 | One-Sentence (Berman tactical) | Highest reply-per-word. Even "wrong person" replies route the lead. |
| 8 | Inverted Demand / Heads-Up | Scarcity flavor. Flips power dynamic. |
| 9 | Pay-on-Results / Risk-Reversal | For prospects burned by past AI vendors. |

## How Leads Get Assigned

- Hash(`lead_id` + `test_id`) deterministically buckets each lead into one of the 9 arms (~11.1% each).
- Same lead always lands in the same variant.
- The variant's `email_template_id` and `variant_framework` flow into the email prompt.
- The lead is pushed to that variant's specific Smartlead campaign.

## What You See

`python -m src.analytics report`:

```
ACTIVE TEST: framework_tournament_v1 (Day 12 of 30)

VARIANT     FRAMEWORK                              SENT   OPEN%  REPLY%  BOOKED  BOOK%
Variant 1   3C (Berman)                            1,210  42.3   3.1     12      1.0
Variant 2   Predictable Revenue Referral           1,212  44.1   4.8     19      1.6  ← leading
Variant 3   AIDA                                   1,211  41.0   3.2     11      0.9
Variant 4   PAS                                    1,212  39.2   2.4     8       0.7
Variant 5   BAB                                    1,213  43.5   3.4     14      1.2
Variant 6   3Ps                                    1,210  46.0   3.7     15      1.2
Variant 7   One-Sentence                           1,212  48.2   5.1     8       0.7  ← high reply, low book
Variant 8   Inverted Demand                        1,211  41.5   2.9     12      1.0
Variant 9   Pay-on-Results                         1,209  40.0   3.6     13      1.1

Significance vs leader (book_rate):
  Variant 4 (PAS)            p=0.001   leader wins 95%
  Variant 7 (One-Sentence)   p=0.005   leader wins 95% (despite high reply rate)
  Other variants             p>0.05    no significant diff yet

Recommendation: Variant 2 (Predictable Revenue Referral) leading on book rate.
Variant 7 has highest reply rate but lowest book conversion — replies are
mostly "wrong person, try X" routing rather than buying intent.
```

## Why "Reply Rate" and "Booked-Call Rate" Don't Always Agree

This is critical to understanding the data. Phase 1 cuts on **reply rate** because it's the faster signal — you get reply data in days, booked calls take weeks. But the actual money metric is **booked-call rate**.

Variants can win on reply rate but lose on booked-call rate. Variant 7 (one-sentence "are you the right person?") is the clearest example: it generates a TON of replies because almost everyone responds with "yes me" or "no, talk to John." But those replies don't convert to calls at the same rate as Variant 2's deeper Predictable Revenue framework, which produces fewer but higher-intent replies.

**The system shows both metrics so you can make the right tradeoff.** For Phase 1 cuts, weight reply rate more (it's faster + statistically more reliable). For Phase 2 finalist selection, weight booked-call rate more (it's the actual conversion event).

## The Decision Rules

### Cut a variant from further testing when:
1. Variant has 1,500+ sent
2. Reply rate is statistically significantly below the leader (p < 0.05 via two-proportion z-test)
3. The reply quality (when you read 10-20 actual replies) confirms it's not just noise

### Declare a Phase 1 winner when:
1. ALL variants have 1,500+ sent
2. Top 4 variants are clearly separated from bottom 5 by reply rate (and ideally book rate)
3. The leader has at least one secondary signal (book rate, click rate, reply quality)

### Move to Phase 2:
1. Lock the top 4 from Phase 1
2. Set `variants.locked: false`
3. Update `variants.active_test` to `phase_2_finalists`
4. Populate the `phase_2_finalists.arms` block with the 4 surviving variants at 25% weight each
5. Set `locked: true` again
6. Run for another 4 weeks at ~7,500 sends per variant
7. Winner determined by booked-call rate at p<0.05

## What Variant Wins Tells You About Your Buyer

This is the meta-knowledge worth more than the win itself. Because each variant maps to a documented framework, the winning variant tells you what kind of buyer you actually have:

- **Variant 1 wins (3C)** → Your buyers respond to specificity + social proof. Future campaigns lean on case studies.
- **Variant 2 wins (Predictable Revenue)** → Your buyers are inside organizations where the right contact isn't obvious. Future targeting needs better account mapping.
- **Variant 3 wins (AIDA)** → Your buyers know they have a problem. Future campaigns can lead with the pain directly.
- **Variant 4 wins (PAS)** → Your buyers respond to acute pain framing. Future campaigns should agitate the problem more aggressively.
- **Variant 5 wins (BAB)** → Your buyers are aspirational. Future campaigns paint the better future state.
- **Variant 6 wins (3Ps)** → Your buyers want to be respected as peers, not pitched. Future campaigns adopt peer-tone universally.
- **Variant 7 wins (one-sentence)** → Your buyers are time-poor. ALL future emails should drop to under 50 words.
- **Variant 8 wins (Inverted Demand)** → Your buyers respond to scarcity. Future campaigns need supply-constraint framing.
- **Variant 9 wins (Pay-on-Results)** → Your buyers have been burned by vendors. Risk reversal is the unlock.

Whatever wins month 1 reshapes everything you do for months 2-12.

## The AI Insights Module

`python -m src.analytics insights` calls Claude Sonnet 4.6 weekly with:
- Aggregate variant table (9 rows)
- Vertical breakdown per variant
- Motion breakdown per variant (PLG vs hybrid vs sales-led)
- Sample replies (~20 random from past 7 days)
- Sample booked-call payloads

Claude returns 2-4 patterns. Examples:

> **Pattern 1: Variant 2 wins on bookings, but only when the lead is a non-decision-maker.**
> Predictable Revenue Referral books at 1.6% overall — but slicing by role, the wins are concentrated when the lead is a Manager-level (1.9%) vs VP-level (1.2%). The variant excels at routing through orgs, less at converting actual buyers. Suggest: route Director+ leads to Variant 1 (3C) and Manager- leads to Variant 2 (Referral).

> **Pattern 2: Variant 7's reply rate is misleading.**
> One-sentence variant has 5.1% reply rate but 0.7% book rate. Reading 20 random replies: 14 are "talk to X" routing (not buying intent), 4 are "not interested," 2 are buying intent. The variant works AS DESIGNED — it routes — but the routed leads then need a follow-up that isn't being sent. Suggest: add a follow-up sequence specifically for Variant 7 that hits the routed contact with Variant 1 (3C).

> **Pattern 3: PLG companies prefer Variant 5 (BAB), sales-led prefer Variant 9 (Pay-on-Results).**
> Strong split by motion. Suggest: motion-pin variants in Phase 2 — assign PLG leads to Variant 5 and sales-led to Variant 9 by default.

This is the kind of insight that's invisible in Smartlead's native analytics.

## The Weekly Analyst Habit

Every Monday morning, 30 minutes:

1. `python -m src.analytics report --deep` — see per-variant + per-vertical + per-motion
2. Open localhost:8000 dashboard
3. Click "Generate AI Insights"
4. **Read 20 raw replies in Smartlead** (the qualitative signal beats every aggregate)
5. Decide ONE thing: keep running, cut a variant, or refine wording. Don't decide more than one thing per week.

## What This System Refuses To Do

- Run more than 9 variants. Past 9, sample noise dominates.
- Run a new test while another is active.
- Declare a winner before minimum 1,500 sent per variant.
- Test cosmetic things (voice, send time micro-tweaks) — already optimized in 2026 best practice.
- Auto-declare based on early data — all winner decisions are manual, by you.

## Cold-Email Books Worth Reading

If you want to deepen the methodology beyond what's encoded in the prompts:

1. **The Cold Email Manifesto** — Alex Berman, 2022. Most current. The 3C framework, ICP selection, sending system. Read first.
2. **Predictable Revenue** — Aaron Ross, 2011. Still the bible. Read for understanding why we prospect → qualify → close as separate stages.
3. **$100M Offers** — Alex Hormozi, 2021. The offer-engineering framework underneath the email is from Hormozi's value equation. Already encoded in the Ascentir master document.
4. **The Sales Acceleration Formula** — Mark Roberge (HubSpot's first CRO), 2015. Data-driven sales scaling. Read after the first month of running this system.
