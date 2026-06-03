"""
Cloudflare R2 uploader + landing page generator.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import boto3
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

_LANDING_PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>A message for {first_name} from Ascentir</title>
  <meta property="og:title" content="A personal message for {first_name}" />
  <meta property="og:description" content="{sender_name} from Ascentir recorded this specifically for you." />
  <meta property="og:video" content="{video_url}" />
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#0f0f0f;color:#fff;min-height:100vh;
          display:flex;flex-direction:column;align-items:center;
          justify-content:center;padding:24px}}
    .wrap{{max-width:720px;width:100%}}
    h1{{font-size:1.3rem;margin-bottom:16px;font-weight:500;color:#e0e0e0}}
    video{{width:100%;border-radius:12px;box-shadow:0 8px 40px rgba(0,0,0,.6)}}
    .cta{{margin-top:28px;text-align:center}}
    .cta a{{display:inline-block;background:#E63946;color:#fff;
            padding:18px 48px;border-radius:8px;text-decoration:none;
            font-size:1.1rem;font-weight:700;letter-spacing:.04em}}
    .cta a:hover{{background:#c1121f}}
    .sub{{margin-top:12px;font-size:.8rem;color:#555;text-align:center}}
    .sender{{margin-top:24px;font-size:.75rem;color:#444;text-align:center}}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Hey {first_name} — {sender_name} recorded this for you</h1>
    <video autoplay muted controls playsinline preload="auto">
      <source src="{video_url}" type="video/mp4">
    </video>
    <div class="cta">
      <a href="{book_a_call_url}" target="_blank" rel="noopener">🤖 GET A.I DEMO</a>
    </div>
    <p class="sub">20 minutes &middot; No obligation &middot; Leave your card at home</p>
    <p class="sender">Sent personally by {sender_name} &middot; Ascentir</p>
  </div>
</body>
</html>
"""


def _make_s3_client(settings: Any) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.cloudflare_r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.cloudflare_r2_access_key_id,
        aws_secret_access_key=settings.cloudflare_r2_secret_access_key,
        region_name="auto",
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def upload_video(local_path: Path, lead_id: str, settings: Any) -> str:
    """Upload MP4 to R2. Returns the public URL."""
    object_key = f"videos/{lead_id}.mp4"
    s3 = _make_s3_client(settings)
    s3.upload_file(
        str(local_path),
        settings.cloudflare_r2_bucket,
        object_key,
        ExtraArgs={"ContentType": "video/mp4"},
    )
    return f"{settings.cloudflare_r2_public_url}/{object_key}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def upload_thumbnail(local_path: Path, lead_id: str, settings: Any) -> str:
    """Upload email thumbnail JPEG to R2. Returns the public URL."""
    object_key = f"thumbnails/{lead_id}.jpg"
    s3 = _make_s3_client(settings)
    s3.upload_file(
        str(local_path),
        settings.cloudflare_r2_bucket,
        object_key,
        ExtraArgs={"ContentType": "image/jpeg"},
    )
    return f"{settings.cloudflare_r2_public_url}/{object_key}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_landing_page(
    lead: dict[str, Any],
    video_url: str,
    settings: Any,
    cta_url: str = "",
) -> str:
    """
    Render static HTML landing page and upload to R2.
    Returns the public R2 URL for the page (e.g. https://pub-xxx.r2.dev/pages/{lead_id}.html).
    """
    identity = settings.your_identity if isinstance(settings.your_identity, dict) else {}
    book_url = cta_url or identity.get("calendly_url", "") or settings.book_a_call_url
    sender   = identity.get("your_first_name", "Frank")

    html = _LANDING_PAGE_TEMPLATE.format(
        first_name=lead.get("first_name", ""),
        video_url=video_url,
        book_a_call_url=book_url,
        sender_name=sender,
    )

    lead_id    = lead["lead_id"]
    object_key = f"pages/{lead_id}.html"
    s3 = _make_s3_client(settings)
    s3.put_object(
        Bucket=settings.cloudflare_r2_bucket,
        Key=object_key,
        Body=html.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )
    return f"{settings.cloudflare_r2_public_url}/{object_key}"
