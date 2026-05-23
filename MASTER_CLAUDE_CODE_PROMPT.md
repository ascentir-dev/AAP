# MASTER CLAUDE CODE PROMPT

This is the prompt to paste into Claude Code after running `claude` from inside
the unzipped `lead-personalization-system/` folder.

Copy everything between the triple-backtick code fences below.

---

````
Read these files in order before writing any code:

1. CLAUDE.md
2. PLAYBOOK.md
3. FRAMEWORK_RESEARCH.md
4. ANALYTICS.md
5. COST_ARCHITECTURE.md
6. prompts/analysis.md
7. prompts/email.md
8. prompts/script.md
9. config/settings.yaml
10. .env.example

These define what this system does, why each module exists, what voice the AI
calls produce, and what configuration shape the modules read from.

ALREADY IMPLEMENTED — DO NOT MODIFY:
- src/orchestrator/__main__.py
- src/orchestrator/pipeline.py
- src/video/composite/compositor.py
- src/video/scroll/recorder.py
- src/smartlead/client.py
- src/analytics/__main__.py
- src/analytics/queries.py
- src/analytics/insights_generator.py
- src/analytics/variant_assigner.py
- src/dashboard/__main__.py
- src/dashboard/templates/dashboard.html
- src/dashboard/templates/_metrics_row.html
- src/dashboard/templates/_insights_panel.html
- src/dashboard/static/dashboard.css
- src/webhooks/server.py

YOUR JOB: build 12 stub modules in the exact order below. After each module:
- Write a pytest test in tests/ that verifies it works
- Run the test
- Don't move to the next module until the test passes

Don't batch. Don't skip ahead. Build one, test, verify, then proceed.

CONTEXT:
The system is for Frank, founder of Ascentir. We send personalized cold outreach
with a 55-second video to high-intent leads (companies that signaled interest in
AI automation, 100+ employees). The cold-email offer is a 14-Day Command Brief,
not the full Ascentir platform. Volume target: 30K/month with phased ramp
(5K → 12K → 30K over 3 months).

The system runs A/B tests across 9 variants modeled on proven cold-email
frameworks (PPP, AIDA, 3Cs, QVC, Authority, InvertedDemand, PAS). Each lead
gets deterministically assigned to a variant. Each variant has its own Smartlead
campaign. The dashboard at localhost:8000 reads webhooks back into a SQLite
ledger to show which variants are winning by reply rate and book rate, sliced
by framework, motion, and vertical.

------------------------------------------------------------
BUILD ORDER (12 modules)
------------------------------------------------------------

MODULE 1: src/utils/settings.py
- Pydantic Settings class loading from .env and config/settings.yaml
- Properties for all .env vars: anthropic_api_key, anthropic_analysis_model,
  anthropic_generation_model, openai_api_key, openai_tts_model, openai_tts_voice,
  elevenlabs_api_key, elevenlabs_voice_id, elevenlabs_model, apify_api_token,
  apify_linkedin_actor, linkedin_enrich_all, cloudflare_r2_account_id,
  cloudflare_r2_access_key_id, cloudflare_r2_secret_access_key, cloudflare_r2_bucket,
  cloudflare_r2_public_url, cloudflare_pages_base_url, smartlead_api_key,
  smartlead_campaign_id (the default fallback campaign), book_a_call_url, log_level,
  max_daily_budget_usd, max_concurrent_leads, batch_size_threshold,
  use_batch_api, use_prompt_caching
- Nested config objects from settings.yaml: your_identity, offer (including
  fixed_second_half_plg_self_serve, fixed_second_half_hybrid_sales_assisted,
  fixed_second_half_sales_led_outbound), variants, video, scroll_capture, composite,
  script, email, enrichment, orchestrator, cost_tracking, model_routing, tts,
  volume_ramp
- Method: active_test_config() -> dict | None
  Returns the variants[active_test] config with `id` field added to the dict, or
  None if no test configured. Used by analytics, dashboard, and orchestrator.
- Method: lookup_variant_arm(test_id, variant_id) -> dict | None
- Method: fixed_second_half_for_motion(motion: str) -> str
  Returns the appropriate fixed_second_half template based on motion. Used by
  the script builder.
- load_settings() returns a singleton (use lru_cache)
- Test: load and assert all required keys accessible; active_test_config() returns
  expected shape with arms list; fixed_second_half_for_motion('plg_self_serve')
  returns the PLG version.

