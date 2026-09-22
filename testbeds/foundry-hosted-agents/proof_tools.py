"""Side-effect-free custom script; no network, files, credentials or subprocesses."""

import hashlib
import re


def nonce_digest(nonce: str) -> dict[str, str]:
    """Return a deterministic SHA-256 proof for a 32-character hexadecimal nonce."""
    if not isinstance(nonce, str) or re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
        raise ValueError("nonce must contain exactly 32 lowercase hexadecimal characters")
    return {
        "marker": "foundry-custom-script-v1",
        "nonce": nonce,
        "sha256": hashlib.sha256(("foundry-custom-script-v1:" + nonce).encode()).hexdigest(),
    }


def nonce_statistics(nonce: str) -> dict[str, str | int]:
    """Return deterministic byte sum and population count for a hexadecimal nonce."""
    nonce_digest(nonce)
    values = bytes.fromhex(nonce)
    return {"marker": "foundry-custom-script-v2-statistics", "nonce": nonce,
            "byte_sum": sum(values), "set_bits": sum(value.bit_count() for value in values)}