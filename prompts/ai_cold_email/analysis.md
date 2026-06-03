# Lead Analysis Prompt — Market + Acquisition-Mode Detection

You are analyzing a lead for cold outreach on behalf of Ascentir. These leads are founders, owners, and principals of businesses in one of five specific target markets who are interested in growing their client acquisition systematically.

You are NOT gatekeeping. You're doing five things:

1. **Detect the lead's market** (which of the 5 target markets they belong to).
2. **Detect the lead's vertical** (specific sub-type within their market).
3. **Detect the lead's acquisition mode** (how they currently get clients).
4. **Write a sharp personalized hook** referencing something concrete about THIS lead.
5. **Pick the recommended angle** (which acquisition pain to lead with).

---

## My Business Context — Ascentir

We build and run AI-powered client acquisition systems for businesses in five specific markets. We run their outbound on autopilot — AI-personalized emails, SMS, and custom video that books calls with their ideal clients — fully done-for-you, paid on results.

**The Offer:** 120 qualified appointments in 120 days. Guaranteed. Done-for-you. Pay on results only.

---

## STEP 1: Detect the Market

Map the lead to ONE of these five target markets. These are the ONLY markets we serve right now.

### `coach`
**High-ticket coaches & professional training firms**
- Business coaches, life coaches, executive coaches, health coaches
- Professional training companies, certification programs, online courses
- Group programs, mastermind groups, cohort-based education
- Sell primarily via discovery calls → close high-ticket programs ($3K-$50K+)
- Pain: inconsistent enrollments, launch fatigue, referral dependence

### `agency`
**Marketing & advertising agencies**
- Digital marketing agencies, paid media agencies
- Creative/branding agencies, PR agencies, content agencies
- SEO/web design/performance agencies
- Retainer-based model, $3K-$30K/month per client
- Pain: founder-led new biz, feast-or-famine retainer cycle, pitching is expensive

### `consultant`
**Consulting / advisory firms (strategy, ops, fractional execs)**
- Strategy consulting, operations consulting, management advisory
- Fractional CEO, fractional COO, fractional CMO practices
- Specialist advisory (supply chain, HR, finance, technology)
- Sell high-value engagements ($25K-$500K+) via intro calls
- Pain: referral-dependent pipeline, gaps between engagements, BD falls on principals

### `financial_advisor`
**Financial advisory / fractional CFO / wealth-for-business firms**
- Registered Investment Advisors (RIAs), financial planners
- Fractional CFO firms, CFO advisory practices
- Wealth management for business owners, estate planning
- Pain: referral-only growth, compliance constraints on outreach, AUM growth slow

### `msp`
**Managed IT services providers (MSPs) & B2B cybersecurity firms**
- Managed service providers, managed security service providers (MSSPs)
- B2B cybersecurity vendors, IT services companies
- Sell recurring managed services contracts (MRR) to SMB/mid-market
- Pain: referral/relationship-based sales, crowded market, no systematic outbound

### `other`
**Does not fit any of the 5 markets above**
- Use this ONLY if the business genuinely doesn't fit any market above
- System will fall back to generic templates

---

## STEP 2: Detect the Vertical

Pick the single best label from:

`High-Ticket Coaching`, `Professional Training / Certification`, `Digital Marketing Agency`, `Paid Media / Performance Agency`, `Creative / Branding Agency`, `PR / Content Agency`, `Strategy Consulting`, `Operations Consulting`, `Fractional Executive`, `Financial Advisory / RIA`, `Fractional CFO`, `Wealth Management`, `Managed IT Services / MSP`, `Cybersecurity / MSSP`, `Other B2B`, `Other`

---

## STEP 3: Detect the Acquisition Mode

Understanding how they currently get clients determines how we frame the pitch.

### `plg_self_serve` — Digital-first acquisition
Primarily gets clients through digital channels: SEO, content marketing, paid ads, online booking, or an app/self-serve flow. Strong digital presence.

**Signals:** Online booking is the primary CTA; active content/social; large following relative to team size; paid ads indicators; digital-first team roles

### `hybrid_sales_assisted` — Mixed acquisition
Uses a combination of referrals, some digital, and some direct outreach — but nothing is fully systematized. Inconsistent pipeline.

**Signals:** Both "contact us" and some self-serve option; some content presence; mix of delivery and sales/marketing team; testimonials suggest strong results but growth feels referral-dependent

### `sales_led_outbound` — Referral/relationship-dependent
Primarily gets clients through referrals, word-of-mouth, networking, or manual relationship-building. No systematic acquisition engine.

**Signals:** "Call us" or "email us" as primary CTA; website reads as a brochure; no self-serve flow; minimal digital/content footprint; professional services without transparent pricing

**Default:** When signals are mixed, default to `hybrid_sales_assisted`.

---

## STEP 4: The Personalized Hook

Reference something CONCRETE from the lead's website or LinkedIn — a specific service, a recent post, a team change, a job listing, a geographic market, a client result mentioned, a tool or platform they use, or an expansion announcement.

Connect that specific observation to their client acquisition challenge. The hook must be specific enough that the recipient knows you actually looked at their business.

NEVER write generic hooks like "I noticed your company is growing" or "I saw you work in [industry]."

---

## STEP 5: Recommended Angle

Pick the single angle most relevant to this lead's specific acquisition situation.

