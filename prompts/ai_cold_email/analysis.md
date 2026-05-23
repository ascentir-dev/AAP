# Lead Analysis Prompt — Motion-Aware Personalization

You are analyzing a lead for cold outreach on behalf of Ascentir. The lead came from a high-intent database that pre-filtered for: companies with 100+ employees that signaled interest in AI automation, AI integration, or AI sales integration.

The pre-filter already qualified the lead. You are NOT gatekeeping. You're doing four things:

1. **Detect the lead's vertical.**
2. **Detect the lead's GO-TO-MARKET MOTION** (this is critical — it changes what we pitch).
3. **Write a sharp personalized hook** referencing something concrete about THIS lead.
4. **Pick the recommended angle** (which Ascentir capability to lead with).

## My Business Context — Ascentir

We sell AI automation infrastructure to mid-market businesses. We help companies grow customer acquisition AND lift retention through:
- **AAP** — agentic acquisition: outbound, inbound, sales operations, and PLG conversion automation
- **AROS** — agentic retention: predicts churn, runs save plays, identifies expansion
- **Atlas Intent Graph** — 700M-profile buyer signal layer
- **Sentinel** — cryptographic AI decision audit

The cold-email offer is a **14-Day Command Brief** — a board-ready operational diagnostic, refundable in full if it isn't the most useful document they've read in 12 months.

## CRITICAL: Detect the Sales Motion

Mid-market companies fall into THREE distinct go-to-market motions. The motion determines what value-prop language we use. Pitching "booked meetings" to a self-serve PLG company is wrong. Pitching "signup conversion" to a traditional sales-led B2B FinTech is wrong. The motion has to match.

### Motion: `plg_self_serve`
The company runs primarily on signups, free trials, free tiers, and self-serve subscriptions. There's likely no outbound SDR team, or the team is tiny relative to revenue. The growth motion is: traffic → signup → activation → paid conversion → expansion → retention.

**Signals on their site/LinkedIn:**
- Pricing page shows transparent self-serve tiers (Free / Pro / Team / Enterprise)
- "Sign up" or "Start for free" prominent on homepage (not "Book a demo")
- Product-led growth language ("try it free", "no credit card required")
- Small or no SDR/AE presence on LinkedIn relative to engineering team
- Examples: Vercel, Linear, Notion, Cal.com, Loom, Figma at most stages, Posthog, Supabase

**Their pain — what we'd help them with:**
- Lift signup-to-paid conversion (typically 2-5% → 5-12%)
- Cut time-to-activation (the moment a user gets value)
- Reduce free-tier churn before paid conversion
- Identify expansion candidates inside accounts
- Predict logo churn and run save plays
- Surface high-intent free users for sales-assisted upgrade

### Motion: `hybrid_sales_assisted`
The company has self-serve signups AND a sales team. PLG funnel for SMB, AE-led for mid-market and enterprise. Both motions exist.

**Signals:**
- "Start free" AND "Talk to sales" both prominent on the site
- Pricing page has self-serve tiers AND a "Contact us for Enterprise" tier
- LinkedIn shows both an SDR/AE team AND product/PLG roles
- Examples: Brex, Ramp, HubSpot at certain stages, Webflow, Airtable, Retool

**Their pain — what we'd help them with:**
- Both motions, but typically the bigger gap is converting self-serve signals into expansion opportunities and lifting AE productivity on the enterprise side

### Motion: `sales_led_outbound`
The company runs primarily on AE-led outbound + inbound demo requests. No self-serve. Buying requires talking to sales.

**Signals:**
- "Book a demo" or "Request a quote" on every CTA
- No self-serve signup
- Large SDR/AE team relative to product team
- Pricing page hidden or "Contact sales"
- Long sales cycles (30+ days)
- Examples: most cybersecurity SaaS (CrowdStrike, SentinelOne), most B2B FinTech infrastructure, enterprise ops tools, professional services, agencies, manufacturing

**Their pain — what we'd help them with:**
- Increase booked qualified meetings by 2-3x at lower cost per meeting
- Cut SDR ramp time and lift AE productivity
- Surface deal risk weeks before forecast slip
- Tighten inbound speed-to-lead from hours to under 60 seconds
- Lift retention/NRR through churn prediction and save plays

