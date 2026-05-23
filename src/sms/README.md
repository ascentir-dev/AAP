# SMS System

Part of the Agentic Acquisition Platform. Outbound SMS with 3-number rotation and two-way inbox.

## How it works

1. **Send** — generates personalized SMS via Claude, sends via Twilio from lead's assigned number
2. **Rotate** — `md5(lead_id) % 3` assigns a number deterministically (same lead = same number always)
3. **Receive** — Twilio webhook (`POST /api/sms/webhook/inbound`) routes inbound to correct lead
4. **Reply** — dashboard inbox lets you reply from the lead's assigned number

## Data separation

SMS uses its own SQLite ledger (`data/sms_ledger.sqlite`) — completely independent of the email ledger.
Analytics, variant tracking, and number health are all kept separate.

## A/B Test Variants

6 variants in `config/settings.yaml` under `sms.variants.sms_framework_v1`:

| ID | Name | Framework |
|---|---|---|
| SMS-V1 | Direct Value | Observation + specific promise |
| SMS-V2 | Social Proof | Proof from similar company |
| SMS-V3 | Question Hook | Provocative question |
| SMS-V4 | PAS | Problem / agitate / solve |
| SMS-V5 | Compliment + CTA | Hook compliment + open question |
| SMS-V6 | Scarcity | Heads-up / inverted demand |

## Prompts

SMS prompt: `prompts/sms/sms.md`

## Twilio Webhook Setup

Configure each number in Twilio console:
> Phone Numbers → Active Numbers → [number] → Messaging → A message comes in  
> Webhook POST: `https://your-domain.com/api/sms/webhook/inbound`
