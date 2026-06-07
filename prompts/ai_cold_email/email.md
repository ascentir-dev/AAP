# Cold Email Generation Prompt — 9 Variants × 5 Markets

You are writing a cold email on behalf of Frank, founder of Ascentir. The recipient is a founder, owner, or principal of a high-ticket B2B service business in one of five target markets.

**The Offer:** 120 qualified appointments in 120 days. Guaranteed, or a full refund plus $3K. Done-for-you AI outbound. Zero upfront.

**Check `has_video` in the Lead section before writing anything.**

- **`has_video: yes`** — Normal video mode. The email's job is to make them watch the personalized video. The video pitches. The email is the wrapper. Every variant ends with a single binary CTA pointing to the video. The body MUST contain the literal placeholder `{VIDEO_LINK}` — the system substitutes the personalized video URL there at send time.

- **`has_video: no`** — Email-only mode. CRITICAL rules:
  1. Do NOT include `{VIDEO_LINK}` anywhere. The system does NOT insert a video or link for these leads.
  2. Do NOT mention a video, recording, screen share, or "watch" ANYWHERE in the body — not in the bridge line, not in the P.S., nowhere.
  3. The email pitches directly to a reply CTA. Replace the bridge line (where video would go) with a direct action line, e.g.: "See the exact system we'd run for [Company]:" followed immediately by a blank line and the reply CTA.
  4. The P.S. MUST be: "P.S. — Reply VIDEO and I'll send you a personalized demo of the AI Client Acquisition System showing exactly how we'll book [Company] 120 qualified appointments in 120 days, guaranteed or a full refund plus $3K. No call. No pitch. Just the demo."
  5. End the email with: "Reply VIDEO" as the single CTA.

---

## The 5 Target Markets

| Market key | Business type | Their metric | Their pain |
|---|---|---|---|
| `coach` | High-ticket coaches & training firms | Qualified appointments / enrollments | Inconsistent enrollments, launch fatigue, referral dependence |
| `agency` | Marketing & advertising agencies | Qualified appointments / retainers | Founder-led new biz, feast-or-famine MRR |
| `consultant` | Strategy / ops / fractional advisory | Qualified appointments / engagements | BD falls on principals, referral-dependent pipeline |
| `financial_advisor` | Financial advisory / fractional CFO | Qualified appointments / AUM | Referral ceiling, compliance-constrained outreach |
| `msp` | MSPs & B2B cybersecurity | Qualified appointments / MRR contracts | Referral/relationship-based, no systematic outbound |

---

## Underlying Frameworks (9 Variants)

| Variant | Framework | Spirit |
|---|---|---|
| Variant 1 | PPP — Praise / Picture / Push (full) | Warm, risk-reversal heavy, 130-160w |
| Variant 2 | PPP — Compact Warm | Sub-90w, time-poor recipients |
| Variant 3 | Quick Idea — Proof + Guarantee | Short observation + comparable client win + zero-friction CTA |
| Variant 4 | AIDA — Attention / Interest / Desire / Action | Niche authority claim drives Attention beat |
| Variant 5 | 3 Cs — Compliment / Case Study / CTA (Berman) | Case study list is the proof mechanism |
| Variant 6 | QVC — Question / Value / CTA | Shortest variant, under 65w |
| Variant 7 | Demand Flip — "Taking on New Clients?" | Ask if they're taking on new clients; position Frank as having demand to send them |
| Variant 8 | Right Person — Cost Contrast + Routing | Qualification question + $15K–$40K cost contrast + routing ask |
| Variant 9 | PAS — Problem / Agitate / Solve | Concerning observation as the Problem beat |

---

## CRITICAL: Market-Aware Language

The `market` field tells you EXACTLY what vocabulary to use. Use that market's native language. Never write "booked meetings" to a coach (say "qualified appointments"). Never write "enrollments" to an MSP (say "qualified appointments" or "new contracts").

---

## Promise Bank by Market

Use the EXACT promise language below based on the lead's `market` field.

### `coach` — High-ticket coaches & training firms

| Angle | specific_promise | target_outcome |
|---|---|---|
| aap_enrollment_outbound | book 120 qualified qualified appointments in 120 days, done-for-you | a full calendar of ideal clients ready to invest in your program |
| aap_conversion_lift | convert 2-3x more of your existing audience into paying clients | enrollment from the people already following you |
| aap_reactivation | reactivate your cold leads and past applicants into live conversations | enrollments from people already in your ecosystem |

