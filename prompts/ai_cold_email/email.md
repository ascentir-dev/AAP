# Cold Email Generation Prompt — 9 Variants, Framework-Grounded

You are writing a cold email on behalf of Frank, founder of Ascentir. The recipient is on a high-intent list (their company signaled interest in AI automation, 100+ employees).

The email's job: make them watch the personalized video. The video pitches. The email is the wrapper. The CTA every variant uses is the binary question that drives action: "Open to a quick walkthrough this week?" — not "would you be open to discussing" or "let's connect."

The body MUST contain the literal placeholder `{VIDEO_LINK}` — the system substitutes the personalized video URL there.

## Underlying Frameworks Each Variant Uses

These are the proven cold-email frameworks the variants are built on. You should understand which one drives each variant so you can write within the framework's spirit, not just its surface structure.

| Framework | What it does | Used by |
|---|---|---|
| **PPP — Praise / Picture / Push** | Compliment the prospect → paint a picture of their better state → push them to act | Variants 1, 2, 3 |
| **3 Cs — Compliment / Case study / CTA** (Berman) | Quick compliment → relevant case study → binary CTA | Variant 5, parts of Variant 7 |
| **AIDA — Attention / Interest / Desire / Action** | Hook attention → build interest → create desire → drive action | Variant 4 |
| **QVC — Question / Value / CTA** | Open with question → show value → ask binary question | Variant 6 |
| **Authority / Aggregate Proof** (Suby) | Lead with overwhelming proof, position offer as risk-free | Variant 7 |
| **Inverted Demand / Scarcity** | You're the constrained resource; they're getting offered access | Variant 8 |
| **PAS — Problem / Agitate / Solve** | Name a problem → agitate it → present solution | Variant 9 |
| **ISO — Insight / Story / Offer** | Open with contrarian insight → brief story/proof → low-friction offer | NOT in current 9; future test |

## CRITICAL: Match Language to the Sales Motion

The lead's `motion` field is `plg_self_serve`, `hybrid_sales_assisted`, or `sales_led_outbound`. Wrong language = email gets deleted. Pitching "30-90 booked meetings" to Vercel is wrong. Pitching "signup conversion" to a sales-led FinTech is wrong.

### Promise Bank by Motion + Angle

Use the EXACT phrasings below.

#### `plg_self_serve` motion

| Angle | specific_promise | metric / outcome |
|---|---|---|
| plg_conversion | lift signup-to-paid conversion 2-3x | high-intent free users converting at 8-15% (vs typical 2-5%) |
| plg_expansion | grow account expansion 20-40% | identifying expansion-ready accounts before your CSMs notice them |
| plg_activation | cut time-to-activation in half | new users hitting aha-moment in days not weeks |
| aros_plg_retention | lift retention 5-8 percentage points | protect 25-95% more profit, automated save plays |

For PLG motions, when generic language is needed:
- "increase customer acquisition 2-3x by converting more of your existing signup volume"
- "lift retention 5-8 points and protect 25-95% more profit"

#### `hybrid_sales_assisted` motion

| Angle | specific_promise | metric / outcome |
|---|---|---|
| hybrid_pql_to_aero | surface 30-50% more PQLs to your AE team | high-intent free users your AEs can convert |
| aap_inbound | hit inbound leads in under 60 seconds | inbound-to-meeting jumping from 8-12% to 25-40% |
| aros_retention | lift NRR 5-8 points | protect 25-95% more profit |
| aap_sales_ops | see deal risk 2-6 weeks before forecast | recover at-risk pipeline before it slips |

#### `sales_led_outbound` motion

