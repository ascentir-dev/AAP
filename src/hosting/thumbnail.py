"""
Email thumbnail generator.

Takes the website screenshot captured during scroll recording and adds:
  - Subtle dark overlay (makes the play button pop)
  - White circle with a red play triangle in the centre
  - "Click to watch" hint text below the circle

Output is a JPEG sized to fit nicely in a cold email (~560px wide).
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

log = logging.getLogger(__name__)

_EMAIL_WIDTH  = 560   # px — fits most email clients without horizontal scroll
_JPEG_QUALITY = 88


def make_email_thumbnail(
    source: Path,
    output: Path,
    width: int = _EMAIL_WIDTH,
) -> Path:
    """
    Add a play button overlay to `source` (JPEG/PNG), save to `output`.
    Returns `output`.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError("Pillow required: pip install Pillow")

    img = Image.open(source).convert("RGB")

    # Resize to target width, keep aspect ratio
    orig_w, orig_h = img.size
    scale  = width / orig_w
    height = int(orig_h * scale)
    img    = img.resize((width, height), Image.LANCZOS)

    # Semi-transparent dark overlay
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 70))
    img_rgba = img.convert("RGBA")
    img_rgba = Image.alpha_composite(img_rgba, overlay)

    draw = ImageDraw.Draw(img_rgba)
    cx, cy = width // 2, height // 2
    r = min(width, height) // 9      # circle radius

    # White circle
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        fill=(255, 255, 255, 220),
    )

    # Red play triangle (slightly right of centre so it looks optically centred)
    t = r * 0.42
    offset_x = r * 0.12   # nudge right
    pts = [
        (cx - t * 0.7 + offset_x, cy - t),
        (cx - t * 0.7 + offset_x, cy + t),
        (cx + t * 1.0 + offset_x, cy),
    ]
    draw.polygon(pts, fill=(230, 57, 70, 255))

    # "Click to watch" hint text below circle
    hint = "Click to watch  ▶"
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    except Exception:
        font = ImageFont.load_default()

    bbox   = draw.textbbox((0, 0), hint, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx     = cx - tw // 2
    ty     = cy + r + 12

    # Drop shadow
    draw.text((tx + 1, ty + 1), hint, font=font, fill=(0, 0, 0, 160))
    draw.text((tx, ty), hint, font=font, fill=(255, 255, 255, 220))

    output.parent.mkdir(parents=True, exist_ok=True)
    img_rgba.convert("RGB").save(str(output), "JPEG", quality=_JPEG_QUALITY)
    log.debug(f"Email thumbnail saved: {output}  ({width}×{height})")
    return output
