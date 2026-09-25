"""Frozen oracle for the parcel-quote task. Evaluator-side truth; the agent's tool scripts must agree with it."""

import math

# Synthetic zone table: not public, not guessable; the agent can only learn it through its tool.
ZONES = {
    "Z-ALPHA": {"rate_cents_per_kg": 410, "base_fee_cents": 250},
    "Z-BRAVO": {"rate_cents_per_kg": 575, "base_fee_cents": 300},
    "Z-CHARLIE": {"rate_cents_per_kg": 690, "base_fee_cents": 180},
    "Z-DELTA": {"rate_cents_per_kg": 820, "base_fee_cents": 450},
    "Z-ECHO": {"rate_cents_per_kg": 1230, "base_fee_cents": 600},
    "Z-FOXTROT": {"rate_cents_per_kg": 355, "base_fee_cents": 900},
}
UNKNOWN_ZONES = ("Z-GOLF", "Z-HOTEL", "Z-OMEGA")
MAX_WEIGHT_GRAMS = 30000
ERRORS = ("E_ZONE_UNKNOWN", "E_WEIGHT_LIMIT", "E_WEIGHT_INVALID")


class QuoteError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def lookup_zone(zone_code):
    if zone_code not in ZONES:
        raise QuoteError("E_ZONE_UNKNOWN")
    return dict(ZONES[zone_code], zone=zone_code)


def quote_parcel(weight_grams, rate_cents_per_kg, base_fee_cents, express):
    if not isinstance(weight_grams, int) or isinstance(weight_grams, bool) or weight_grams <= 0:
        raise QuoteError("E_WEIGHT_INVALID")
    if weight_grams > MAX_WEIGHT_GRAMS:
        raise QuoteError("E_WEIGHT_LIMIT")
    half_kilograms = math.ceil(weight_grams / 500)
    total = base_fee_cents + math.ceil(rate_cents_per_kg * half_kilograms / 2)
    if express:
        total = math.ceil(total * 3 / 2)
    return {"total_cents": total, "billable_half_kilograms": half_kilograms}


def expected_answer(zone_code, weight_grams, express):
    """Exact final answer the agent must emit: `TOTAL_CENTS=<int>` or `ERROR=<code>`."""
    try:
        zone = lookup_zone(zone_code)
        quote = quote_parcel(weight_grams, zone["rate_cents_per_kg"], zone["base_fee_cents"], express)
    except QuoteError as error:
        return f"ERROR={error.code}"
    return f"TOTAL_CENTS={quote['total_cents']}"


def expected_tools(zone_code):
    return ["lookup_zone"] if zone_code not in ZONES else ["lookup_zone", "quote_parcel"]
