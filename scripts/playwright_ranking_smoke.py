#!/usr/bin/env python3
"""Playwright smoke test for Lenslet ranking mode.

This probe covers the MVP ranking operator flow:
1. Launch ranking mode against a tiny local fixture dataset.
2. Complete first instance via keyboard rank assignment (autosave path).
3. Verify navigation guards (`Next` disabled until complete).
4. Partially rank second instance, reload, and verify resume hydration.
5. Confirm `completed_only` export collapse behavior.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image


class SmokeFailure(RuntimeError):
    """Raised when ranking smoke assertions fail."""


@dataclass(frozen=True)
class SmokeResult:
    dataset_json: str
    results_path: str
    resumed_instance_position: int
    total_instances: int
    resumed_unranked_count: int
    completed_only_export_count: int
    save_line_count: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ranking-mode browser smoke checks.")
    parser.add_argument(
        "--dataset-json",
        type=Path,
        default=None,
        help="Optional existing ranking dataset JSON path.",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=None,
        help="Optional fixture directory when auto-generating a dataset.",
    )
    parser.add_argument(
        "--keep-fixture",
        action="store_true",
        help="Keep generated fixture directory after the run.",
    )
    parser.add_argument(
        "--results-path",
        type=Path,
        default=None,
        help="Optional results JSONL path passed to `lenslet rank`.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Lenslet host bind (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=7071, help="Preferred Lenslet port (default: 7071).")
    parser.add_argument(
        "--server-timeout-seconds",
        type=float,
        default=60.0,
        help="Timeout waiting for /health to become reachable.",
    )
    parser.add_argument(
        "--browser-timeout-ms",
        type=float,
        default=45_000.0,
        help="Playwright default timeout in milliseconds.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional file path for machine-readable smoke output.",
    )
    return parser.parse_args(argv)


def _build_jpeg_payload() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 48), color=(42, 96, 150)).save(buffer, format="JPEG", quality=84)
    return buffer.getvalue()


def build_fixture_dataset(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    image_dir = root / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    payload = _build_jpeg_payload()
    image_names = [
        "a1.jpg",
        "a2.jpg",
        "a3.jpg",
        "b1.jpg",
        "b2.jpg",
        "b3.jpg",
    ]
    for name in image_names:
        (image_dir / name).write_bytes(payload)

    dataset = [
        {
            "instance_id": "one",
            "images": ["images/a1.jpg", "images/a2.jpg", "images/a3.jpg"],
        },
        {
            "instance_id": "two",
            "images": ["images/b1.jpg", "images/b2.jpg", "images/b3.jpg"],
        },
    ]
    dataset_json = root / "ranking_dataset.json"
    dataset_json.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    return dataset_json


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def choose_port(host: str, preferred: int) -> int:
    if _port_available(host, preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def fetch_json(url: str, timeout: float = 2.0) -> dict[str, Any]:
    with urlopen(url, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise SmokeFailure(f"expected JSON object from {url}")
    return payload


def wait_for_health(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            payload = fetch_json(f"{base_url}/health", timeout=2.0)
            if payload.get("mode") != "ranking":
                raise SmokeFailure(f"unexpected /health mode: {payload.get('mode')!r}")
            return payload
        except URLError as exc:
            last_error = exc
        except TimeoutError as exc:  # pragma: no cover - defensive runtime guard
            last_error = exc
        time.sleep(0.2)
    raise SmokeFailure(f"/health unavailable after {timeout_seconds:.1f}s: {last_error!r}")


def health_results_path(health_payload: dict[str, Any]) -> Path:
    raw_value = health_payload.get("results_path")
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise SmokeFailure("/health did not report a results_path")
    return Path(raw_value).expanduser().resolve()


def parse_instance_position(label: str) -> tuple[int, int]:
    tokens = [part.strip() for part in label.split("/")]
    if len(tokens) != 2:
        raise SmokeFailure(f"invalid instance position label: {label!r}")
    try:
        current = int(tokens[0])
        total = int(tokens[1])
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise SmokeFailure(f"invalid instance position label: {label!r}") from exc
    if current < 1 or total < 1:
        raise SmokeFailure(f"invalid instance position values: {label!r}")
    return current, total


def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise SmokeFailure(
            "playwright is required: pip install -e '.[dev]' && python -m playwright install chromium"
        ) from exc
    return sync_playwright


def _wait_for_saved_state(page, timeout_ms: float) -> None:
    page.wait_for_function(
        """() => {
          const el = document.querySelector('.ranking-save-status');
          const text = (el?.textContent || '').trim();
          return text.startsWith('Saved');
        }""",
        timeout=max(1, int(timeout_ms)),
    )


def _rank_all_unranked_to_first_column(page) -> None:
    unranked = page.locator('.ranking-column').first
    while True:
        count = unranked.locator('.ranking-card').count()
        if count <= 0:
            break
        unranked.locator('.ranking-card').first.click()
        page.keyboard.press('1')
        page.wait_for_timeout(120)


def run_browser_probe(base_url: str, browser_timeout_ms: float) -> tuple[int, int, int]:
    sync_playwright = _import_playwright()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1520, "height": 940})
        page = context.new_page()
        page.set_default_timeout(browser_timeout_ms)

        page.goto(base_url, wait_until="domcontentloaded")
        page.locator('.ranking-root').first.wait_for(state='visible')

        next_button = page.get_by_role('button', name='Next')
        if not next_button.is_disabled():
            raise SmokeFailure("`Next` should be disabled before first instance is complete")

        _rank_all_unranked_to_first_column(page)
        _wait_for_saved_state(page, browser_timeout_ms)
        if next_button.is_disabled():
            raise SmokeFailure("`Next` should be enabled after first instance completion")

        page.keyboard.press('Enter')
        page.wait_for_function(
            """() => {
              const label = document.querySelector('.ranking-meta strong')?.textContent || '';
              return label.trim().startsWith('2 /');
            }""",
            timeout=max(1, int(browser_timeout_ms)),
        )

        if not next_button.is_disabled():
            raise SmokeFailure("`Next` should be disabled on second instance before completion")

        unranked = page.locator('.ranking-column').first
        initial_unranked = unranked.locator('.ranking-card').count()
        if initial_unranked <= 0:
            raise SmokeFailure("second instance unexpectedly has no unranked cards")
        unranked.locator('.ranking-card').first.click()
        page.keyboard.press('1')
        _wait_for_saved_state(page, browser_timeout_ms)
        remaining_unranked = unranked.locator('.ranking-card').count()
        if remaining_unranked != initial_unranked - 1:
            raise SmokeFailure(
                f"unexpected unranked card count after partial rank: {remaining_unranked}"
            )

        page.reload(wait_until='domcontentloaded')
        page.locator('.ranking-root').first.wait_for(state='visible')
        position_text = page.locator('.ranking-meta strong').first.inner_text().strip()
        position, total = parse_instance_position(position_text)
        if position != 2:
            raise SmokeFailure(f"expected resume to land on instance 2, got {position_text!r}")

        resumed_unranked = page.locator('.ranking-column').first.locator('.ranking-card').count()
        if resumed_unranked != remaining_unranked:
            raise SmokeFailure(
                "partial autosave did not resume expected unranked count: "
                f"expected {remaining_unranked}, got {resumed_unranked}"
            )

        page.keyboard.press('Backspace')
        page.wait_for_function(
            """() => {
              const label = document.querySelector('.ranking-meta strong')?.textContent || '';
              return label.trim().startsWith('1 /');
            }""",
            timeout=max(1, int(browser_timeout_ms)),
        )

        context.close()
        browser.close()
        return position, total, resumed_unranked


def _count_non_empty_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open('r', encoding='utf-8') as handle:
        return sum(1 for line in handle if line.strip())


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    fixture_root: Path | None = None
    created_temp = False
    try:
        if args.dataset_json is not None:
            dataset_json = args.dataset_json.expanduser().resolve()
            if not dataset_json.exists() or not dataset_json.is_file():
                print(f"[ranking-smoke:error] dataset JSON not found: {dataset_json}")
                return 1
        else:
            if args.fixture_dir is not None:
                fixture_root = args.fixture_dir.expanduser().resolve()
                fixture_root.mkdir(parents=True, exist_ok=True)
            else:
                fixture_root = Path(tempfile.mkdtemp(prefix='lenslet-ranking-smoke-'))
                created_temp = True
            dataset_json = build_fixture_dataset(fixture_root)

        port = choose_port(args.host, args.port)
        base_url = f"http://{args.host}:{port}"
        command = [
            sys.executable,
            '-m',
            'lenslet.cli',
            'rank',
            str(dataset_json),
            '--host',
            args.host,
            '--port',
            str(port),
        ]
        if args.results_path is not None:
            command.extend(['--results-path', str(args.results_path)])

        print(f"[ranking-smoke] starting lenslet: {' '.join(command)}")
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        try:
            health = wait_for_health(base_url, args.server_timeout_seconds)
            results_path = health_results_path(health)

            resumed_position, total_instances, resumed_unranked = run_browser_probe(
                base_url=base_url,
                browser_timeout_ms=args.browser_timeout_ms,
            )

            completed_export = fetch_json(f"{base_url}/rank/export?completed_only=true", timeout=5.0)
            completed_count = int(completed_export.get('count', 0))
            if completed_count != 1:
                raise SmokeFailure(
                    f"expected completed-only export count=1 after probe, got {completed_count}"
                )

            save_line_count = _count_non_empty_lines(results_path)
            if save_line_count < 2:
                raise SmokeFailure(
                    f"expected at least 2 save lines in results log, got {save_line_count}"
                )

            result = SmokeResult(
                dataset_json=str(dataset_json),
                results_path=str(results_path),
                resumed_instance_position=resumed_position,
                total_instances=total_instances,
                resumed_unranked_count=resumed_unranked,
                completed_only_export_count=completed_count,
                save_line_count=save_line_count,
            )
            print(
                "[ranking-smoke] pass: "
                f"resume={result.resumed_instance_position}/{result.total_instances}, "
                f"resumed_unranked={result.resumed_unranked_count}, "
                f"completed_only={result.completed_only_export_count}, "
                f"save_lines={result.save_line_count}"
            )

            if args.output_json is not None:
                args.output_json.parent.mkdir(parents=True, exist_ok=True)
                args.output_json.write_text(json.dumps(asdict(result), indent=2), encoding='utf-8')
                print(f"[ranking-smoke] wrote summary: {args.output_json}")
            return 0
        except SmokeFailure as exc:
            print(f"[ranking-smoke:error] {exc}")
            return 1
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    finally:
        if created_temp and fixture_root is not None and fixture_root.exists() and not args.keep_fixture:
            shutil.rmtree(fixture_root, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
