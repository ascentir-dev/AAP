# Framework Research — Why The 9 Variants Are Built This Way

This document captures the research foundation behind each variant. When you (or Claude Code) edit `prompts/email.md`, refer to this so you don't accidentally break a structure that's working for a specific psychological reason.

## The Source Material

**Books / authors I synthesized:**
- *The Cold Email Manifesto* — Alex Berman & Robert Indries (2022). The "Three Cs" framework: Compliment / Case study / CTA. Berman's ICP framework, the binary-CTA principle.
- *Sell Like Crazy* — Sabri Suby (2019). The Godfather Offer principle, authority/proof persuasion triggers, the importance of risk reversal in offers, varying sentence length for rhythm.
- *Influence* — Robert Cialdini. Reciprocity, social proof, scarcity, authority — the underlying psychology behind every variant.
- *$100M Offers* — Alex Hormozi. The value equation (Dream Outcome × Likelihood ÷ Time × Effort) — embedded in how Variants 1, 3, and 7 frame the promise.

**Industry data sources (2026):**
- Instantly Cold Email Benchmark Report 2026 — 3.43% average reply rate, top performers 10%+, elite performers under 80 words first-touch
- Sendspark 2026 — video cold email achieves 2-3x more replies than text-only
- Autobound 2026 — signal-personalized emails get 18% reply rates vs 3.4% generic
- Gong research — subject lines under 36 chars get 25% higher open rate
- Belkins 2025 — only 5% of senders personalize every email; those who do see 2-3x replies
- Backlinko's analysis of 12M outreach emails — 8.5% reply average, top 10% hit 25%+

## The 7 Cold Email Frameworks (and which ones we use)

| Framework | What it does | Used in our variants |
|---|---|---|
| **AIDA** — Attention / Interest / Desire / Action | Mirrors how persuasion works psychologically. Each beat moves the prospect closer to action. | Variant 4 |
| **PAS** — Problem / Agitate / Solve | Names a pain → makes it feel urgent → presents the solution. Strongest when the problem is genuinely concerning. | Variant 9 |
| **BAB** — Before / After / Bridge | Paints current pain → paints better future state → bridges with the offer. | Not used directly; future test |
| **PPP** — Praise / Picture / Push | Compliment → paint a picture of better state → push to act. Warm, low-pressure. | Variants 1, 2, 3 |
| **3 Cs** — Compliment / Case study / CTA (Berman) | Lightning-fast compliment → relevant proof → binary CTA. Berman's signature. | Variant 5 |
| **QVC** — Question / Value / CTA | Direct question opens → value statement → binary CTA. Shortest, frictionless. | Variant 6 |
| **ISO** — Insight / Story / Offer | Contrarian insight → brief story or proof → low-friction offer. The 2026 favorite for high-conviction senders. | Not in current 9; first candidate for Phase 2 testing |

Variants 7 (Authority + Aggregate Proof) and 8 (Inverted Demand / Scarcity) don't map to a single framework — they're built around Cialdini-style persuasion principles (Authority and Scarcity) that work across frameworks.

## The 5 Non-Negotiable Principles (Every Variant Follows These)

These come from cross-referencing Berman's Manifesto, Suby's Sell Like Crazy, and the 2026 elite-performer benchmarks:

1. **Relevance over reach.** Every variant references something specific to THIS lead via the personalized hook. Generic emails get 3.4% reply, personalized get 18%.

2. **Brevity wins (mostly).** 5 of our 9 variants are under 110 words. The longest is Variant 1 at ~150 words, Variant 3 at ~120, Variant 7 at ~140. The 2026 elite-performer norm is under 80 words; we deliberately keep some longer variants for testing because the original gym templates ran longer and proved out.

3. **Single binary CTA.** Every variant ends with a yes/no question, never "would you be open to discussing" or a calendar link. Berman: "The CTA should be binary — a yes or no question, not a calendar link." This creates psychological commitment.

4. **Proof must be specific.** When proof is included (Variants 5, 7), use specific numbers and outcomes. Suby: authority is one of the two most powerful persuasion triggers. We use anonymized vertical patterns ("a B2B SaaS company we worked with") rather than fabricated names — never invent.

5. **Risk reversal where it fits.** The pay-on-results / refundable framing makes responding feel risk-free. Variants 1, 3, and 7 all explicitly state the risk reversal. This is straight from Hormozi's value equation — reduce Effort/Sacrifice on the denominator side.

## How The Variants Map To Buyer Awareness Stages

Suby's 4-tier market targeting (3% ready to buy, 17% gathering info, 20% problem-aware, 60% unaware) — different variants work at different awareness stages.