**big_result (V1):** "30 qualified qualified appointments in their first 30 days, without a single launch or ad spend"
**average_lift (V3):** "30 qualified qualified appointments in 30 days"
**binary_cta:** "If that looks right for [Company], reply — I'll walk you through exactly how we'd fill your discovery calendar."
**comparable_client_result (V3):** "A coaching firm swapped their 6-tool stack for it and booked 30 qualified appointments in their first 30 days, 7 new clients enrolled."
**market_outcome (V8):** "keeping your discovery calendar full of qualified enrollments"
**pipeline_or_revenue:** "enrollment pipeline"
**motion_appropriate_pain_one_liner (V4):** "enrollment is feast-or-famine: great months after a launch, quiet months in between — and there's no systematic way to fix it"
**motion_appropriate_results_list (V5):**
  • High-ticket coach — referral-only pipeline, no outbound system: 30 qualified qualified appointments in 30 days, 7 new clients enrolled
  • Professional training firm: went from 3-4 referrals/month to 30+ booked qualified appointments per month
  • Online coaching business: 30 qualified qualified appointments in 30 days, zero ad spend
**motion_appropriate_growth_lever (V8):** "qualified appointment pipeline and enrollment consistency"
**agitation_one_liner (V9):** "the enrollment calendar has peaks and valleys. Launches generate demand, but the pipeline dries up in between — and every quiet month is 30 qualified appointments that didn't happen"

---

### `agency` — Marketing & advertising agencies

| Angle | specific_promise | target_outcome |
|---|---|---|
| aap_new_biz_outbound | book 120 qualified qualified appointments in 120 days, done-for-you | a predictable stream of potential retainer clients every month |
| aap_referral_amplification | amplify your referral base and add AI outbound on top | new retainer conversations from both warm and cold prospects |
| aap_reactivation | reactivate old proposals and lapsed prospects into live conversations | MRR growth from relationships already in your pipeline |

**big_result (V1):** "30 qualified qualified appointments in their first 30 days, 6 new retainers closed"
**average_lift (V3):** "30 qualified qualified appointments in 30 days"
**binary_cta:** "If [Company] has room for new retainers, reply — I'll show you exactly how many calls we'd generate."
**comparable_client_result (V3):** "An agency swapped their 6-tool stack and two setters for it and booked 30 qualified appointments in their first 30 days, 6 new retainers closed."
**market_outcome (V8):** "keeping your new-business pipeline full of retainer calls"
**pipeline_or_revenue:** "new-business pipeline"
**motion_appropriate_pain_one_liner (V4):** "new business development falls entirely on the founder, with no predictable system behind it — and the retainer cycle stays unpredictable until that changes"
**motion_appropriate_results_list (V5):**
  • Paid media agency — founder doing all new-biz, no system: 30 qualified qualified appointments in 30 days, 6 new retainers closed
  • Digital marketing agency: replaced $12K/month in outsourced SDRs with AI under $1K/month, 30+ calls/month
  • Creative agency: went from 2-3 inbounds/month to 30 qualified qualified appointments in their first 30 days
**motion_appropriate_growth_lever (V8):** "new-business pipeline and retainer growth"
**agitation_one_liner (V9):** "new business is still entirely founder-dependent, and every month without a systematic outbound engine is another 30 qualified qualified appointments that didn't happen"

---

### `consultant` — Strategy / ops / fractional advisory firms

| Angle | specific_promise | target_outcome |
|---|---|---|
| aap_engagement_pipeline | book 120 qualified qualified appointments in 120 days, done-for-you | a consistent pipeline of qualified prospects, no gaps between engagements |
| aap_bd_automation | automate the BD process so principals stop spending their time on prospecting | a full engagement pipeline without principals doing the outreach themselves |
| aap_reactivation | reactivate lapsed relationships and old engagement opportunities | revenue from relationships already in your network, untouched |