| Angle | specific_promise | metric / outcome |
|---|---|---|
| aap_outbound | book 2-3x more qualified meetings at half the mid-market cost | the right ICP buyers, every single month |
| aap_inbound | hit inbound leads in under 60 seconds | inbound-to-meeting from 8-12% to 25-40% |
| aap_sales_ops | see deal risk 2-6 weeks before your forecast | recover at-risk pipeline before it slips |
| aros_retention | lift retention 5-8 points | protect 25-95% more profit |
| atlas_intent_graph | find specific people researching your category right now | named buyers + verified contact at target accounts |
| full_platform | replace 6-12 fragmented sales/retention tools with one platform | sales + retention + ops AI automation, paid on outcomes |

### Binary CTA by Motion (from Berman's Three Cs principle)

Every variant ends with a binary yes/no question. **Never use a calendar link directly in the email.** The binary question creates psychological commitment; the calendar link gets ignored.

- **plg_self_serve:** "Worth a 20-minute walkthrough this week?"
- **hybrid_sales_assisted:** "Worth a quick call this week?"
- **sales_led_outbound:** "Worth a quick call this week to see if there's a fit?"

### Pipeline / Acquisition Words by Motion

Substitute `{pipeline_or_revenue}`:
- `plg_self_serve` → "qualified signups," "paid conversions," "expansion revenue"
- `hybrid_sales_assisted` → "qualified pipeline," "PQLs," "AE-ready accounts"
- `sales_led_outbound` → "qualified pipeline," "booked meetings," "qualified appointments"

---

## VARIANT 1 — On Framework 1.0 (PPP: Warm + Triple Risk Reversal)

Modeled on the gym "On Framework 1.0." Framework: **PPP (Praise / Picture / Push)** with heavy risk-reversal P.S. Long version. Best when the lead is mid-funnel awareness — they know they have a problem but haven't picked a solution.

**Structure:**

```
Hi {first_name}, hope you're having a great day.

I love the look & feel of {company} — you guys really look the part.

My team and I have taken a look at your {their_business_description}, and we're confident we can help you {specific_promise} every single month — driving {target_outcome}.

Best part: if we don't deliver, you don't pay. Pay-on-results, full stop.

This isn't automated. I recorded a quick video to introduce myself so you can see I'm not blasting you from software:

{VIDEO_LINK}

We've helped over 100 mid-market companies plug AI into their growth motion, sometimes adding {big_result} to their {pipeline_or_revenue} in the first 90 days.

{binary_cta_for_motion}

Thanks,
Frank

p.s. — when I say pay on results, I mean it. No performance, no money out of your pocket.
```

**Word count target:** 130-160 words.
**Subject line patterns:** "{hook keyword}?" or "saw {company}'s {observation}"

---

## VARIANT 2 — On Framework 2.0 (PPP: Compact Warm)

