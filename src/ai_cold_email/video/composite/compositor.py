"""
FFmpeg compositor.

Layers (bottom → top):
  0  Scroll video  — scrolling website recording
  1  Browser frame — Chrome dark-mode UI (optional; transparent content area)
  2  Corner image  — circular face photo, bottom-left
  3  CTA button    — red pill "Book A Call", top-right of CONTENT area
  4  Audio         — TTS voiceover

Output: 1280x720 MP4 (H.264 + AAC), exact duration of audio track.

CTA pill is pre-rendered as a PNG with PIL (no libfreetype / drawtext needed).
When browser_frame is used the scroll video is placed at content_y so it
appears inside the Chrome window, not behind the address bar.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

from src.utils.settings import Settings

log = logging.getLogger(__name__)


def _make_cta_png(
    text: str,
    bg_color: str,
    width: int,
    height: int,
    out_path: Path,
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    bg = tuple(int(bg_color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)) + (255,)
    img  = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, width - 1, height - 1],
                           radius=height // 2, fill=bg)

    font_size = int(height * 0.40)
    font = None
    for fpath in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        try:
            from PIL import ImageFont as _IF
            font = _IF.truetype(fpath, font_size)
            break
        except (OSError, IOError):
            continue
    if font is None:
        from PIL import ImageFont as _IF
        font = _IF.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        ((width - tw) // 2 - bbox[0], (height - th) // 2 - bbox[1]),
        text, fill=(255, 255, 255, 255), font=font,
    )
    img.save(str(out_path), "PNG")


async def composite_video(
    scroll_video: Path,
    audio: Path,
    corner_image: Path,
    output_path: Path,
    settings: Settings,
    browser_frame: Optional[Path] = None,
    content_y: int = 0,
    thumbnail_path: Optional[Path] = None,
) -> Path:
    """
    Composite all layers into final MP4 using FFmpeg.

    browser_frame  — optional Path to a Chrome-frame RGBA PNG (transparent
                     in the content area). When provided the scroll video is
                     placed starting at content_y.
    content_y      — y offset where the webpage content starts (= Chrome
                     header height when browser_frame is used, else 0).
    thumbnail_path — optional JPEG screenshot of the website homepage.
                     When provided, embedded as MP4 cover art so every
                     player / email client / OS file browser shows the
                     website as the video thumbnail instead of a white frame.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cfg           = settings.video
    composite_cfg = settings.composite
    w, h          = cfg["resolution"]["width"], cfg["resolution"]["height"]

    # ── Corner image (bottom-left circle) ────────────────────────────────────
    img_size   = composite_cfg["corner_image"]["size_pixels"]
    img_margin = composite_cfg["corner_image"]["margin_pixels"]
    border_w   = composite_cfg["corner_image"]["border_width"]
    img_x      = img_margin
    img_y      = h - img_size - img_margin

    # ── CTA pill (top-right, but inside the content area) ────────────────────
    cta_w      = composite_cfg["cta_overlay"]["width_pixels"]
    cta_h      = composite_cfg["cta_overlay"]["height_pixels"]
    cta_margin = composite_cfg["cta_overlay"]["margin_pixels"]
    cta_text   = composite_cfg["cta_overlay"]["text"]
    cta_bg     = composite_cfg["cta_overlay"]["background_color"]
    cta_x      = w - cta_w - cta_margin
    # Place CTA below the browser chrome so it's inside the content area
    cta_y      = content_y + cta_margin

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        cta_png = Path(tmp.name)
    _make_cta_png(cta_text, cta_bg, cta_w, cta_h, cta_png)

    try:
        return await _run_composite(
            scroll_video=scroll_video,
            audio=audio,
            corner_image=corner_image,
            output_path=output_path,
            settings=settings,
            browser_frame=browser_frame,
            content_y=content_y,
            thumbnail_path=thumbnail_path,
            cta_png=cta_png,
            w=w, h=h,
            content_h=h - content_y,
            img_size=img_size, img_margin=img_margin, border_w=border_w,
            img_x=img_x, img_y=img_y,
            cta_w=cta_w, cta_h=cta_h, cta_x=cta_x, cta_y=cta_y,
            cfg=cfg,
        )
    finally:
        cta_png.unlink(missing_ok=True)   # always clean up, even if FFmpeg crashes


