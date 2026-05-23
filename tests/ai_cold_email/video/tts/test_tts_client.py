"""Tests for src/video/tts/tts_client.py — all external clients mocked."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ai_cold_email.video.tts.tts_client import synthesize


def make_settings(provider: str = "edge_tts", voice: str = "en-US-ChristopherNeural"):
    s = MagicMock()
    s.tts = {"primary_provider": provider, "primary_voice": voice}
    s.openai_api_key = "fake-openai"
    s.openai_tts_model = "tts-1"
    s.elevenlabs_api_key = "fake-el"
    s.elevenlabs_voice_id = "ErXwobaYiN019PkySvjV"
    s.elevenlabs_model = "eleven_turbo_v2_5"
    return s


def make_cost_tracker():
    ct = MagicMock()
    ct.log = MagicMock()
    return ct


def _fake_edge_comm(tmp_dir: str):
    """Returns a Communicate mock whose save() writes real bytes to the path."""
    comm = MagicMock()

    async def fake_save(p: str) -> None:
        Path(p).write_bytes(b"x" * 10_000)

    comm.save = fake_save
    return comm


# ─── edge_tts (free, default) ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_edge_tts_is_default_provider():
    """Default provider is edge_tts — free, no API key needed."""
    settings = make_settings("edge_tts")
    ct = make_cost_tracker()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.mp3"
        comm = _fake_edge_comm(tmp)

        # edge_tts is imported lazily inside _synthesize_edge → patch at source
        with patch("edge_tts.Communicate", return_value=comm):
            result = await synthesize("Hello world", path, settings, ct)

    assert result == path
    ct.log.assert_called_once()
    assert ct.log.call_args[0][1] == "edge_tts"
    assert ct.log.call_args[0][3] == 0.0   # Free!


@pytest.mark.asyncio
async def test_edge_tts_voice_from_settings():
    """Voice name comes from settings.tts.primary_voice."""
    settings = make_settings("edge_tts", "en-US-AndrewNeural")
    ct = make_cost_tracker()
    captured: dict = {}

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.mp3"

        def capture(text, voice, **kwargs):
            captured["voice"] = voice
            return _fake_edge_comm(tmp)

        with patch("edge_tts.Communicate", side_effect=capture):
            await synthesize("Test", path, settings, ct)

    assert captured["voice"] == "en-US-AndrewNeural"


@pytest.mark.asyncio
async def test_voice_override_neural_uses_edge_tts():
    """A voice_override containing 'Neural' routes to edge_tts with that voice."""
    settings = make_settings("edge_tts")
    ct = make_cost_tracker()
    captured: dict = {}

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.mp3"

        def capture(text, voice, **kwargs):
            captured["voice"] = voice
            return _fake_edge_comm(tmp)

        with patch("edge_tts.Communicate", side_effect=capture):
            await synthesize("Test", path, settings, ct, voice_override="en-US-GuyNeural")

    assert captured["voice"] == "en-US-GuyNeural"


@pytest.mark.asyncio
async def test_cost_is_zero_for_edge_tts():
    """edge_tts logs $0 cost — it's free."""
    settings = make_settings("edge_tts")
    ct = make_cost_tracker()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.mp3"

        with patch("edge_tts.Communicate", return_value=_fake_edge_comm(tmp)):
            await synthesize("A" * 600, path, settings, ct)

    assert ct.log.call_args[0][3] == 0.0


# ─── ElevenLabs (paid, optional) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_elevenlabs_provider_chosen_when_configured():
    settings = make_settings("elevenlabs")
    ct = make_cost_tracker()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.mp3"
        el_client = MagicMock()
        el_client.text_to_speech.convert.return_value = iter([b"audio-chunk"])

        # Lazy import inside _synthesize_elevenlabs → patch at source
        with patch("elevenlabs.client.ElevenLabs", return_value=el_client):
            result = await synthesize("Hello world", path, settings, ct)

    el_client.text_to_speech.convert.assert_called_once()
    assert result == path
    ct.log.assert_called_once()
    assert ct.log.call_args[0][1] == "elevenlabs"


@pytest.mark.asyncio
async def test_voice_override_elevenlabs_forces_elevenlabs():
    """voice_override='elevenlabs' overrides even an edge_tts primary config."""
    settings = make_settings("edge_tts")
    ct = make_cost_tracker()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.mp3"
        el_client = MagicMock()
        el_client.text_to_speech.convert.return_value = iter([b"audio-chunk"])

        with patch("elevenlabs.client.ElevenLabs", return_value=el_client):
            result = await synthesize("Hello world", path, settings, ct, voice_override="elevenlabs")

    el_client.text_to_speech.convert.assert_called_once()
    ct.log.assert_called_once()
    assert ct.log.call_args[0][1] == "elevenlabs"


# ─── OpenAI TTS (legacy, optional) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_openai_provider_explicit():
    """OpenAI still works when explicitly configured."""
    settings = make_settings("openai")
    settings.tts = {"primary_provider": "openai", "primary_voice": "echo"}
    ct = make_cost_tracker()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.mp3"
        openai_resp = MagicMock()
        openai_resp.write_to_file = MagicMock()
        openai_client = MagicMock()
        openai_client.audio.speech.create.return_value = openai_resp

        # Lazy import inside _synthesize_openai → patch at source
        with patch("openai.OpenAI", return_value=openai_client):
            result = await synthesize("Hello world", path, settings, ct)

    openai_client.audio.speech.create.assert_called_once()
    assert result == path
    ct.log.assert_called_once()
    assert ct.log.call_args[0][1] == "openai"
