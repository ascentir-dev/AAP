"""
Settings: loads .env + config/settings.yaml into a typed Pydantic model.
Singleton via lru_cache — call load_settings() everywhere.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


def _load_yaml(path: Path = Path("config/settings.yaml")) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # Anthropic
    # ------------------------------------------------------------------
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_analysis_model: str = Field(
        default="claude-haiku-4-5-20251001", alias="ANTHROPIC_ANALYSIS_MODEL"
    )
    anthropic_generation_model: str = Field(
        default="claude-sonnet-4-6", alias="ANTHROPIC_GENERATION_MODEL"
    )
    use_batch_api: bool = Field(default=True, alias="USE_BATCH_API")
    use_prompt_caching: bool = Field(default=True, alias="USE_PROMPT_CACHING")

    # ------------------------------------------------------------------
    # OpenAI TTS
    # ------------------------------------------------------------------
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_tts_model: str = Field(default="tts-1", alias="OPENAI_TTS_MODEL")
    openai_tts_voice: str = Field(default="echo", alias="OPENAI_TTS_VOICE")

    # ------------------------------------------------------------------
    # ElevenLabs (optional fallback)
    # ------------------------------------------------------------------
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field(
        default="ErXwobaYiN019PkySvjV", alias="ELEVENLABS_VOICE_ID"
    )
    elevenlabs_model: str = Field(
        default="eleven_turbo_v2_5", alias="ELEVENLABS_MODEL"
    )

    # ------------------------------------------------------------------
    # Apify / LinkedIn
    # ------------------------------------------------------------------
    apify_api_token: str = Field(default="", alias="APIFY_API_TOKEN")
    apify_linkedin_actor: str = Field(
        default="curious_coder/linkedin-profile-scraper",
        alias="APIFY_LINKEDIN_ACTOR",
    )
    linkedin_enrich_all: bool = Field(default=False, alias="LINKEDIN_ENRICH_ALL")

    # ------------------------------------------------------------------
    # Cloudflare R2
    # ------------------------------------------------------------------
    cloudflare_r2_account_id: str = Field(
        default="", alias="CLOUDFLARE_R2_ACCOUNT_ID"
    )
    cloudflare_r2_access_key_id: str = Field(
        default="", alias="CLOUDFLARE_R2_ACCESS_KEY_ID"
    )
    cloudflare_r2_secret_access_key: str = Field(
        default="", alias="CLOUDFLARE_R2_SECRET_ACCESS_KEY"
    )
    cloudflare_r2_bucket: str = Field(
        default="lead-videos", alias="CLOUDFLARE_R2_BUCKET"
    )
    cloudflare_r2_public_url: str = Field(
        default="https://videos.example.com", alias="CLOUDFLARE_R2_PUBLIC_URL"
    )
    cloudflare_pages_base_url: str = Field(
        default="https://go.example.com", alias="CLOUDFLARE_PAGES_BASE_URL"
    )
    # Worker URL — set automatically by tools/deploy_tracking_worker.py
    cloudflare_worker_url: str = Field(
        default="", alias="CLOUDFLARE_WORKER_URL"
    )
    cloudflare_kv_namespace_id: str = Field(
        default="", alias="CLOUDFLARE_KV_NAMESPACE_ID"
    )
    cloudflare_api_token: str = Field(
        default="", alias="CLOUDFLARE_API_TOKEN"
    )

    # ------------------------------------------------------------------
    # Twilio (SMS)
    # ------------------------------------------------------------------
    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_number_1: str = Field(default="", alias="TWILIO_NUMBER_1")
    twilio_number_2: str = Field(default="", alias="TWILIO_NUMBER_2")
    twilio_number_3: str = Field(default="", alias="TWILIO_NUMBER_3")

    # ------------------------------------------------------------------
    # Smartlead
    # ------------------------------------------------------------------
    smartlead_api_key: str = Field(default="", alias="SMARTLEAD_API_KEY")
    smartlead_campaign_id: str = Field(default="", alias="SMARTLEAD_CAMPAIGN_ID")

    # ------------------------------------------------------------------
    # Offer / booking
    # ------------------------------------------------------------------
    book_a_call_url: str = Field(
        default="https://calendly.com/your-handle/intro",
        alias="BOOK_A_CALL_URL",
    )

    # ------------------------------------------------------------------
    # Dashboard / tracking base URL
    # The public-facing URL of this server — used to build /v/{lead_id}
    # tracking links embedded in emails.
    # Local dev:  http://localhost:8000
    # Production: https://your-domain.com  (set BASE_URL in .env)
    # ------------------------------------------------------------------
    base_url: str = Field(
        default="http://localhost:8000",
        alias="BASE_URL",
    )

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    max_daily_budget_usd: float = Field(
        default=50.0, alias="MAX_DAILY_BUDGET_USD"
    )
    max_concurrent_leads: int = Field(default=8, alias="MAX_CONCURRENT_LEADS")
    batch_size_threshold: int = Field(default=500, alias="BATCH_SIZE_THRESHOLD")

    # ------------------------------------------------------------------
    # YAML-loaded config (populated after __init__)
    # ------------------------------------------------------------------
    _yaml: dict[str, Any] = {}

    model_config = {
        "populate_by_name": True,
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "env_ignore_empty": True,   # empty shell vars don't shadow .env values
    }

    def model_post_init(self, __context: Any) -> None:
        object.__setattr__(self, "_yaml", _load_yaml())

    # ------------------------------------------------------------------
    # YAML accessors (nested dicts from settings.yaml)
    # ------------------------------------------------------------------
    @property
    def your_identity(self) -> dict[str, Any]:
        return self._yaml.get("your_identity", {})

    @property
    def offer(self) -> dict[str, Any]:
        return self._yaml.get("offer", {})

    @property
    def fixed_second_half_plg_self_serve(self) -> str:
        return self.offer.get("fixed_second_half_plg_self_serve", "")

    @property
    def fixed_second_half_hybrid_sales_assisted(self) -> str:
        return self.offer.get("fixed_second_half_hybrid_sales_assisted", "")

    @property
    def fixed_second_half_sales_led_outbound(self) -> str:
        return self.offer.get("fixed_second_half_sales_led_outbound", "")

    @property
    def variants(self) -> dict[str, Any]:
        return self._yaml.get("variants", {})

    @property
    def video(self) -> dict[str, Any]:
        return self._yaml.get("video", {})

    @property
    def scroll_capture(self) -> dict[str, Any]:
        return self._yaml.get("scroll_capture", {})

    @property
    def composite(self) -> dict[str, Any]:
        return self._yaml.get("composite", {})

    @property
    def script(self) -> dict[str, Any]:
        return self._yaml.get("script", {})

    @property
    def email(self) -> dict[str, Any]:
        return self._yaml.get("email", {})

    @property
    def enrichment(self) -> dict[str, Any]:
        return self._yaml.get("enrichment", {})

    @property
    def orchestrator(self) -> dict[str, Any]:
        return self._yaml.get("orchestrator", {})

    @property
    def cost_tracking(self) -> dict[str, Any]:
        return self._yaml.get("cost_tracking", {})

    @property
    def model_routing(self) -> dict[str, Any]:
        return self._yaml.get("model_routing", {})

    @property
    def tts(self) -> dict[str, Any]:
        return self._yaml.get("tts", {})

    @property
    def sms(self) -> dict[str, Any]:
        return self._yaml.get("sms", {})

    @property
    def twilio_numbers(self) -> list[str]:
        """Return list of configured Twilio numbers (non-empty only)."""
        return [n for n in [self.twilio_number_1, self.twilio_number_2, self.twilio_number_3] if n and not n.startswith("+1XXXX")]

    @property
    def volume_ramp(self) -> dict[str, Any]:
        return self._yaml.get("volume_ramp", {})

    # ------------------------------------------------------------------
    # Business logic helpers
    # ------------------------------------------------------------------
    def active_test_config(self) -> dict[str, Any] | None:
        """Return active test's config dict with 'id' injected, or None."""
        active = self.variants.get("active_test")
        if not active:
            return None
        config = self.variants.get(active)
        if not config:
            return None
        return {**config, "id": active}

    def lookup_variant_arm(
        self, test_id: str, variant_id: str
    ) -> dict[str, Any] | None:
        """Return the arm dict for a specific test + variant id."""
        test = self.variants.get(test_id)
        if not test:
            return None
        for arm in test.get("arms", []):
            if arm.get("id") == variant_id:
                return arm
        return None

    def fixed_second_half_for_motion(self, motion: str) -> str:
        """Return the appropriate fixed second half based on sales motion."""
        mapping = {
            "plg_self_serve": self.fixed_second_half_plg_self_serve,
            "hybrid_sales_assisted": self.fixed_second_half_hybrid_sales_assisted,
            "sales_led_outbound": self.fixed_second_half_sales_led_outbound,
        }
        return mapping.get(motion, self.fixed_second_half_sales_led_outbound)

    def fixed_second_half_for_market(self, market: str, motion: str = "sales_led_outbound") -> str:
        """Return the market-specific fixed second half for the video offer script.

        Lookup order:
          1. offer.fixed_second_half_{market}  — market-specific (preferred)
          2. fixed_second_half_for_motion(motion) — motion-based fallback
        """
        key = f"fixed_second_half_{market}"
        result = self.offer.get(key, "")
        if result:
            return result
        return self.fixed_second_half_for_motion(motion)


def load_settings() -> Settings:
    """Load settings from .env + config/settings.yaml.

    NOTE: lru_cache removed — each call re-reads .env so API key
    changes take effect immediately without a server restart.
    """
    return Settings()
