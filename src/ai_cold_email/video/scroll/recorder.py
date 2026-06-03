"""
Playwright scroll recorder — fully dynamic, works on any website.

Before scrolling, the system measures the actual page height and computes:
  - target_down  : how many px to scroll (never more than fits the time budget)
  - tick_delta   : per-tick scroll size that keeps speed human-natural
  - phase ratios : down / hover / up, adjusted for short vs tall pages

Scroll pattern:
  Phase 1 (0–40%)  Fast burst DOWN — stops exactly at target, never overshoots
  Phase 2 (40–58%) Cursor hovers + small circular move ("pointing at content")
  Phase 3 (58–end) Fast burst UP — position-tracked, guaranteed to land on y=0

Uses page.mouse.wheel() (real wheel events visible in recording) not
window.scrollTo() (programmatic, invisible).
"""
from __future__ import annotations

import logging
import math
import random
import time as _time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import async_playwright

from src.utils.settings import Settings

log = logging.getLogger(__name__)


@dataclass
class ScrollResult:
    """Return value from record_scroll — carries the video path plus page metadata."""
    path:           Path
    page_title:     str        = ""
    page_height:    int        = 0
    scroll_px:      float      = 0.0   # how far down we actually scrolled
    thumbnail_path: Path | None = None  # JPEG screenshot of website homepage (for video cover art)

    # Make it usable wherever a Path is expected
    def __fspath__(self) -> str:
        return str(self.path)

    def __str__(self) -> str:
        return str(self.path)


