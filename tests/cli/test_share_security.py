from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import lenslet.cli.share as cli


class _FakeProcess:
    def __init__(self) -> None:
        self.stdout = iter(())
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        _ = timeout
        return 0

    def kill(self) -> None:
        self.killed = True


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


def test_share_tunnel_runner_launch_records_owned_process(
    monkeypatch, tmp_path: Path
) -> None:
    cloudflared = tmp_path / "cloudflared"
    cloudflared.write_text("#!/bin/sh\n", encoding="utf-8")
    cloudflared.chmod(0o755)
    process = _FakeProcess()
    captured: dict[str, object] = {}

    def _fake_popen(cmd: list[str], **kwargs) -> _FakeProcess:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return process

    monkeypatch.setattr(cli, "_ensure_cloudflared_binary", lambda: cloudflared)
    monkeypatch.setattr(cli.subprocess, "Popen", _fake_popen)

    runner = cli._ShareTunnel(port=8888, bind_host="0.0.0.0", verbose=False)

    assert runner.launch() is process
    assert runner._process is process
    assert captured["cmd"] == [str(cloudflared), "tunnel", "--url", "localhost:8888"]
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["stdout"] == cli.subprocess.PIPE
    assert kwargs["stderr"] == cli.subprocess.STDOUT


def test_share_tunnel_runner_reads_cleaned_url() -> None:
    runner = cli._ShareTunnel(port=7070, bind_host="127.0.0.1", verbose=False)
    process = SimpleNamespace(
        stdout=iter(["\x1b[32mINFO https://example.trycloudflare.com).\n"])
    )

    assert runner.read_url(process) == "https://example.trycloudflare.com"


def test_share_tunnel_runner_stop_terminates_owned_process() -> None:
    runner = cli._ShareTunnel(port=7070, bind_host="127.0.0.1", verbose=False)
    process = _FakeProcess()
    runner._process = process

    runner.stop()

    assert runner._stop_event.is_set()
    assert process.terminated is True
    assert process.killed is False