MODULE 2: src/utils/ledger.py
- SQLite-backed lead state + event tracker
- Schema:
  CREATE TABLE leads (
    lead_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    company TEXT,
    website TEXT,
    role TEXT,
    vertical TEXT,
    motion TEXT,
    intent_confidence INTEGER,
    variant_id TEXT,
    test_id TEXT,
    framework TEXT,
    recommended_angle TEXT,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT
  );
  CREATE TABLE stages (
    lead_id TEXT,
    stage_name TEXT,
    data_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (lead_id, stage_name)
  );
  CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    smartlead_payload TEXT
  );
  CREATE INDEX idx_events_lead ON events(lead_id);
  CREATE INDEX idx_events_type_time ON events(event_type, occurred_at);
- Methods on Ledger class:
  - has_stage(lead_id, stage_name) -> bool
  - save_stage(lead_id, stage_name, data: dict) — JSON-serializes data
  - get_stage(lead_id, stage_name) -> dict | None
  - is_complete(lead_id) -> bool
  - mark_complete(lead_id, status='success')
  - mark_failed(lead_id, error: str)
  - save_lead_metadata(lead_id, **fields) — upsert into leads table
  - record_event(lead_id, event_type, occurred_at: datetime, smartlead_payload: dict)
  - lead_id_for_email(email: str) -> str | None — used by webhooks
- Use sqlite3 stdlib, not an ORM. Auto-create tables on Ledger() init.
- Path passed to constructor (default: 'ledger.sqlite').
- Test: write a stage, read it back; save lead metadata with variant_id and framework;
  record an event; verify lead_id_for_email returns the right id.

MODULE 3: src/utils/cost_tracker.py
- SQLite-backed cost ledger. Same DB as Ledger or separate — your call. Keep simple.
- Schema:
  CREATE TABLE costs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT,
    vendor TEXT NOT NULL,
    operation TEXT,
    cost_usd REAL NOT NULL,
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX idx_costs_lead ON costs(lead_id);
  CREATE INDEX idx_costs_date ON costs(occurred_at);
