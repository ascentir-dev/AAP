# Setup & Build — Step by Step

This is the canonical walkthrough from "I just unzipped this" to "first lead is sent."
Follow it in order. Don't skip steps.

Time estimate end-to-end: **3-5 hours of active work**, spread across a day or two
because some steps require waiting (domain warmup, API key approvals).

---

## Phase 1 — Configure (60 minutes)

### 1.1 Unzip and open the project

```bash
unzip lead-personalization-system.zip
cd lead-personalization-system
```

Open the folder in your editor (Cursor, VS Code, whatever).

### 1.2 Read these 5 docs in order, in full

This is the part most people skip. Don't skip it. Each doc has a specific purpose.

1. **`README.md`** — 2-minute overview, file structure
2. **`PLAYBOOK.md`** — what this system is selling, to whom, with what offer
3. **`FRAMEWORK_RESEARCH.md`** — why each of the 9 email variants is structured the way it is
4. **`ANALYTICS.md`** — how the A/B testing tournament works
5. **`COST_ARCHITECTURE.md`** — model routing for ~$720/mo at 30K volume

If anything in these reads off (offer wording, ICP, voice), fix it before building.
The prompts inherit from these docs philosophically — if your read of the offer is
different from what's documented, the system will produce off-brand outputs.

### 1.3 Edit `config/settings.yaml`

