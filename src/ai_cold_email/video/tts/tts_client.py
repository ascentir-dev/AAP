"""
TTS adapter — intelligent cost tiering.

Provider selection (in priority order):
  1. If lead's intent_confidence < tts.elevenlabs_intent_threshold  → Edge TTS (FREE)
  2. If intent_confidence meets threshold AND ElevenLabs is configured → ElevenLabs
  3. Fallback → Edge TTS

Cost breakdown (per ~900-char script):
  ElevenLabs eleven_v3:  ~$0.162/lead  (cloned Frank voice — use for warm leads only)
  Edge TTS:              $0.000/lead   (Microsoft Neural TTS — free, no API key)

Threshold guide (set tts.elevenlabs_intent_threshold in settings.yaml):
  10 → always Edge TTS (fully free)
  8  → ElevenLabs only for highest-intent leads (~0% of typical lead lists)
  7  → ElevenLabs for warm leads (~35%)
  0  → always ElevenLabs (old behaviour, expensive)

Edge voice recommendation: "en-US-AndrewMultilingualNeural"
  Calm, confident, professional male — best free voice for B2B cold outreach.
  Other good options: en-US-GuyNeural, en-US-DavisNeural, en-US-JasonNeural
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

# Cost constants
_OPENAI_COST_PER_CHAR     = 15.0  / 1_000_000
_ELEVENLABS_COST_PER_CHAR =  0.18 / 1_000        # ~$0.18/1K chars


def _strip_elevenlabs_tags(text: str) -> str:
    """Remove ElevenLabs-specific audio tags from script text.

    ElevenLabs supports inline tags like [excited], [warm], [chuckles] and
    <break time="0.3s"> that are processed by eleven_v3.  Edge TTS doesn't
    understand [word] style tags — it would read them aloud as text.

    Edge TTS DOES support SSML <break> natively, so we keep those.
    We only strip the square-bracket emotion/delivery tags.
    """
    # Remove [tag] style ElevenLabs delivery tags
    text = re.sub(r'\[(?:excited|warm|chuckles?|pause|thoughtful|genuine|sad|angry|whisper)\]',
                  '', text, flags=re.IGNORECASE)
    # Collapse extra whitespace left by tag removal
    text = re.sub(r'  +', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def synthesize(
    text: str,
    output_path: Path,
    settings: Any,
    cost_tracker: Any,
    voice_override: str | None = None,
    lead_id: str | None = None,
    intent_score: float = 0.0,
) -> Path:
    """Convert text to speech and write MP3 to output_path.

    Tiered provider selection:
    - intent_score < tts.elevenlabs_intent_threshold  → Edge TTS (free)
    - intent_score >= threshold AND ElevenLabs key set  → ElevenLabs (cloned voice)
    - voice_override='edge_tts'                         → force Edge TTS
    - voice_override='openai'                           → legacy OpenAI TTS
    """
    provider = _select_provider(settings, voice_override, intent_score)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if provider == "elevenlabs":
        await _synthesize_elevenlabs(text, output_path, settings)
        cost = len(text) * _ELEVENLABS_COST_PER_CHAR
        cost_tracker.log(lead_id, "elevenlabs", "tts", cost)
        log.info("[%s] TTS: ElevenLabs (intent=%.1f ≥ threshold)", lead_id or "?", intent_score)

    elif provider == "openai":
        await _synthesize_openai(text, output_path, settings, voice_override)
        cost = len(text) * _OPENAI_COST_PER_CHAR
        cost_tracker.log(lead_id, "openai", "tts", cost)

    else:  # edge_tts — free
        clean_text = _strip_elevenlabs_tags(text)
        voice = _get_edge_voice(settings, voice_override)
        await _synthesize_edge(clean_text, output_path, voice)
        cost_tracker.log(lead_id, "edge_tts", "tts", 0.0)
        log.info("[%s] TTS: Edge (free, intent=%.1f, voice=%s)", lead_id or "?", intent_score, voice)

    return output_path


# ─── Provider selection ────────────────────────────────────────────────────────

def _select_provider(settings: Any, voice_override: str | None, intent_score: float) -> str:
    """Pick TTS provider based on intent score and config threshold.

    Logic:
      1. explicit voice_override  → honour it
      2. intent < threshold       → edge_tts (free)
      3. ElevenLabs configured    → elevenlabs
      4. fallback                 → edge_tts
    """
    if voice_override == "openai":
        return "openai"
    if voice_override == "edge_tts":
        return "edge_tts"

    tts_cfg = settings.tts if isinstance(settings.tts, dict) else {}
    primary = tts_cfg.get("primary_provider", "edge_tts")

    if primary == "elevenlabs":
        # Check intent threshold — only pay for ElevenLabs on warm leads
        threshold = float(tts_cfg.get("elevenlabs_intent_threshold", 8))
        if intent_score < threshold:
            log.debug(
                "TTS tier: intent_score=%.1f < threshold=%.1f → Edge TTS (free)",
                intent_score, threshold,
            )
            return "edge_tts"
        # Verify the API key is actually set
        api_key = getattr(settings, "elevenlabs_api_key", None) or tts_cfg.get("api_key", "")
        if not api_key:
            log.warning("ElevenLabs key not configured → falling back to Edge TTS")
            return "edge_tts"
        return "elevenlabs"

    return primary  # "edge_tts" or anything else


def _get_edge_voice(settings: Any, voice_override: str | None) -> str:
    if voice_override and "Neural" in (voice_override or ""):
        return voice_override
    tts_cfg = settings.tts if isinstance(settings.tts, dict) else {}
    # Prefer fallback_voice; legacy field is primary_voice
    return (
        tts_cfg.get("fallback_voice")
        or tts_cfg.get("primary_voice")
        or "en-US-AndrewMultilingualNeural"
    )


# ─── ElevenLabs (premium — cloned voice, most human-sounding) ─────────────────

async def _synthesize_elevenlabs(text: str, output_path: Path, settings: Any) -> None:
    """Generate voice using ElevenLabs eleven_v3 (or multilingual_v2 fallback).

    Voice settings tuned for confident, enthusiastic B2B outreach delivery.
    Processes inline audio tags ([excited], [warm], <break> etc.) natively.
    """
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings

    tts_cfg = settings.tts if isinstance(settings.tts, dict) else {}
    api_key  = getattr(settings, "elevenlabs_api_key", None) or tts_cfg.get("api_key")
    voice_id = (
        getattr(settings, "elevenlabs_voice_id", None)
        or tts_cfg.get("voice_id")
        or "pNInz6obpgDQGcFmaJgB"   # Adam — warm, confident, natural male voice
    )
    model_id          = tts_cfg.get("model_id",          "eleven_v3")
    model_id_fallback = tts_cfg.get("model_id_fallback", "eleven_multilingual_v2")

    if not api_key:
        raise ValueError(
            "ElevenLabs API key not set. Add ELEVENLABS_API_KEY to .env "
            "or set tts.elevenlabs_intent_threshold: 10 to use Edge TTS for all leads."
        )

    client = ElevenLabs(api_key=api_key)

    vs_kwargs: dict = dict(
        stability=0.35,
        similarity_boost=0.75,
        style=0.45,
        use_speaker_boost=True,
        speed=1.05,
    )

    active_model = model_id
    try:
        audio_gen = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id=active_model,
            text=text,
            voice_settings=VoiceSettings(**vs_kwargs),
            output_format="mp3_44100_128",
        )
        with open(output_path, "wb") as f:
            for chunk in audio_gen:
                if chunk:
                    f.write(chunk)
    except Exception as primary_err:
        log.warning("ElevenLabs %s failed (%s), retrying with %s", active_model, primary_err, model_id_fallback)
        active_model = model_id_fallback
        audio_gen = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id=active_model,
            text=text,
            voice_settings=VoiceSettings(**vs_kwargs),
            output_format="mp3_44100_128",
        )
        with open(output_path, "wb") as f:
            for chunk in audio_gen:
                if chunk:
                    f.write(chunk)

    log.info(
        "ElevenLabs (%s, voice=%s): wrote %s bytes → %s",
        active_model, voice_id, output_path.stat().st_size, output_path.name,
    )


# ─── Edge TTS (free — Microsoft Neural TTS) ───────────────────────────────────

async def _synthesize_edge(text: str, output_path: Path, voice: str) -> None:
    """Free Microsoft Edge Neural TTS. No API key required.

    Recommended voice: en-US-AndrewMultilingualNeural
      — calm, confident, professional; best free voice for B2B outreach.
    """
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=voice, rate="+0%", volume="+0%")
    await communicate.save(str(output_path))
    log.info("Edge TTS (%s): wrote %s bytes → %s", voice, output_path.stat().st_size, output_path.name)


# ─── OpenAI TTS (legacy — not recommended) ────────────────────────────────────

async def _synthesize_openai(
    text: str, output_path: Path, settings: Any, voice_override: str | None
) -> None:
    from openai import OpenAI
    tts_cfg = settings.tts if isinstance(settings.tts, dict) else {}
    voice = (
        voice_override
        if voice_override and voice_override not in ("elevenlabs", "openai", "edge_tts")
        else tts_cfg.get("primary_voice", "echo")
    )
    model = getattr(settings, "openai_tts_model", "tts-1")
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.audio.speech.create(model=model, voice=voice, input=text)
    response.write_to_file(str(output_path))
