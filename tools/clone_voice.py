"""
Voice Clone Setup — Ascentir Outreach OS
=========================================
Uploads your voice recordings to ElevenLabs Instant Voice Clone,
then auto-writes the new voice_id to your .env file so every future
video uses YOUR voice.

STEP-BY-STEP BEFORE RUNNING:
─────────────────────────────
1.  Record yourself saying the scripts (see RECORDING GUIDE below).
    Save the files into:  assets/voice_samples/

2.  Accepted formats: .mp3  .wav  .m4a  .ogg  (anything clear and clean)

3.  Run:
        python3 tools/clone_voice.py

4.  Done. Your .env gets ELEVENLABS_VOICE_ID=<your_new_id> automatically.
    Every video from now on will sound like YOU.

─────────────────────────────────────────────────────────────────────────────
RECORDING GUIDE  (read this — it's the most important part)
─────────────────────────────────────────────────────────────────────────────

Goal: give ElevenLabs enough of your voice to clone it convincingly.
Instant Voice Clone needs as little as 1 minute. More = better quality.
Aim for 3–10 minutes total across all files.

WHAT TO RECORD:
  ✓  Read each of the 4 video scripts naturally — as if you're actually
     recording a Loom right now. Don't perform. Don't "do a voice."
     Just talk the way you normally talk.
  ✓  Record a few minutes of casual speech — explain what Ascentir does,
     talk about a client win, answer "what problem do you solve?" out loud.
     Variety in content helps the clone generalise.
  ✓  Aim for 3–5 recording files, 1–3 minutes each.

WHAT NOT TO DO:
  ✗  Don't read the same script multiple times back-to-back — the clone
     needs tonal variety, not repetition.
  ✗  Don't record in a noisy room, coffee shop, or with background music.
  ✗  Don't use a speakerphone or laptop mic if you can avoid it.
     AirPods Pro work fine. A USB mic is ideal.
  ✗  Don't rush. Natural pace = better clone.

TIPS FOR MAXIMUM QUALITY:
  • Record in a small room or near soft furnishings (kills echo)
  • Stay ~15–20cm from the mic — not too close (plosives), not too far (thin)
  • Do a 10-second test recording, play it back, check for hiss/reverb
  • If you hear room echo — record in a closet with clothes around you.
    Sounds dumb, works brilliantly.

FILE NAMING (anything is fine — the script reads all audio in the folder):
  voice_samples/script_v1.mp3
  voice_samples/script_v2.mp3
  voice_samples/free_talk.mp3
  etc.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import os
import sys
import re
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
SAMPLES_DIR = ROOT / "assets" / "voice_samples"
ENV_FILE    = ROOT / ".env"

AUDIO_EXTS  = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm"}
VOICE_NAME  = "Frank — Ascentir"
VOICE_DESC  = "Frank Frederico — Ascentir founder voice for personalised Loom-style videos"


def load_api_key() -> str:
    """Load ElevenLabs API key from .env or environment."""
    # Try .env first
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("ELEVENLABS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        print("❌  ELEVENLABS_API_KEY not found in .env")
        sys.exit(1)
    return key


def get_sample_files() -> list[Path]:
    files = sorted(
        p for p in SAMPLES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )
    return files


def write_voice_id_to_env(voice_id: str) -> None:
    """Update or append ELEVENLABS_VOICE_ID in .env."""
    text = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    pattern = r"^ELEVENLABS_VOICE_ID=.*$"
    new_line = f"ELEVENLABS_VOICE_ID={voice_id}"

    if re.search(pattern, text, re.MULTILINE):
        text = re.sub(pattern, new_line, text, flags=re.MULTILINE)
    else:
        text = text.rstrip("\n") + f"\n{new_line}\n"

    ENV_FILE.write_text(text)
    print(f"  ✓  .env updated: ELEVENLABS_VOICE_ID={voice_id}")


def check_existing_clone(client, name: str) -> str | None:
    """Return voice_id if a clone with this name already exists."""
    try:
        voices = client.voices.get_all()
        for v in voices.voices:
            if v.name == name:
                return v.voice_id
    except Exception:
        pass
    return None


def main() -> None:
    print("\n" + "=" * 62)
    print("  Ascentir Voice Clone Setup")
    print("=" * 62 + "\n")

    # ── Check samples exist ───────────────────────────────────────────────────
    files = get_sample_files()
    if not files:
        print(f"❌  No audio files found in:  {SAMPLES_DIR}\n")
        print("    Create the folder and add your recordings, then re-run.")
        print("    Read the RECORDING GUIDE at the top of this script first.\n")
        print(f"    Expected location:  {SAMPLES_DIR}")
        print(f"    Accepted formats:   {', '.join(sorted(AUDIO_EXTS))}\n")
        sys.exit(1)

    total_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
    print(f"  Found {len(files)} recording(s)  ({total_mb:.1f} MB total)")
    for f in files:
        mb = f.stat().st_size / (1024 * 1024)
        print(f"    • {f.name}  ({mb:.1f} MB)")
    print()

    if total_mb < 0.5:
        print("⚠️   Recordings seem very short (< 0.5 MB total).")
        print("    The clone will still work but quality may be limited.")
        print("    Aim for 3–10 minutes across all files for best results.\n")

    # ── Load API key and init client ──────────────────────────────────────────
    api_key = load_api_key()
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError:
        print("❌  elevenlabs package not installed. Run: pip install elevenlabs")
        sys.exit(1)

    client = ElevenLabs(api_key=api_key)

    # ── Check for existing clone ──────────────────────────────────────────────
    existing_id = check_existing_clone(client, VOICE_NAME)
    if existing_id:
        print(f"  Found existing clone '{VOICE_NAME}' (id: {existing_id})")
        answer = input("  Update it with new recordings? [y/N] ").strip().lower()
        if answer != "y":
            print("\n  Using existing clone — writing id to .env...")
            write_voice_id_to_env(existing_id)
            _write_settings_yaml(existing_id)
            print(f"\n  Done! Your existing voice is active: {existing_id}\n")
            return

    # ── Upload and create clone ───────────────────────────────────────────────
    print(f"  Uploading to ElevenLabs Instant Voice Clone...")
    print(f"  Voice name: '{VOICE_NAME}'\n")

    try:
        file_handles = [open(f, "rb") for f in files]
        try:
            voice = client.voices.ivc.create(
                name=VOICE_NAME,
                files=file_handles,
                description=VOICE_DESC,
            )
        finally:
            for fh in file_handles:
                fh.close()

        voice_id = voice.voice_id
        print(f"\n  ✅  Voice clone created!")
        print(f"      Voice ID: {voice_id}\n")

    except Exception as e:
        print(f"\n  ❌  Upload failed: {e}")
        print("\n  Troubleshooting:")
        print("    • Check your API key has Voice Clone access")
        print("    • ElevenLabs free tier supports Instant Voice Clone")
        print("    • Creator tier ($22/mo) unlocks Professional Voice Clone")
        print("    • Try uploading manually at: elevenlabs.io/voice-lab")
        sys.exit(1)

    # ── Write to .env and settings.yaml ──────────────────────────────────────
    write_voice_id_to_env(voice_id)
    _write_settings_yaml(voice_id)

    print("\n" + "=" * 62)
    print("  All done! Every new video will now use your voice.")
    print(f"  Voice ID: {voice_id}")
    print("=" * 62 + "\n")
    print("  Next step: run python3 demo_video.py to hear the difference.\n")


def _write_settings_yaml(voice_id: str) -> None:
    """Update voice_id in config/settings.yaml."""
    settings_path = ROOT / "config" / "settings.yaml"
    if not settings_path.exists():
        return
    text = settings_path.read_text()
    # Replace the active voice_id line
    pattern = r"(  voice_id:\s+)['\"]?[A-Za-z0-9]+['\"]?"
    replacement = f'\\g<1>"{voice_id}"'
    new_text = re.sub(pattern, replacement, text, count=1)
    if new_text != text:
        settings_path.write_text(new_text)
        print(f"  ✓  config/settings.yaml updated: voice_id={voice_id}")


if __name__ == "__main__":
    main()