- **Most aware (3% ready to buy):** Variants 6 (direct question), 8 (inverted demand) work best. They want to skip the dance.
- **Solution-aware (17%):** Variants 5 (case study), 7 (authority + proof) work best. They're comparing options.
- **Problem-aware (20%):** Variants 4 (AIDA niche authority), 9 (PAS) work best. They know they have a problem.
- **Unaware (60%):** Variants 1, 2, 3 (PPP warm) work best. Lead with compliment, paint the picture, soft push.

Your high-intent database is biased toward the top three buckets (most-aware, solution-aware, problem-aware) — anyone signaling interest in AI automation is at minimum problem-aware. So we expect Variants 4, 5, 6, 7, 8 to outperform Variants 1, 2, 3 on this list. We're testing all 9 anyway because intuition fails at scale and the data will prove it one way or the other.

## The Loom Video Logic (Why It's In Every Variant)

2026 data: <cite>teams using personalized video see 2-3x more replies than text-only sequences</cite>. The video does three things text alone can't:
1. **Proves you're a real human** — the website-scrolling visual + audio reference is the only thing that proves it isn't AI-generated. Without it, the email's "real human" claim is unfalsifiable.
2. **Compresses the pitch into a watchable format** — 50 seconds of video conveys what would take 300 words of text.
3. **Differentiates from the 99% of other cold emails** they got that day.

Every variant references the video specifically. The video is the single most important asset in the entire system — more important than the email body that delivers it.

## The Subject Line Strategy

Per Gong 2026: subject lines under 36 chars get 25% higher open rate than longer ones. Per Sendspark 2026: under 6 words is the sweet spot. The three highest-performing patterns:

1. **Company-specific call-out:** "Idea for {company}'s Q2 pipeline"
2. **Trigger event:** "Congrats on the Series B, {first_name}"
3. **Direct question:** "Quick question about your SDR team"

All 9 of our variants have subject patterns mapped to one of these three. Lowercase always — uppercase signals marketing automation.

## The Send Cadence (Outside the Email Itself)

Per Saleshandy / Instantly 2026: 4-7 email sequences hit 8.3% reply rates vs 4.1% for single-touch. 58% of replies come from step 1, but the remaining 42% come from follow-ups 2-7. So:

- The system generates the **first email + video** for every lead
- The Smartlead campaign should have **3-4 follow-up emails** (text-only, no video) configured per variant
- Follow-ups should NOT use the same variant structure as the first touch — they should be progressively shorter and more direct
- The breakup email (final touch) often produces the highest reply rate of any single touch

The system as built handles only the first email. Configure follow-ups directly in Smartlead per campaign — see the "Follow-up Templates" section of `PLAYBOOK.md` (or design them yourself based on what's worked for you).

## Why We Aren't Testing These (Yet)

These are real frameworks but aren't in the current 9 variants:

- **BAB (Before / After / Bridge)** — strong framework but overlaps significantly with PPP (Variants 1-3). Diminishing returns to test both.
- **ISO (Insight / Story / Offer)** — Berman's newest favorite. Strong candidate for Phase 2 testing once the current 9 narrow to a top 4. Adding ISO would require an "insight" the system can reliably generate, which is the hard part — most insights from AI sound canned.
- **The Falconer / Native Ad Style** — disguising the email as something other than outreach. We considered this; it gets short-term reply rate lifts but degrades long-term sender reputation as the trick gets discovered.
- **Permission-Based Opener** ("Mind if I share something I noticed?") — works in some markets, feels manipulative to senior buyers who recognize it.

## When To Update The Variants

Don't change the variants weekly. The minimum cycle is one full Phase 1 tournament (~4 weeks at 30K/month). After Phase 1 closes:

- If a variant clearly wins by both reply rate AND book rate → keep it, test variations of subject line / opener
- If a variant clearly loses → kill it, replace with a new framework (ISO is the first candidate)
- If results are statistically tied → run another Phase 1 with the same variants (don't add new ones, you need more data)

Iterate on the prompts, not the underlying framework selection. The frameworks are proven; the prompt is where execution lives.

## Honest Limits

These frameworks are battle-tested in B2B cold outreach. They're not magic. The reply rate ceiling at 30K/month is structural — even with perfect personalization, perfect deliverability, and perfect framework selection, you're targeting roughly 3-8% reply rate, not 30%. The math works because of cost discipline + volume + the multiplicative effect of high-intent inputs, not because of message magic.

If your replies aren't following these patterns after 5,000+ sends across all 9 variants, the problem is almost never the framework. It's:
1. Deliverability (check SPF/DKIM/DMARC, inbox warmup, domain age)
2. Targeting (the high-intent list isn't actually high-intent)
3. The video itself (people open the email but don't watch the video)
4. The CTA destination (they watch the video but don't book)

Diagnose in that order. Frameworks are last on the list because they're the most-researched and most-stable variable.