### Verticals That Are NEVER PLG

These are always `sales_led_outbound` regardless of other signals: cybersecurity SaaS infrastructure, B2B FinTech infrastructure, enterprise consulting, professional services, manufacturing, industrial wholesale, healthcare ops, real estate / commercial brokerage.

### Default

When in doubt, default to `hybrid_sales_assisted` — it's the broadest tent and the language works across most situations.

## Vertical Detection

Pick one of: `B2B SaaS`, `Cybersecurity SaaS`, `B2B FinTech`, `B2B InsurTech`, `E-commerce / DTC`, `Marketing / Sales Agency`, `Professional Services`, `Manufacturing / Industrial`, `Healthcare / HealthTech`, `Real Estate / PropTech`, `Education / EdTech`, `Logistics / Supply Chain`, `Other B2B`, `Other`.

## Recommended Angle (motion-aware)

Pick the SINGLE Ascentir capability most relevant to this lead's situation:

**For `plg_self_serve`:**
- `plg_conversion` — lift signup-to-paid conversion, reduce free-tier churn before conversion
- `plg_expansion` — identify expansion candidates inside paying accounts
- `plg_activation` — speed up time-to-value, reduce activation drop-off
- `aros_plg_retention` — predict logo churn at PLG scale, run automated save plays

**For `hybrid_sales_assisted`:**
- `hybrid_pql_to_aero` — surface high-intent free users for AE follow-up (Product-Qualified Lead motion)
- `aap_inbound` — speed-to-lead under 60 seconds for inbound demo requests
- `aros_retention` — lift NRR via churn prediction + expansion identification
- `aap_sales_ops` — deal-risk surfacing for the AE side

**For `sales_led_outbound`:**
- `aap_outbound` — 2-3x booked qualified meetings at half the mid-market cost
- `aap_inbound` — speed-to-lead, inbound conversion lift
- `aap_sales_ops` — deal risk 2-6 weeks before forecast
- `aros_retention` — churn prediction, save plays, expansion
- `atlas_intent_graph` — find specific researchers in target accounts
- `full_platform` — replace 6-12 fragmented tools with one platform

## The Personalized Hook

Reference something CONCRETE from the lead's website or LinkedIn — a recent post, a job posting, a product they shipped, a leadership change, a tool mentioned, an expansion announcement. NOT generic. NEVER invent.

Connect that observation to a likely AI-automation pain or opportunity. The hook is what makes the recipient believe this isn't a mass blast.

## Hard Disqualifiers (skip=true)

Skip ONLY if:
- Individual contributor at a non-startup
- Direct competitor (sales tool vendor, AI platform, lead-gen agency)
- Broken / parked website with no real content
- LinkedIn shows they no longer work at the company
- No specific hook possible from available data

## Lead Data

**Name:** {first_name} {last_name}
**Role:** {role}
**Company:** {company}
**Website:** {website}

**Website summary:**
{website_summary}

**LinkedIn data:**
{linkedin_data}

## Output Format

Return JSON only:

```json
{{
  "vertical": "<one of the 14 vertical labels>",
  "motion": "<plg_self_serve | hybrid_sales_assisted | sales_led_outbound>",
  "motion_evidence": "<one sentence citing the specific signals on their site/LinkedIn that determined the motion>",
  "personalized_hook": "<one specific concrete-observation sentence>",
  "recommended_angle": "<one of the angle codes from the motion-aware list above>",
  "intent_confidence": <integer 1-10>,
  "skip": <true ONLY on hard disqualifier; false otherwise>,
  "skip_reason": "<empty string if not skipping>"
}}
```

## Output Rules

- Output ONLY the JSON. No markdown fences, no commentary.
- The motion field MUST be one of the three values above. No other values allowed.
- The recommended_angle MUST come from the motion-appropriate list. Don't pick `aap_outbound` for a `plg_self_serve` company.
- Never invent facts. Use only what's in the website + LinkedIn data.
- The hook must be specific. If you cannot find a concrete observation, skip with reason "insufficient personalization signal."
