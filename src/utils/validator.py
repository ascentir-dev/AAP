"""
Pipeline asset validator.

Two hard gates — both must pass or the lead is failed immediately:

  Gate 1 — pre_upload_gate(lead_id, paths, email)
    Called after composite (step 9), before any R2 upload.
    Checks local files on disk: video integrity, audio, thumbnail, face image,
    email content. Uses ffprobe for accurate video/audio inspection.

  Gate 2 — post_upload_gate(lead_id, hosting, email)
    Called after R2 upload (step 10), before Smartlead push.
    Checks every remote URL is live, correct content-type, landing page has
    the right video src and Calendly link, tracking worker redirects correctly.

Raises ValidationError (subclass of RuntimeError) on the first failing check
in each gate. The pipeline's except block catches this and marks the lead failed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import urllib.error
import urllib.request
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Shared SSL context — reused for all remote checks
_SSL_CTX = ssl.create_default_context()

# Thresholds
# NOTE: _MIN_AUDIO_BYTES was 200 KB — calibrated for ElevenLabs (128 kbps → ~700 KB/44s).
# Edge TTS runs at ~33 kbps, so a valid 44s file is naturally ~180 KB. Lowered to 80 KB
# which still catches truly empty/silent files (silence at 33 kbps for 5s ≈ 20 KB).
_MIN_AUDIO_BYTES      = 80_000       # 80 KB   — covers Edge TTS (~33 kbps) + ElevenLabs
_MIN_SCROLL_BYTES     = 500_000      # 500 KB
_MIN_FINAL_BYTES      = 1_000_000    # 1 MB
_MIN_THUMB_BYTES      = 5_000        # 5 KB
_MIN_EMAIL_THUMB_BYTES = 8_000       # 8 KB
_MIN_FACE_BYTES       = 10_000       # 10 KB  — placeholder check
# NOTE: _VIDEO_DURATION_MIN was 45.0s. Edge TTS can run ~5-10% faster than the 165 WPM
# estimate, producing 43-44s output for scripts that estimate at 45-46s. Lowered to 42s —
# still catches genuinely short scripts while allowing for TTS speed variation.
_VIDEO_DURATION_MIN   = 42.0         # seconds (was 45.0 — Edge TTS speed variation)
_VIDEO_DURATION_MAX   = 80.0         # seconds
_EXPECTED_WIDTH       = 1280
_EXPECTED_HEIGHT      = 720
_MAX_SUBJECT_CHARS    = 60
_HTTP_TIMEOUT         = 15           # seconds for remote checks


class ValidationError(RuntimeError):
    """Raised when a validation gate fails. Message describes the exact check."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _check(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _ffprobe(path: Path) -> dict:
    """Run ffprobe on path and return parsed JSON. Raises on error."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=30)
        return json.loads(out)
    except subprocess.CalledProcessError as e:
        raise ValidationError(f"ffprobe failed on {path.name}: {e.output.decode()[:200]}")
    except subprocess.TimeoutExpired:
        raise ValidationError(f"ffprobe timed out on {path.name}")
    except (json.JSONDecodeError, ValueError) as e:
        raise ValidationError(f"ffprobe output unparseable for {path.name}: {e}")


def _http_get(url: str, follow_redirects: bool = True) -> tuple[int, str, str]:
    """
    Fetch url, return (status_code, body_snippet, location_header).
    Does NOT follow redirects when follow_redirects=False (for tracking worker check).
    """
    class _NoRedirect(urllib.request.HTTPErrorProcessor):
        def http_response(self, req, r): return r
        https_response = http_response

    handlers: list = [urllib.request.HTTPSHandler(context=_SSL_CTX)]
    if not follow_redirects:
        handlers.append(_NoRedirect())
    opener = urllib.request.build_opener(*handlers)

    req = urllib.request.Request(url, headers={"User-Agent": "AscentirValidator/1.0"})
    try:
        with opener.open(req, timeout=_HTTP_TIMEOUT) as r:
            body = r.read(4096).decode("utf-8", errors="replace")
            return r.status, body, r.getheader("Location", "")
    except urllib.error.HTTPError as e:
        return e.code, "", ""
    except Exception as e:
        raise ValidationError(f"HTTP request failed for {url}: {e}")


# ── Gate 1 — Local asset checks ───────────────────────────────────────────────

def pre_upload_gate(
    lead_id: str,
    paths: dict[str, Path],
    email: dict[str, Any],
    face_path: Path,
) -> None:
    """
    Validates all local files before any R2 upload.
    paths keys: audio, scroll, final_video, thumb, email_thumb
    """
    log.info(f"[{lead_id}] Gate 1: validating local assets")

    # ── 1. File existence + minimum size ─────────────────────────────────────
    checks = [
        ("audio",       paths["audio"],       _MIN_AUDIO_BYTES,       "TTS audio"),
        ("scroll",      paths["scroll"],       _MIN_SCROLL_BYTES,      "scroll recording"),
        ("final_video", paths["final_video"],  _MIN_FINAL_BYTES,       "composited video"),
        ("email_thumb", paths["email_thumb"],  _MIN_EMAIL_THUMB_BYTES, "email thumbnail"),
    ]
    for key, path, min_bytes, label in checks:
        _check(path.exists(), f"Gate 1: {label} file missing: {path}")
        size = path.stat().st_size
        _check(
            size >= min_bytes,
            f"Gate 1: {label} suspiciously small ({size:,} bytes < {min_bytes:,}). "
            f"Likely empty/corrupt: {path.name}",
        )

    # ── 2. Website thumbnail (used as cover art — can be missing on resume) ──
    if paths.get("thumb") and paths["thumb"].exists():
        size = paths["thumb"].stat().st_size
        _check(
            size >= _MIN_THUMB_BYTES,
            f"Gate 1: website thumbnail suspiciously small ({size:,} bytes): {paths['thumb'].name}",
        )

    # ── 3. Face / corner image ────────────────────────────────────────────────
    _check(
        face_path.exists(),
        f"Gate 1: face image not found at {face_path}. "
        "Add assets/frank.jpg (your real headshot) before running the pipeline.",
    )
    face_size = face_path.stat().st_size
    _check(
        face_size >= _MIN_FACE_BYTES,
        f"Gate 1: face image is only {face_size:,} bytes — looks like a placeholder. "
        "Replace assets/frank.jpg with a real headshot photo.",
    )

    # ── 4. Final video — duration, resolution, audio stream ──────────────────
    probe = _ffprobe(paths["final_video"])
    streams = probe.get("streams", [])
    fmt     = probe.get("format", {})

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    _check(video_streams, f"Gate 1: no video stream found in {paths['final_video'].name}")
    _check(audio_streams, f"Gate 1: no audio stream in composited video — TTS may have failed")

    v = video_streams[0]
    width  = v.get("width",  0)
    height = v.get("height", 0)
    _check(
        width == _EXPECTED_WIDTH and height == _EXPECTED_HEIGHT,
        f"Gate 1: wrong video resolution {width}x{height}, expected {_EXPECTED_WIDTH}x{_EXPECTED_HEIGHT}",
    )

    duration = float(fmt.get("duration") or 0)
    _check(
        _VIDEO_DURATION_MIN <= duration <= _VIDEO_DURATION_MAX,
        f"Gate 1: video duration {duration:.1f}s is outside expected range "
        f"{_VIDEO_DURATION_MIN}-{_VIDEO_DURATION_MAX}s",
    )

    # ── 5. Email content ──────────────────────────────────────────────────────
    subject = email.get("subject", "")
    body    = email.get("body", "")

    _check(subject, "Gate 1: email subject is empty")
    _check(
        len(subject) <= _MAX_SUBJECT_CHARS,
        f"Gate 1: subject too long ({len(subject)} chars > {_MAX_SUBJECT_CHARS}): '{subject}'",
    )
    _check(
        "{VIDEO_LINK}" in body,
        "Gate 1: email body missing {VIDEO_LINK} placeholder — video won't be embedded",
    )
    _check(body.strip(), "Gate 1: email body is empty")

    # ── 6. No em/en dashes in email body ─────────────────────────────────────
    dashes_found = re.findall(r"[—–]", body)
    _check(
        not dashes_found,
        f"Gate 1: email body contains {len(dashes_found)} em/en dash(es) — AI writing signal. "
        "Check templates.yaml and email.md.",
    )

    log.info(f"[{lead_id}] Gate 1 passed: video {duration:.1f}s, {width}x{height}, audio OK, email OK")


# ── Gate 2 — Remote URL checks ────────────────────────────────────────────────

def post_upload_gate(
    lead_id: str,
    hosting: dict[str, str],
    email: dict[str, Any],
    expected_calendly_url: str,
) -> None:
    """
    Validates all remote URLs after R2 upload, before Smartlead push.
    """
    log.info(f"[{lead_id}] Gate 2: validating remote assets")

    video_url     = hosting.get("video_url", "")
    thumbnail_url = hosting.get("thumbnail_url", "")
    landing_url   = hosting.get("landing_url", "")
    tracking_url  = hosting.get("tracking_url", "")

    # ── 1. Video on R2 ───────────────────────────────────────────────────────
    _check(video_url, "Gate 2: video_url is empty — upload may have silently failed")
    status, _, _ = _http_get(video_url)
    _check(
        status == 200,
        f"Gate 2: video URL returned HTTP {status} (expected 200): {video_url}",
    )

    # ── 2. Thumbnail on R2 ───────────────────────────────────────────────────
    if thumbnail_url:
        status, _, _ = _http_get(thumbnail_url)
        _check(
            status == 200,
            f"Gate 2: thumbnail URL returned HTTP {status}: {thumbnail_url}",
        )

    # ── 3. Landing page on R2 ────────────────────────────────────────────────
    _check(landing_url, "Gate 2: landing_url is empty")
    status, body, _ = _http_get(landing_url)
    _check(
        status == 200,
        f"Gate 2: landing page returned HTTP {status}: {landing_url}",
    )
    _check(
        bool(video_url) and video_url in body,
        f"Gate 2: landing page does not reference the video URL. "
        "Landing page may have been generated before video was uploaded.",
    )
    _check(
        bool(expected_calendly_url) and expected_calendly_url in body,
        f"Gate 2: landing page has wrong Calendly URL. "
        f"Expected '{expected_calendly_url}' not found. "
        "Check settings.yaml calendly_url.",
    )

    # ── 4. Tracking worker redirect ───────────────────────────────────────────
    # Only check the 302 redirect when a Cloudflare Worker is deployed.
    # When tracking_url == landing_url the worker is not configured — the email
    # links directly to R2, so no redirect check is needed or possible.
    _check(tracking_url, "Gate 2: tracking_url is empty")
    if tracking_url != landing_url:
        status, _, location = _http_get(tracking_url, follow_redirects=False)
        _check(
            status == 302,
            f"Gate 2: tracking URL returned HTTP {status} instead of 302 redirect: {tracking_url}. "
            "Check CLOUDFLARE_WORKER_URL in .env and that the worker is deployed.",
        )
        _check(
            landing_url in location,
            f"Gate 2: tracking URL redirects to wrong location. "
            f"Expected '{landing_url}', got '{location}'",
        )

    log.info(f"[{lead_id}] Gate 2 passed: video, thumbnail, landing page, tracking URL all live")
