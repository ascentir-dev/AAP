"""
R2 Setup Verifier — run once before your first campaign.

Checks:
  1. Credentials are set in .env
  2. boto3 can reach your R2 bucket
  3. Uploads a tiny test file and gets a public URL back
  4. Confirms the URL is publicly accessible via HTTP

Usage:
  python3 tools/setup_r2.py

On success: prints a green ✓ for each check and the test URL.
On failure: prints exactly what is wrong and how to fix it.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# ── make sure we can import from src ─────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _check(label: str, ok: bool, detail: str = "") -> None:
    icon = "✓" if ok else "✗"
    line = f"  {icon}  {label}"
    if detail:
        line += f"\n       {detail}"
    print(line)
    if not ok:
        sys.exit(1)


def main() -> None:
    print("\n── Cloudflare R2 Setup Check ─────────────────────────────────────\n")

    # 1. Load settings (reads .env automatically)
    try:
        from src.utils.settings import Settings
        s = Settings()
    except Exception as e:
        _check("Load settings", False, f"Could not load settings: {e}")
        return

    # 2. Check required fields
    missing = []
    for field in ("cloudflare_r2_account_id", "cloudflare_r2_access_key_id",
                  "cloudflare_r2_secret_access_key", "cloudflare_r2_bucket",
                  "cloudflare_r2_public_url"):
        val = getattr(s, field, "")
        if not val or "example.com" in val or "XXXX" in val:
            missing.append(field.upper())

    _check(
        "Credentials in .env",
        not missing,
        f"Missing / placeholder values: {', '.join(missing)}\n"
        "       Open .env and fill in the real Cloudflare R2 values." if missing else "",
    )

    # 3. Import boto3
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError:
        _check("boto3 installed", False, "Run:  pip install boto3")
        return
    _check("boto3 installed", True)

    # 4. Connect to R2
    try:
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{s.cloudflare_r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=s.cloudflare_r2_access_key_id,
            aws_secret_access_key=s.cloudflare_r2_secret_access_key,
            region_name="auto",
        )
        client.head_bucket(Bucket=s.cloudflare_r2_bucket)
    except Exception as e:
        err = str(e)
        hint = ""
        if "NoSuchBucket" in err or "404" in err:
            hint = (f"Bucket '{s.cloudflare_r2_bucket}' does not exist.\n"
                    "       Create it at: dash.cloudflare.com → R2 → Create Bucket")
        elif "403" in err or "AccessDenied" in err or "InvalidAccessKeyId" in err:
            hint = ("API token has no access to this bucket.\n"
                    "       R2 → Manage R2 API Tokens → check Object Read & Write on "
                    f"'{s.cloudflare_r2_bucket}'")
        elif "EndpointResolutionError" in err or "connection" in err.lower():
            hint = "Wrong CLOUDFLARE_R2_ACCOUNT_ID — check the 32-char hex ID from the R2 dashboard."
        _check("Connect to R2 bucket", False, hint or err[:120])
        return
    _check("Connect to R2 bucket", True, f"Bucket: {s.cloudflare_r2_bucket}")

    # 5. Upload test file
    test_key = "test/setup_check.txt"
    test_body = f"R2 setup check — {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}".encode()
    try:
        client.put_object(
            Bucket=s.cloudflare_r2_bucket,
            Key=test_key,
            Body=test_body,
            ContentType="text/plain",
        )
    except Exception as e:
        _check("Upload test file", False, str(e)[:120])
        return
    _check("Upload test file", True)

    # 6. Build public URL and verify accessibility (use curl to avoid Python SSL quirks)
    public_url = f"{s.cloudflare_r2_public_url.rstrip('/')}/{test_key}"
    try:
        import subprocess
        result = subprocess.run(
            ["curl", "-si", "--max-time", "10", public_url],
            capture_output=True, text=True,
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        status_code = int(first_line.split()[1]) if len(first_line.split()) >= 2 else 0
        accessible = status_code == 200
        if not accessible:
            hint = ""
            if status_code == 403:
                hint = ("Bucket is not public.\n"
                        "       R2 → your bucket → Settings → Public Access → Allow Public Access")
            elif status_code == 0:
                hint = (f"Could not reach {public_url}\n"
                        "       Check CLOUDFLARE_R2_PUBLIC_URL in .env")
            else:
                hint = f"HTTP {status_code} — {first_line}"
            _check("Public URL accessible", False, hint)
            return
    except Exception as e:
        _check("Public URL accessible", False, str(e)[:120])
        return

    _check("Public URL accessible", accessible, public_url)

    # 7. Clean up test file
    try:
        client.delete_object(Bucket=s.cloudflare_r2_bucket, Key=test_key)
    except Exception:
        pass  # non-fatal

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("  All checks passed. R2 is ready.")
    print(f"\n  Videos will be uploaded to:")
    print(f"    {s.cloudflare_r2_public_url}/videos/{{lead_id}}.mp4")
    print(f"\n  Tracking links in emails will look like:")
    base = getattr(s, "base_url", "http://localhost:8000")
    print(f"    {base}/v/{{lead_id}}")
    print()
    print("  Next step: python3 run_batch.py --csv data/input/leads.csv --dry-run")
    print()


if __name__ == "__main__":
    main()
