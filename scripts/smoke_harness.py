from __future__ import annotations

import ipaddress
import json
import socket
import subprocess  # nosec B404 - helpers launch Lenslet with fixed argv and shell=False.
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import urlopen

from lenslet.atomic_write import atomic_write_json
from lenslet.processes import long_running_process, start_process


class SmokeFailure(RuntimeError):
    """Raised when a shared smoke harness check fails."""


@dataclass(frozen=True)
class RunningLensletServer:
    base_url: str
    log_path: Path
    process: subprocess.Popen[Any]


def choose_port(host: str, preferred: int) -> int:
    if _port_available(host, preferred):
        return preferred
    with socket.socket(_socket_family_for_host(host), socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def wait_for_health(base_url: str, timeout_seconds: float, *, request_timeout: float = 1.5) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    health_url = _require_http_url(f"{base_url}/health")
    while time.monotonic() < deadline:
        try:
            with urlopen(health_url, timeout=request_timeout) as response:  # nosec B310
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


def _require_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SmokeFailure(f"health check requires an http(s) URL, got {url!r}")
    return url


def server_base_url(host: str, port: int, *, scheme: str = "http") -> str:
    if port <= 0:
        raise SmokeFailure(f"server port must be positive, got {port}")
    normalized_scheme = scheme.lower()
    if normalized_scheme not in {"http", "https"}:
        raise SmokeFailure(f"server URL requires an http(s) scheme, got {scheme!r}")
    normalized_host = host.strip()
    if not normalized_host:
        raise SmokeFailure("server URL host cannot be empty")
    if normalized_host.startswith("[") and normalized_host.endswith("]"):
        rendered_host = normalized_host
    elif ":" in normalized_host:
        rendered_host = f"[{normalized_host}]"
    else:
        rendered_host = normalized_host
    return _require_http_url(f"{normalized_scheme}://{rendered_host}:{port}")


def import_playwright() -> tuple[type[BaseException], type[BaseException], Callable[[], Any]]:
    try:
        from playwright.sync_api import Error as playwright_error
        from playwright.sync_api import TimeoutError as playwright_timeout_error
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise SmokeFailure(
            "playwright is required: run python scripts/setup_dev.py from the repo root"
        ) from exc
    return playwright_error, playwright_timeout_error, sync_playwright


def lenslet_command(
    source_path: Path,
    *,
    host: str,
    port: int,
    extra_args: list[str] | None = None,
) -> list[str]:
    return [
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


def launch_lenslet(
    source_path: Path,
    *,
    host: str,
    port: int,
    extra_args: list[str] | None = None,
    cwd: Path | None = None,
) -> subprocess.Popen[Any]:
    command = lenslet_command(source_path, host=host, port=port, extra_args=extra_args)
    return start_process(
        command,
        timeout_policy=long_running_process("Lenslet smoke server is stopped by stop_process()."),
        cwd=None if cwd is None else str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def launch_lenslet_with_log(
    source_path: Path,
    *,
    host: str,
    port: int,
    log_path: Path,
    extra_args: list[str] | None = None,
    cwd: Path | None = None,
) -> subprocess.Popen[Any]:
    command = lenslet_command(source_path, host=host, port=port, extra_args=extra_args)
    log_handle = log_path.open("w", encoding="utf-8")
    try:
        return start_process(
            command,
            timeout_policy=long_running_process("Lenslet smoke server is stopped by stop_process()."),
            cwd=None if cwd is None else str(cwd),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
    finally:
        log_handle.close()


@contextmanager
def running_lenslet_server(
    source_path: Path,
    *,
    host: str,
    port: int,
    extra_args: list[str] | None = None,
    cwd: Path | None = None,
    log_prefix: str = "lenslet-smoke-server-",
) -> Iterator[RunningLensletServer]:
    log_file = tempfile.NamedTemporaryFile(prefix=log_prefix, suffix=".log", delete=False)
    log_path = Path(log_file.name)
    log_file.close()
    process = launch_lenslet_with_log(
        source_path,
        host=host,
        port=port,
        log_path=log_path,
        extra_args=extra_args,
        cwd=cwd,
    )
    try:
        yield RunningLensletServer(
            base_url=server_base_url(host, port),
            log_path=log_path,
            process=process,
        )
    finally:
        stop_process(process)


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


def read_log_tail(path: Path, line_count: int = 40) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return "<unavailable>"
    return "\n".join(lines[-line_count:])


def write_json_evidence(path: Path, payload: dict[str, Any], *, sort_keys: bool = True) -> None:
    atomic_write_json(path, payload, indent=2, sort_keys=sort_keys)


def _port_available(host: str, port: int) -> bool:
    with socket.socket(_socket_family_for_host(host), socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _socket_family_for_host(host: str) -> socket.AddressFamily:
    normalized = host.strip()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return socket.AF_INET
    if address.version == 6:
        return socket.AF_INET6
    return socket.AF_INET
