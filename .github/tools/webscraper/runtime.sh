#!/usr/bin/env bash
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-${XDG_CACHE_HOME:-$HOME/.cache}/harness/webscraper/venv}"
export WEBSCRAPER_STATE_HOME="${WEBSCRAPER_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/harness/webscraper}"
export PYTHONDONTWRITEBYTECODE=1