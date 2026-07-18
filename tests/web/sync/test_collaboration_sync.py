import asyncio
import threading
import time
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from PIL import Image

from lenslet.server import LocalAppOptions, create_app, create_app_from_datasets, create_app_from_table
from lenslet.web.auth import (
    MutationPolicy,
    READ_ONLY_MUTATION_POLICY,
    mutation_denial_payload,
    trusted_local_mutation_policy,
    trusted_write_origins_for_host,
)
from lenslet.web.context import get_app_context, get_app_runtime, set_app_context
import lenslet.web.routes.items as item_routes

LOCAL_ORIGIN = "http://localhost:7070"


def _trusted_policy() -> MutationPolicy:
    return trusted_local_mutation_policy(trusted_write_origins_for_host("127.0.0.1", 7070))


def _origin_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Origin": LOCAL_ORIGIN}
    if extra:
        headers.update(extra)
    return headers


def _trusted_app(root: Path):
    return create_app(str(root), options=LocalAppOptions(trusted_write_origins=(LOCAL_ORIGIN,)))


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="JPEG")


def test_patch_requires_idempotency_and_base_version(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)

    app = _trusted_app(tmp_path)

    async def _run(path: str) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url=LOCAL_ORIGIN) as client:
            resp = await client.patch(
                "/item",
                params={"path": path},
                headers=_origin_headers(),
                json={"base_version": 1},
            )
            assert resp.status_code == 400

            resp = await client.patch(
                "/item",
                params={"path": path},
                headers=_origin_headers({"Idempotency-Key": "idem-test"}),
                json={},
            )
            assert resp.status_code == 400
            body = resp.json()
            assert body.get("error") == "missing_base_version"

    asyncio.run(_run("/sample.jpg"))


def test_item_mutations_publish_modeled_openapi_contracts(tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")
    schema = _trusted_app(tmp_path).openapi()

    put_responses = schema["paths"]["/item"]["put"]["responses"]
    patch_responses = schema["paths"]["/item"]["patch"]["responses"]

    assert put_responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/Sidecar")
    assert patch_responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/SidecarMutationResponse",
    )
    assert patch_responses["409"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/SidecarConflictResponse",
    )
    assert put_responses["403"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    assert patch_responses["500"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")


def test_read_only_workspace_rejects_item_mutations(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)

    for app, path in (
        (create_app_from_datasets({"demo": [str(image_path)]}), "/demo/sample.jpg"),
        (
            create_app_from_table(
                [{"path": "/gallery/sample.jpg", "source": str(image_path)}],
            ),
            "/gallery/sample.jpg",
        ),
    ):
        client = TestClient(app)
        put_response = client.put(
            "/item",
            params={"path": path},
            json={"tags": [], "notes": "blocked", "star": 1},
        )
        assert put_response.status_code == 403
        assert put_response.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)

        patch_response = client.patch(
            "/item",
            params={"path": path},
            headers={"Idempotency-Key": "readonly"},
            json={"base_version": 1, "set_notes": "blocked"},
        )
        assert patch_response.status_code == 403
        assert patch_response.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)


def test_read_only_workspace_rejects_view_mutations(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)

    payload = {
        "version": 1,
        "views": [
            {
                "id": "demo",
                "name": "Demo",
                "pool": {"kind": "folder", "path": "/"},
                "view": {"filters": {"and": []}, "sort": {"kind": "builtin", "key": "added", "dir": "desc"}},
            }
        ],
    }

    for app in (
        create_app_from_datasets({"demo": [str(image_path)]}),
        create_app_from_table([{"path": "/gallery/sample.jpg", "source": str(image_path)}]),
    ):
        client = TestClient(app)
        response = client.put("/views", json=payload)
        assert response.status_code == 403
        assert response.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)