async def record_scroll(
    url: str,
    duration_seconds: float,
    output_path: Path,
    settings: Settings,
    viewport_height: int | None = None,
) -> ScrollResult:
    """
    Record a human-like scroll of `url` for `duration_seconds`.
    Returns a ScrollResult (page_title and page_height populated from the live page).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cfg    = settings.scroll_capture
    width  = cfg["viewport_width"]
    height = viewport_height if viewport_height is not None else cfg["viewport_height"]

    page_title  = ""
    page_height = 0
    scroll_px   = 0.0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(output_path.parent),
            record_video_size={"width": width, "height": height},
        )
        page = await context.new_page()

        # ── Load ──────────────────────────────────────────────────────────────
        try:
            await page.goto(url, wait_until="load",
                            timeout=cfg["page_load_timeout_seconds"] * 1000)
        except Exception as e:
            log.warning(f"Slow load ({url}): {e} — continuing")

        # Dismiss cookie banners
        for sel in [
            "button:has-text('Accept all')", "button:has-text('Accept')",
            "button:has-text('Got it')",     "button:has-text('I agree')",
            "[id*='cookie'] button",
        ]:
            try:
                await page.click(sel, timeout=600)
                break
            except Exception:
                pass

        # Measure page
        page_title  = await page.evaluate("document.title") or url.split("/")[2]
        page_height = await page.evaluate("document.body.scrollHeight")

        # ── Thumbnail — screenshot of homepage before any scrolling ───────────
        # This becomes the video cover art and the visible first frame.
        # Captured at the exact viewport size used for the video content area.
        # Named per-lead (derived from output_path) so concurrent leads don't
        # overwrite each other's thumbnails.
        thumbnail_path = output_path.with_name(
            output_path.stem.replace("_scroll", "_thumb") + ".jpg"
        )
        await page.screenshot(
            path=str(thumbnail_path),
            type="jpeg",
            quality=92,
            clip={"x": 0, "y": 0, "width": width, "height": height},
        )
        log.info(f"Thumbnail captured → {thumbnail_path.name}")

        # ── Human scroll (adaptive) ───────────────────────────────────────────
        scroll_px = await _human_scroll(
            page, duration_seconds, width, height, page_height
        )

        await context.close()
        await browser.close()

    # webm → mp4
    webm_files = list(output_path.parent.glob("*.webm"))
    if not webm_files:
        raise RuntimeError(f"Playwright produced no video for {url}")
    latest = max(webm_files, key=lambda f: f.stat().st_mtime)

    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(latest),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(output_path)],
        check=True, capture_output=True,
    )
    latest.unlink()

    log.info(
        f"Scroll recorded → {output_path.name}  "
        f"[{width}×{height}  page={page_height}px  scrolled={scroll_px:.0f}px  {duration_seconds:.0f}s]"
    )
    return ScrollResult(
        path=output_path,
        page_title=page_title,
        page_height=page_height,
        scroll_px=scroll_px,
        thumbnail_path=thumbnail_path if thumbnail_path.exists() else None,
    )


# ── Core adaptive scroll ──────────────────────────────────────────────────────

async def _human_scroll(
    page, dur: float, W: int, H: int, page_h: int
) -> float:
    """
    Execute a human-like scroll sequence.
    Returns the actual peak scroll position reached (px).
    """
    scrollable = max(0, page_h - H)

    # ── 1-second still hold at top ────────────────────────────────────────
    # Ensures the first frame of the video shows the website homepage cleanly
    # (not a white flash or partial load). This frame IS the video thumbnail
    # shown in email clients, QuickTime, messaging apps, etc.
    await page.mouse.move(W // 2, H // 2)
    await page.wait_for_timeout(1000)

    # ── Compute scroll target ──────────────────────────────────────────────
    if scrollable == 0:
        # Page fits entirely in the viewport — no scrolling needed
        log.info("Page fits in viewport — no scroll needed")
        await _idle_cursor(page, dur, W, H)
        return 0.0

    # How many px we can naturally scroll in the down phase
    # (40% of duration, at ~120 px/s average human trackpad speed)
    down_secs      = dur * 0.40
    natural_budget = 120 * down_secs          # px reachable at comfortable pace

    # Show at most 3.5 "screens" of content — enough to look thorough
    screen_limit   = H * 3.5

    # Never go beyond 75% of scrollable distance — keeps recovery comfortable
    page_limit     = scrollable * 0.75

    target_down = min(natural_budget, screen_limit, page_limit)
    target_down = max(target_down, min(scrollable, 400))  # at least 400px

    log.info(
        f"Scroll plan: page={page_h}px  scrollable={scrollable}px  "
        f"target={target_down:.0f}px  duration={dur:.0f}s"
    )

    # ── Timing ────────────────────────────────────────────────────────────
    t0    = _time.monotonic()
    t_p1  = t0 + dur * 0.40   # end of fast-down
    t_p2  = t0 + dur * 0.57   # end of hover
    t_end = t0 + dur

    cx = W // 2
    cy = H // 2

    await page.mouse.move(cx, int(cy * 0.8))
    await page.wait_for_timeout(200)

    # ── Phase 1: scroll DOWN to target (never overshoots) ─────────────────
    peak = 0.0
    while _time.monotonic() < t_p1:
        pos = await page.evaluate("window.scrollY")
        peak = max(peak, pos)

        if pos >= target_down:
            # At target — drift cursor until phase 1 ends
            await _cursor_drift(page, cx, cy, W, H)
            continue

        remaining = target_down - pos
        delta = _adaptive_delta(remaining, direction=1)
        await page.mouse.wheel(0, delta)
        await page.wait_for_timeout(random.randint(14, 55))

        if random.random() < 0.18:
            await page.wait_for_timeout(random.randint(80, 280))
        if random.random() < 0.28:
            await _cursor_drift(page, cx, cy, W, H)

    # ── Phase 2: hover + circular point ───────────────────────────────────
    px = cx + random.randint(-180, 180)
    py = random.randint(int(H * 0.18), int(H * 0.55))

    await page.mouse.move(px, py, steps=random.randint(10, 18))
    await page.wait_for_timeout(random.randint(320, 650))

    r = random.randint(9, 18)
    for deg in range(0, 360, 15):
        await page.mouse.move(
            px + int(r * math.cos(math.radians(deg))),
            py + int(r * math.sin(math.radians(deg))),
        )
        await page.wait_for_timeout(random.randint(12, 25))
    await page.mouse.move(px, py)
    await page.wait_for_timeout(random.randint(300, 550))

    while _time.monotonic() < t_p2:
        await page.wait_for_timeout(random.randint(100, 250))

    # ── Phase 3: scroll UP — position-tracked, guaranteed to reach y=0 ───
    while _time.monotonic() < t_end - 0.7:
        pos = await page.evaluate("window.scrollY")
        if pos <= 0:
            break

        delta = _adaptive_delta(pos, direction=-1)
        await page.mouse.wheel(0, delta)
        await page.wait_for_timeout(random.randint(14, 55))

        if random.random() < 0.14:
            await page.wait_for_timeout(random.randint(60, 220))
        if random.random() < 0.20:
            await _cursor_drift(page, cx, cy, W, H)

    # Hard snap to top + hold remaining time
    await page.evaluate("window.scrollTo(0, 0)")
    hold_ms = max(0, int((t_end - _time.monotonic()) * 1000))
    if hold_ms > 0:
        await page.wait_for_timeout(hold_ms)

    return peak


# ── Helpers ───────────────────────────────────────────────────────────────────

def _adaptive_delta(remaining: float, direction: int) -> int:
    """
    Returns a wheel delta sized appropriately for the remaining scroll distance.
    Larger when far away (feels fast), smaller when close (decelerates naturally).
    Never exceeds |remaining|.
    """
    if remaining > 600:
        d = random.randint(60, 140)
    elif remaining > 200:
        d = random.randint(30, 80)
    elif remaining > 50:
        d = random.randint(12, 45)
    else:
        d = random.randint(6, max(6, int(remaining)))
    return int(min(d, remaining)) * direction


async def _cursor_drift(page, cx: int, cy: int, W: int, H: int):
    """Move cursor naturally — like eyes following content."""
    await page.mouse.move(
        cx + random.randint(-230, 230),
        random.randint(60, H - 60),
        steps=random.randint(4, 12),
    )
    await page.wait_for_timeout(random.randint(30, 130))


async def _idle_cursor(page, dur: float, W: int, H: int):
    """Move cursor around naturally for pages that don't need scrolling."""
    t_end = _time.monotonic() + dur
    cx, cy = W // 2, H // 2
    while _time.monotonic() < t_end:
        await page.mouse.move(
            cx + random.randint(-250, 250),
            random.randint(80, H - 80),
            steps=random.randint(8, 18),
        )
        await page.wait_for_timeout(random.randint(300, 800))
