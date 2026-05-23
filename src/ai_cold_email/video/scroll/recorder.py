"""
Playwright scroll recorder.

Loads the lead's website, smoothly scrolls down then back up to fill the
target duration, and saves a silent MP4. Used as the background layer
of the final composited video.
"""
from __future__ import annotations

import logging
from pathlib import Path

from playwright.async_api import async_playwright

from src.utils.settings import Settings

log = logging.getLogger(__name__)


async def record_scroll(
    url: str,
    duration_seconds: float,
    output_path: Path,
    settings: Settings,
) -> Path:
    """Record a smooth-scroll capture of the URL for the target duration."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = settings.scroll_capture

    width = cfg["viewport_width"]
    height = cfg["viewport_height"]
    scroll_speed = cfg["scroll_speed_pixels_per_second"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(output_path.parent),
            record_video_size={"width": width, "height": height},
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=cfg["page_load_timeout_seconds"] * 1000)
        except Exception as e:
            log.warning(f"Slow load on {url}: {e} — continuing anyway")

        # Dismiss common cookie banners (best effort)
        for selector in [
            "button:has-text('Accept')",
            "button:has-text('Got it')",
            "button:has-text('I agree')",
            "[id*='cookie'] button",
        ]:
            try:
                await page.click(selector, timeout=1000)
                break
            except Exception:
                pass

        await page.wait_for_timeout(cfg["wait_after_load_seconds"] * 1000)

        # Get full page height
        page_height = await page.evaluate("document.body.scrollHeight")
        max_scroll = max(0, page_height - height)

        # Plan oscillating scroll: down for half duration, up for half
        half = duration_seconds / 2
        scroll_down_distance = min(max_scroll, scroll_speed * half)

        # Smooth scroll using JS rAF for buttery output
        await page.evaluate(
            """async ({duration, distance}) => {
                const start = performance.now();
                const half = duration * 1000 / 2;

                return new Promise(resolve => {
                    function step(now) {
                        const t = now - start;
                        let y;
                        if (t < half) {
                            y = (t / half) * distance;
                        } else if (t < duration * 1000) {
                            y = distance - ((t - half) / half) * distance;
                        } else {
                            window.scrollTo(0, 0);
                            resolve();
                            return;
                        }
                        window.scrollTo(0, y);
                        requestAnimationFrame(step);
                    }
                    requestAnimationFrame(step);
                });
            }""",
            {"duration": duration_seconds, "distance": scroll_down_distance},
        )

        await context.close()  # finalizes the video file
        await browser.close()

    # Playwright writes a webm; rename/convert to the target path
    # The video is in output_path.parent/<random>.webm
    webm_files = list(output_path.parent.glob("*.webm"))
    if not webm_files:
        raise RuntimeError(f"Playwright did not produce a video for {url}")
    latest = max(webm_files, key=lambda p: p.stat().st_mtime)

    # Convert webm → mp4 via ffmpeg (faster than re-encoding in Playwright)
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(latest), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-an", str(output_path)],
        check=True, capture_output=True,
    )
    latest.unlink()

    log.info(f"Scroll recorded: {output_path} ({duration_seconds}s)")
    return output_path
