from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import threading
import time
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any, Literal, Sequence

import httpx
from fastapi import FastAPI, Request
from PIL import Image

from lenslet.server import create_app
from lenslet.web.context import get_app_runtime, replace_app_runtime


SCHEMA_VERSION = 1
_QUERY_HEADERS = {
    "X-Lenslet-Client-Session": "thumbnail-event-loop-probe",
    "X-Lenslet-Query-Revision": "1",
}
_QUERY_BODY = {
    "path": "/",
    "recursive": True,
    "offset": 0,
    "limit": 10,
    "filters": {"and": []},
    "sort": {"kind": "builtin", "key": "name", "dir": "asc"},
}


class _InjectedSlowCache:
    def __init__(self, mode: Literal["hit", "miss"], content: bytes, delay_seconds: float) -> None:
        self.mode = mode
        self.content = content
        self.delay_seconds = delay_seconds
        self.started = threading.Event()
        self.finished = threading.Event()

    def get(self, _key: str) -> bytes | None:
        if self.mode == "miss":
            return None
        self.started.set()
        time.sleep(self.delay_seconds)
        self.finished.set()
        return self.content

    def set(self, _key: str, _content: bytes) -> bool:
        if self.mode == "hit":
            raise AssertionError("cache hit must not be persisted again")
        self.started.set()
        time.sleep(self.delay_seconds)
        self.finished.set()
        return True


def _make_images(root: Path) -> bytes:
    for name in ("hit.jpg", "miss.jpg"):
        Image.new("RGB", (32, 24), color=(20, 40, 60)).save(root / name, format="JPEG")
    buffer = BytesIO()
    Image.new("RGB", (16, 12), color=(20, 40, 60)).save(buffer, format="WEBP")
    return buffer.getvalue()


async def _wait_for_thread_event(event: threading.Event, timeout: float) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not event.is_set():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("injected thumbnail operation did not start")
        await asyncio.sleep(0.002)


async def _heartbeat(stop: asyncio.Event, gaps_ms: list[float]) -> None:
    loop = asyncio.get_running_loop()
    previous = loop.time()
    while not stop.is_set():
        await asyncio.sleep(0.005)
        now = loop.time()
        gaps_ms.append((now - previous) * 1000)
        previous = now


def _events_endpoint(app: FastAPI):
    for route in app.routes:
        if getattr(route, "path", None) == "/events":
            return route.endpoint
    raise RuntimeError("events route is not registered")


async def _read_one_sse_event(app: FastAPI) -> str:
    async def receive() -> dict[str, str]:
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}

    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/events",
            "raw_path": b"/events",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
            "root_path": "",
            "app": app,
            "state": {},
        },
        receive=receive,
    )
    response = await _events_endpoint(app)(request)
    iterator = response.body_iterator
    next_chunk = asyncio.create_task(anext(iterator))
    await asyncio.sleep(0)
    get_app_runtime(app).broker.publish(
        "presence",
        {"gallery_id": "thumbnail-probe", "viewing": 1, "editing": 0},
    )
    try:
        chunk = await asyncio.wait_for(next_chunk, timeout=0.25)
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()
    if isinstance(chunk, bytes):
        return chunk.decode("utf-8")
    return str(chunk)


async def _timed(awaitable) -> tuple[Any, float]:
    started = time.perf_counter()
    value = await awaitable
    return value, (time.perf_counter() - started) * 1000


