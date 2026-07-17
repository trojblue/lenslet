from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import TableAppOptions, create_app_from_table
from lenslet.web.hotpath import HotpathTelemetry, HotpathTimingMiddleware
from lenslet.workspace import Workspace


def _timing_names(response) -> set[str]:
    header = response.headers.get("server-timing", "")
    return {part.strip().split(";", 1)[0] for part in header.split(",") if part.strip()}


def _table_client(tmp_path: Path, *, writable: bool = False) -> TestClient:
    source = tmp_path / "shared.jpg"
    Image.new("RGB", (12, 8), color=(30, 60, 90)).save(source, format="JPEG")
    workspace = (
        Workspace.for_dataset(str(tmp_path), can_write=True)
        if writable
        else Workspace.for_dataset(None, can_write=False)
    )
    app = create_app_from_table(
        [
            {
                "image_path": "shared.jpg",
                "path": "gallery/item.jpg",
                "metric_a": 0.5,
                "category": "sample",
            }
        ],
        options=TableAppOptions(
            base_dir=str(tmp_path),
            source_column="image_path",
            skip_dimension_probe=True,
            workspace=workspace,
            trusted_write_origins=("http://testserver",) if writable else (),
        ),
    )
    return TestClient(app, headers={
        "X-Lenslet-Client-Session": "request-timing-tests",
        "X-Lenslet-Query-Revision": "1",
    })


def test_query_and_facet_routes_emit_named_server_timing_and_health_counts(
    tmp_path: Path,
) -> None:
    body = {
        "path": "/gallery",
        "recursive": True,
        "offset": 0,
        "limit": 1,
        "filters": {"and": [{"metricRange": {"key": "metric_a", "min": 0, "max": 1}}]},
        "sort": {"kind": "builtin", "key": "name", "dir": "asc"},
    }
    with _table_client(tmp_path) as client:
        query = client.post("/folders/query", json=body)
        facets = client.post("/folders/facets", json=body)

        assert query.status_code == 200
        assert {"queue", "analysis", "ordering", "projection", "serialize"} <= _timing_names(query)
        assert facets.status_code == 200
        facet_timings = _timing_names(facets)
        assert {"queue", "analysis", "facet", "serialize"} <= facet_timings
        assert "ordering" not in facet_timings
        assert "projection" not in facet_timings

        counters = client.get("/health").json()["hotpath"]["counters"]
        assert counters["analysis_started_total"] == 2
        assert counters["analysis_completed_total"] == 2


def test_thumbnail_and_mutation_routes_emit_work_phase_timing(tmp_path: Path) -> None:
    with _table_client(tmp_path, writable=True) as client:
        thumbnail = client.get("/thumb", params={"path": "/gallery/item.jpg"})
        mutation = client.patch(
            "/item",
            params={"path": "/gallery/item.jpg"},
            json={"base_version": 1, "set_star": 1},
            headers={
                "Idempotency-Key": "timing-mutation-1",
                "Origin": "http://testserver",
            },
        )

    assert thumbnail.status_code == 200
    assert "thumbnail" in _timing_names(thumbnail)
    assert mutation.status_code == 200
    assert {"mutation", "writer"} <= _timing_names(mutation)


def test_analysis_outcomes_have_distinct_bounded_counter_keys() -> None:
    metrics = HotpathTelemetry()
    for event in ("started", "completed", "joined", "superseded", "cancelled"):
        metrics.record_analysis(event)

    assert metrics.snapshot().counters == {
        "analysis_started_total": 1,
        "analysis_completed_total": 1,
        "analysis_joined_total": 1,
        "analysis_superseded_total": 1,
        "analysis_cancelled_total": 1,
    }


def test_http_terminal_outcomes_are_mutually_exclusive_after_response_start() -> None:
    scope = {"type": "http"}

    async def receive():
        return {"type": "http.disconnect"}

    async def send(_message):
        return None

    async def completed_app(_scope, _receive, app_send):
        await app_send({"type": "http.response.start", "status": 200, "headers": []})
        await app_send({"type": "http.response.body", "body": b"ok"})

    completed_metrics = HotpathTelemetry()
    asyncio.run(HotpathTimingMiddleware(completed_app, completed_metrics)(scope, receive, send))
    assert completed_metrics.snapshot().counters == {"http_request_completed_total": 1}

    async def failed_app(_scope, _receive, app_send):
        await app_send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("late response failure")

    failed_metrics = HotpathTelemetry()
    with pytest.raises(RuntimeError, match="late response failure"):
        asyncio.run(HotpathTimingMiddleware(failed_app, failed_metrics)(scope, receive, send))
    assert failed_metrics.snapshot().counters == {"http_request_failed_total": 1}

    async def abandoned_app(_scope, _receive, app_send):
        await app_send({"type": "http.response.start", "status": 200, "headers": []})
        raise asyncio.CancelledError

    abandoned_metrics = HotpathTelemetry()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(HotpathTimingMiddleware(abandoned_app, abandoned_metrics)(scope, receive, send))
    assert abandoned_metrics.snapshot().counters == {"http_request_abandoned_total": 1}