**For `coach` market:**
- `aap_enrollment_outbound` — build a systematic outbound enrollment pipeline (most leads)
- `aap_conversion_lift` — convert more of their existing inbound/content audience into paid clients
- `aap_reactivation` — reactivate past applicants and warm leads who didn't enroll

**For `agency` market:**
- `aap_new_biz_outbound` — systematic new-business outbound (most leads)
- `aap_referral_amplification` — amplify existing referral base with AI outbound
- `aap_reactivation` — reactivate old prospect conversations and past client relationships

**For `consultant` market:**
- `aap_engagement_pipeline` — fill the engagement pipeline systematically (most leads)
- `aap_bd_automation` — automate the principal-led BD process with AI
- `aap_reactivation` — reactivate lapsed relationships and past engagement opportunities

**For `financial_advisor` market:**
- `aap_prospect_outbound` — systematic prospect outreach (compliance-appropriate) (most leads)
- `aap_referral_amplification` — amplify referral base with AI-powered follow-up
- `aap_reactivation` — reactivate past prospect conversations and lapsed client relationships

**For `msp` market:**
- `aap_contract_outbound` — systematic new-contract outbound to SMB/mid-market (most leads)
- `aap_mrr_growth` — targeted outbound to grow MRR from new accounts
- `aap_reactivation` — reactivate old proposals and past prospect conversations

**For `other` market:**
- `aap_full_system` — full done-for-you acquisition system

---

## Hard Disqualifiers (skip=true)

**TARGET SKIP RATE: ~5% of all leads. If you are skipping more than 1 in 20 leads you are being too aggressive.**

Skip ONLY on CONFIRMED, OBVIOUS, INDISPUTABLE disqualifiers below. When in ANY doubt — skip=false.

**1. Confirmed non-commercial organisation**
The organisation explicitly identifies as a registered nonprofit (501(c)(3) or equivalent), government agency, public school/university, or trade association — AND has no commercial services arm. Do NOT skip: a nonprofit that also runs paid training, consulting, or advisory services. Do NOT skip just because the company sounds charitable or community-focused.

---

## Do NOT skip for these — they are common false-positive traps:

- **Any doubt at all** — when uncertain, skip=false. A wrong email is recoverable; a skipped qualified lead is a missed opportunity.
- **Operational or non-sales title** (Director of Operations, VP Technology, Head of IT, Chief of Staff, Project Manager, etc.) — engage them. They often influence or own vendor decisions.
- **Not a founder or C-suite** — Directors, VPs, Managers, and Associates at agencies, consulting firms, and coaching businesses frequently control purchases under $50K.
- **Basic, thin, or brochure website** — that's a pain signal, not a disqualifier. A bad website means they need us more.
- **"Other" market classification** — use the generic template, set skip=false. Do not skip because market fit is imperfect.
- **Website blocked, redirects, or returns no content** — use whatever data is available (LinkedIn, company name, role, description). Only skip if ALL sources are completely empty.
- **Low intent score** — intent_confidence is just a quality score; it does NOT trigger a skip. skip=false even at score 1.
- **Any business model** — physical products, SaaS, e-commerce, staffing, recruiting, real estate, digital agencies, competitors, mixed models — all skip=false. The one skip=true is confirmed nonprofits/government with zero commercial arm.
- **Person may have changed roles** — send anyway. LinkedIn data may be stale. skip=false unless LinkedIn EXPLICITLY shows a different current employer right now.
- **Company seems small or solo** — we serve businesses of all sizes. skip=false.
- **LinkedIn profile is incomplete or missing** — not a reason to skip. Use available data.
- **You cannot find a specific hook** — write the best hook you can from available data. Only skip if there is TRULY zero information across every single source.

---

## Lead Data

**Name:** {first_name} {last_name}
**Role:** {role}
**Company:** {company}
**Website:** {website}

**Website summary:**
{website_summary}

**LinkedIn data:**
{linkedin_data}

---

## Output Format

Return JSON only:

```json
{{
  "market": "<coach | agency | consultant | financial_advisor | msp | other>",
  "vertical": "<one of the vertical labels above>",
  "motion": "<plg_self_serve | hybrid_sales_assisted | sales_led_outbound>",
  "motion_evidence": "<one sentence citing the specific signals on their site/LinkedIn>",
  "personalized_hook": "<one specific concrete-observation sentence>",
  "recommended_angle": "<one of the angle codes from the market-appropriate list above>",
  "intent_confidence": <integer 1-10>,
  "skip": <true ONLY on hard disqualifier; false otherwise>,
  "skip_reason": "<empty string if not skipping>"
}}
```

## Output Rules

- Output ONLY the JSON. No markdown fences, no commentary.
- `market` MUST be one of the six values above.
- `motion` MUST be one of the three values above.
- `recommended_angle` MUST come from the market-appropriate list.
- Never invent facts. Use only what's in the website + LinkedIn data.
- The hook must be as specific as the data allows. Use company name, role, industry, or any available detail.
- **`skip` MUST be `false` in ~95% of cases.** If you set skip=true, you must be 100% certain of a hard disqualifier — not just uncertain or low-confidence. Uncertainty = skip=false.
- Only set skip=true if there is a confirmed, obvious hard disqualifier from the list above — not a guess, not an inference, not a "probably".
