"""
Unit tests for src/sms/timezone_lookup.phone_to_zone().

Covers:
  - Normal US Eastern number            (212, NYC)
  - Normal US Central number            (312, Chicago)
  - Multi-zone area code                (208, Idaho → Boise + LA → pick Boise)
  - Multi-zone Alaska                   (907 → Anchorage + Adak → pick Anchorage)
  - Canadian number                     (416, Toronto → Eastern)
  - Canadian number Pacific             (604, Vancouver → Pacific)
  - Malformed / unparseable input       → default + review_flag
  - Completely empty input              → default + review_flag
  - No area code / too-short number     → default + review_flag
  - Various common input formats        → all resolve to the same zone
  - NPA fallback dictionary sanity      → spot-check key entries
  - source field reflects lookup path
"""
from __future__ import annotations

import pytest

from src.sms.timezone_lookup import phone_to_zone, ZoneResult, _NPA_FALLBACK, _DEFAULT_ZONE


# ── helpers ───────────────────────────────────────────────────────────────────

def _z(raw: str) -> ZoneResult:
    return phone_to_zone(raw)


# ── normal US numbers ─────────────────────────────────────────────────────────

class TestNormalUSNumbers:
    def test_eastern_212_new_york(self):
        r = _z("+12125550100")
        assert r.zone == "America/New_York"
        assert r.source == "libphonenumber"
        assert r.ambiguous is False
        assert r.review_flag is False

    def test_eastern_617_boston(self):
        r = _z("+16175550100")
        assert r.zone == "America/New_York"
        assert r.source == "libphonenumber"
        assert r.review_flag is False

    def test_central_312_chicago(self):
        r = _z("+13125550100")
        assert r.zone == "America/Chicago"
        assert r.source == "libphonenumber"
        assert r.review_flag is False

    def test_pacific_213_los_angeles(self):
        r = _z("+12135550100")
        assert r.zone == "America/Los_Angeles"
        assert r.source == "libphonenumber"
        assert r.review_flag is False

    def test_mountain_no_dst_602_phoenix(self):
        r = _z("+16025550100")
        assert r.zone == "America/Phoenix"
        assert r.source == "libphonenumber"
        assert r.review_flag is False

    def test_hawaii_808(self):
        r = _z("+18085550100")
        assert r.zone == "Pacific/Honolulu"
        assert r.source == "libphonenumber"
        assert r.review_flag is False


# ── multi-zone area codes ─────────────────────────────────────────────────────

class TestMultiZoneAreaCodes:
    def test_idaho_208_picks_easternmost(self):
        """
        208 (Idaho) spans Mountain (Boise) and Pacific (western Idaho near OR border).
        libphonenumber returns ['America/Boise', 'America/Los_Angeles'].
        We must pick America/Boise — easternmost = most conservative.
        """
        r = _z("+12085550100")
        # Must be one of the two possible zones
        assert r.zone in ("America/Boise", "America/Los_Angeles"), (
            f"Unexpected zone: {r.zone}"
        )
        # Because libphonenumber returns multiple zones, we should pick Boise
        assert r.zone == "America/Boise", (
            "Expected America/Boise (easternmost) but got {r.zone!r}; "
            f"ambiguous={r.ambiguous}"
        )
        # ambiguous should be flagged when >1 zone was returned
        assert r.ambiguous is True
        assert r.source == "libphonenumber"
        assert r.review_flag is False

    def test_alaska_907_picks_anchorage_over_adak(self):
        """
        907 (Alaska) spans Anchorage (UTC-9/-8) and Adak (UTC-10/-9).
        Anchorage is easternmost → more conservative for TCPA cutoff.
        """
        r = _z("+19075550100")
        assert r.zone in ("America/Anchorage", "America/Adak"), (
            f"Unexpected zone: {r.zone}"
        )
        assert r.zone == "America/Anchorage"
        assert r.ambiguous is True
        assert r.source == "libphonenumber"


# ── canadian numbers ──────────────────────────────────────────────────────────

class TestCanadianNumbers:
    def test_toronto_416_eastern(self):
        r = _z("+14165550100")
        # libphonenumber returns America/Toronto (which observes Eastern time)
        assert "America/" in r.zone
        assert r.source == "libphonenumber"
        assert r.review_flag is False
        # Toronto is Eastern
        assert r.zone in ("America/Toronto", "America/New_York"), (
            f"Expected Eastern zone, got {r.zone!r}"
        )

    def test_vancouver_604_pacific(self):
        r = _z("+16045550100")
        assert r.zone in ("America/Vancouver", "America/Los_Angeles"), (
            f"Expected Pacific zone, got {r.zone!r}"
        )
        assert r.source == "libphonenumber"
        assert r.review_flag is False

    def test_alberta_403_mountain(self):
        r = _z("+14035550100")
        # Alberta → Mountain time
        assert r.zone in ("America/Edmonton", "America/Denver"), (
            f"Expected Mountain zone, got {r.zone!r}"
        )
        assert r.source == "libphonenumber"
        assert r.review_flag is False


