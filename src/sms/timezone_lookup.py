"""
Phone number → IANA time-zone resolver for TCPA-aware SMS scheduling.

Resolution chain:
  1. phonenumbers.timezone.time_zones_for_number()  — primary (libphonenumber)
  2. NPA (area-code) fallback table                 — when libphonenumber fails
  3. America/New_York hard default                  — last resort; sets review_flag

Multi-zone area codes (e.g. 208 Idaho, 907 Alaska):
  libphonenumber may return >1 zone.  We pick the EASTERNMOST — the zone where
  9 PM arrives first in UTC, which is the most conservative TCPA cutoff.
  A debug log line is emitted when the choice was ambiguous.

TCPA note:
  "Easternmost" = highest UTC offset (least negative).  Eastern 9 PM = 02:00 UTC
  while Pacific 9 PM = 05:00 UTC, so stopping at the Eastern cutoff is the
  safest choice when the recipient's exact zone is unknown.
"""
from __future__ import annotations

import logging
import re
from typing import NamedTuple

log = logging.getLogger(__name__)

# ── Zones ordered easternmost → westernmost ───────────────────────────────────
# Used to pick the single "safest" zone when libphonenumber returns multiples.
# Zones earlier in this list have an earlier 9 PM in UTC → more conservative.
_EAST_TO_WEST: list[str] = [
    # UTC-4 / UTC-5  (Eastern)
    "America/New_York",
    "America/Detroit",
    "America/Indiana/Indianapolis",
    "America/Indiana/Marengo",
    "America/Indiana/Petersburg",
    "America/Indiana/Vevay",
    "America/Indiana/Vincennes",
    "America/Indiana/Winamac",
    "America/Kentucky/Louisville",
    "America/Kentucky/Monticello",
    "America/Toronto",
    "America/Montreal",
    "America/Nipigon",
    "America/Thunder_Bay",
    "America/Iqaluit",
    "America/Pangnirtung",
    # UTC-5 / UTC-6  (Central)
    "America/Chicago",
    "America/Indiana/Knox",
    "America/Indiana/Tell_City",
    "America/Menominee",
    "America/North_Dakota/Beulah",
    "America/North_Dakota/Center",
    "America/North_Dakota/New_Salem",
    "America/Rainy_River",
    "America/Rankin_Inlet",
    "America/Resolute",
    "America/Winnipeg",
    "America/Matamoros",
    # UTC-6 / UTC-7  (Mountain)
    "America/Denver",
    "America/Boise",
    "America/Cambridge_Bay",
    "America/Edmonton",
    "America/Inuvik",
    "America/Ojinaga",
    "America/Yellowknife",
    # UTC-7 no-DST  (Mountain-no-DST — equivalent to UTC-7 all year)
    "America/Phoenix",
    "America/Creston",
    "America/Dawson_Creek",
    "America/Fort_Nelson",
    "America/Hermosillo",
    # UTC-7 / UTC-8  (Pacific)
    "America/Los_Angeles",
    "America/Tijuana",
    "America/Vancouver",
    "America/Whitehorse",
    # UTC-8 / UTC-9  (Alaska)
    "America/Anchorage",
    "America/Juneau",
    "America/Metlakatla",
    "America/Nome",
    "America/Sitka",
    "America/Yakutat",
    "America/Dawson",
    # UTC-9 / UTC-10  (Aleutian / Hawaii-Aleutian)
    "America/Adak",
    # UTC-10 no-DST  (Hawaii)
    "Pacific/Honolulu",
    "Pacific/Johnston",
]

# Build a rank dict for O(1) lookup.  Lower rank = more easterly = more conservative.
_ZONE_RANK: dict[str, int] = {z: i for i, z in enumerate(_EAST_TO_WEST)}

