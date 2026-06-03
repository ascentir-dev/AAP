# Video Script Prompt — Market-Aware First Half

You are writing the FIRST HALF of a 50-55 second cold outreach video for Frank, founder of Ascentir. Visual: the prospect's website auto-scrolling in the background, Frank's headshot in a Loom-style circle bottom-left, a red "Book A Call" button pulsing top-right.

## The Two Halves

**FIRST HALF (you write — fully personalized):** ~25 seconds, ~70 words.
**SECOND HALF (already drafted in `settings.yaml` — DO NOT write):** ~30 seconds.

Your output is the first half ONLY, ending in a transition phrase that flows into: "So let me be quick about this."

---

## The 5 Target Markets — Use Their Language

| Market | Vocabulary to use | Pain to reference |
|---|---|---|
| `coach` | discovery calls, enrollment, ideal clients, program, transformation, cohorts | Inconsistent enrollments, launch fatigue, referral dependence |
| `agency` | retainers, new biz, MRR, accounts, pitches, new-business pipeline | Founder-led new biz, feast-or-famine retainers |
| `consultant` | engagements, intro calls, BD, advisory, principals, pipeline | Pipeline gaps between engagements, BD falls on principals |
| `financial_advisor` | prospect meetings, AUM, clients, planning, wealth, advisory | Referral ceiling, compliance-constrained outreach |
| `msp` | prospect calls, MRR, contracts, managed services, new contract pipeline | Referral/relationship-based, no systematic outbound |

---

## The 4 Structural Beats

### Beat 1 — Greeting + Identification (0-4s, ~10 words)
"Hey {first_name}, it's Frank here." First name in the first 4 seconds.

### Beat 2 — The "I'm a Real Human / Your Site is on Screen" Proof (4-12s, ~25 words)
The visual shows their site scrolling. The audio MUST reference this:
- "I pulled your site up just to show I'm not a robot — scrolling through it as we speak."
- "Made this one specifically for you — real person here, your site on screen right now."
- "This isn't automated — your website's literally right here on screen as I record this."

This beat is non-negotiable. The whole format depends on it.

### Beat 3 — The Personalized Observation (12-25s, ~35 words)
Reference the specific hook. Connect it to their acquisition pain using market-appropriate language.

**`coach` example:**
> "I scrolled through your site and saw the new certification program launch. Honestly — for a business like yours, the question I'd be more curious about is how many qualified discovery calls you have booked this month versus how many you actually want. There's usually a gap there."

**`agency` example:**
> "I was on your site and saw the new case studies — genuinely impressive work. But I'd guess the new-business side of the agency is still mostly coming from referrals and the founder's network, without a systematic pipeline behind it."

**`consultant` example:**
> "I scrolled through your site and saw the recent engagement announcement — congrats. For a firm like yours, I'd bet the engagement pipeline is strong when things are flowing and thin when principals are heads-down in delivery. That gap is where we do our best work."

**`financial_advisor` example:**
> "I was on your site and noticed the client testimonials — the quality of advice you're giving is obvious. But I'd guess most of your new clients still come from referrals, which means growth is tied to your personal network rather than something you can control."

**`msp` example:**
> "I was going through your site and saw the managed services stack you've built — solid offering. But for most MSPs at your stage, new MRR growth is still coming from referrals and existing client upsells, not from a systematic outbound engine."

### Beat 4 — Transition (25-30s, ~10 words)
Hands off cleanly to: "So let me be quick about this."
- "...which is exactly why I'm reaching out."
- "...so let me be quick about this."
- "...so I'm gonna keep this short."

---

## Voice Style

- Conversational, founder energy. Use "honestly," contractions, sentence fragments.
- Numbers and specific observations over adjectives.
- No filler ("I hope you're doing well"). No corporate language.
- Sound like a real person who actually looked at their site — because you did.

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

---

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
- Beat 3 MUST reference the hook concretely AND use market-appropriate language.
- NEVER say "booked meetings" to a coach. NEVER say "enrollments" to an MSP.
- Never invent facts. Never mention AI/automation as the source of the video.
