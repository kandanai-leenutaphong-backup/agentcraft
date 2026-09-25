"""Example deterministic tools: no network, files, credentials or subprocesses. Replace or extend."""

MAX_TEXT_CHARACTERS = 4096
SI_BASE_UNITS = {"m": ("metre", "length"), "kg": ("kilogram", "mass"), "s": ("second", "time"),
                 "A": ("ampere", "electric current"), "K": ("kelvin", "thermodynamic temperature"),
                 "mol": ("mole", "amount of substance"), "cd": ("candela", "luminous intensity")}


class UnknownUnitError(LookupError):
    """Declared failure; the runtime reports `error_code` instead of the exception class name."""

    error_code = "unknown_unit"


def count_words(text: str) -> dict[str, int]:
    """Count whitespace-separated words and characters in the supplied text."""
    if not isinstance(text, str) or len(text) > MAX_TEXT_CHARACTERS:
        raise ValueError(f"text must be a string of at most {MAX_TEXT_CHARACTERS} characters")
    return {"words": len(text.split()), "characters": len(text)}


def describe_unit(symbol: str) -> dict[str, str]:
    """Name and quantity of an SI base unit symbol such as m, kg or s; other symbols fail with unknown_unit."""
    if not isinstance(symbol, str) or symbol not in SI_BASE_UNITS:
        raise UnknownUnitError("not an SI base unit symbol")
    name, quantity = SI_BASE_UNITS[symbol]
    return {"symbol": symbol, "name": name, "quantity": quantity}
