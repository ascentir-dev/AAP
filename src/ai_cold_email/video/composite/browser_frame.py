"""
Generates a macOS Chrome dark-mode browser frame PNG.

The content area (below the Chrome header) is fully transparent so the
scroll recording shows through underneath it in FFmpeg.

Layout (96px total header):
  y 0–40   Tab bar  — traffic lights + active tab + favicon + title
  y 40–72  Address bar — back/fwd, lock icon, URL (blue), extensions
  y 72–96  Bookmarks bar — typical bookmarks strip
  y 96+    ← transparent (your webpage goes here)
"""
from __future__ import annotations

from pathlib import Path


CHROME_HEADER_HEIGHT = 96   # px consumed by Chrome UI above the content area
_TAB_BAR_H   = 40
_ADDR_BAR_H  = 32
_BOOKMARK_H  = 24

# Chrome dark-mode palette
_BG        = (32,  33,  36,  255)   # #202124
_TAB_ACT   = (53,  54,  58,  255)   # #35363A active tab
_ADDR_BG   = (48,  49,  52,  255)   # #303134 address pill bg
_TXT       = (232, 234, 237, 255)   # #E8EAED primary text
_TXT_URL   = (138, 180, 248, 255)   # #8AB4F8 URL blue
_TXT_DIM   = (154, 160, 166, 255)   # #9AA0A6 dim text
_SEP       = (60,  61,  66,  255)   # separator line


def make_browser_frame(
    url: str,
    width: int,
    height: int,
    out_path: Path,
    page_title: str = "Ascentir",
) -> int:
    """
    Render a Chrome dark-mode frame as RGBA PNG.

    The region y >= CHROME_HEADER_HEIGHT is fully transparent — FFmpeg
    overlays this on top of the scroll video so the webpage shows through.

    Returns CHROME_HEADER_HEIGHT so callers know where content starts.
    """
    from PIL import Image, ImageDraw, ImageFont

    img  = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def _font(size: int):
        for path in [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSDisplay.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]:
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                pass
        return ImageFont.load_default()

    f11 = _font(11)
    f12 = _font(12)
    f13 = _font(13)
    f16 = _font(16)

    # ── Tab bar (y 0–40) ─────────────────────────────────────────────────────
    draw.rectangle([0, 0, width, _TAB_BAR_H], fill=_BG)

    # Traffic lights
    dot_cy = _TAB_BAR_H // 2
    for cx, col in [
        (13, (255,  95,  87, 255)),   # red
        (29, (255, 189,  46, 255)),   # yellow
        (45, ( 40, 205,  65, 255)),   # green
    ]:
        draw.ellipse([cx-6, dot_cy-6, cx+6, dot_cy+6], fill=col)

    # Active tab pill
    tx, ty, tw, th = 66, 5, 210, _TAB_BAR_H - 5
    draw.rounded_rectangle([tx, ty, tx+tw, ty+th], radius=6, fill=_TAB_ACT)

    # Favicon circle inside tab
    fav_r = 7
    fav_cx = tx + 14
    fav_cy = ty + th // 2
    draw.ellipse([fav_cx-fav_r, fav_cy-fav_r, fav_cx+fav_r, fav_cy+fav_r],
                 fill=(15, 157, 88, 255))   # green favicon

    # Tab title
    draw.text((fav_cx + fav_r + 6, fav_cy), page_title[:22],
              fill=_TXT, font=f12, anchor="lm")

    # ×  close button inside tab
    close_x = tx + tw - 14
    draw.text((close_x, fav_cy), "×", fill=_TXT_DIM, font=f13, anchor="mm")

    # New-tab + button
    draw.text((tx + tw + 18, dot_cy), "+", fill=_TXT_DIM, font=f16, anchor="mm")

    # ── Address bar (y 40–72) ─────────────────────────────────────────────────
    ay = _TAB_BAR_H
    draw.rectangle([0, ay, width, ay + _ADDR_BAR_H], fill=_BG)

    nav_cy = ay + _ADDR_BAR_H // 2
    # Back (dim = no history), Forward, Refresh
    draw.text((14, nav_cy), "‹",  fill=_TXT_DIM,  font=f16, anchor="mm")
    draw.text((32, nav_cy), "›",  fill=_TXT,      font=f16, anchor="mm")
    draw.text((50, nav_cy), "↻",  fill=_TXT,      font=f16, anchor="mm")

    # Address pill
    bx, by = 68, ay + 4
    bw, bh = width - bx - 68, _ADDR_BAR_H - 8
    draw.rounded_rectangle([bx, by, bx+bw, by+bh], radius=bh//2, fill=_ADDR_BG)

    # Lock + URL
    lock_x = bx + 12
    draw.text((lock_x, by + bh//2), "🔒", fill=_TXT_DIM, font=f11, anchor="lm")
    url_short = url.replace("https://", "").replace("http://", "").rstrip("/")
    draw.text((lock_x + 22, by + bh//2), url_short,
              fill=_TXT_URL, font=f12, anchor="lm")

    # Right of address bar: Extensions / menu
    rx = bx + bw + 8
    draw.text((rx + 8,  nav_cy), "⊞", fill=_TXT_DIM, font=f13, anchor="mm")
    draw.text((rx + 28, nav_cy), "⋮", fill=_TXT_DIM, font=f16, anchor="mm")

    # ── Bookmarks bar (y 72–96) ───────────────────────────────────────────────
    by2 = ay + _ADDR_BAR_H
    draw.rectangle([0, by2, width, CHROME_HEADER_HEIGHT], fill=_BG)

    bm_items = ["Gmail", "Drive", "LinkedIn", "Notion", "Slack", "HubSpot"]
    bm_x = 10
    bm_cy = by2 + _BOOKMARK_H // 2
    for item in bm_items:
        draw.text((bm_x, bm_cy), item, fill=_TXT_DIM, font=f11, anchor="lm")
        try:
            bbox = draw.textbbox((0, 0), item, font=f11)
            bm_x += (bbox[2] - bbox[0]) + 22
        except Exception:
            bm_x += len(item) * 7 + 22
        if bm_x > width - 120:
            break

    # Separator at bottom of header
    draw.line([(0, CHROME_HEADER_HEIGHT - 1), (width, CHROME_HEADER_HEIGHT - 1)],
              fill=_SEP, width=1)

    # ── Content area (y 96+) — fully transparent ──────────────────────────────
    # Already transparent by default.

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), "PNG")
    return CHROME_HEADER_HEIGHT
