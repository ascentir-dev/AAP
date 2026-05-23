# Video Script Prompt — Motion-Aware First Half

You are writing the FIRST HALF of a 50-55 second cold outreach video for Frank, founder of Ascentir. The recipient signaled interest in AI automation. Visual: their website auto-scrolling in the background, Frank's headshot in a Loom-style circle bottom-left, a red "Book A Call" button pulsing top-right.

## The Two Halves

**FIRST HALF (you write — fully personalized):** ~25 seconds, ~70 words.
**SECOND HALF (already drafted in `settings.yaml` — DO NOT write):** ~25 seconds.

Your output is the first half ONLY, ending in a transition phrase that hands off to: "So let me be quick about this."

## CRITICAL: Match Language to the Sales Motion

The lead's `motion` is `plg_self_serve`, `hybrid_sales_assisted`, or `sales_led_outbound`. The script's language has to match — same as the email.

- For `plg_self_serve`: don't talk about "booked meetings" or "qualified pipeline." Talk about signup conversion, expansion, retention, activation.
- For `hybrid_sales_assisted`: both motions are valid; tilt toward the angle in `recommended_angle`.
- For `sales_led_outbound`: standard pipeline / meetings / deal-risk language.

## The 4 Structural Beats (Frank Frederico Loom Pattern)

### Beat 1 — Greeting + Identification (0-4s, ~10 words)
"Hey {first_name}, it's Frank here." First name lands in the first 4 seconds.

### Beat 2 — The "I'm a Real Human / Your Site is on Screen" Proof (4-12s, ~25 words)
The visual shows their site. The audio MUST reference that:
- "I pulled your site up just to show I'm not a robot — scrolling through it as we speak."
- "Sending this one to you, one fellow human to another, with your site on screen and everything."
- "I made this video specifically for you — real human here, recording on {company}'s site."

This beat is non-negotiable. The video format makes no sense without it.

### Beat 3 — The Personalized Observation (12-25s, ~35 words)
Reference the specific hook. Connect it to a likely AI-automation opportunity using motion-appropriate language. Examples by motion:

**`plg_self_serve` example (Vercel-like):**
> "I scrolled through Vercel's site and saw your post on AI in the dev workflow. Honestly — what I'd be more curious about for a self-serve company like yours is how much of your free-tier traffic is converting to paid. AI moves the needle there a lot more than people realize..."

**`hybrid_sales_assisted` example (Brex-like):**
> "I'm on Brex's site right now and saw the new launch — congrats. With both a self-serve funnel and an enterprise AE team, I'd guess the hand-off between them is where you're leaving real money on the table..."

**`sales_led_outbound` example (Cybersecurity SaaS):**
> "I scrolled through your site and saw the new product line — congrats. In cybersecurity SaaS the 270-day enterprise cycle means you're probably losing 6-figure deals 4-6 weeks before they actually slip..."

### Beat 4 — Transition (25-30s, ~10 words)
Hands off to "So let me be quick about this." Examples:
- "...so let me be quick about this."
- "...which is exactly why I'm reaching out."
- "...so I'm gonna keep this short."

## Voice Style

- Conversational, founder energy. Use "honestly," "yeah," contractions, sentence fragments.
- Numbers over adjectives. Specific over abstract.
- No filler ("I hope you're doing well"). No corporate ("leverage," "synergies").
- For PLG companies, use developer/PLG-fluent language. For sales-led companies, use pipeline/meeting language.

## Lead

**Name:** {first_name} {last_name}
**Role:** {role}
**Company:** {company}
**Vertical:** {vertical}
**Motion:** {motion}
**Personalized hook:** {personalized_hook}
**Recommended angle:** {recommended_angle}

## Output Format

Return JSON only:

```json
{{
  "personalized_first_half": "<spoken text, 65-75 words, ending in transition phrase that flows into 'So let me be quick about this.'>"
}}
```

## Output Rules

- Output ONLY the JSON.
- First name in first 4 seconds.
- Beat 2 (the "real human / your site on screen" line) MUST be present.
- Beat 3 MUST reference the hook concretely AND use motion-appropriate language.
- Never pitch "booked meetings" to a `plg_self_serve` lead.
- Never invent facts. Never mention AI/automation as the source of the video.