def test_patch_idempotency_and_conflict(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url=LOCAL_ORIGIN) as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            assert base.status_code == 200
            base_version = base.json().get("version", 1)

            headers = _origin_headers({"Idempotency-Key": "idem-1", "If-Match": str(base_version)})
            body = {"base_version": base_version, "set_notes": "hello"}
            first = await client.patch("/item", params={"path": "/sample.jpg"}, headers=headers, json=body)
            assert first.status_code == 200
            first_payload = first.json()
            assert first_payload["mutation_id"] == "idem-1"
            assert first_payload["sidecar"]["notes"] == "hello"
            assert first_payload["persistence"] == "pending"
            assert first_payload["accepted_event"]["boot_epoch"]
            assert (
                first_payload["accepted_event"]["event_id"]
                > first_payload["durable_watermark"]["event_id"]
            )

            sync_state = await client.get("/sync/state")
            assert sync_state.status_code == 200
            assert sync_state.json()["boot_epoch"] == first_payload["accepted_event"]["boot_epoch"]
            assert sync_state.json()["pending_count"] == 1

            second = await client.patch("/item", params={"path": "/sample.jpg"}, headers=headers, json=body)
            assert second.status_code == 200
            assert second.json() == first_payload

            latest = await client.get("/item", params={"path": "/sample.jpg"})
            assert latest.status_code == 200
            assert latest.json()["version"] == base_version + 1

            conflict_headers = _origin_headers({"Idempotency-Key": "idem-2", "If-Match": str(base_version)})
            conflict_body = {"base_version": base_version, "set_star": 3}
            conflict = await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers=conflict_headers,
                json=conflict_body,
            )
            assert conflict.status_code == 409
            payload = conflict.json()
            assert payload.get("error") == "version_conflict"
            assert payload["current"]["version"] == base_version + 1

    asyncio.run(_run())


def test_noop_patch_never_claims_pending_sidecar_is_saved(tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")
    app = _trusted_app(tmp_path)
    client = TestClient(app, base_url=LOCAL_ORIGIN)
    base_version = client.get("/item", params={"path": "/sample.jpg"}).json()["version"]
    first = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=_origin_headers({"Idempotency-Key": "idem-change", "If-Match": str(base_version)}),
        json={"base_version": base_version, "set_notes": "pending"},
    )
    assert first.status_code == 200

    noop = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=_origin_headers(
            {"Idempotency-Key": "idem-noop-pending", "If-Match": str(base_version + 1)}
        ),
        json={"base_version": base_version + 1, "set_notes": "pending"},
    )
    assert noop.status_code == 200
    assert noop.json().get("accepted_event") is None
    assert noop.json()["persistence"] == "pending"

    get_app_runtime(app).label_writer.flush_all()
    saved_noop = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=_origin_headers(
            {"Idempotency-Key": "idem-noop-saved", "If-Match": str(base_version + 1)}
        ),
        json={"base_version": base_version + 1, "set_notes": "pending"},
    )
    assert saved_noop.status_code == 200
    assert saved_noop.json()["persistence"] == "saved"


def test_delayed_response_cannot_overwrite_durable_idempotency_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _make_image(tmp_path / "sample.jpg")
    app = _trusted_app(tmp_path)
    with TestClient(app, base_url=LOCAL_ORIGIN) as client:
        runtime = get_app_runtime(app)
        original_publish = runtime.broker.publish_reserved
        publication_waiting = threading.Event()
        release_publication = threading.Event()

        def delayed_publish(event_id, event, data) -> None:
            if event == "item-updated":
                publication_waiting.set()
                assert release_publication.wait(timeout=2.0)
            original_publish(event_id, event, data)

        monkeypatch.setattr(runtime.broker, "publish_reserved", delayed_publish)
        base_version = client.get("/item", params={"path": "/sample.jpg"}).json()["version"]
        headers = _origin_headers(
            {"Idempotency-Key": "idem-delayed-response", "If-Match": str(base_version)}
        )
        body = {"base_version": base_version, "set_notes": "durable-before-response"}
        response: list = []
        thread = threading.Thread(
            target=lambda: response.append(
                client.patch("/item", params={"path": "/sample.jpg"}, headers=headers, json=body)
            ),
            daemon=True,
        )
        thread.start()
        assert publication_waiting.wait(timeout=1.0)
        deadline = time.monotonic() + 2.0
        while runtime.label_writer.status()["state"] != "saved" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime.label_writer.status()["state"] == "saved"
        release_publication.set()
        thread.join(timeout=1.0)
        assert response and response[0].json()["persistence"] == "pending"

        replay = client.patch(
            "/item",
            params={"path": "/sample.jpg"},
            headers=headers,
            json=body,
        )
        assert replay.status_code == 200
        assert replay.json()["persistence"] == "saved"
        assert replay.json()["durable_watermark"] == replay.json()["accepted_event"]