async def _run_composite(
    scroll_video, audio, corner_image, output_path, settings,
    browser_frame, content_y, thumbnail_path, cta_png,
    w, h, content_h, img_size, img_margin, border_w,
    img_x, img_y, cta_w, cta_h, cta_x, cta_y, cfg,
) -> Path:
    # ── Build FFmpeg inputs and filter graph ─────────────────────────────────
    if browser_frame:
        # Inputs:  0=scroll  1=browser_frame  2=corner  3=cta  4=audio
        filter_complex = (
            # 1. Scale scroll to content area, then PAD to full frame (black at top)
            #    pad=w:h:x_offset:y_offset — adds content_y black px at top
            f"[0:v]scale={w}:{content_h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{content_h},"
            f"pad={w}:{h}:0:{content_y}:color=0x1c1c1e[bg_scroll];"
            # 2. Overlay browser frame (top content_y rows are opaque chrome UI,
            #    rest is transparent — the padded scroll shows through)
            f"[bg_scroll][1:v]overlay=0:0[bg_framed];"
            # 3. Circular-mask corner image
            f"[2:v]scale={img_size}:{img_size},format=rgba,"
            f"geq="
            f"r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
            f"a='if(lte(hypot(X-{img_size//2},Y-{img_size//2}),"
            f"{img_size//2 - border_w}),255,"
            f"if(lte(hypot(X-{img_size//2},Y-{img_size//2}),{img_size//2}),255,0))'"
            f"[corner];"
            # 4. Overlay corner image
            f"[bg_framed][corner]overlay={img_x}:{img_y}[v1];"
            # 5. Scale & overlay CTA pill
            f"[3:v]scale={cta_w}:{cta_h},format=rgba[cta];"
            f"[v1][cta]overlay={cta_x}:{cta_y}[vout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(scroll_video),   # [0]
            "-i", str(browser_frame),                          # [1]
            "-i", str(corner_image),                           # [2]
            "-i", str(cta_png),                                # [3]
            "-i", str(audio),                                  # [4]
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "4:a",
        ]
    else:
        # No browser frame — original behaviour
        filter_complex = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}[bg];"
            f"[1:v]scale={img_size}:{img_size},format=rgba,"
            f"geq="
            f"r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
            f"a='if(lte(hypot(X-{img_size//2},Y-{img_size//2}),"
            f"{img_size//2 - border_w}),255,"
            f"if(lte(hypot(X-{img_size//2},Y-{img_size//2}),{img_size//2}),255,0))'"
            f"[corner];"
            f"[bg][corner]overlay={img_x}:{img_y}[v1];"
            f"[2:v]scale={cta_w}:{cta_h},format=rgba[cta];"
            f"[v1][cta]overlay={cta_x}:{cta_y}[vout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(scroll_video),   # [0]
            "-i", str(corner_image),                          # [1]
            "-i", str(cta_png),                               # [2]
            "-i", str(audio),                                 # [3]
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "3:a",
        ]

    cmd += [
        "-c:v", cfg["codec"],
        "-c:a", cfg["audio_codec"],
        "-pix_fmt", "yuv420p",
        "-r", str(cfg["fps"]),
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]

    log.info(f"FFmpeg compositing → {output_path}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        log.error(f"FFmpeg failed:\n{stderr.decode()}")
        raise RuntimeError(f"FFmpeg failed with code {proc.returncode}")

    # ── Embed website screenshot as MP4 cover art ────────────────────────────
    # This makes every player, OS file browser, and email client show the
    # prospect's website homepage as the video thumbnail — not a white frame.
    # Works by attaching a JPEG as a second video stream with the
    # 'attached_pic' disposition (standard MP4 cover art mechanism).
    if thumbnail_path and thumbnail_path.exists():
        thumb_out = output_path.with_suffix(".thumb.mp4")
        thumb_cmd = [
            "ffmpeg", "-y",
            "-i", str(output_path),
            "-i", str(thumbnail_path),
            "-map", "0",
            "-map", "1",
            "-c", "copy",
            "-c:v:1", "mjpeg",
            "-disposition:v:1", "attached_pic",
            "-movflags", "+faststart",
            str(thumb_out),
        ]
        thumb_proc = await asyncio.create_subprocess_exec(
            *thumb_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, thumb_err = await thumb_proc.communicate()
        if thumb_proc.returncode == 0:
            thumb_out.replace(output_path)   # swap in place
            log.info(f"Cover art embedded → {thumbnail_path.name}")
        else:
            log.warning(f"Cover art embedding skipped: {thumb_err.decode()[:120]}")
            if thumb_out.exists():
                thumb_out.unlink()

    log.info(f"Composited: {output_path} ({output_path.stat().st_size / 1024:.0f} KB)")
    return output_path