# ── NPA (area-code) fallback ──────────────────────────────────────────────────
# Used only when libphonenumber lookup fails entirely.
# Covers the ~120 highest-volume US NPAs.
_NPA_FALLBACK: dict[str, str] = {
    # ── Eastern ──────────────────────────────────────────────────────────────
    "201": "America/New_York", "202": "America/New_York",
    "203": "America/New_York", "207": "America/New_York",
    "212": "America/New_York", "215": "America/New_York",
    "216": "America/New_York", "228": "America/New_York",
    "229": "America/New_York", "231": "America/New_York",
    "240": "America/New_York", "248": "America/New_York",
    "267": "America/New_York", "272": "America/New_York",
    "301": "America/New_York", "302": "America/New_York",
    "304": "America/New_York", "305": "America/New_York",
    "309": "America/New_York", "313": "America/New_York",
    "315": "America/New_York", "321": "America/New_York",
    "330": "America/New_York", "332": "America/New_York",
    "336": "America/New_York", "347": "America/New_York",
    "351": "America/New_York", "352": "America/New_York",
    "386": "America/New_York", "401": "America/New_York",
    "404": "America/New_York", "407": "America/New_York",
    "408": "America/New_York", "410": "America/New_York",
    "412": "America/New_York", "413": "America/New_York",
    "419": "America/New_York", "423": "America/New_York",
    "440": "America/New_York", "443": "America/New_York",
    "470": "America/New_York", "475": "America/New_York",
    "484": "America/New_York", "516": "America/New_York",
    "517": "America/New_York", "518": "America/New_York",
    "540": "America/New_York", "551": "America/New_York",
    "561": "America/New_York", "567": "America/New_York",
    "570": "America/New_York", "571": "America/New_York",
    "585": "America/New_York", "586": "America/New_York",
    "603": "America/New_York", "607": "America/New_York",
    "609": "America/New_York", "610": "America/New_York",
    "614": "America/New_York", "615": "America/New_York",
    "617": "America/New_York", "631": "America/New_York",
    "646": "America/New_York", "678": "America/New_York",
    "689": "America/New_York", "703": "America/New_York",
    "704": "America/New_York", "706": "America/New_York",
    "716": "America/New_York", "717": "America/New_York",
    "718": "America/New_York", "724": "America/New_York",
    "727": "America/New_York", "730": "America/New_York",
    "732": "America/New_York", "734": "America/New_York",
    "740": "America/New_York", "743": "America/New_York",
    "754": "America/New_York", "757": "America/New_York",
    "762": "America/New_York", "770": "America/New_York",
    "772": "America/New_York", "781": "America/New_York",
    "786": "America/New_York", "803": "America/New_York",
    "804": "America/New_York", "813": "America/New_York",
    "828": "America/New_York", "843": "America/New_York",
    "845": "America/New_York", "848": "America/New_York",
    "850": "America/New_York", "856": "America/New_York",
    "857": "America/New_York", "860": "America/New_York",
    "862": "America/New_York", "863": "America/New_York",
    "864": "America/New_York", "865": "America/New_York",
    "904": "America/New_York", "908": "America/New_York",
    "910": "America/New_York", "912": "America/New_York",
    "914": "America/New_York", "917": "America/New_York",
    "919": "America/New_York", "929": "America/New_York",
    "930": "America/New_York", "937": "America/New_York",
    "941": "America/New_York", "947": "America/New_York",
    "954": "America/New_York", "973": "America/New_York",
    "978": "America/New_York", "980": "America/New_York",
    "984": "America/New_York",
    # ── Central ───────────────────────────────────────────────────────────────
    "205": "America/Chicago",  "210": "America/Chicago",
    "214": "America/Chicago",  "217": "America/Chicago",
    "218": "America/Chicago",  "220": "America/Chicago",
    "224": "America/Chicago",  "225": "America/Chicago",
    "228": "America/Chicago",  "254": "America/Chicago",
    "256": "America/Chicago",  "262": "America/Chicago",
    "270": "America/Chicago",  "274": "America/Chicago",
    "281": "America/Chicago",  "312": "America/Chicago",
    "314": "America/Chicago",  "316": "America/Chicago",
    "318": "America/Chicago",  "319": "America/Chicago",
    "320": "America/Chicago",  "325": "America/Chicago",
    "331": "America/Chicago",  "337": "America/Chicago",
    "346": "America/Chicago",  "361": "America/Chicago",
    "380": "America/Chicago",  "382": "America/Chicago",
    "385": "America/Chicago",  "402": "America/Chicago",
    "405": "America/Chicago",  "414": "America/Chicago",
    "417": "America/Chicago",  "430": "America/Chicago",
    "432": "America/Chicago",  "464": "America/Chicago",
    "469": "America/Chicago",  "479": "America/Chicago",
    "501": "America/Chicago",  "502": "America/Chicago",
    "504": "America/Chicago",  "507": "America/Chicago",
    "512": "America/Chicago",  "515": "America/Chicago",
    "573": "America/Chicago",  "601": "America/Chicago",
    "605": "America/Chicago",  "608": "America/Chicago",
    "612": "America/Chicago",  "620": "America/Chicago",
    "630": "America/Chicago",  "636": "America/Chicago",
    "641": "America/Chicago",  "651": "America/Chicago",
    "659": "America/Chicago",  "660": "America/Chicago",
    "662": "America/Chicago",  "682": "America/Chicago",
    "701": "America/Chicago",  "712": "America/Chicago",
    "713": "America/Chicago",  "715": "America/Chicago",
    "737": "America/Chicago",  "763": "America/Chicago",
    "769": "America/Chicago",  "773": "America/Chicago",
    "785": "America/Chicago",  "815": "America/Chicago",
    "816": "America/Chicago",  "817": "America/Chicago",
    "820": "America/Chicago",  "830": "America/Chicago",
    "832": "America/Chicago",  "870": "America/Chicago",
    "872": "America/Chicago",  "901": "America/Chicago",
    "903": "America/Chicago",  "913": "America/Chicago",
    "915": "America/Chicago",  "918": "America/Chicago",
    "920": "America/Chicago",  "940": "America/Chicago",
    "952": "America/Chicago",  "956": "America/Chicago",
    "972": "America/Chicago",  "979": "America/Chicago",
    # ── Mountain ──────────────────────────────────────────────────────────────
    "303": "America/Denver",   "307": "America/Denver",
    "406": "America/Denver",   "435": "America/Denver",
    "505": "America/Denver",   "575": "America/Denver",
    "719": "America/Denver",   "720": "America/Denver",
    "801": "America/Denver",   "970": "America/Denver",
    # Mountain (no DST — Arizona)
    "480": "America/Phoenix",  "520": "America/Phoenix",
    "602": "America/Phoenix",  "623": "America/Phoenix",
    "928": "America/Phoenix",
    # ── Pacific ───────────────────────────────────────────────────────────────
    "206": "America/Los_Angeles", "209": "America/Los_Angeles",
    "213": "America/Los_Angeles", "253": "America/Los_Angeles",
    "310": "America/Los_Angeles", "323": "America/Los_Angeles",
    "360": "America/Los_Angeles", "408": "America/Los_Angeles",
    "415": "America/Los_Angeles", "424": "America/Los_Angeles",
    "425": "America/Los_Angeles", "458": "America/Los_Angeles",
    "503": "America/Los_Angeles", "509": "America/Los_Angeles",
    "510": "America/Los_Angeles", "530": "America/Los_Angeles",
    "541": "America/Los_Angeles", "559": "America/Los_Angeles",
    "562": "America/Los_Angeles", "619": "America/Los_Angeles",
    "626": "America/Los_Angeles", "628": "America/Los_Angeles",
    "650": "America/Los_Angeles", "657": "America/Los_Angeles",
    "661": "America/Los_Angeles", "669": "America/Los_Angeles",
    "702": "America/Los_Angeles", "707": "America/Los_Angeles",
    "714": "America/Los_Angeles", "725": "America/Los_Angeles",
    "747": "America/Los_Angeles", "760": "America/Los_Angeles",
    "775": "America/Los_Angeles", "805": "America/Los_Angeles",
    "818": "America/Los_Angeles", "831": "America/Los_Angeles",
    "858": "America/Los_Angeles", "909": "America/Los_Angeles",
    "916": "America/Los_Angeles", "925": "America/Los_Angeles",
    "949": "America/Los_Angeles", "951": "America/Los_Angeles",
    # ── Alaska ────────────────────────────────────────────────────────────────
    "907": "America/Anchorage",
    # ── Hawaii ────────────────────────────────────────────────────────────────
    "808": "Pacific/Honolulu",
}