def test_mutation_waiting_across_context_swap_is_rejected(tmp_path: Path, monkeypatch) -> None:
    _make_image(tmp_path / "sample.jpg")
    app = _trusted_app(tmp_path)
    context = get_app_context(app)
    client = TestClient(app, base_url=LOCAL_ORIGIN)
    base_version = client.get("/item", params={"path": "/sample.jpg"}).json()["version"]
    bound = threading.Event()
    original_get_request_context = item_routes.get_request_context

    def signal_bound(request):
        request_context = original_get_request_context(request)
        bound.set()
        return request_context

    monkeypatch.setattr(item_routes, "get_request_context", signal_bound)
    response: list = []
    context.runtime.sidecar_lock.acquire()
    try:
        thread = threading.Thread(
            target=lambda: response.append(
                client.patch(
                    "/item",
                    params={"path": "/sample.jpg"},
                    headers=_origin_headers(
                        {"Idempotency-Key": "idem-stale-context", "If-Match": str(base_version)}
                    ),
                    json={"base_version": base_version, "set_notes": "must-not-commit"},
                )
            ),
            daemon=True,
        )
        thread.start()
        assert bound.wait(timeout=1.0)
        set_app_context(app, replace(context))
    finally:
        context.runtime.sidecar_lock.release()
    thread.join(timeout=1.0)

    assert response and response[0].status_code == 503
    assert response[0].json()["error"] == "application_context_changed"
    assert context.storage.get_sidecar_readonly("/sample.jpg")["notes"] == ""


def test_sse_replay_last_event_id(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url=LOCAL_ORIGIN) as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            base_version = base.json().get("version", 1)

            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers=_origin_headers({"Idempotency-Key": "idem-a", "If-Match": str(base_version)}),
                json={"base_version": base_version, "set_notes": "first"},
            )

            broker = get_app_runtime(app).broker
            replay = broker.replay(0)
            assert replay
            event1_id = replay[-1].get("id")
            assert replay[-1].get("event") == "item-updated"
            assert replay[-1]["data"]["mutation_id"] == "idem-a"
            assert replay[-1]["data"]["changed_fields"] == ["notes"]
            assert isinstance(event1_id, int)

            base2 = await client.get("/item", params={"path": "/sample.jpg"})
            base_version2 = base2.json().get("version", 1)
            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers=_origin_headers({"Idempotency-Key": "idem-b", "If-Match": str(base_version2)}),
                json={"base_version": base_version2, "set_notes": "second"},
            )

            replay2 = broker.replay(event1_id)
            assert replay2
            assert replay2[-1].get("event") == "item-updated"
            assert replay2[-1].get("id") > event1_id

    asyncio.run(_run())


