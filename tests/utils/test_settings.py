"""Tests for src/utils/settings.py"""
import pytest
from src.utils.settings import Settings, load_settings


def make_settings(**env_overrides) -> Settings:
    """Build a Settings instance without needing a .env file."""
    return Settings(**env_overrides)


def test_required_keys_accessible():
    s = make_settings()
    # env-backed keys
    assert isinstance(s.anthropic_api_key, str)
    assert isinstance(s.anthropic_analysis_model, str)
    assert isinstance(s.anthropic_generation_model, str)
    assert isinstance(s.openai_api_key, str)
    assert isinstance(s.openai_tts_model, str)
    assert isinstance(s.openai_tts_voice, str)
    assert isinstance(s.elevenlabs_api_key, str)
    assert isinstance(s.elevenlabs_voice_id, str)
    assert isinstance(s.elevenlabs_model, str)
    assert isinstance(s.apify_api_token, str)
    assert isinstance(s.apify_linkedin_actor, str)
    assert isinstance(s.linkedin_enrich_all, bool)
    assert isinstance(s.cloudflare_r2_account_id, str)
    assert isinstance(s.cloudflare_r2_access_key_id, str)
    assert isinstance(s.cloudflare_r2_secret_access_key, str)
    assert isinstance(s.cloudflare_r2_bucket, str)
    assert isinstance(s.cloudflare_r2_public_url, str)
    assert isinstance(s.cloudflare_pages_base_url, str)
    assert isinstance(s.smartlead_api_key, str)
    assert isinstance(s.smartlead_campaign_id, str)
    assert isinstance(s.book_a_call_url, str)
    assert isinstance(s.log_level, str)
    assert isinstance(s.max_daily_budget_usd, float)
    assert isinstance(s.max_concurrent_leads, int)
    assert isinstance(s.batch_size_threshold, int)
    assert isinstance(s.use_batch_api, bool)
    assert isinstance(s.use_prompt_caching, bool)


def test_yaml_sections_accessible():
    s = make_settings()
    # These all come from config/settings.yaml
    assert isinstance(s.your_identity, dict)
    assert isinstance(s.offer, dict)
    assert isinstance(s.variants, dict)
    assert isinstance(s.video, dict)
    assert isinstance(s.scroll_capture, dict)
    assert isinstance(s.composite, dict)
    assert isinstance(s.script, dict)
    assert isinstance(s.email, dict)
    assert isinstance(s.enrichment, dict)
    assert isinstance(s.orchestrator, dict)
    assert isinstance(s.cost_tracking, dict)
    assert isinstance(s.model_routing, dict)
    assert isinstance(s.tts, dict)
    assert isinstance(s.volume_ramp, dict)


def test_active_test_config_shape():
    s = make_settings()
    config = s.active_test_config()
    assert config is not None, "active_test_config() returned None — check settings.yaml"
    assert "id" in config
    assert "arms" in config
    assert isinstance(config["arms"], list)
    assert len(config["arms"]) > 0
    # Each arm must have id and weight
    for arm in config["arms"]:
        assert "id" in arm
        assert "weight" in arm


def test_fixed_second_half_for_motion_plg():
    s = make_settings()
    text = s.fixed_second_half_for_motion("plg_self_serve")
    assert isinstance(text, str)
    assert len(text) > 20, "PLG second half should have meaningful content"
    # Must contain the pivot phrase
    assert "let me be quick" in text.lower() or "quick" in text.lower()


def test_fixed_second_half_for_motion_all_three():
    s = make_settings()
    plg = s.fixed_second_half_for_motion("plg_self_serve")
    hybrid = s.fixed_second_half_for_motion("hybrid_sales_assisted")
    sales = s.fixed_second_half_for_motion("sales_led_outbound")
    # All three should be non-empty strings
    assert plg and hybrid and sales
    # They should be different from each other
    assert plg != sales


def test_lookup_variant_arm():
    s = make_settings()
    config = s.active_test_config()
    if config and config["arms"]:
        first_arm = config["arms"][0]
        result = s.lookup_variant_arm(config["id"], first_arm["id"])
        assert result is not None
        assert result["id"] == first_arm["id"]


def test_lookup_variant_arm_missing_returns_none():
    s = make_settings()
    result = s.lookup_variant_arm("nonexistent_test", "Variant X")
    assert result is None


def test_load_settings_singleton():
    # load_settings() should return the same instance each time
    s1 = load_settings()
    s2 = load_settings()
    assert s1 is s2
