"""
Deploy the Ascentir Video Tracking Worker to Cloudflare.

What it does (one-time setup):
  1. Creates a KV namespace called "ascentir-views" (skips if already exists)
  2. Deploys tools/cloudflare_worker.js as a Worker script with the KV binding
  3. Prints the worker URL
  4. Writes CLOUDFLARE_WORKER_URL and CLOUDFLARE_KV_NAMESPACE_ID to .env

Requirements:
  - CLOUDFLARE_R2_ACCOUNT_ID already in .env
  - CLOUDFLARE_API_TOKEN in .env  (needs Workers:Edit + KV:Edit permissions)

Usage:
  python3 tools/deploy_tracking_worker.py

To get an API token:
  dash.cloudflare.com → My Profile → API Tokens → Create Token
  Template: "Edit Cloudflare Workers" — gives Workers + KV access
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WORKER_NAME   = "ascentir-tracker"
KV_NAMESPACE  = "ascentir-views"
WORKER_JS     = ROOT / "tools" / "cloudflare_worker.js"
ENV_PATH      = ROOT / ".env"


def _check(ok: bool, label: str, detail: str = "") -> None:
    icon = "✓" if ok else "✗"
    print(f"  {icon}  {label}" + (f"\n       {detail}" if detail else ""))
    if not ok:
        sys.exit(1)


def _update_env(key: str, value: str) -> None:
    """Add or update a key in .env."""
    text = ENV_PATH.read_text()
    pattern = rf"^{re.escape(key)}=.*$"
    new_line = f"{key}={value}"
    if re.search(pattern, text, re.MULTILINE):
        text = re.sub(pattern, new_line, text, flags=re.MULTILINE)
    else:
        text = text.rstrip() + f"\n{new_line}\n"
    ENV_PATH.write_text(text)


def main() -> None:
    import httpx

    from src.utils.settings import Settings
    s = Settings()

    print("\n── Deploy Tracking Worker ──────────────────────────────────────\n")

    # Check API token
    api_token = getattr(s, "cloudflare_api_token", "") or ""
    _check(bool(api_token), "CLOUDFLARE_API_TOKEN set in .env",
           "Add it: dash.cloudflare.com → My Profile → API Tokens → Create Token\n"
           "       Use the 'Edit Cloudflare Workers' template, then add CLOUDFLARE_API_TOKEN=xxx to .env"
           if not api_token else "")

    account_id = s.cloudflare_r2_account_id
    r2_public  = s.cloudflare_r2_public_url
    _check(bool(account_id), "CLOUDFLARE_R2_ACCOUNT_ID set")
    _check(bool(r2_public) and "example.com" not in r2_public, "CLOUDFLARE_R2_PUBLIC_URL set")

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type":  "application/json",
    }
    base = f"https://api.cloudflare.com/client/v4/accounts/{account_id}"

    # ── 1. Create (or get) KV namespace ──────────────────────────────────────
    print("  Creating KV namespace…")
    r = httpx.post(f"{base}/storage/kv/namespaces",
                   headers=headers,
                   json={"title": KV_NAMESPACE})

    if r.status_code == 200 and r.json().get("success"):
        kv_id = r.json()["result"]["id"]
        print(f"  ✓  KV namespace created: {kv_id}")
    elif r.status_code == 400 and "already exists" in r.text.lower():
        # Get existing
        r2 = httpx.get(f"{base}/storage/kv/namespaces", headers=headers)
        ns_list = r2.json().get("result", [])
        existing = next((n for n in ns_list if n["title"] == KV_NAMESPACE), None)
        _check(bool(existing), f"KV namespace '{KV_NAMESPACE}' exists",
               f"Could not find existing namespace: {r.text[:100]}" if not existing else "")
        kv_id = existing["id"]
        print(f"  –  KV namespace already exists: {kv_id}")
    else:
        _check(False, "Create KV namespace", r.text[:200])
        return

    # ── 2. Deploy Worker script ───────────────────────────────────────────────
    print("  Deploying Worker script…")
    script_code = WORKER_JS.read_text()

    # Multipart upload: metadata + script (ES module format)
    import json
    metadata = {
        "main_module": "worker.js",
        "bindings": [
            {
                "type": "kv_namespace",
                "name": "VIEWS",
                "namespace_id": kv_id,
            },
            {
                "type": "plain_text",
                "name": "R2_PUBLIC_URL",
                "text": r2_public.rstrip("/"),
            },
        ],
        "compatibility_date": "2024-01-01",
    }

    import httpx as _httpx
    # Use multipart/form-data for Workers API
    deploy_r = _httpx.put(
        f"{base}/workers/scripts/{WORKER_NAME}",
        headers={"Authorization": f"Bearer {api_token}"},
        files={
            "metadata":   (None, json.dumps(metadata), "application/json"),
            "worker.js":  ("worker.js", script_code, "application/javascript+module"),
        },
    )

    if deploy_r.status_code in (200, 201) and deploy_r.json().get("success"):
        print(f"  ✓  Worker deployed: {WORKER_NAME}")
    else:
        _check(False, "Deploy Worker", deploy_r.text[:300])
        return

    # ── 3. Get worker subdomain ───────────────────────────────────────────────
    sub_r = httpx.get(f"{base}/workers/subdomain", headers=headers)
    subdomain = sub_r.json().get("result", {}).get("subdomain", "")
    _check(bool(subdomain), "Get workers.dev subdomain",
           "Could not get subdomain — check your account has Workers enabled." if not subdomain else "")

    worker_url = f"https://{WORKER_NAME}.{subdomain}.workers.dev"
    print(f"  ✓  Worker URL: {worker_url}")

    # ── 4. Test /health ───────────────────────────────────────────────────────
    import time
    time.sleep(2)   # brief propagation wait
    try:
        health = httpx.get(f"{worker_url}/health", timeout=10)
        ok = health.status_code == 200
    except Exception:
        ok = False
    print(f"  {'✓' if ok else '–'}  Health check: {'OK' if ok else 'not yet reachable (may take ~30s to propagate)'}")

    # ── 5. Update .env ────────────────────────────────────────────────────────
    _update_env("CLOUDFLARE_WORKER_URL",      worker_url)
    _update_env("CLOUDFLARE_KV_NAMESPACE_ID", kv_id)
    _update_env("CLOUDFLARE_API_TOKEN",       api_token)
    print(f"\n  ✓  .env updated with CLOUDFLARE_WORKER_URL and CLOUDFLARE_KV_NAMESPACE_ID")

    print(f"""
  ── Done ──────────────────────────────────────────────────────────

  Tracking URL format in emails:
    {worker_url}/v/{{lead_id}}

  Landing pages on R2:
    {r2_public}/pages/{{lead_id}}.html

  Dashboard sync:
    python3 -c "from src.utils.video_tracker import sync_from_cloudflare_kv; import asyncio; asyncio.run(sync_from_cloudflare_kv())"

  Next: run a campaign and views will appear in your Testing Dashboard.
""")


if __name__ == "__main__":
    main()