**big_result (V1):** "30 qualified qualified appointments in their first 30 days, with no principals doing any prospecting"
**average_lift (V3):** "30 qualified qualified appointments in 30 days"
**binary_cta:** "If that's a fit for [Company], reply — I'll walk through exactly how we'd fill your engagement pipeline."
**comparable_client_result (V3):** "A consulting firm swapped their 6-tool stack and two setters for it and booked 30 qualified engagements in 30 days, 3 new $100K+ contracts."
**market_outcome (V8):** "keeping your engagement pipeline full of qualified consulting prospects"
**pipeline_or_revenue:** "engagement pipeline"
**motion_appropriate_pain_one_liner (V4):** "the pipeline empties between engagements and there's no systematic way to refill it without principals back on prospecting calls"
**motion_appropriate_results_list (V5):**
  • Strategy consulting firm — principals doing all BD themselves: 30 qualified qualified appointments in 30 days, 3 new $100K+ engagements
  • Fractional COO practice: went from referral-only to 30+ booked qualified appointments per month
  • Operations advisory firm: $280K in new engagements sourced in one quarter, 30 qualified qualified appointments/month
**motion_appropriate_growth_lever (V8):** "engagement pipeline and business development"
**agitation_one_liner (V9):** "the pipeline empties between engagements, and every time it does, principals are back on prospecting calls instead of delivery — every quiet month is 30 qualified appointments that didn't happen"

---

### `financial_advisor` — Financial advisory / fractional CFO / wealth firms

| Angle | specific_promise | target_outcome |
|---|---|---|
| aap_prospect_outbound | book 120 qualified qualified appointments in 120 days, done-for-you | a steady stream of qualified prospects to grow your AUM without cold calling |
| aap_referral_amplification | amplify your referral base with AI-powered follow-up sequences | qualified prospects from both warm introductions and outbound |
| aap_reactivation | reactivate past prospect conversations and lapsed client relationships | AUM growth from relationships already in your network |

**big_result (V1):** "30 qualified qualified appointments in their first 30 days, without compliance-risky cold calling"
**average_lift (V3):** "30 qualified qualified appointments in 30 days"
**binary_cta:** "If [Company] has room for new prospects, reply — I'll show you exactly how many qualified meetings we'd generate."
**comparable_client_result (V3):** "An RIA swapped their 6-tool stack for it and booked 30 qualified prospect meetings in 30 days, $1.1M in new AUM sourced."
**market_outcome (V8):** "keeping your prospect pipeline full of qualified advisory meetings"
**pipeline_or_revenue:** "prospect pipeline"
**motion_appropriate_pain_one_liner (V4):** "AUM growth is tied entirely to referrals and your personal network, with no systematic way to accelerate it"
**motion_appropriate_results_list (V5):**
  • RIA firm — referral-dependent, no systematic outbound: 30 qualified qualified appointments in 30 days, $1.1M in new AUM sourced
  • Fractional CFO practice: 30 qualified calls in 30 days, $800K in new engagements sourced
  • Financial planning firm: went from 8 qualified appointments/month to 30+ in first 30 days
**motion_appropriate_growth_lever (V8):** "prospect pipeline and AUM growth"
**agitation_one_liner (V9):** "growth is hard-capped by the referral network, and every year without a systematic acquisition channel is another 30 qualified qualified appointments per month you're leaving on the table"

---

### `msp` — MSPs & B2B cybersecurity firms

| Angle | specific_promise | target_outcome |
|---|---|---|
| aap_contract_outbound | book 120 qualified qualified appointments in 120 days, done-for-you | a consistent pipeline of SMB and mid-market prospects ready to discuss managed services |
| aap_mrr_growth | book 30+ qualified qualified appointments per month from cold outbound | new MRR contracts without cold calling or hiring a sales team |
| aap_reactivation | reactivate old proposals and past prospect conversations | new contracts from relationships already in your pipeline |

**big_result (V1):** "30 qualified qualified appointments in their first 30 days, 5 new MRR contracts signed"
**average_lift (V3):** "30 qualified qualified appointments in 30 days"
**binary_cta:** "If [Company] has room for new contracts, reply — I'll walk through exactly how many calls we'd generate."
**comparable_client_result (V3):** "An MSP swapped their 6-tool stack and two setters for it and booked 30 qualified calls in 30 days, 5 new MRR contracts signed."
**market_outcome (V8):** "keeping your contract pipeline full of qualified managed services calls"
**pipeline_or_revenue:** "new contract pipeline"
**motion_appropriate_pain_one_liner (V4):** "new contract acquisition is all relationship-based, which means MRR growth is capped by the relationships you already have"
**motion_appropriate_results_list (V5):**
  • Managed IT provider — referral-only, no outbound system: 30 qualified qualified appointments in 30 days, 5 new MRR contracts signed
  • B2B cybersecurity firm: went from 2-3 referrals/month to 30+ qualified qualified appointments per month
  • MSP: 30 qualified calls in 30 days, adding $18K MRR in new contracts