- Methods on CostTracker class:
  - log(lead_id, vendor, operation, cost_usd)
  - lead_cost(lead_id) -> float
  - daily_total() -> float (today's costs)
  - total() -> float (all costs)
  - check_budget() -> bool — True if daily_total < max_daily_budget_usd
- Test: log a few costs across vendors, verify totals and budget check.

MODULE 4: src/ingestion/csv_reader.py
- Function: read_leads(csv_path: Path) -> list[dict]
- Required columns: first_name, last_name, email, company, website, linkedin_url, role
- Optional columns: industry, company_size, priority
- For each row:
  - Lowercase + strip the email
  - Validate URL format on website (add https:// if missing)
  - Generate lead_id = hashlib.sha256(email.encode()).hexdigest()[:16]
- Skip rows with missing required fields, log warnings via logging module
- Use pandas or csv stdlib (your choice; csv stdlib is sufficient)
- Test: fixture CSV with 3 rows (good, missing email, no https://), assert correct
  behavior — 1 lead returned, 2 warnings logged.

MODULE 5: src/enrichment/website.py
- Function: async scrape_website(url: str, settings) -> dict[str, str]
- Use Playwright. Fetch homepage. Extract clean text via page.inner_text("body").
- Then look for <a> tags with hrefs containing about/product/platform/solutions/pricing
- Fetch up to 2 of those, extract their text too
- Cap each text field at settings.enrichment.website.max_text_chars_per_page (default 8000)
- Strip nav/footer noise (look for nav, footer, header tags and skip their content)
- Return: {
    "homepage_text": "...",
    "about_text": "...",
    "product_text": "...",
    "title": "<page title>",
    "meta_description": "<meta description if present>"
  }
- Wrap with tenacity retry (3 attempts, exponential backoff)
- Test: mock Playwright via pytest-asyncio + monkeypatch, verify output shape

MODULE 6: src/enrichment/linkedin.py
- Function: async enrich_linkedin(linkedin_url, settings, cost_tracker) -> dict
- Call Apify's LinkedIn profile scraper actor (settings.apify_linkedin_actor) via apify-client
- Return: {
    "headline": "...",
    "current_role": "...",
    "about": "...",
    "recent_post": "...",
    "company_size": "..."
  }
- Handle Apify rate limits and errors gracefully — return {} with logged warning if it fails
  (LinkedIn data is nice-to-have, not required for the pipeline to proceed)
- Log cost via cost_tracker: ~$0.008 per profile
- Test: mock the apify client, verify output shape and cost logging

MODULE 7: src/analysis/fit_analyzer.py
- Function: async analyze_fit(lead, enrichment, settings, cost_tracker) -> dict
- Load prompts/analysis.md as a template
- Substitute placeholders: {first_name}, {last_name}, {role}, {company}, {website},
  {website_summary} (concatenated text from enrichment), {linkedin_data} (formatted as
  "Headline: X\nRole: Y\n..." string)
- Call Claude using settings.model_routing.analysis_model (claude-haiku-4-5-20251001)
- CRITICAL: set cache_control: {"type": "ephemeral"} on the system prompt block
  to enable prompt caching — saves ~85% on input tokens at scale
- Parse JSON response, validate it has keys: vertical, motion, motion_evidence,
  personalized_hook, recommended_angle, intent_confidence, skip, skip_reason
- Validate motion is one of: plg_self_serve, hybrid_sales_assisted, sales_led_outbound
- Log cost based on response.usage (input + output tokens × Haiku 4.5 rates)
- Return the parsed dict
- Test: mock anthropic client to return a fake JSON; assert parsing works,
  validation catches bad motion values, cost is logged

MODULE 8: src/email/generator.py
- Function: async generate_email(lead, analysis, variant_arm, settings, cost_tracker) -> dict
- IMPORTANT: apply variant overrides BEFORE substituting prompt vars:
    from src.analytics.variant_assigner import apply_variant_overrides
    merged = apply_variant_overrides(analysis, variant_arm)
- Load prompts/email.md, substitute placeholders including {variant_id} = variant_arm['id']
- Call Claude using settings.model_routing.generation_model (claude-sonnet-4-6)
- If run size > settings.orchestrator.batch_size_threshold (500), use Batch API
  (50% cheaper, async, results in minutes-hours). Build a small BatchRunner helper
  in src/utils/batch_runner.py if you need it for this module.
- Validate output JSON has: subject, body, variant_id, framework_used, motion_used
- Validate body contains literal "{VIDEO_LINK}" string (with curly braces)
- If body doesn't contain {VIDEO_LINK}, retry once with explicit reminder in the message
- Save framework_used to ledger via save_lead_metadata so analytics can query by framework
- Test: mock anthropic; assert subject < 50 chars, body has placeholder, variant_id matches

MODULE 9: src/video/script/builder.py
- Function: async build_script(lead, analysis, variant_arm, settings, cost_tracker) -> dict
- Same variant-override pattern as email
- Load prompts/script.md, substitute placeholders, call Claude (Sonnet 4.6)
- Get personalized_first_half from response
- Get the right fixed second half from settings.fixed_second_half_for_motion(analysis['motion'])
- Concatenate: full_script = personalized_first_half + "\n\n" + fixed_second_half
- Calculate duration_seconds = word_count(full_script) / settings.script.speaking_rate_words_per_minute * 60
- Return: {
    "personalized_first_half": "...",
    "fixed_second_half": "...",
    "full_script": "<combined>",
    "duration_seconds": 38.5
  }
- Test: mock anthropic; verify concatenation, motion-correct second half is picked,
  duration calc is correct

MODULE 10: src/video/tts/tts_client.py
- Adapter pattern. NOT named elevenlabs_client.py.
- Function: async synthesize(text, output_path, settings, cost_tracker, voice_override=None) -> Path
- If voice_override or settings.tts.primary_provider == "openai":
  - Use OpenAI TTS (tts-1) with settings.tts.primary_voice (echo)
  - Cost: $15/M chars, so cost_usd = len(text) * 15 / 1_000_000
- If settings.tts.primary_provider == "elevenlabs" or voice_override == "elevenlabs":
  - Use ElevenLabs SDK with settings.elevenlabs_voice_id and settings.elevenlabs_model
  - Cost: ~$0.18 per 1K chars on Creator plan
- Save MP3 to output_path
- Log cost via cost_tracker
- Test: mock both providers; verify file is written; verify correct provider chosen
  based on settings; verify cost logging

MODULE 11: src/hosting/uploader.py
- Function: async upload_video(local_path, lead_id, settings) -> str
  - Upload to Cloudflare R2 via boto3 (S3-compatible)
  - Object key: f"videos/{lead_id}.mp4"
  - Return public URL: f"{settings.cloudflare_r2_public_url}/videos/{lead_id}.mp4"
- Function: async generate_landing_page(lead, video_url, settings) -> str
  - Render an HTML template with: lead first_name, video_url,
    settings.book_a_call_url, Ascentir branding
  - Template should include:
    - Autoplay video muted with controls (browsers block sound-on-autoplay)
    - Big "Book A Call" button below the video, links to settings.book_a_call_url
    - Mobile responsive layout
    - OG meta tags for social preview
  - Upload the HTML to R2 at f"pages/{lead_id}.html"
  - Return: f"{settings.cloudflare_pages_base_url}/v/{lead_id}"
    (the page route is handled by Cloudflare Pages or a CF Worker — Frank will set up)
- Test: mock boto3 client; verify upload calls; verify returned URLs match expected format

MODULE 12: src/orchestrator/pipeline.py — MODIFY EXISTING
- The current pipeline.py exists but doesn't call the variant_assigner or
  motion-aware second half. Update it to:

  After analyze_fit() returns:
    1. Save lead metadata to ledger including vertical, motion, intent_confidence
    2. Call variant_assigner.assign_variant(lead.lead_id, settings.active_test_config())
       to get the variant_arm dict
    3. Save lead metadata again with variant_id and test_id
    4. Pass variant_arm into both generate_email() and build_script()
    5. After generate_email() returns, save framework (from email_result['framework_used'])
       to ledger via save_lead_metadata
    6. Push to the variant arm's smartlead_campaign_id, NOT the global default
       (variant_arm['smartlead_campaign_id'])

- Don't touch the resume logic, retry logic, or the high-level stage flow — those work.
- Test: integration test with all modules mocked, verify variant_id flows correctly
  through the pipeline end-to-end and the right Smartlead campaign ID is used

------------------------------------------------------------
GLOBAL RULES
------------------------------------------------------------

- Type hints on every function signature
- Tenacity retries on every external API call (3 attempts, exponential backoff)
- Every external API call logs cost to cost_tracker
- Use httpx for HTTP, not requests
- No print statements — use logging module
- pytest tests in tests/ mirroring src/ structure
- pytest-asyncio for async tests
- Don't modify anything in src/orchestrator/__main__.py, src/video/composite/,
  src/video/scroll/, src/smartlead/, src/analytics/, src/dashboard/, or src/webhooks/
  — those are done

------------------------------------------------------------
WHEN ALL 12 MODULES BUILD AND TEST
------------------------------------------------------------

Run these checks in order:

1. Pipeline dry-run on 1 test lead:
   python -m src.orchestrator --csv data/input/sample_leads.csv --single-lead 0 --dry-run

   Expected: video appears at data/videos/{lead_id}_final.mp4, email JSON appears
   at data/output/{lead_id}.json. No actual Smartlead push.

2. Read the generated outputs. Open the video. Read the email. Confirm:
   - Email body contains the {VIDEO_LINK} placeholder substituted with the real URL
   - Subject is lowercase, under 50 chars
   - The variant_id field matches what the assigner picked
   - The framework matches what the variant config says

3. Analytics CLI loads with no crashes (will show empty data):
   python -m src.analytics report

4. Dashboard loads with no crashes:
   python -m src.dashboard
   Then curl http://localhost:8000/health → expect {"status":"ok"}
   Then curl http://localhost:8000/ → expect HTML rendering the empty dashboard

5. Webhook receiver loads:
   python -m src.webhooks.server
   Then curl -X POST http://localhost:8001/webhooks/smartlead with a fake payload
   Verify it logs the event correctly.

DO NOT push to live Smartlead until Frank explicitly approves a generated
email + video. The --dry-run flag exists for exactly this reason.

When all 5 checks pass, report back to Frank with:
- Confirmation all 12 modules build and tests pass
- The output of the dry-run check
- Any decisions you had to make that weren't obvious from the spec

Start with module 1 (settings.py). Build it, write its test, run the test, then
move to module 2. One at a time.
````

---

## Done? Now What?

After Claude Code finishes the build, see `SETUP_AND_BUILD.md` for the next steps —
testing, configuring Smartlead campaigns, the volume ramp plan.
