"""Check optional principal composition without discovering sibling skill files."""

from __future__ import annotations

import builtins
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("entra_composition", ROOT / "examples/entra_composition.py")
assert spec is not None and spec.loader is not None
composition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(composition)


def test_missing_dependency_refuses_without_path_mutation() -> None:
    original_import = builtins.__import__
    original_path = list(sys.path)

    def unavailable(name, *args, **kwargs):
        if name == "entraauth":
            raise ModuleNotFoundError("not installed", name=name)
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=unavailable):
        try:
            composition.principal_for_slug("alice")
        except ModuleNotFoundError as error:
            assert "installed in this interpreter" in str(error)
        else:
            raise AssertionError("missing optional dependency must be refused")
    assert sys.path == original_path


def test_principal_and_scope_handoff() -> None:
    peer = SimpleNamespace(Principal=SimpleNamespace, KIND_SERVICE="service", DEFAULT_SCOPE_KEY="auth_principal")
    with patch.dict(sys.modules, {"entraauth": peer}):
        principal = composition.principal_for_slug("alice")
        assert principal.id == "devkey-alice"
        assert principal.kind == "service" and principal.kind_certain is True
        assert principal.roles == () and principal.scopes == ()
        assert composition.principal_for_slug("").id == "devkey-default"
        application = object()
        with patch.object(composition, "install_signed_request_auth", return_value=False) as install:
            assert composition.install(application, public_key_b64="") is False
            install.assert_called_once_with(application, public_key_b64="",
                                            identity_factory=composition.principal_for_slug,
                                            scope_key="auth_principal")


if __name__ == "__main__":
    test_missing_dependency_refuses_without_path_mutation()
    test_principal_and_scope_handoff()
    print("signed-dev-access composition selftest: PASS")