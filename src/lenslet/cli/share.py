"""Share tunnel support for the Lenslet CLI."""

from __future__ import annotations

import os
import ipaddress
import re
import shutil
import subprocess  # nosec B404 - cloudflared is launched with a validated executable and shell=False.
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ..degraded import report_degraded_feature
from ..http_safety import http_request, open_http_url
from ..processes import long_running_process, start_process


def _ensure_cloudflared_binary() -> Path:
    configured_path = os.getenv("LENSLET_CLOUDFLARED_BIN", "").strip()
    if configured_path:
        binary_path = Path(configured_path).expanduser()
        if not binary_path.is_file():
            raise RuntimeError(
                "LENSLET_CLOUDFLARED_BIN must point to an existing cloudflared binary."
            )
        if not os.access(binary_path, os.X_OK):
            raise RuntimeError("LENSLET_CLOUDFLARED_BIN must point to an executable file.")
        return binary_path

    discovered = shutil.which("cloudflared")
    if discovered:
        return Path(discovered)

    raise RuntimeError(
        "cloudflared is required for --share. Install cloudflared and ensure it is on PATH, "
        "or set LENSLET_CLOUDFLARED_BIN to a trusted executable path."
    )


def _tunnel_target_host(bind_host: str) -> str:
    if bind_host == "localhost":
        return "localhost"
    try:
        address = ipaddress.ip_address(bind_host)
    except ValueError:
        return bind_host
    if address.is_loopback or address.is_unspecified:
        return "localhost"
    return bind_host


@dataclass(frozen=True)
class ShareTunnelOptions:
    port: int
    bind_host: str
    verbose: bool
    max_retries: int = 3
    reachable_timeout: float = 20.0


@dataclass
class _ShareTunnel:
    port: int
    bind_host: str
    verbose: bool
    max_retries: int = 3
    reachable_timeout: float = 20.0
    _ansi_escape: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"\x1b\[[0-9;]*[a-zA-Z]"),
        init=False,
    )
    _trycloudflare_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"https?://[A-Za-z0-9.-]*trycloudflare\.com\S*"),
        init=False,
    )
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    _process: subprocess.Popen[str] | None = field(default=None, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def run(self) -> None:
        try:
            last_error = "Share tunnel exited before a URL was created."
            for _attempt in range(1, self.max_retries + 1):
                if self._stop_event.is_set():
                    return
                process = self.launch()
                share_url = self.read_url(process)
                if share_url is None:
                    if process.poll() not in (None, 0):
                        print("[lenslet] Share tunnel exited before a URL was created.", file=sys.stderr)
                    _stop_process(process)
                    self._clear_process(process)
                    continue
                _print_share_url(share_url)
                if process.stdout is None:
                    raise RuntimeError("Failed to start cloudflared: no stdout pipe available.")
                drain_thread = threading.Thread(
                    target=self._drain_output,
                    args=(process.stdout,),
                    daemon=True,
                )
                drain_thread.start()
                if not self.wait_reachable(share_url):
                    print(
                        "[lenslet] Share URL not reachable within 20 seconds.",
                        file=sys.stderr,
                    )
                return
            if not self._stop_event.is_set():
                report_degraded_feature("share tunnel", detail=last_error, stream=sys.stderr)
        except Exception as exc:
            if not self._stop_event.is_set():
                report_degraded_feature(
                    "share tunnel",
                    exc,
                    detail=f"failed: {exc}",
                    stream=sys.stderr,
                )

    def launch(self) -> subprocess.Popen[str]:
        binary_path = _ensure_cloudflared_binary()
        target_host = _tunnel_target_host(self.bind_host)
        cmd = [str(binary_path), "tunnel", "--url", f"{target_host}:{self.port}"]
        process = start_process(
            cmd,
            timeout_policy=long_running_process("cloudflared tunnel is stopped by ShareTunnel.stop()."),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        with self._lock:
            self._process = process
        return process

    def read_url(self, process: subprocess.Popen[str]) -> str | None:
        if process.stdout is None:
            raise RuntimeError("Failed to start cloudflared: no stdout pipe available.")
        for raw in process.stdout:
            line = raw.rstrip()
            if self.verbose:
                print(f"[cloudflared] {line}")
            cleaned = self._ansi_escape.sub("", line)
            match = self._trycloudflare_pattern.search(cleaned)
            if match:
                return match.group(0).rstrip(").,")
        return None

    def wait_reachable(self, url: str) -> bool:
        import urllib.error
        import urllib.request

        deadline = time.monotonic() + self.reachable_timeout
        while True:
            if self._stop_event.is_set():
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            timeout = max(0.5, min(3.0, remaining))
            try:
                request = http_request(url, method="HEAD")
                with open_http_url(request, timeout=timeout):
                    return True
            except urllib.error.HTTPError:
                return True
            except Exception:
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.5)

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            process = self._process
        if process is not None:
            _stop_process(process)

    def _clear_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            if self._process is process:
                self._process = None

    def _drain_output(self, lines: Iterable[str]) -> None:
        for raw in lines:
            if self._stop_event.is_set():
                break
            if self.verbose:
                print(f"[cloudflared] {raw.rstrip()}")


def _start_share_tunnel(options: ShareTunnelOptions) -> _ShareTunnel:
    tunnel = _ShareTunnel(
        port=options.port,
        bind_host=options.bind_host,
        verbose=options.verbose,
        max_retries=options.max_retries,
        reachable_timeout=options.reachable_timeout,
    )
    tunnel.start()
    return tunnel


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _print_share_url(url: str) -> None:
    print(f"Share URL: {url}", file=sys.stderr, flush=True)
