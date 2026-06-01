"""Small subprocess policy helpers used by CLI and repository scripts."""

from __future__ import annotations

import subprocess  # nosec B404 - this module only exposes argv-list helpers with shell disabled.
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ProcessTimeoutPolicy:
    seconds: float | None
    reason: str


def _validate_policy(policy: ProcessTimeoutPolicy) -> ProcessTimeoutPolicy:
    if policy.seconds is not None and policy.seconds <= 0:
        raise ValueError("subprocess timeout must be positive")
    if policy.seconds is None and not policy.reason.strip():
        raise ValueError("long-running subprocesses need an explicit lifecycle reason")
    return policy


def command_timeout(seconds: float, *, reason: str = "") -> ProcessTimeoutPolicy:
    return _validate_policy(ProcessTimeoutPolicy(seconds=float(seconds), reason=reason))


def long_running_process(reason: str) -> ProcessTimeoutPolicy:
    return _validate_policy(ProcessTimeoutPolicy(seconds=None, reason=reason))


def run_command(
    command: Sequence[str],
    *,
    timeout_policy: ProcessTimeoutPolicy,
    cwd: str | Path | None = None,
    check: bool = False,
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    policy = _validate_policy(timeout_policy)
    return subprocess.run(  # nosec B603 - command is an argv sequence and shell is forced off.
        list(command),
        cwd=None if cwd is None else str(cwd),
        check=check,
        shell=False,
        timeout=policy.seconds,
        **kwargs,
    )


def start_process(
    command: Sequence[str],
    *,
    timeout_policy: ProcessTimeoutPolicy,
    cwd: str | Path | None = None,
    **kwargs: Any,
) -> subprocess.Popen[Any]:
    _validate_policy(timeout_policy)
    return subprocess.Popen(  # nosec B603 - command is an argv sequence and shell is forced off.
        list(command),
        cwd=None if cwd is None else str(cwd),
        shell=False,
        **kwargs,
    )