def test_labels_persist_via_snapshot_and_log(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url=LOCAL_ORIGIN) as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            base_version = base.json().get("version", 1)
            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers=_origin_headers({"Idempotency-Key": "idem-persist", "If-Match": str(base_version)}),
                json={"base_version": base_version, "set_notes": "persisted", "set_star": 4},
            )

    asyncio.run(_run())
    get_app_runtime(app).label_writer.flush_all()

    snapshot_path = tmp_path / ".lenslet" / "labels.snapshot.json"
    log_path = tmp_path / ".lenslet" / "labels.log.jsonl"
    assert snapshot_path.exists()
    assert log_path.exists()

    app2 = _trusted_app(tmp_path)

    async def _verify() -> None:
        transport = ASGITransport(app=app2)
        async with AsyncClient(transport=transport, base_url=LOCAL_ORIGIN) as client:
            resp = await client.get("/item", params={"path": "/sample.jpg"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["notes"] == "persisted"
            assert payload["star"] == 4

    asyncio.run(_verify())


def test_durable_idempotency_survives_restart_with_new_boot_epoch(tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")
    app = _trusted_app(tmp_path)
    client = TestClient(app, base_url=LOCAL_ORIGIN)
    base_version = client.get("/item", params={"path": "/sample.jpg"}).json()["version"]
    headers = _origin_headers(
        {"Idempotency-Key": "idem-restart", "If-Match": str(base_version)}
    )
    body = {"base_version": base_version, "set_notes": "durable"}
    first = client.patch("/item", params={"path": "/sample.jpg"}, headers=headers, json=body)
    assert first.status_code == 200
    first_payload = first.json()
    first_epoch = first_payload["accepted_event"]["boot_epoch"]
    get_app_runtime(app).label_writer.flush_all()
    same_process_replay = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=headers,
        json=body,
    )
    assert same_process_replay.json()["persistence"] == "saved"
    durable_log = get_app_context(app).workspace.read_labels_log()

    restarted = _trusted_app(tmp_path)
    restarted_client = TestClient(restarted, base_url=LOCAL_ORIGIN)
    state = restarted_client.get("/sync/state")
    assert state.status_code == 200
    assert state.json()["boot_epoch"] != first_epoch
    replay = restarted_client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=headers,
        json=body,
    )
    assert replay.status_code == 200
    assert replay.json()["mutation_id"] == "idem-restart"
    assert replay.json()["sidecar"]["notes"] == "durable"
    assert replay.json()["persistence"] == "saved"
    assert replay.json()["durable_watermark"] == replay.json()["accepted_event"]
    assert get_app_context(restarted).workspace.read_labels_log() == durable_log


def test_graceful_shutdown_forces_pending_labels(tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")
    app = _trusted_app(tmp_path)
    with TestClient(app, base_url=LOCAL_ORIGIN) as client:
        base_version = client.get("/item", params={"path": "/sample.jpg"}).json()["version"]
        response = client.patch(
            "/item",
            params={"path": "/sample.jpg"},
            headers=_origin_headers(
                {"Idempotency-Key": "idem-shutdown", "If-Match": str(base_version)}
            ),
            json={"base_version": base_version, "set_notes": "shutdown"},
        )
        assert response.status_code == 200
        assert response.json()["persistence"] == "pending"
    workspace = get_app_context(app).workspace
    assert workspace.read_labels_log()[0]["mutation_id"] == "idem-shutdown"
    assert workspace.read_labels_snapshot()["last_event_id"] > 0


def test_blocked_writer_does_not_hold_mutation_or_broker_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _make_image(tmp_path / "sample.jpg")
    app = _trusted_app(tmp_path)
    context = get_app_context(app)
    client = TestClient(app, base_url=LOCAL_ORIGIN)
    base_version = client.get("/item", params={"path": "/sample.jpg"}).json()["version"]
    first = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=_origin_headers({"Idempotency-Key": "idem-slow-a", "If-Match": str(base_version)}),
        json={"base_version": base_version, "set_notes": "first"},
    )
    assert first.status_code == 200

    original_append = context.workspace.append_labels_log_batch
    writer_started = threading.Event()
    release_writer = threading.Event()

    def blocked_append(entries: list[dict]) -> None:
        writer_started.set()
        assert release_writer.wait(timeout=2.0)
        original_append(entries)

    monkeypatch.setattr(context.workspace, "append_labels_log_batch", blocked_append)
    flush_thread = threading.Thread(
        target=lambda: context.runtime.label_writer.flush_due(force=True),
        daemon=True,
    )
    flush_thread.start()
    assert writer_started.wait(timeout=1.0)

    started_at = time.monotonic()
    second = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=_origin_headers(
            {"Idempotency-Key": "idem-slow-b", "If-Match": str(base_version + 1)}
        ),
        json={"base_version": base_version + 1, "set_star": 3},
    )
    elapsed = time.monotonic() - started_at
    assert second.status_code == 200
    assert elapsed < 0.1
    assert context.runtime.broker.register() is not None
    assert len(context.runtime.broker.replay(0)) >= 2

    release_writer.set()
    flush_thread.join(timeout=2.0)
    context.runtime.label_writer.flush_all()


