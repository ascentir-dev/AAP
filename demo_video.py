"""
Demo: Loom-style personalised video — works for any URL.

The system measures the target website before deciding how to scroll:
  • Short page  → scrolls through it all, holds at top
  • Medium page → scrolls ~3 screens, hovers, returns to top
  • Long page   → caps at natural time budget, never gets stuck

Usage:
  python3 demo_video.py
  python3 demo_video.py --url https://example.com --duration 45
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── CLI args ──────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--url",      default="https://www.ascentir.io")
parser.add_argument("--duration", type=float, default=None,   # None = use settings.yaml
                    help="Override video duration in seconds")
parser.add_argument("--name",     default="Alex",             help="Lead first name")
parser.add_argument("--company",  default="Ascentir",         help="Lead company name")
args, _ = parser.parse_known_args()

DEMO_URL     = args.url
LEAD_NAME    = args.name
LEAD_COMPANY = args.company

# ── Output paths ──────────────────────────────────────────────────────────────
OUT_DIR = Path("data/output/demo")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SCROLL_PATH = OUT_DIR / "scroll_raw.mp4"
AUDIO_PATH  = OUT_DIR / "voiceover.mp3"
FRAME_PATH  = OUT_DIR / "browser_frame.png"
FINAL_PATH  = OUT_DIR / "demo_final.mp4"

# ── Face photo ────────────────────────────────────────────────────────────────
_PHOTO_CANDIDATES = [
    Path("assets/frank.jpg"),
    Path("assets/frank_alt.jpg"),
    Path("assets/frank.png"),
]
FACE_PATH = next((p for p in _PHOTO_CANDIDATES if p.exists()),
                 OUT_DIR / "face_placeholder.png")

# ── Script ────────────────────────────────────────────────────────────────────
def build_script(name: str, company: str, variant_id: str | None = None) -> tuple[str, str]:
    """
    Return (script_text, variant_id) using the video_scripts A/B system.
    If variant_id is supplied, that variant is used; otherwise one is assigned
    deterministically from the company name.
    """
    from src.ai_cold_email.video.script.video_scripts import render_script, assign_variant
    vid = variant_id or assign_variant(company)
    lead = {"first_name": name, "company": company}
    return render_script(vid, lead), vid


def _make_placeholder_face(path: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
        size = 400
        img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for r in range(size // 2, 0, -1):
            ratio = r / (size // 2)
            c = int(30 + ratio * 40)
            draw.ellipse([size//2-r, size//2-r, size//2+r, size//2+r],
                         fill=(c, c+20, c+60, 255))
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 180)
        except Exception:
            font = ImageFont.load_default()
        draw.text((size//2, size//2), "F",
                  fill=(255, 255, 255, 255), font=font, anchor="mm")
        img.save(str(path))
    except ImportError:
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", "color=c=0x1a3a6e:size=400x400:rate=1",
             "-frames:v", "1", str(path)],
            check=True, capture_output=True,
        )


async def main():
    from src.utils.settings import Settings
    from src.utils.cost_tracker import CostTracker
    from src.ai_cold_email.video.scroll.recorder import record_scroll
    from src.ai_cold_email.video.tts.tts_client import synthesize
    from src.ai_cold_email.video.composite.compositor import composite_video
    from src.ai_cold_email.video.composite.browser_frame import (
        make_browser_frame, CHROME_HEADER_HEIGHT,
    )

    settings     = Settings()
    cost_tracker = CostTracker()

    dur = args.duration or settings.video["duration_seconds"]
    W   = settings.video["resolution"]["width"]    # 1280
    H   = settings.video["resolution"]["height"]   # 720

    content_y = CHROME_HEADER_HEIGHT               # 96
    content_h = H - content_y                      # 624

    # ── Face photo ───────────────────────────────────────────────────────────
    if not FACE_PATH.exists():
        log.info("No headshot found — generating placeholder")
        _make_placeholder_face(FACE_PATH)
    log.info(f"Face: {FACE_PATH.name}")

    # ── 1. Record scroll (adaptive — measures page first) ────────────────────
    log.info(f"Recording scroll: {DEMO_URL}  ({dur:.0f}s)")
    result = await record_scroll(
        url=DEMO_URL,
        duration_seconds=dur,
        output_path=SCROLL_PATH,
        settings=settings,
        viewport_height=content_h,     # 624 — fits below Chrome header
    )
    page_title = result.page_title or LEAD_COMPANY
    log.info(f"Page title: '{page_title}'  |  height: {result.page_height}px  "
             f"|  scrolled: {result.scroll_px:.0f}px")

    # ── 2. Browser frame (uses real page title and URL) ───────────────────────
    log.info("Rendering Chrome browser frame...")
    make_browser_frame(
        url=DEMO_URL,
        width=W,
        height=H,
        out_path=FRAME_PATH,
        page_title=page_title,
    )

    # ── 3. TTS voiceover ─────────────────────────────────────────────────────
    script, variant_id = build_script(LEAD_NAME, LEAD_COMPANY)
    log.info(f"Script variant: {variant_id}")
    log.info("Synthesising voiceover (ElevenLabs)...")
    await synthesize(
        text=script,
        output_path=AUDIO_PATH,
        settings=settings,
        cost_tracker=cost_tracker,
    )
    log.info(f"Audio: {AUDIO_PATH.stat().st_size // 1024} KB")

    # ── 4. Composite ─────────────────────────────────────────────────────────
    log.info("Compositing: scroll + Chrome frame + face circle + CTA + audio...")
    await composite_video(
        scroll_video=SCROLL_PATH,
        audio=AUDIO_PATH,
        corner_image=FACE_PATH,
        output_path=FINAL_PATH,
        settings=settings,
        browser_frame=FRAME_PATH,
        content_y=content_y,
        thumbnail_path=result.thumbnail_path,   # website homepage → video cover art
    )

    # ── 5. Track sent event ──────────────────────────────────────────────────
    try:
        import src.utils.video_tracker as vt
        lead_id   = f"{LEAD_NAME.lower()}_{LEAD_COMPANY.lower()}".replace(" ", "_")
        video_url = str(FINAL_PATH.resolve())   # local path until uploaded to R2
        vt.log_sent(
            lead_id=lead_id,
            variant_id=variant_id,
            video_url=video_url,
            email="",
            company=LEAD_COMPANY,
        )
        log.info(f"Tracked: lead_id={lead_id}  variant={variant_id}")
    except Exception as e:
        log.warning(f"Tracking skipped: {e}")

    size_mb = FINAL_PATH.stat().st_size / (1024 * 1024)
    print(f"\n{'='*62}")
    print(f"  VIDEO COMPLETE: {FINAL_PATH.name}  ({size_mb:.1f} MB)")
    print(f"  URL    : {DEMO_URL}")
    print(f"  Lead   : {LEAD_NAME} @ {LEAD_COMPANY}")
    print(f"  Variant: {variant_id}")
    print(f"  Page   : {result.page_height}px tall, scrolled {result.scroll_px:.0f}px")
    print(f"{'='*62}")
    print(f"\n🎬  {FINAL_PATH.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
