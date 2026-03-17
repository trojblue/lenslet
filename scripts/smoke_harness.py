from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen


class SmokeFailure(RuntimeError):
    """Raised when a shared smoke harness check fails."""


def choose_port(host: str, preferred: int) -> int:
    if _port_available(host, preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def wait_for_health(base_url: str, timeout_seconds: float, *, request_timeout: float = 1.5) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=request_timeout) as response:
                if response.status != 200:
                    raise SmokeFailure(f"unexpected /health status: {response.status}")
                payload = json.load(response)
                if not isinstance(payload, dict):
                    raise SmokeFailure("unexpected /health payload")
                return payload
        except URLError as exc:
            last_error = exc
        except TimeoutError as exc:  # pragma: no cover - runtime guard
            last_error = exc
        time.sleep(0.2)
    raise SmokeFailure(f"/health unavailable after {timeout_seconds:.1f}s: {last_error!r}")


def import_playwright() -> tuple[type[BaseException], type[BaseException], Callable[[], Any]]:
    try:
        from playwright.sync_api import Error as playwright_error
        from playwright.sync_api import TimeoutError as playwright_timeout_error
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise SmokeFailure(
            "playwright is required: pip install -e '.[dev]' && python -m playwright install chromium"
        ) from exc
    return playwright_error, playwright_timeout_error, sync_playwright


def launch_lenslet(
    source_path: Path,
    *,
    host: str,
    port: int,
    extra_args: list[str] | None = None,
    cwd: Path | None = None,
) -> subprocess.Popen[Any]:
    command = [
        sys.executable,
        "-m",
        "lenslet.cli",
        str(source_path),
        "--host",
        host,
        "--port",
        str(port),
        *(extra_args or []),
    ]
    return subprocess.Popen(
        command,
        cwd=None if cwd is None else str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_process(
    process: subprocess.Popen[Any],
    *,
    terminate_timeout_seconds: float = 10.0,
    kill_timeout_seconds: float = 5.0,
) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=terminate_timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=kill_timeout_seconds)


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True