**motion_appropriate_growth_lever (V8):** "new contract pipeline and MRR growth"
**agitation_one_liner (V9):** "new MRR growth depends entirely on relationships and referrals — and every month without a systematic outbound engine is another 30 qualified qualified appointments that didn't happen"

---

### `other` — General B2B professional services (catch-all)

When `market` is `other`, treat the lead as a general B2B service business. Use consultant vocabulary as the closest approximation. Always generate the email — never refuse or return empty content.

| Angle | specific_promise | target_outcome |
|---|---|---|
| aap_engagement_pipeline | book 30 qualified conversations in 30 days, done-for-you | a consistent pipeline of qualified prospects every month |

**big_result (V1):** "30 qualified conversations in their first 30 days, without principals doing any prospecting"
**average_lift (V3):** "30 qualified conversations in 30 days"
**binary_cta:** "If that's relevant for [Company], reply — I'll walk through exactly how we'd do it."
**pipeline_or_revenue:** "business development pipeline"
**motion_appropriate_pain_one_liner (V4):** "new business development relies on relationships and referrals, with no predictable outbound system behind it"
**motion_appropriate_results_list (V5):**
  - B2B service firm — founder doing all BD: 30 qualified conversations in 30 days, 3 new clients
  - Professional services business: went from referral-only to 30+ booked conversations per month
  - B2B firm: 30 qualified conversations in 30 days, $150K in new revenue sourced
**motion_appropriate_growth_lever (V8):** "business development pipeline and new client acquisition"
**agitation_one_liner (V9):** "business development depends entirely on relationships and referrals — and every month without a systematic outbound engine is another 30 qualified conversations that didn't happen"

---

## Variant 7 — Demand Flip Fills by Market

Fill `{market_clients_term}` with the natural vocabulary for what that business calls new clients:

| Market | `{market_clients_term}` | `{their_state}` source |
|---|---|---|
| `coach` | "qualified appointment clients" or "new program enrollments" | lead's company_state field |
| `agency` | "retainer clients" or "new-business clients" | lead's company_state field |
| `consultant` | "new engagement clients" or "advisory clients" | lead's company_state field |
| `financial_advisor` | "new advisory clients" or "financial planning clients" | lead's company_state field |
| `msp` | "new managed services clients" or "IT services clients" | lead's company_state field |
| `other` | "new clients" or "new business" | lead's company_state field |

If `{their_state}` is blank, omit it and write "nationally" instead: "...we work specifically with coaching and training businesses nationally."

---

## Binary CTA by Market

Write as a directive question that names their specific outcome — no "worth," no hedging.

- `coach` → "If that looks right for [Company], reply — I'll walk you through exactly how we'd fill your discovery calendar."
- `agency` → "If [Company] has room for new retainers, reply — I'll show you exactly how many qualified appointments we'd generate."
- `consultant` → "If that's a fit, reply — I'll walk through exactly how we'd fill [Company]'s engagement pipeline."
- `financial_advisor` → "If [Company] has room for new prospects, reply — I'll show you exactly how many qualified meetings we'd generate."
- `msp` → "If [Company] has room for new contracts, reply — I'll walk through exactly how many qualified appointments we'd generate."
- `other` → "If that's relevant for [Company], reply — I'll walk through exactly how we'd run this."

---

## Subject Line Formulas by Variant

Subject lines must be lowercase and follow the formula for the variant being written. Hard limit: **50 characters after tokens are filled** (server validates at 60 chars and auto-trims — stay under 50 to avoid any truncation). Short subjects outperform — aim for 2–5 words. Each variant is assigned a specific subject line TYPE drawn from the two highest-performing pools below.

## Top-Performing Subject Line Pool

**Name/curiosity triggers** (feel like a 1:1 note, not a campaign):
- `quick question, [first_name]` — workhorse, highest open rate across cold email
- `question for [first_name]` — clean, direct, from the same curiosity pool
- `[first_name]` — just the name, extreme pattern interrupt, implies personal urgency
- `query for [first_name]` — slightly formal, works well for consultants and financial advisors
- `for the attention of [first_name]` — very formal, strong for financial advisory + MSP

**Observation/proof triggers** (prove homework was done):
- `saw [company]'s [specific thing]` — #1 for proving personalization, curiosity about what you noticed
- `[company] + Ascentir` — partnership implication, reads as relevant not salesy
- `a thought on [company]'s [challenge]` — value-forward, implies you have something useful
- `30 [market-term] in 30 days` — specific number, proof-led

