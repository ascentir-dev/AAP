"""
TTS adapter.

Provider priority (set in settings.yaml → tts.primary_provider):

  "edge_tts"   — Microsoft Edge Neural TTS. FREE. No API key. Same Azure Neural
                  voices Microsoft charges $16/M chars for on Azure directly.
                  Best voices for outreach: en-US-ChristopherNeural (confident,
                  warm), en-US-AndrewNeural (natural), en-US-GuyNeural (clear).
                  This is the default.

  "elevenlabs" — ElevenLabs. Paid. Free tier = 10K chars/month.
                  Use for premium-tier accounts if you want hyper-realistic voice.

  "openai"     — OpenAI TTS-1. $15/M chars. Kept for backward compat only.
                  No need to use this — edge_tts sounds just as good for free.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

# Cost constants (edge_tts = $0 — no cost to track)
_OPENAI_COST_PER_CHAR = 15.0 / 1_000_000
_ELEVENLABS_COST_PER_CHAR = 0.18 / 1_000


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def synthesize(
    text: str,
    output_path: Path,
    settings: Any,
    cost_tracker: Any,
    voice_override: str | None = None,
) -> Path:
    """
    Convert text to speech. Writes MP3 to output_path. Returns output_path.

    Provider selection:
    - voice_override="elevenlabs" → ElevenLabs
    - voice_override="openai"     → OpenAI TTS (legacy)
    - voice_override=<name>       → edge_tts with that voice name
    - Otherwise: settings.tts.primary_provider (default: "edge_tts")
    """
    provider = _select_provider(settings, voice_override)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if provider == "edge_tts":
        voice = _get_edge_voice(settings, voice_override)
        await _synthesize_edge(text, output_path, voice)
        # Free — log $0 so cost tracking doesn't break
        cost_tracker.log(None, "edge_tts", "tts", 0.0)

    elif provider == "elevenlabs":
        from elevenlabs.client import ElevenLabs
        await _synthesize_elevenlabs(text, output_path, settings)
        cost = len(text) * _ELEVENLABS_COST_PER_CHAR
        cost_tracker.log(None, "elevenlabs", "tts", cost)

    else:  # openai (legacy)
        from openai import OpenAI
        await _synthesize_openai(text, output_path, settings, voice_override)
        cost = len(text) * _OPENAI_COST_PER_CHAR
        cost_tracker.log(None, "openai", "tts", cost)

    return output_path


# ─── Provider selection ────────────────────────────────────────────────────

def _select_provider(settings: Any, voice_override: str | None) -> str:
    if voice_override == "elevenlabs":
        return "elevenlabs"
    if voice_override == "openai":
        return "openai"
    tts_cfg = settings.tts if isinstance(settings.tts, dict) else {}
    return tts_cfg.get("primary_provider", "edge_tts")


def _get_edge_voice(settings: Any, voice_override: str | None) -> str:
    """Return the edge-tts voice name to use."""
    # If override looks like an edge voice name (contains 'Neural'), use it
    if voice_override and "Neural" in voice_override:
        return voice_override
    tts_cfg = settings.tts if isinstance(settings.tts, dict) else {}
    return tts_cfg.get("primary_voice", "en-US-ChristopherNeural")


# ─── Edge TTS (free) ───────────────────────────────────────────────────────

async def _synthesize_edge(text: str, output_path: Path, voice: str) -> None:
    """
    Use Microsoft Edge Neural TTS — completely free, no API key required.
    Produces the same Azure Neural voice quality as the paid Azure TTS API.
    """
    import edge_tts

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate="+0%",   # Normal speaking speed. "+10%" speeds up slightly.
        volume="+0%",
    )
    await communicate.save(str(output_path))
    log.info(f"Edge TTS: wrote {output_path.stat().st_size:,} bytes → {output_path.name}")


# ─── ElevenLabs (paid) ────────────────────────────────────────────────────

async def _synthesize_elevenlabs(text: str, output_path: Path, settings: Any) -> None:
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    audio = client.text_to_speech.convert(
        voice_id=settings.elevenlabs_voice_id,
        model_id=settings.elevenlabs_model,
        text=text,
    )
    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)


# ─── OpenAI TTS (legacy / optional) ──────────────────────────────────────

async def _synthesize_openai(
    text: str, output_path: Path, settings: Any, voice_override: str | None
) -> None:
    from openai import OpenAI

    tts_cfg = settings.tts if isinstance(settings.tts, dict) else {}
    voice = (
        voice_override
        if voice_override and voice_override not in ("elevenlabs", "openai")
        else tts_cfg.get("primary_voice", "echo")
    )
    model = getattr(settings, "openai_tts_model", "tts-1")
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.audio.speech.create(model=model, voice=voice, input=text)
    response.write_to_file(str(output_path))
