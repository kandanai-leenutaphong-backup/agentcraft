"""Foundry invocations 2.0 entry point; the platform owns authenticated ingress."""

from pathlib import Path

from hostedagents.application import serve


if __name__ == "__main__":
    serve(Path(__file__).resolve().parent)