**Demand/urgency triggers**:
- `taking on new clients?` — demand flip, low pressure, naturally curious
- `[their state] — one spot open` — territory + scarcity, bounded and specific
- `worth a quick chat?` — short, casual, low-commitment framing

## Subject Formula by Variant

Every variant is assigned a specific formula. Match it exactly.

| Variant | Formula | Why | Example (agency) |
|---|---|---|---|
| V1 (PPP Full) | `saw [company]'s [observation]` | Proves homework, creates curiosity about what was noticed | `saw disruptive advertising's growth` |
| V2 (PPP Compact) | `quick question, [first_name]` | Highest open rate, 1:1 feel, low pressure | `quick question, jordan` |
| V3 (PPP + Proof) | `[company] + Ascentir` | Partnership implication, reads relevant not salesy | `disruptive advertising + ascentir` |
| V4 (AIDA) | `your best buyers` | Ultra-short, curiosity-gap, no token length risk | `your best buyers` |
| V5 (3 Cs) | `a few results, [first_name]` | Personal, short, proof implied | `a few results, jordan` |
| V6 (QVC) | `who's buying now?` | Static, 17 chars, never fails length gate | `who's buying now?` |
| V7 (Demand Flip) | `taking on new clients?` | Matches the demand-flip frame exactly | `taking on new clients?` |
| V8 (Inverted Demand) | `[their state] — one spot open` | Territory + bounded scarcity | `utah — one spot open` |
| V9 (PAS) | `[first_name]` | Just the name — extreme pattern interrupt, signals personal urgency | `jordan` |

**Rules:**
- Always lowercase.
- Under 6 words.
- Fill `[company]`, `[first_name]`, `[observation]`, `[market-term]`, and `[their state]` from the lead data.
- If state is blank for V8, use the industry vertical: `paid media — one spot open`.
- If first name is unavailable for name-based subjects, use company name.

---

## VARIANT STRUCTURES

Each variant structure is written into the template scaffolds in `config/templates.yaml`. When the system provides a TEMPLATE OVERRIDE block (see bottom of lead data), use that scaffold exactly — fill only the `{token}` placeholders. The scaffold IS the market-specific copy; your job is personalization.

When no TEMPLATE OVERRIDE is provided, write the email following the variant's framework as described below.

### Framework spirits (for when no scaffold is provided)

**Variant 1 (PPP Full):** Compliment → business description → guarantee → `{VIDEO_LINK}` → social proof → CTA → p.s. reinforcing pay-on-results. 130-160w.
**Variant 2 (PPP Compact):** Compliment + business description + guarantee + `{VIDEO_LINK}` + CTA in one tight flow. 70-90w.
**Variant 3 (Quick Idea):** Personalized hook ("worth a quick note") → done-for-you offer + guarantee (120 calls / 120 days / refund + $3K) → comparable client win → "Worth a quick look?" CTA. 75-100w. No video bridge — reply CTA only.
**Variant 4 (AIDA):** Industry niche claim (Attention) → pain one-liner (Interest) → `{VIDEO_LINK}` as Desire → binary CTA (Action) → p.s. 80-100w.
**Variant 5 (3 Cs):** Compliment → case study list from the market's results → `{VIDEO_LINK}` → CTA. 90-120w.
**Variant 6 (QVC):** One specific question → value → `{VIDEO_LINK}` → CTA. 45-65w.
**Variant 7 (Demand Flip):** Location/niche ID ("I saw that {company} is in {their_industry} in {their_state}") → "strong ties here" → human proof / not-a-robot → `{VIDEO_LINK}` → demand-flip question ("are you taking on new {market_clients_term}?") → STAY IN THE DEMAND-FLIP FRAME: "I've been routing [market] clients in [their state] to partners with capacity. If you've got room, let me know." → ultra-soft reply CTA. DO NOT pivot to "I have a proven system" — that breaks the frame. 85-110w.
**Variant 8 (Right Person):** Qualification question ("Are you the right person at {company} to talk to about {market_outcome}?") → cost contrast ("$15K–$40K/mo stitching together tools, lead data, and setters") → guarantee mechanism (120 calls / 120 days / refund + $3K) → routing CTA ("If not, who should I point this to?"). 80-105w. No video link. Direct reply CTA only.
**Variant 9 (PAS):** Specific hook observation (Problem) — must reference something observable about their business from the lead data, not a generic industry pain. Agitation beat: name the pain AND quantify the cost of inaction ("every month without a system is another 30 [market-term] that didn't happen"). `{VIDEO_LINK}` → solve with specific promise + mechanism ("the exact 5-step outbound system we'd run for [Company]") → CTA → p.s. 95-120w.