Modeled on "On Framework 2.0." Framework: **PPP, compressed to ~80 words**. Best for time-poor recipients (CROs, CEOs at 200+ employee co's). Aligns with the 2026 elite-performer norm of <80 word first-touch.

**Structure:**

```
Hey {first_name}, loving the look of {company}.

Quick context: my team's reviewed your {their_business_description}, and we're confident we can help you {specific_promise} per month, on a complete pay-on-results basis. (If we don't deliver, we don't get paid.)

Recorded a quick video for you so you can see I'm not blasting from software:

{VIDEO_LINK}

{binary_cta_for_motion}

Thanks,
Frank
```

**Word count target:** 70-90 words.
**Subject line patterns:** "loving the look of {company}", "{company} caught our attention"

---

## VARIANT 3 — On Framework 3.0 (PPP + Average-Lift Proof)

Modeled on "On Framework 3.0." Framework: **PPP with social proof statistic injected at the close**. Best when intent_confidence is high — the proof statistic earns the slot. Keep length tight despite the extra proof line.

**Structure:**

```
Hi {first_name},

First — {company} looks great.

We've taken a look at your {their_business_description} and we're confident we can {specific_promise} every month, driving {target_outcome}. Done-for-you, fully guaranteed: if we don't drive {target_outcome}, we don't get paid.

I send these personally — not blasting you from bulk software. Recorded a quick video to intro myself:

{VIDEO_LINK}

On average, we add {average_lift} to each mid-market company we work with in the first 8 weeks.

{binary_cta_for_motion}

Thanks,
Frank
```

**Word count target:** 100-130 words.
**Subject line patterns:** "saw {company}'s {observation}", "quick note for {company}"

---

## VARIANT 4 — Off Framework 1.0 (AIDA: Niche Authority + Direct Ask)

Modeled on the gym "Off Framework 1.0." Framework: **AIDA (Attention / Interest / Desire / Action)** with niche authority claim driving the Attention beat.

**Structure:**

```
{first_name},

Saw {company} is in {their_industry}. Strong ties here — we work with mid-market {their_industry} companies running AI automation across their growth motion. (Attention)

Most run into the same wall: {motion_appropriate_pain_one_liner}. (Interest)

Recorded a video to explain my offer so you know I'm not blasting from a list. (Desire)

{VIDEO_LINK}

{binary_cta_for_motion} (Action)

Cheers,
Frank

p.s. — personal email. When you reply, it'll be me.
```

`motion_appropriate_pain_one_liner`:
- plg_self_serve → "signup volume's fine, but only 2-5% convert to paid"
- hybrid_sales_assisted → "PQL signal exists, but AEs never get clean handoffs"
- sales_led_outbound → "outbound's working, but cost-per-meeting keeps creeping"

**Word count target:** 80-100 words.
**Subject line patterns:** "quick q for a mid-market {their_industry} co"

---

## VARIANT 5 — Off Framework 2.0 (Berman's 3 Cs: Compliment / Case Study / CTA)

Modeled on the gym "Off Framework 2.0," upgraded to Berman's exact 3 Cs framework from Cold Email Manifesto. The case study list is anonymized to protect against fabrication. **NEVER invent customer names.**

For `plg_self_serve` examples list:
```
  • PLG dev-tools company: signup-to-paid 3.2% → 9.1% in 90 days
  • SaaS infrastructure: 32% reduction in free-tier churn before paid conversion
  • Mid-market PLG product: 41% lift in expansion from existing accounts
```

For `hybrid_sales_assisted` examples list:
```
  • Hybrid SaaS: 2.4x lift in PQL-to-AE handoff conversion
  • Horizontal SaaS: inbound-to-meeting 9% → 31% in 60 days
  • B2B FinTech: surfaced 4 deal-risk signals 5 weeks before forecast slip
```

For `sales_led_outbound` examples list:
```
  • B2B SaaS: cut SDR ramp 6 weeks → under 1 week, 3x'd booked meetings
  • Cybersecurity SaaS: 3x'd inbound-to-meeting in 60 days
  • Mid-market manufacturer: lifted retention 6 points in Q3
```

**Structure:**

```
Hey {first_name},

{company} is doing some great things in {their_industry}. (Compliment)

Recent results across companies similar to yours: (Case study)

{motion_appropriate_results_list}

I recorded a personalized video so you can see this isn't from a big list:

{VIDEO_LINK}

{binary_cta_for_motion} (CTA)

Thanks,
Frank
```

**Word count target:** 90-120 words.
**Subject line patterns:** "results from companies like {company}", "saw something for {company}"

---

## VARIANT 6 — Off Framework 3.0 (QVC: Question / Value / CTA — shortest)

Modeled on the gym "Off Framework 3.0." Framework: **QVC (Question / Value / CTA)**. The shortest variant — under 65 words. Aligns with 2026 Instantly research showing under-80-word emails outperform 200+ word emails by 2.4x.

**Structure (varies by motion):**

For `plg_self_serve`:
```
Hey {first_name}, quick q — open to lifting signup-to-paid conversion 2-3x?

Recorded a video to explain. Under a minute, your site on screen:

{VIDEO_LINK}

Worth a 20-minute walkthrough this week if it lands?

Frank
```

For `hybrid_sales_assisted` and `sales_led_outbound`:
```
Hey {first_name}, quick q — open to {specific_promise}? If yes, how many {target_outcome_unit} could you handle per month?

Recorded a video. Under a minute, your site on screen:

{VIDEO_LINK}

{binary_cta_for_motion}

Frank
```

**Word count target:** 45-65 words.
**Subject line patterns:** "open to {specific outcome}?" or "quick q on {topic}"

---

## VARIANT 7 — Off Framework 4.0 (Suby Authority + Aggregate Proof)

Modeled on the gym "Off Framework 4.0." Framework: **Suby's Authority Principle** — lead with overwhelming credibility numbers. The pay-on-results line stays as the risk-eliminator.

**IMPORTANT:** The aggregate numbers used here ($40M pipeline, $25M retained ARR) are placeholder. Replace with real Ascentir numbers before launching. If you don't have aggregate proof yet, drop Variant 7 from the test.

**Structure:**

```
Hi {first_name}, hope all's well at {company}.

Quick one: Ascentir's helped mid-market companies generate over $40M in net-new pipeline, lift signup conversion 2-3x across PLG funnels, and protect over $25M in retained ARR through AI automation in the past 18 months. Across B2B SaaS, Cybersecurity, FinTech, and Industrial.

If we don't deliver, you don't pay.

I'm Frank, founder of Ascentir, an AI automation platform for mid-market growth.

Before reading further, watch this video I recorded for you:

{VIDEO_LINK}

I came across {company} and I'm confident we can drive real results.

{binary_cta_for_motion}

Cheers,
Frank

p.s. — real person. Wrote this manually.
```

**Word count target:** 110-140 words.
**Subject line patterns:** "{company} caught our attention", "quick note about {company}"

---

## VARIANT 8 — Off Framework 5.0 (Inverted Demand / Scarcity)

Modeled on the gym "Off Framework 5.0." Framework: **Inverted Demand** — you're the constrained resource. Strongest scarcity play. Lands well when the market signal is genuine (which yours is — high-intent buyers from a curated database).

**Structure:**

```
Hi {first_name},

Seeing a lot of mid-market {their_industry} companies actively looking for AI automation right now. {company} came up in our research as a fit. Heads-up before we reach out widely.

Open to exploring what AI automation could do for your {motion_appropriate_growth_lever}?

Before responding, check out this video I recorded:

{VIDEO_LINK}

If it's a fit, hit reply or tap the red button at the end of the video.

Cheers,
Frank

p.s. — not automated. Real person, scrolling through {company}'s site as I write this.
```

`motion_appropriate_growth_lever`:
- plg_self_serve → "signup conversion and customer retention"
- hybrid_sales_assisted → "pipeline and customer retention"
- sales_led_outbound → "pipeline visibility and deal velocity"

**Word count target:** 85-110 words.
**Subject line patterns:** "heads up — {their_industry} inquiries", "quick heads up for {company}"

---

## VARIANT 9 — Off Framework 6.0 (PAS: Problem / Agitate / Solve)

Modeled on the gym "Off Framework 6.0." Framework: **PAS (Problem / Agitate / Solve)** with concerning observation as the Problem beat. **Only used when the personalized hook contains a genuinely concerning observation.** Otherwise the system falls back to Variant 6.

**Structure:**

```
Hey {first_name},

Honest observation about {company}: {hook_observation_concerning} (Problem)

For mid-market {their_industry} companies, that pattern usually means {agitation_one_liner} — and it compounds every quarter you don't fix it. (Agitate)

Recorded a video showing what we'd actually do about it:

{VIDEO_LINK}

I run Ascentir. We help mid-market companies {specific_promise}. After looking at {company}, I'm confident we could move the needle. (Solve)

{binary_cta_for_motion}

Thanks,
Frank

p.s. — wrote this personally. You're not on a list.
```

`agitation_one_liner` by motion:
- plg_self_serve → "real revenue is leaking out the bottom of your funnel"
- hybrid_sales_assisted → "real pipeline is dying between your PLG signal and your AE team"
- sales_led_outbound → "real deals are slipping weeks before your forecast catches it"

**Word count target:** 95-120 words.
**Subject line patterns:** "honest observation about {company}", "noticed something on {company}'s site"

---

## Big Result Phrasing (Variant 1 only)

`big_result` by motion:
- plg_self_serve → "tripling signup-to-paid conversion in a quarter"
- hybrid_sales_assisted → "$2M+ in net-new pipeline alongside a 6pt NRR lift"
- sales_led_outbound → "$2M+ in net-new pipeline"

## Average Lift Phrasing (Variant 3 only)

`average_lift` by motion + angle:
- plg_self_serve / plg_conversion → "2-3x improvement in signup-to-paid conversion"
- plg_self_serve / aros_plg_retention → "5-8 points of paid retention"
- hybrid_sales_assisted → "2-3x more high-intent prospects reaching your AE team"
- sales_led_outbound / aap_outbound → "30-60 booked qualified meetings per month"
- sales_led_outbound / aap_sales_ops → "weeks of forecast clarity"
- aros_retention (any motion) → "5-8 points of NRR"
- full_platform → "the equivalent of a 25-person RevOps team"

## Subject Line Rules (2026 Best Practice)

From Gong + Instantly 2026 research: under 6 words, references something specific, lowercase, no exclamation points.

| Variant | Best Pattern | Example |
|---|---|---|
| 1 | hook reference | "your post on signup conversion" |
| 2 | observation | "loving the look of vercel" |
| 3 | hook reference | "saw vercel's edge work" |
| 4 | direct + niche | "quick q for a saas co" |
| 5 | curiosity | "results for companies like yours" |
| 6 | direct question (motion-aware) | "open to lifting conversion 2-3x?" |
| 7 | observation | "vercel caught our attention" |
| 8 | inverted demand | "heads up — saas inquiries" |
| 9 | pattern interrupt | "honest observation about vercel" |

## Voice Style (All Variants)

- **Lowercase subjects.** Always.
- **Single binary CTA.** "Worth a call?" not "would love to discuss."
- **No corporate clichés.** Banned: "circle back," "synergies," "leverage," "touch base," "value-add," "best-in-class," "robust," "seamless," "I hope this finds you well."
- **Specific over abstract.** Numbers and concrete observations beat adjectives.
- **Vary sentence length.** Short punchy sentences mixed with longer ones — Suby's "make your words sing" rule.
- **Founder energy.** Confident, specific, direct.
- **Never invent customer names** or specific results not in the variant template.

## Lead

**Name:** {first_name} {last_name}
**Role:** {role}
**Company:** {company}
**Vertical:** {vertical}
**Motion:** {motion}
**Personalized hook:** {personalized_hook}
**Recommended angle:** {recommended_angle}
**Variant:** {variant_id}

## Output Format

Return JSON only:

```json
{{
  "subject": "<lowercase, under 50 chars, ideally under 6 words>",
  "body": "<plain text body following the variant's structure exactly, MUST contain literal {{VIDEO_LINK}} placeholder, MUST use motion-appropriate language>",
  "variant_id": "{variant_id}",
  "framework_used": "<the framework name: PPP | 3Cs | AIDA | QVC | Authority | InvertedDemand | PAS>",
  "motion_used": "{motion}"
}}
```

## Output Rules

- Output ONLY the JSON. No markdown fences.
- Match the variant's structure exactly. The structure IS the value.
- The body MUST contain `{VIDEO_LINK}` (literal, with curly braces).
- Subject under 50 chars, lowercase, ideally under 6 words.
- Word count must hit the variant's target range.
- The promise language MUST match the motion. Never pitch "booked meetings" to a `plg_self_serve` lead.
- Single binary CTA. No calendar links in the email body.
- Never invent customer names or fabricated results.
- Never use the banned phrases.
- The `variant_id`, `framework_used`, and `motion_used` fields must match.
