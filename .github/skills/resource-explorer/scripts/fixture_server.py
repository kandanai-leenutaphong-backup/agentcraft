#!/usr/bin/env python3
"""Serve only the bundled fixture application on loopback with its principal guard enabled."""

import argparse
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "vendor/azdata/src")]

from azdata import AzureDataConfig
from resource_explorer_api.app import create_app
from resource_explorer_api.fixtures import SUBSCRIPTION
from resource_explorer_api.settings import Settings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8099)
    arguments = parser.parse_args()
    app = create_app(Settings(
        azure=AzureDataConfig(subscription_id=SUBSCRIPTION), fake_discovery=True,
        static_dir=ROOT / "frontend/dist",
    ))
    uvicorn.run(app, host="127.0.0.1", port=arguments.port)