# ── bad / missing input ───────────────────────────────────────────────────────

class TestMalformedInput:
    def test_empty_string(self):
        r = _z("")
        assert r.zone == _DEFAULT_ZONE
        assert r.source == "default"
        assert r.review_flag is True

    def test_whitespace_only(self):
        r = _z("   ")
        assert r.zone == _DEFAULT_ZONE
        assert r.review_flag is True

    def test_obvious_garbage(self):
        r = _z("not-a-phone-number")
        assert r.zone == _DEFAULT_ZONE
        assert r.review_flag is True

    def test_letters_mixed_in(self):
        r = _z("abc-def-ghij")
        assert r.zone == _DEFAULT_ZONE
        assert r.review_flag is True

    def test_too_short_no_area_code(self):
        """7-digit local number with no area code — unresolvable."""
        r = _z("5550100")
        # No valid zone can be derived; must default
        assert r.zone == _DEFAULT_ZONE
        assert r.review_flag is True

    def test_never_raises(self):
        """phone_to_zone must never raise regardless of input."""
        bad_inputs = [None, "", "   ", "000", "9" * 20, "!@#$%", "+00000000000"]
        for inp in bad_inputs:
            try:
                result = phone_to_zone(inp)  # type: ignore[arg-type]
                assert isinstance(result.zone, str) and result.zone, (
                    f"Expected a non-empty zone string for input {inp!r}"
                )
            except Exception as exc:
                pytest.fail(
                    f"phone_to_zone({inp!r}) raised unexpectedly: {exc!r}"
                )


# ── input format consistency ──────────────────────────────────────────────────

class TestInputFormats:
    def test_same_number_different_formats(self):
        """All common US formats of the same number must resolve to the same zone."""
        formats = [
            "+12125550100",        # E.164
            "12125550100",         # E.164 without +
            "2125550100",          # 10-digit
            "212-555-0100",        # dashes
            "(212) 555-0100",      # parentheses
            "212.555.0100",        # dots
            "+1 (212) 555-0100",   # formatted E.164
        ]
        zones = [_z(f).zone for f in formats]
        assert len(set(zones)) == 1, (
            f"Inconsistent zone resolution across formats: {list(zip(formats, zones))}"
        )

    def test_e164_with_plus(self):
        r = _z("+13125550100")
        assert r.zone == "America/Chicago"
        assert r.source == "libphonenumber"


# ── NPA fallback table sanity ─────────────────────────────────────────────────

class TestNPAFallback:
    """Spot-check the hardcoded NPA → zone mapping for correctness."""

    def test_key_eastern_npas(self):
        eastern = ["212", "617", "202", "305", "404", "703", "718"]
        for npa in eastern:
            assert _NPA_FALLBACK.get(npa) == "America/New_York", (
                f"NPA {npa} should map to America/New_York"
            )

    def test_key_central_npas(self):
        central = ["312", "713", "214", "512", "612", "314"]
        for npa in central:
            assert _NPA_FALLBACK.get(npa) == "America/Chicago", (
                f"NPA {npa} should map to America/Chicago"
            )

    def test_key_mountain_npas(self):
        assert _NPA_FALLBACK["303"] == "America/Denver"
        assert _NPA_FALLBACK["720"] == "America/Denver"

    def test_arizona_no_dst(self):
        az_npas = ["480", "520", "602", "623", "928"]
        for npa in az_npas:
            assert _NPA_FALLBACK.get(npa) == "America/Phoenix", (
                f"NPA {npa} (Arizona) should map to America/Phoenix"
            )

    def test_key_pacific_npas(self):
        pacific = ["213", "310", "415", "503", "206", "619"]
        for npa in pacific:
            assert _NPA_FALLBACK.get(npa) == "America/Los_Angeles", (
                f"NPA {npa} should map to America/Los_Angeles"
            )

    def test_alaska_and_hawaii(self):
        assert _NPA_FALLBACK["907"] == "America/Anchorage"
        assert _NPA_FALLBACK["808"] == "Pacific/Honolulu"

    def test_all_values_are_valid_iana_zones(self):
        """Every zone in the fallback table must be importable from zoneinfo."""
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo  # type: ignore

        bad = []
        for npa, zone in _NPA_FALLBACK.items():
            try:
                ZoneInfo(zone)
            except Exception:
                bad.append((npa, zone))
        assert not bad, f"Invalid IANA zones in _NPA_FALLBACK: {bad}"
