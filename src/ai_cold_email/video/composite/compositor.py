"""
FFmpeg compositor.

Layers:
  1. Background: scrolling website video (sized to fit full frame)
  2. Bottom-left: circular masked image with white border + drop shadow
  3. Top-right: "Book A Call" CTA pill button
  4. Audio: TTS voiceover

Output: 1280x720 MP4 (H.264 + AAC), exact duration of audio track.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from src.utils.settings import Settings

log = logging.getLogger(__name__)


async def composite_video(
    scroll_video: Path,
    audio: Path,
    corner_image: Path,
    output_path: Path,
    settings: Settings,
) -> Path:
    """Composite all layers into final MP4 using FFmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cfg = settings.video
    composite_cfg = settings.composite
    w, h = cfg["resolution"]["width"], cfg["resolution"]["height"]

    # --- Corner image config (bottom-left circle) ---
    img_size = composite_cfg["corner_image"]["size_pixels"]
    img_margin = composite_cfg["corner_image"]["margin_pixels"]
    border_w = composite_cfg["corner_image"]["border_width"]
    img_x = img_margin
    img_y = h - img_size - img_margin

    # --- CTA config (top-right pill) ---
    cta_w = composite_cfg["cta_overlay"]["width_pixels"]
    cta_h = composite_cfg["cta_overlay"]["height_pixels"]
    cta_margin = composite_cfg["cta_overlay"]["margin_pixels"]
    cta_text = composite_cfg["cta_overlay"]["text"]
    cta_bg = composite_cfg["cta_overlay"]["background_color"]
    cta_x = w - cta_w - cta_margin
    cta_y = cta_margin

    # FFmpeg filtergraph:
    # [0:v] scroll video, scale to full frame
    # [1:v] corner image -> resize -> circular alpha mask
    # generate CTA pill via drawbox + drawtext
    # overlay everything, then mux audio

    filter_complex = (
        # 1. Scale scroll video to canvas
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}[bg];"
        # 2. Prepare corner image (resize + circular mask + border)
        f"[1:v]scale={img_size}:{img_size},"
        f"format=rgba,"
        f"geq="
        f"r='r(X,Y)':"
        f"g='g(X,Y)':"
        f"b='b(X,Y)':"
        f"a='if(lte(hypot(X-{img_size//2},Y-{img_size//2}),{img_size//2 - border_w}),255,"
        f"if(lte(hypot(X-{img_size//2},Y-{img_size//2}),{img_size//2}),255,0))'"
        f"[corner_masked];"
        # 3. Overlay corner image onto background
        f"[bg][corner_masked]overlay={img_x}:{img_y}[v1];"
        # 4. Draw CTA pill background + text
        f"[v1]drawbox=x={cta_x}:y={cta_y}:w={cta_w}:h={cta_h}:"
        f"color={cta_bg}@1.0:t=fill,"
        f"drawtext=text='{cta_text}':"
        f"fontcolor=white:fontsize=22:fontfile=/System/Library/Fonts/Helvetica.ttc:"
        f"x={cta_x}+({cta_w}-text_w)/2:"
        f"y={cta_y}+({cta_h}-text_h)/2"
        f"[vout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(scroll_video),  # loop scroll if shorter than audio
        "-i", str(corner_image),
        "-i", str(audio),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "2:a",
        "-c:v", cfg["codec"],
        "-c:a", cfg["audio_codec"],
        "-pix_fmt", "yuv420p",
        "-r", str(cfg["fps"]),
        "-shortest",  # match audio length
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

    log.info(f"Composited: {output_path} ({output_path.stat().st_size / 1024:.0f} KB)")
    return output_path


# NOTE TO CLAUDE CODE:
# The geq filter for circular masking is correct but slow on long videos.
# If you need speed, switch to a precomputed circular alpha PNG mask:
#   1. Generate a circle PNG once (PIL: white circle on transparent bg)
#   2. Use overlay with `format=auto,format=rgba` and the mask as a third input
# This is a common future optimization. Profile first; only switch if it's a bottleneck.
#
# The font path /System/Library/Fonts/Helvetica.ttc is macOS. On Linux, use:
#   /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
# Make this configurable via settings.yaml when you generalize.