def test_label_log_append_failure_surfaces_failure_and_rejects_followup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)
    context = get_app_context(app)

    def fail_append(_entries: list[dict]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(context.workspace, "append_labels_log_batch", fail_append)
    client = TestClient(app, base_url=LOCAL_ORIGIN)
    base = client.get("/item", params={"path": "/sample.jpg"})
    assert base.status_code == 200
    base_payload = base.json()
    base_version = base_payload["version"]

    response = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=_origin_headers({"Idempotency-Key": "idem-log-failure", "If-Match": str(base_version)}),
        json={"base_version": base_version, "set_notes": "should not commit"},
    )

    assert response.status_code == 200
    assert response.json()["persistence"] == "pending"
    assert context.runtime.label_writer.flush_due(force=True) is False
    status = context.runtime.label_writer.status()
    assert status["state"] == "failed"
    assert status["pending_count"] == 1
    latest = client.get("/item", params={"path": "/sample.jpg"})
    assert latest.status_code == 200
    assert latest.json()["version"] == base_version + 1
    assert latest.json()["notes"] == "should not commit"
    followup = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=_origin_headers(
            {"Idempotency-Key": "idem-log-failure-2", "If-Match": str(base_version + 1)}
        ),
        json={"base_version": base_version + 1, "set_notes": "blocked"},
    )
    assert followup.status_code == 503
    assert followup.json()["error"] == "label_persistence_unavailable"
    failed_noop = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=_origin_headers(
            {"Idempotency-Key": "idem-log-failure-noop", "If-Match": str(base_version + 1)}
        ),
        json={"base_version": base_version + 1, "set_notes": "should not commit"},
    )
    assert failed_noop.status_code == 503
    assert failed_noop.json()["error"] == "label_persistence_unavailable"


def test_label_log_fsync_failure_keeps_pending_watermark(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)
    client = TestClient(app, base_url=LOCAL_ORIGIN)
    base = client.get("/item", params={"path": "/sample.jpg"})
    assert base.status_code == 200
    base_payload = base.json()
    base_version = base_payload["version"]

    def fail_fsync(_fd: int) -> None:
        raise OSError("disk refused sync")

    monkeypatch.setattr("lenslet.workspace.os.fsync", fail_fsync)

    response = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers=_origin_headers({"Idempotency-Key": "idem-fsync-failure", "If-Match": str(base_version)}),
        json={"base_version": base_version, "set_notes": "should not commit"},
    )

    assert response.status_code == 200
    runtime = get_app_runtime(app)
    accepted_event = response.json()["accepted_event"]
    assert runtime.label_writer.flush_due(force=True) is False
    status = runtime.label_writer.status()
    assert status["state"] == "failed"
    assert status["durable_watermark"]["event_id"] < accepted_event["event_id"]
    latest = client.get("/item", params={"path": "/sample.jpg"})
    assert latest.status_code == 200
    assert latest.json()["version"] == base_version + 1
    assert latest.json()["notes"] == "should not commit"


def test_spoofed_write_headers_do_not_control_updated_by(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)
    client = TestClient(app, base_url=LOCAL_ORIGIN)

    base = client.get("/item", params={"path": "/sample.jpg"})
    assert base.status_code == 200
    base_version = base.json()["version"]

    response = client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers={
            "Origin": LOCAL_ORIGIN,
            "Idempotency-Key": "idem-spoof",
            "If-Match": str(base_version),
            "x-client-id": "spoofed-client",
            "x-updated-by": "spoofed-user",
        },
        json={"base_version": base_version, "set_notes": "server-owned"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mutation_id"] == "idem-spoof"
    assert payload["sidecar"]["updated_by"].startswith("session:")
    assert payload["sidecar"]["updated_by"] != "spoofed-user"
    assert payload["sidecar"]["updated_by"] != "spoofed-client"


def test_non_local_origin_rejects_mutations_before_write_flow(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = _trusted_app(tmp_path)
    remote_client = TestClient(app, base_url="https://public.trycloudflare.com")

    health = remote_client.get("/health")
    assert health.status_code == 200
    assert health.json()["can_write"] is False

    patch_response = remote_client.patch(
        "/item",
        params={"path": "/sample.jpg"},
        headers={"Host": "localhost:7070"},
        json={"base_version": 1, "set_notes": "blocked"},
    )
    assert patch_response.status_code == 403
    assert patch_response.json() == mutation_denial_payload(_trusted_policy())

    view_response = remote_client.put(
        "/views",
        json={"version": 1, "views": []},
    )
    assert view_response.status_code == 403
    assert view_response.json() == mutation_denial_payload(_trusted_policy())
