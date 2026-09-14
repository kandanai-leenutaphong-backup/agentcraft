"""Test isolation for the SDK substitution seam.

``override`` mutates module-global state, so a test that installs a fake and
does not remove it leaks into every test that runs after it. Clearing around
each test makes ordering irrelevant and makes an absent-SDK assertion mean
what it says.
"""

from __future__ import annotations

import pytest

from azdata.core.optional import clear_overrides


@pytest.fixture(autouse=True)
def _isolate_sdk_overrides():
    clear_overrides()
    yield
    clear_overrides()
