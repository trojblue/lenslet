from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from lenslet.processes import ProcessTimeoutPolicy, command_timeout, long_running_process, run_command, start_process


def test_run_command_passes_bounded_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(command, 0, stdout="ok")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_command(
        ["python", "--version"],
        cwd=tmp_path,
        check=True,
        timeout_policy=command_timeout(12.5, reason="unit test"),
        text=True,
    )

    assert result.returncode == 0
    assert calls == [
        {
            "command": ["python", "--version"],
            "cwd": str(tmp_path),
            "check": True,
            "shell": False,
            "timeout": 12.5,
            "text": True,
        }
    ]


def test_start_process_accepts_explicit_long_running_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    sentinel = object()

    def fake_popen(command: list[str], **kwargs: Any) -> object:
        calls.append({"command": command, **kwargs})
        return sentinel

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    process = start_process(
        ["python", "-m", "lenslet.cli"],
        timeout_policy=long_running_process("stopped by test cleanup"),
        stdout=subprocess.DEVNULL,
    )

    assert process is sentinel
    assert calls == [
        {
            "command": ["python", "-m", "lenslet.cli"],
            "cwd": None,
            "shell": False,
            "stdout": subprocess.DEVNULL,
        }
    ]


def test_timeout_policies_reject_unbounded_processes_without_lifecycle_reason() -> None:
    with pytest.raises(ValueError, match="timeout must be positive"):
        command_timeout(0)

    with pytest.raises(ValueError, match="explicit lifecycle reason"):
        long_running_process(" ")

    with pytest.raises(ValueError, match="explicit lifecycle reason"):
        start_process(["python"], timeout_policy=ProcessTimeoutPolicy(seconds=None, reason=""))