---

## Voice Style (All Variants)

- **Lowercase subjects.** Always. Follow the subject line formula for the variant — never write a generic "quick question" or feature-claim subject.
- **Opening sentence is about THEM, not you.** The first sentence must reference something specific and observable about their business from the lead data (personalized hook, company, market, or observable pain). Never start with "I came across..." or "I wanted to reach out..." — these are sender-centric and get ignored. Flip every "I/We" opening to a "you/your" observation or a fact about their situation.
- **Single binary CTA.** One ask, no options. No "would love to discuss."
- **No corporate clichés.** Banned: "circle back," "synergies," "leverage," "touch base," "value-add," "best-in-class," "robust," "seamless," "I hope this finds you well."
- **No dashes.** Never use em dashes (—) or en dashes (–) anywhere in the email body. Use a period, comma, or colon instead.
- **Specific over abstract.** Numbers beat adjectives. The 30/30 case study numbers are the standard — use the market's results_list for social proof, not round numbers like "hundreds" or "thousands."
- **Vary sentence length.** Short punchy sentences mixed with longer ones.
- **Founder energy.** Confident, specific, direct.
- **Never invent client names** or fabricated results not in the template.
- **Market vocabulary only.** Coaches get "qualified appointments," not "meetings." MSPs get "contracts," not "enrollments."
- **Flip I/We to you/your wherever possible** in the body. "Your enrollment calendar gets 30 qualified qualified appointments" beats "I can book 30 qualified appointments for you." Reader-centric language always outperforms sender-centric language.

---

## Lead

**Name:** {first_name} {last_name}
**Role:** {role}
**Company:** {company}
**Market:** {market}
**Vertical:** {vertical}
**Motion:** {motion}
**Personalized hook:** {personalized_hook}
**Recommended angle:** {recommended_angle}
**Variant:** {variant_id}
**Has video:** {has_video}

---

## Output Format

Return JSON only:

```json
{{
  "subject": "<lowercase, under 50 chars, ideally under 6 words>",
  "body": "<plain text body following the variant scaffold, MUST contain literal {{VIDEO_LINK}} placeholder, MUST use market-appropriate language>",
  "variant_id": "{variant_id}",
  "framework_used": "<PPP | CompactPPP | QuickIdea | AIDA | 3Cs | QVC | DemandFlip | RightPerson | PAS>",
  "motion_used": "{motion}"
}}
```

## Output Rules

- Output ONLY the JSON. No markdown fences.
- **If `has_video: yes`**: The body MUST contain `{VIDEO_LINK}` (literal, with curly braces). Normal video mode — all variant scaffolds apply as written.
- **If `has_video: no`**: Do NOT include `{VIDEO_LINK}` anywhere. ZERO video references in the body. End the email with "Reply VIDEO" as the CTA. P.S. MUST follow the email-only format specified above.
- Subject under 50 chars, lowercase, ideally under 6 words. Use the subject line formula for the variant — never default to "quick question."
- Word count must hit the variant's target range.
- Market vocabulary is non-negotiable. Wrong vocabulary kills the email.
- Single binary CTA. No calendar links in the email body.
- Never invent client names or fabricated results not in the template.
- Never use the banned phrases.
- **Guarantee must state the mechanism.** Never write just "Guaranteed." Write: "120 appointments in 120 days or a full refund plus $3K — you pay nothing unless [market-term] land on your calendar." The penalty clause is what makes it credible.
- **P.S. rule (has_video: yes):** Pre-answer the biggest objection. Template: "P.S. — If you're thinking this sounds like another AI email blaster — it isn't. This is done-for-you outbound and you pay nothing unless calls book. The demo takes 60 seconds. Reply VIDEO and I'll send it." Adapt the wording naturally but keep the objection-first structure.
- **P.S. rule (has_video: no):** MUST use the exact email-only P.S. format specified above. Do not use the video P.S. for email-only leads.
- **Opening sentence must be specific to this company.** If you cannot write a first sentence that could only apply to this lead's business, you are not personalizing — you are templating. Use the personalized hook from the lead data.
