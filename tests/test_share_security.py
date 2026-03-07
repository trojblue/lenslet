from __future__ import annotations

from pathlib import Path

import pytest

import lenslet.cli as cli


def test_ensure_cloudflared_binary_uses_explicit_env_path(monkeypatch, tmp_path: Path) -> None:
    cloudflared = tmp_path / "cloudflared"
    cloudflared.write_text("#!/bin/sh\n", encoding="utf-8")
    cloudflared.chmod(0o755)

    monkeypatch.setenv("LENSLET_CLOUDFLARED_BIN", str(cloudflared))

    assert cli._ensure_cloudflared_binary() == cloudflared


def test_ensure_cloudflared_binary_rejects_non_executable_env_path(
    monkeypatch, tmp_path: Path
) -> None:
    cloudflared = tmp_path / "cloudflared"
    cloudflared.write_text("#!/bin/sh\n", encoding="utf-8")
    cloudflared.chmod(0o644)

    monkeypatch.setenv("LENSLET_CLOUDFLARED_BIN", str(cloudflared))

    with pytest.raises(RuntimeError, match="executable"):
        cli._ensure_cloudflared_binary()


def test_ensure_cloudflared_binary_uses_path_lookup(monkeypatch, tmp_path: Path) -> None:
    cloudflared = tmp_path / "cloudflared"
    cloudflared.write_text("#!/bin/sh\n", encoding="utf-8")
    cloudflared.chmod(0o755)

    monkeypatch.delenv("LENSLET_CLOUDFLARED_BIN", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: str(cloudflared))

    assert cli._ensure_cloudflared_binary() == cloudflared

def test_ensure_cloudflared_binary_requires_trusted_binary(monkeypatch) -> None:
    monkeypatch.delenv("LENSLET_CLOUDFLARED_BIN", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeError, match="cloudflared is required"):
        cli._ensure_cloudflared_binary()
