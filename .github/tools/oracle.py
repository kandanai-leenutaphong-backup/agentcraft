import json
import random
import sys


def select(candidates):
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise ValueError("Expected three candidates")
    for candidate in candidates:
        if (not isinstance(candidate, str) or not candidate.strip()
                or not candidate.isprintable() or len(candidate) > 200
                or len(candidate.split()) > 16):
            raise ValueError("Invalid candidate")
    if len({candidate.strip() for candidate in candidates}) != 3:
        raise ValueError("Candidates must be distinct")
    return random.SystemRandom().sample(candidates, 2)


def main():
    try:
        selected = select(json.load(sys.stdin))
    except (ValueError, UnicodeError, OSError, RecursionError):
        print("Oracle unavailable.", file=sys.stderr)
        return 2
    print("\n".join(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())