_DEFAULT_ZONE = "America/New_York"


class ZoneResult(NamedTuple):
    zone:         str   # IANA time-zone string, always populated
    source:       str   # "libphonenumber" | "npa_fallback" | "default"
    ambiguous:    bool  # True when libphonenumber returned >1 zone
    review_flag:  bool  # True when zone is a guess (default fallback used)


def _easternmost(zones: list[str]) -> str:
    """Return the easternmost zone from a list using the _ZONE_RANK table.

    Zones earlier in _EAST_TO_WEST have a lower rank (more easterly).
    Falls back to the first element if none are in the table.
    """
    ranked = [(z, _ZONE_RANK.get(z, 9999)) for z in zones]
    ranked.sort(key=lambda t: t[1])
    return ranked[0][0]


def phone_to_zone(raw_phone: str) -> ZoneResult:
    """Resolve a raw phone string to a single IANA time zone.

    Never raises — always returns a usable ZoneResult.

    Args:
        raw_phone: any common phone format, e.g.  "+12125550123",
                   "212-555-0123", "(212) 555-0123", "2125550123".
                   Assumed US (+1) when no country code is present.

    Returns:
        ZoneResult(zone, source, ambiguous, review_flag)
    """
    if not raw_phone or not raw_phone.strip():
        log.warning("phone_to_zone: empty input — defaulting to %s", _DEFAULT_ZONE)
        return ZoneResult(
            zone=_DEFAULT_ZONE, source="default",
            ambiguous=False, review_flag=True,
        )

    # ── 1. libphonenumber (primary) ───────────────────────────────────────────
    try:
        import phonenumbers
        from phonenumbers import timezone as pn_tz

        # First attempt: parse with no default region (requires +country code).
        # Second attempt: assume US/NANP (+1) if the first parse fails or is invalid.
        parsed = None
        for region in (None, "US"):
            try:
                candidate = phonenumbers.parse(raw_phone, region)
                if phonenumbers.is_valid_number(candidate):
                    parsed = candidate
                    break
            except phonenumbers.NumberParseException:
                continue

        if parsed is not None:
            zones = list(pn_tz.time_zones_for_number(parsed))
            if zones:
                ambiguous = len(zones) > 1
                zone = _easternmost(zones) if ambiguous else zones[0]
                if ambiguous:
                    log.debug(
                        "phone_to_zone: %s returned zones=%s — picked easternmost %s",
                        raw_phone, zones, zone,
                    )
                return ZoneResult(
                    zone=zone, source="libphonenumber",
                    ambiguous=ambiguous, review_flag=False,
                )

            log.debug(
                "phone_to_zone: libphonenumber returned no zones for %s (valid number)",
                raw_phone,
            )
        else:
            log.debug("phone_to_zone: libphonenumber could not parse %r", raw_phone)

    except ImportError:
        log.warning(
            "phonenumbers library not installed — "
            "falling back to NPA table (run: pip install phonenumbers)"
        )
    except Exception as exc:
        log.debug("phone_to_zone: libphonenumber error for %r: %s", raw_phone, exc)

    # ── 2. NPA (area-code) fallback ───────────────────────────────────────────
    digits = re.sub(r"\D", "", raw_phone)
    # Strip NANP leading country code (1 + 10 digits = 11 total)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    npa = digits[:3] if len(digits) >= 3 else ""

    if npa and npa in _NPA_FALLBACK:
        zone = _NPA_FALLBACK[npa]
        log.debug("phone_to_zone: NPA fallback NPA=%s → %s for %r", npa, zone, raw_phone)
        return ZoneResult(
            zone=zone, source="npa_fallback",
            ambiguous=False, review_flag=False,
        )

    # ── 3. Hard default ───────────────────────────────────────────────────────
    log.warning(
        "phone_to_zone: could not resolve zone for %r (NPA=%r) — "
        "defaulting to %s and flagging for review",
        raw_phone, npa or "none", _DEFAULT_ZONE,
    )
    return ZoneResult(
        zone=_DEFAULT_ZONE, source="default",
        ambiguous=False, review_flag=True,
    )