Replace placeholders:
- `your_identity.your_first_name` — change "Frank" if your name isn't Frank
- `your_identity.your_company_name` — change "Ascentir" if needed
- All 9 `smartlead_campaign_id` slots in `variants.month_1_test.arms` — these need
  real Smartlead campaign IDs (you'll create them in Phase 3 below)

Read the three `fixed_second_half_*` blocks aloud. These are the pitch close on
every video. If a single phrase doesn't sound like you'd actually say it, change it.

### 1.4 Edit the three prompt files in `prompts/`

`prompts/analysis.md`, `prompts/email.md`, `prompts/script.md`.

Read each one end to end. Specifically:
- The voice rules (banned phrases, tone)
- The motion-aware language tables
- The proof points used in each variant

The proof points (50% below mid-market cost, 17-hour speed-to-lead, 5pt retention
= 25-95% profit) come from the Ascentir master document. Confirm they're accurate
to what you can deliver — if any are aspirational, soften before launch.

**Variant 7 has placeholder aggregate numbers** ($40M pipeline, $25M retained ARR
in 18 months). Replace with real Ascentir numbers, or drop Variant 7 from the
test by removing it from `variants.month_1_test.arms` in `settings.yaml`.

### 1.5 Save your headshot

Save a square 512x512 PNG of your face to `assets/corner_image.png`. Looking at
camera, smiling. This is the Loom-style circle in the bottom-left of every video.

If you don't have a good headshot, a quick selfie shot at a window with neutral
background, square-cropped, works fine. Don't use a logo — videos with faces
convert better than videos with logos.

### 1.6 Create `.env`

```bash
cp .env.example .env
```

Then fill in real values for these 7 services. **Get all keys before moving to
Phase 2 — Claude Code can't build modules that depend on services you haven't
set up yet.**

| Service | Where to get key | Minutes |
|---|---|---|
| Anthropic | console.anthropic.com → Settings → API Keys | 2 |
| OpenAI (TTS) | platform.openai.com → API Keys | 2 |
| Apify (LinkedIn) | console.apify.com → Settings → Integrations | 5 |
| Cloudflare R2 | dash.cloudflare.com → R2 → Manage R2 API Tokens | 10 |
| Smartlead | app.smartlead.ai → Settings → API | 2 |
| Calendly | calendly.com → Integrations → Webhooks (later) | 5 |
| Your booking URL | calendly.com or cal.com | 0 (you have it) |

**Cloudflare R2 setup needs care:**
- Create a bucket called `lead-videos` (or whatever — match `.env`)
- Enable public access on the bucket
- Either use the default R2 public URL, or map a custom subdomain (e.g.,
  `videos.yourdomain.com`) — recommended for cleaner URLs in cold emails
- For landing pages, set up a Cloudflare Pages project pointing at a route like
  `go.yourdomain.com/v/{lead_id}` — or for v0, just use the same R2 bucket and
  link `.html` directly. The system uploads HTML pages to `pages/{lead_id}.html`.

### 1.7 Test that the keys actually work

Quick sanity check before you build anything:

```bash
# Anthropic
curl -s https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-haiku-4-5-20251001","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'

# OpenAI
curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY" | head
```

If either returns an auth error, fix before proceeding.

---

## Phase 2 — Build with Claude Code (60-90 minutes)

### 2.1 Install Claude Code (if you don't have it)

```bash
npm install -g @anthropic-ai/claude-code
```

### 2.2 Run Claude Code in the project folder

```bash
cd lead-personalization-system
claude
```

### 2.3 Paste the master prompt

Open `MASTER_CLAUDE_CODE_PROMPT.md`. Copy the entire content between the triple
backticks (everything inside the ```` ```` block). Paste it into Claude Code as
your first message.

Claude Code will:
1. Read all the context docs
2. Build module 1 (`src/utils/settings.py`), write a test, run the test
3. If the test passes, move to module 2
4. Repeat for all 12 modules

Expect 60-90 minutes. Watch the terminal — if Claude Code asks you a clarifying
question, answer it. If a test fails, let Claude Code debug; only intervene if
it gets stuck for more than a few iterations.

### 2.4 When Claude Code finishes

It should report something like "all 12 modules built, all tests pass." It will
have run the dry-run check on 1 test lead and reported the output.

If anything failed, ask Claude Code to fix the specific module that failed before
moving on.

---

## Phase 3 — Test on yourself (30 minutes)

### 3.1 Create a 1-row test CSV

```bash
mkdir -p data/input
cat > data/input/test_lead_self.csv <<EOF
first_name,last_name,email,company,website,linkedin_url,role,industry
Frank,Frederico,YOUR_REAL_EMAIL@example.com,Ascentir,https://ascentir.com,https://linkedin.com/in/your-handle,Founder,B2B SaaS
EOF
```

Use your own email — you want to receive the test email yourself.

### 3.2 Run the pipeline in dry-run mode

```bash
python -m src.orchestrator --csv data/input/test_lead_self.csv --single-lead 0 --dry-run
```

This generates the email + video but does NOT push to Smartlead.

### 3.3 Watch the video and read the email

```bash
# Generated outputs:
ls data/videos/        # the .mp4 file
ls data/output/        # the email JSON
```

Open the .mp4 in any video player. Open the email JSON in your editor.

**Critical things to verify:**
- The video opens with "Hey Frank, it's Frank here..." (or your name)
- The "I'm a real human / your site on screen" line is there
- The personalized observation in the first half references something specific to your company
- The fixed second half sounds right for your motion (the system auto-detects)
- The email subject is lowercase, under 50 chars
- The email body contains a real video URL (not the literal placeholder)
- The variant_id and framework_used fields are populated

If any of these are off, edit the relevant prompt file (`prompts/analysis.md`,
`prompts/email.md`, or `prompts/script.md`) and re-run. Iterate until the output
is something you'd actually send.

### 3.4 Test all 9 variants on yourself

Make 9 copies of the test CSV with slightly different emails (e.g.,
`frank+v1@yourdomain.com` through `frank+v9@yourdomain.com` if your email
provider supports plus-addressing — Gmail does):

```bash
for i in 1 2 3 4 5 6 7 8 9; do
  python -m src.orchestrator --csv data/input/test_lead_v$i.csv --single-lead 0 --dry-run
done
```

You'll get 9 different videos + emails, one per variant. Watch all 9. Read all 9.
This is the single highest-leverage 30 minutes of QA you'll do — every email you
send for the next 6 months derives from these templates.

If a variant is off, fix the variant block in `prompts/email.md` and re-run.

---

## Phase 4 — Smartlead campaign setup (45 minutes)

### 4.1 Create 9 Smartlead campaigns

In Smartlead, create 9 separate campaigns:
- "Ascentir — Variant 1"
- "Ascentir — Variant 2"
- ... through Variant 9

For each campaign:
1. Set the email template to use these variables:
   - Subject: `{{custom_subject}}`
   - Body: `{{custom_body}}`
2. Configure the send schedule (Tuesday-Thursday 8-10am local time per Gong research)
3. Configure follow-up sequences (3-4 text-only emails over 2-3 weeks per campaign)

### 4.2 Distribute warmed inboxes evenly

You have 40-60 warmed inboxes. Split them across the 9 campaigns:
- 4-7 inboxes per campaign
- Each inbox sends 20-30/day max

At 20-30/day × 6 inboxes × 9 campaigns = ~1,500-1,600/day total = ~45,000/month
ceiling. Comfortably above the 30K target.

### 4.3 Copy campaign IDs into settings.yaml

For each campaign, copy the Smartlead campaign ID (visible in the URL when you
open the campaign) and paste it into the matching slot in `config/settings.yaml`:

```yaml
variants:
  month_1_test:
    arms:
      - id: "Variant 1"
        smartlead_campaign_id: "PASTE_REAL_ID_HERE"
        ...
```

### 4.4 Deploy the webhook receiver

The system needs a publicly-reachable URL Smartlead can POST events to. Two options:

**Option A: VPS (cleanest)**
- Spin up a $5/mo droplet (DigitalOcean / Linode / Hetzner)
- Install nginx + certbot for HTTPS
- Run `python -m src.webhooks.server` behind nginx
- Configure as a systemd service so it auto-restarts

**Option B: Cloudflare Tunnel (free, fastest)**
- Install cloudflared on your local machine
- Run `cloudflared tunnel --url http://localhost:8001`
- Get a public HTTPS URL like `https://random-words.trycloudflare.com`
- Run `python -m src.webhooks.server` locally, leave it running

In Smartlead → Settings → Webhooks, point at `https://your-url/webhooks/smartlead`.
In Calendly → Integrations → Webhooks, point at `https://your-url/webhooks/calendly`.

---

## Phase 5 — First real send (Day 1, 200 leads)

### 5.1 Prepare your CSV

Pull 200 leads from your high-intent database, formatted as the system expects:
```csv
first_name,last_name,email,company,website,linkedin_url,role,industry
Sarah,Chen,sarah@vercel.com,Vercel,https://vercel.com,https://linkedin.com/in/sarahchen,VP Sales,B2B SaaS
...
```

200 leads = ~22 per variant after deterministic assignment. Enough to spot
catastrophic problems but small enough to recover if something is wrong.

### 5.2 Run dry-run on the 200 first

```bash
python -m src.orchestrator --csv data/input/first_200.csv --dry-run
```

Wait for it to finish (~30-45 minutes at 8 concurrent leads). Then **read 10
random outputs**:

```bash
ls data/output/ | shuf | head -10 | xargs -I {} cat data/output/{}
```

Look for:
- Any hallucinated facts about the lead
- Any motion misclassifications (e.g., Vercel pitched as sales-led)
- Generic hooks that could've been written without looking at the lead
- Variant outputs that don't match the variant template

If you find issues, fix the relevant prompt and re-run. The dry-run is cheap
(~$5 for 200 leads); the real send is irreversible.

### 5.3 Run the real send

```bash
python -m src.orchestrator --csv data/input/first_200.csv
```

(no `--dry-run` flag = pushes to Smartlead live)

Smartlead will distribute the 200 across the 9 campaigns and send according to
each campaign's schedule.

### 5.4 Watch the dashboard

In a separate terminal:

```bash
python -m src.dashboard
```

Open `http://localhost:8000` in your browser. You'll see empty data initially,
then events trickle in as Smartlead sends and recipients open/reply.

**Read every reply** — in Smartlead's inbox, not in the dashboard. The qualitative
signal in real replies tells you 10x more than aggregate metrics at this volume.

### 5.5 Decision gate

After 24-48 hours:
- If you got 1+ booked calls and replies look healthy → scale to 1,000 leads
- If you got 0 bookings but multiple positive replies → scale to 1,000, the funnel is working but slow
- If you got 0 replies of any kind → STOP. Debug deliverability before sending more.
  Check inbox warmup, SPF/DKIM/DMARC, and whether your videos are loading.

---

## Phase 6 — The volume ramp

### Week 1: 1,000 leads

Run the same flow as Phase 5 but with 1,000 leads. ~111 per variant.

After 1 week, run:
```bash
python -m src.analytics report --frameworks
python -m src.analytics report --heatmap
python -m src.analytics insights
```

You'll see early framework-level patterns. Don't declare winners yet — the
minimum sample size for significance is 1,500/variant.

### Weeks 2-3: Ramp to full Phase 1 volume (5,000/week)

By end of week 3 you should have 1,500+ sent per variant. The dashboard will
show "Significance reached" or "Min sample reached, no winner yet."

If a clear winner exists at the framework level (e.g., QVC dominates) and at
the variant level within that framework, declare the winner.

### Phase 2: Winners only

Edit `config/settings.yaml`:
```yaml
variants:
  active_test: "phase_2_finalists"
  locked: false  # temporarily unlock to switch tests
```

Then populate `phase_2_finalists.arms` with the top 4 winners (each at 25%
weight). Then re-lock:
```yaml
locked: true
```

Run for another 2-3 weeks. By the end, you have one winner across all dimensions.
That winner becomes your default for everything else.

### Months 2-3: Scale to 30K/month

Once you have a clear Phase 2 winner, scale volume to 12,000 in month 2 and
30,000 in month 3. The system handles the volume; the only thing that changes
is your CSV size and Smartlead's send pace.

---

## What to watch for

**Reply rate by framework** — the headline number. If your top framework hits
3-5%+ reply rate, you're in good territory. Below 1%, something's broken.

**Cost per booked call** — the bottom-line metric. At ~$0.024/lead and a 0.5-1%
book rate, expect $5-15 per booked call.

**Motion misclassification** — read the dashboard's framework × motion heatmap.
If one framework wins all three motions equally, the motion detector might be
collapsing everything to one category. Check the analysis prompt.

**Variant 9 firing too often or too rarely** — Variant 9 (PAS / concerning
observation) is conditional on the hook being genuinely concerning. If it's
firing for 20%+ of leads, the analysis prompt is being too liberal with what
counts as "concerning." If it's firing for 0%, soften the threshold.

---

## Costs you'll actually see

| Phase | Volume | Claude + APIs | Smartlead | Total |
|---|---|---|---|---|
| Test | 200 leads | $5 | (already paid) | $5 |
| Week 1 | 1,000 | $25 | included | $25 |
| Weeks 2-3 | 10,000 | $240 | $200/mo (40 inboxes) | $440 |
| Month 2 | 12,000 | $290 | $300/mo (60 inboxes) | $590 |
| Month 3+ | 30,000 | $720 | $300/mo | $1,020 |

Monthly steady-state at 30K: roughly **$1,000/month all-in** (APIs + Smartlead +
Cloudflare).

---

## When to ask for help

- After the first 100 sent emails: send me 3-5 generated outputs across different
  motions/variants. I'll review for any final prompt tuning.
- After the first 1,500 sent per variant: send me a screenshot of the dashboard.
  I'll help you read the data and decide on the Phase 2 winners.
- If reply rates are below 1% across ALL variants: that's a deliverability
  problem, not a copy problem. Send me the SPF/DKIM/DMARC config + a sample of
  the inbox warmup data.

The system is designed to give you decisions, not just dashboards. If something
is unclear from the data, the answer is usually: get more data (1,500+/variant),
or read 20 raw replies.
