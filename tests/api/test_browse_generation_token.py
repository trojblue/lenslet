from __future__ import annotations

from lenslet.web.generation import build_browse_generation_token


class _TokenStorage:
    def __init__(self, signature: object = "", generation: object = "") -> None:
        self.signature = signature
        self.generation = generation

    def browse_cache_signature(self) -> object:
        return self.signature

    def browse_generation(self) -> object:
        return self.generation


class _FailingTokenStorage:
    def browse_cache_signature(self) -> str:
        raise RuntimeError("signature unavailable")

    def browse_generation(self) -> str:
        raise RuntimeError("generation unavailable")


def test_build_browse_generation_token_joins_signature_and_generation() -> None:
    storage = _TokenStorage(signature="sig", generation=3)

    assert build_browse_generation_token(storage) == "sig|3"


def test_build_browse_generation_token_uses_default_when_storage_has_no_token() -> None:
    assert build_browse_generation_token(_TokenStorage()) == "default"


def test_build_browse_generation_token_propagates_storage_failures() -> None:
    try:
        build_browse_generation_token(_FailingTokenStorage())
    except RuntimeError as exc:
        assert "signature unavailable" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("expected storage failure to propagate")
