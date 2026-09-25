"""Parcel-quote tools: deterministic, standalone; no network, files, credentials or subprocesses."""

import math

MAX_ZONE_CODE_CHARACTERS = 32
MAX_WEIGHT_GRAMS = 30000
ZONES = {
    "Z-ALPHA": {"rate_cents_per_kg": 410, "base_fee_cents": 250},
    "Z-BRAVO": {"rate_cents_per_kg": 575, "base_fee_cents": 300},
    "Z-CHARLIE": {"rate_cents_per_kg": 690, "base_fee_cents": 180},
    "Z-DELTA": {"rate_cents_per_kg": 820, "base_fee_cents": 450},
    "Z-ECHO": {"rate_cents_per_kg": 1230, "base_fee_cents": 600},
    "Z-FOXTROT": {"rate_cents_per_kg": 355, "base_fee_cents": 900},
}


class ZoneUnknownError(LookupError):
    error_code = "E_ZONE_UNKNOWN"


class WeightLimitError(ValueError):
    error_code = "E_WEIGHT_LIMIT"


class WeightInvalidError(ValueError):
    error_code = "E_WEIGHT_INVALID"


ERROR_CODES = tuple(error.error_code for error in (ZoneUnknownError, WeightLimitError, WeightInvalidError))


def lookup_zone(zone_code: str) -> dict:
    """Rates for a destination zone code such as Z-ALPHA; unknown zones fail with E_ZONE_UNKNOWN."""
    if not isinstance(zone_code, str) or len(zone_code) > MAX_ZONE_CODE_CHARACTERS or zone_code not in ZONES:
        raise ZoneUnknownError("destination zone is not served")
    return dict(ZONES[zone_code], zone=zone_code)


def quote_parcel(weight_grams: int, rate_cents_per_kg: int, base_fee_cents: int, express: bool) -> dict:
    """Total price in cents from weight and the zone's rates; express adds 50%. Fails with E_WEIGHT_LIMIT or E_WEIGHT_INVALID."""
    if not isinstance(weight_grams, int) or isinstance(weight_grams, bool) or weight_grams <= 0:
        raise WeightInvalidError("weight_grams must be a positive integer")
    if weight_grams > MAX_WEIGHT_GRAMS:
        raise WeightLimitError(f"weight exceeds {MAX_WEIGHT_GRAMS} grams")
    half_kilograms = math.ceil(weight_grams / 500)
    total = base_fee_cents + math.ceil(rate_cents_per_kg * half_kilograms / 2)
    if express:
        total = math.ceil(total * 3 / 2)
    return {"total_cents": total, "billable_half_kilograms": half_kilograms}