async def _run_case(
    app: FastAPI,
    client: httpx.AsyncClient,
    *,
    mode: Literal["hit", "miss"],
    path: str,
    cache_content: bytes,
    delay_seconds: float,
    revision: int,
) -> dict[str, Any]:
    cache = _InjectedSlowCache(mode, cache_content, delay_seconds)
    runtime = get_app_runtime(app)
    replace_app_runtime(app, replace(runtime, thumb_cache=cache))
    stop_heartbeat = asyncio.Event()
    heartbeat_gaps: list[float] = []
    heartbeat = asyncio.create_task(_heartbeat(stop_heartbeat, heartbeat_gaps))
    thumbnail_started = time.perf_counter()
    thumbnail = asyncio.create_task(client.get("/thumb", params={"path": path}))
    await _wait_for_thread_event(cache.started, timeout=1)

    returned_before_persistence = False
    thumbnail_ms: float | None = None
    if mode == "miss":
        response = await asyncio.wait_for(asyncio.shield(thumbnail), timeout=0.25)
        thumbnail_ms = (time.perf_counter() - thumbnail_started) * 1000
        returned_before_persistence = not cache.finished.is_set()

    headers = {**_QUERY_HEADERS, "X-Lenslet-Query-Revision": str(revision)}
    health_task = asyncio.create_task(_timed(client.get("/health")))
    query_task = asyncio.create_task(
        _timed(client.post("/folders/query", json=_QUERY_BODY, headers=headers))
    )
    sse_task = asyncio.create_task(_timed(_read_one_sse_event(app)))
    (health, health_ms), (query, query_ms), (sse, sse_ms) = await asyncio.gather(
        health_task,
        query_task,
        sse_task,
    )
    traffic_completed_during_work = not cache.finished.is_set()
    await _wait_for_thread_event(cache.finished, timeout=delay_seconds + 1)
    if mode == "hit":
        response = await thumbnail
        thumbnail_ms = (time.perf_counter() - thumbnail_started) * 1000
    assert thumbnail_ms is not None
    stop_heartbeat.set()
    await heartbeat

    return {
        "mode": mode,
        "thumbnail_status": response.status_code,
        "thumbnail_bytes": len(response.content),
        "thumbnail_response_ms": round(thumbnail_ms, 3),
        "health_status": health.status_code,
        "health_ms": round(health_ms, 3),
        "query_status": query.status_code,
        "query_ms": round(query_ms, 3),
        "sse_delivery_ms": round(sse_ms, 3),
        "sse_event_received": "event: presence" in sse,
        "traffic_completed_during_thumbnail_work": traffic_completed_during_work,
        "thumbnail_returned_before_persistence": returned_before_persistence,
        "max_heartbeat_gap_ms": round(max(heartbeat_gaps, default=0), 3),
    }


async def _run_probe_async(root: Path, delay_seconds: float) -> dict[str, Any]:
    cache_content = _make_images(root)
    app = create_app(str(root))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        hit = await _run_case(
            app,
            client,
            mode="hit",
            path="/hit.jpg",
            cache_content=cache_content,
            delay_seconds=delay_seconds,
            revision=1,
        )
        miss = await _run_case(
            app,
            client,
            mode="miss",
            path="/miss.jpg",
            cache_content=cache_content,
            delay_seconds=delay_seconds,
            revision=2,
        )
    runtime = get_app_runtime(app)
    await runtime.query_coordinator.close()
    runtime.thumb_queue.close()
    return {
        "schema_version": SCHEMA_VERSION,
        "injected_delay_ms": round(delay_seconds * 1000, 3),
        "max_heartbeat_gap_ms": max(hit["max_heartbeat_gap_ms"], miss["max_heartbeat_gap_ms"]),
        "hit": hit,
        "miss": miss,
    }


def run_probe(*, delay_seconds: float = 0.5) -> dict[str, Any]:
    if delay_seconds <= 0:
        raise ValueError("delay_seconds must be positive")
    with tempfile.TemporaryDirectory(prefix="lenslet-thumbnail-probe-") as temp_dir:
        return asyncio.run(_run_probe_async(Path(temp_dir), delay_seconds))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure thumbnail event-loop isolation")
    parser.add_argument("--delay-ms", type=float, default=500)
    parser.add_argument("--max-heartbeat-gap-ms", type=float, default=100)
    parser.add_argument("--output-json", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_probe(delay_seconds=args.delay_ms / 1000)
    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if result["max_heartbeat_gap_ms"] > args.max_heartbeat_gap_ms:
        raise RuntimeError("thumbnail event-loop heartbeat threshold exceeded")
    for mode in ("hit", "miss"):
        case = result[mode]
        if case["thumbnail_status"] != 200 or case["health_status"] != 200:
            raise RuntimeError(f"{mode} probe returned an HTTP failure")
        if case["query_status"] != 200 or not case["sse_event_received"]:
            raise RuntimeError(f"{mode} probe delayed query or collaboration traffic")
        if not case["traffic_completed_during_thumbnail_work"]:
            raise RuntimeError(f"{mode} side traffic did not complete during thumbnail work")
    if not result["miss"]["thumbnail_returned_before_persistence"]:
        raise RuntimeError("thumbnail response waited for best-effort persistence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
