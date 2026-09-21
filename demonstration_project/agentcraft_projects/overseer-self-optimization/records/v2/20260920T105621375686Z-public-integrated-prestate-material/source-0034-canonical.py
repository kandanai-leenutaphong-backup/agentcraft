"""Deterministic canonicalization for ontology keys.

Every function here is a *projection*, not an identity claim. Where a projection could
merge two genuinely distinct objects the caller must record the original values and
express the merge as a candidate rather than as equality.
"""

from __future__ import annotations

import ipaddress
import json
import re

#: Values the export uses to mean "no value". Treated as absent everywhere.
NULLISH = frozenset({"", "-", "'-", "UNSET", "NULL", "null", "none", "None", "N/A", "n/a"})

_DOLLAR = re.compile(r"\$$")
_SID = re.compile(r"^S-1-5-21-\d+-\d+-\d+-\d+$")


def clean(value: str | None) -> str:
    """Strip a raw cell and collapse the export's null sentinels to an empty string."""
    text = (value or "").strip().strip('"')
    return "" if text in NULLISH else text


def parse_identity_blob(value: str | None) -> dict[str, str]:
    """Unpack the export's JSON identity object; return empty parts when unusable."""
    text = clean(value)
    if not text.startswith("{"):
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {key: clean(str(parsed.get(key, ""))) for key in ("domain", "name", "original_name", "uid")}


def short_host(value: str | None) -> str:
    """Project a hostname to its first label, upper-cased.

    FQDN and short-name forms of the same string collapse here. That is a heuristic the
    ontology notes flag as non-authoritative, so callers keep every observed spelling.
    """
    text = clean(value)
    if text.startswith("{"):
        text = parse_identity_blob(text).get("name", "")
    if not text or _is_address(text):
        return ""
    return text.split(".", 1)[0].upper()


def host_parts(value: str | None) -> tuple[str, str]:
    """Return (short label, domain) from a host field that may be a JSON object.

    The export ships ``target_host`` as ``{"domain":..,"name":..,"original_name":..}``,
    which states the host's domain directly rather than leaving it to a suffix guess.
    """
    text = clean(value)
    if text.startswith("{"):
        parsed = parse_identity_blob(text)
        name = parsed.get("name", "") or parsed.get("original_name", "")
        domain = parsed.get("domain", "")
        if not domain and "." in name:
            domain = name.partition(".")[2]
        return short_host(name), domain.upper()
    return short_host(text), (text.partition(".")[2].upper() if "." in text else "")


def account_key(name: str, domain: str = "") -> str:
    """Key an account by base name, ignoring UPN realm and casing.

    ``SVPMN082$`` and ``SVPMN082$@WAC.COM.AU`` key together; the realm is retained as an
    observed domain on the node rather than being discarded.
    """
    base = clean(name)
    if "@" in base:
        base, _, realm = base.partition("@")
        domain = domain or realm
    if "\\" in base:
        _, _, base = base.partition("\\")
    return base.casefold()


def account_realm(name: str, domain: str = "") -> str:
    text = clean(name)
    realm = text.partition("@")[2] if "@" in text else ""
    return (clean(domain) or realm).upper()


def looks_like_machine_account(name: str) -> bool:
    """Dollar-suffixed accounts *may* be machine accounts; the export proves it separately."""
    return bool(_DOLLAR.search(clean(name)))


def is_sid(value: str | None) -> bool:
    return bool(_SID.match(clean(value)))


def _is_address(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def address_key(value: str | None) -> str:
    text = clean(value)
    if not text:
        return ""
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return ""


def address_scope(value: str) -> str:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return "unknown"
    if parsed.is_private:
        return "private"
    if parsed.is_loopback or parsed.is_link_local or parsed.is_multicast:
        return "special"
    return "public"


def dns_key(value: str | None) -> str:
    text = clean(value).rstrip(".")
    return text.casefold() if text else ""


def registrable_suffix(name: str) -> str:
    """Last two labels of a DNS name. A cheap stand-in for a public-suffix lookup."""
    parts = [part for part in name.split(".") if part]
    return ".".join(parts[-2:]) if len(parts) >= 2 else name


def is_reverse_lookup(name: str) -> bool:
    return name.endswith(".in-addr.arpa") or name.endswith(".ip6.arpa")


def slug(*parts: str) -> str:
    """Build a stable, Gremlin-safe vertex id from already-canonical parts."""
    joined = "|".join(part for part in parts if part)
    return re.sub(r"[^A-Za-z0-9._|:$-]", "_", joined)[:180]


#: Event edges carry per-bucket counts so an arbitrary window can be scored without
#: re-reading the export. Fifteen minutes keeps a 33-hour export under 132 buckets.
BUCKET_MINUTES = 15


def bucket_key(source_time: str | None) -> str:
    """Floor an ISO timestamp to its 15-minute bucket, as ``YYYY-MM-DDTHH:MM``."""
    text = clean(source_time)
    if len(text) < 16 or text[10] != "T":
        return ""
    try:
        minute = int(text[14:16])
    except ValueError:
        return ""
    return f"{text[:14]}{minute - minute % BUCKET_MINUTES:02d}"


def buckets_in_window(buckets: dict[str, int], start: str, end: str) -> int:
    """Sum the buckets whose start falls inside [start, end).

    A bucket is attributed to its own start, so a window boundary mid-bucket includes the
    whole bucket. The frontend states the resolution rather than implying second accuracy.
    """
    if not start and not end:
        return sum(buckets.values())
    lower = bucket_key(start) if start else ""
    upper = end[:16] if end else ""
    return sum(count for key, count in buckets.items()
               if (not lower or key >= lower) and (not upper or key <= upper))
