import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
from pathlib import Path
import threading
from typing import AsyncIterator

from httpx import ASGITransport, AsyncClient
from PIL import Image
import pytest

from lenslet.server import BrowseAppOptions, LocalAppOptions, create_app, create_app_from_datasets
from lenslet.web.context import get_app_context, get_app_runtime, replace_app_runtime
from lenslet.web.auth import (
    MutationPolicy,
    READ_ONLY_MUTATION_POLICY,
    mutation_denial_payload,
    trusted_local_mutation_policy,
    trusted_write_origins_for_host,
)
from lenslet.web.presence_runtime import run_presence_prune_cycle
from lenslet.web.sync.events import EventBroker
from lenslet.web.sync.presence import PresenceLeaseError, PresenceMetrics, PresenceScopeError, PresenceTracker

LOCAL_ORIGIN = "http://localhost:7070"


def _trusted_policy() -> MutationPolicy:
    return trusted_local_mutation_policy(trusted_write_origins_for_host("127.0.0.1", 7070))


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="JPEG")


def _latest_presence_for_gallery(records: list[dict], gallery_id: str) -> dict | None:
    latest = None
    for record in records:
        if record.get("event") != "presence":
            continue
        data = record.get("data") or {}
        if data.get("gallery_id") == gallery_id:
            latest = data
    return latest


class _FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.current = start

    def monotonic(self) -> float:
        return self.current

    def advance(self, delta: float) -> None:
        self.current += delta


@asynccontextmanager
async def _test_client(app) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url=LOCAL_ORIGIN,
            headers={"Origin": LOCAL_ORIGIN},
        ) as client:
            yield client


def _build_test_app(
    root: Path,
    *,
    presence_view_ttl: float = 1.0,
    presence_edit_ttl: float = 1.0,
    presence_prune_interval: float = 0.2,
):
    _make_image(root / "sample.jpg")
    return create_app(
        str(root),
        options=LocalAppOptions(
            browse=BrowseAppOptions(
                presence_view_ttl=presence_view_ttl,
                presence_edit_ttl=presence_edit_ttl,
                presence_prune_interval=presence_prune_interval,
            ),
            trusted_write_origins=(LOCAL_ORIGIN,),
        ),
    )


def test_presence_tracker_invariants_and_idempotence() -> None:
    tracker = PresenceTracker(view_ttl=30.0, edit_ttl=30.0)

    lease_1, counts = tracker.join("/animals", "client-a")
    assert lease_1
    assert any(c.gallery_id == "/animals" and c.viewing == 1 and c.editing == 0 for c in counts)

    same_lease, counts = tracker.join("/animals", "client-a", lease_id=lease_1)
    assert same_lease == lease_1
    assert any(c.gallery_id == "/animals" and c.viewing == 1 and c.editing == 0 for c in counts)

    counts = tracker.move("/animals", "/animals/cats", "client-a", lease_1)
    assert any(c.gallery_id == "/animals" and c.viewing == 0 for c in counts)
    assert any(c.gallery_id == "/animals/cats" and c.viewing == 1 for c in counts)

    replay_counts = tracker.move("/animals", "/animals/cats", "client-a", lease_1)
    assert any(c.gallery_id == "/animals/cats" and c.viewing == 1 for c in replay_counts)

    removed, leave_counts = tracker.leave("/animals/cats", "client-a", lease_1)
    assert removed is True
    assert any(c.gallery_id == "/animals/cats" and c.viewing == 0 for c in leave_counts)

    removed_again, leave_counts_again = tracker.leave("/animals/cats", "client-a", lease_1)
    assert removed_again is False
    assert any(c.gallery_id == "/animals/cats" and c.viewing == 0 for c in leave_counts_again)

    state = tracker.debug_state()
    assert "client-a" not in state["clients"]

    lease_2, _ = tracker.join("/dogs", "client-b")
    with pytest.raises(PresenceLeaseError):
        tracker.move("/dogs", "/cats", "client-b", lease_1)
    with pytest.raises(PresenceScopeError):
        tracker.move("/wrong", "/cats", "client-b", lease_2)


def test_presence_routes_use_current_runtime_after_context_swap(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path, presence_view_ttl=30.0, presence_edit_ttl=30.0)
    context = get_app_context(app)
    old_broker = context.runtime.broker
    new_broker = EventBroker(buffer_size=8)
    new_runtime = replace(
        context.runtime,
        broker=new_broker,
        presence=PresenceTracker(view_ttl=30.0, edit_ttl=30.0),
        presence_metrics=PresenceMetrics(),
    )
    replace_app_runtime(app, new_runtime)

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url=LOCAL_ORIGIN,
            headers={"Origin": LOCAL_ORIGIN},
        ) as client:
            response = await client.post("/presence/join", json={"gallery_id": "/sample.jpg"})
            assert response.status_code == 200

    asyncio.run(_run())

    assert old_broker.replay(0) == []
    records = new_broker.replay(0)
    assert _latest_presence_for_gallery(records, "/sample.jpg") == {
        "gallery_id": "/sample.jpg",
        "viewing": 1,
        "editing": 0,
    }


def test_presence_prune_loop_uses_current_runtime_after_context_swap(tmp_path: Path) -> None:
    app = _build_test_app(
        tmp_path,
        presence_view_ttl=0.08,
        presence_edit_ttl=0.08,
        presence_prune_interval=0.01,
    )
    context = get_app_context(app)
    old_broker = context.runtime.broker
    new_broker = EventBroker(buffer_size=8)
    new_runtime = replace(
        context.runtime,
        broker=new_broker,
        presence=PresenceTracker(view_ttl=0.08, edit_ttl=0.08),
        presence_metrics=PresenceMetrics(),
    )

    async def _run() -> None:
        async with _test_client(app) as client:
            replace_app_runtime(app, new_runtime)
            await asyncio.sleep(0.03)

            response = await client.post("/presence/join", json={"gallery_id": "/after-swap"})
            assert response.status_code == 200

            await asyncio.sleep(0.03)
            assert _latest_presence_for_gallery(new_broker.replay(0), "/after-swap") == {
                "gallery_id": "/after-swap",
                "viewing": 1,
                "editing": 0,
            }

            deadline = asyncio.get_running_loop().time() + 0.5
            while asyncio.get_running_loop().time() < deadline:
                if _latest_presence_for_gallery(new_broker.replay(0), "/after-swap") == {
                    "gallery_id": "/after-swap",
                    "viewing": 0,
                    "editing": 0,
                }:
                    return
                await asyncio.sleep(0.01)
            raise AssertionError("presence prune loop did not publish the post-swap stale count")

    asyncio.run(_run())

    assert old_broker.replay(0) == []
    assert _latest_presence_for_gallery(new_broker.replay(0), "/after-swap") == {
        "gallery_id": "/after-swap",
        "viewing": 0,
        "editing": 0,
    }


def test_event_broker_replay_latest_event_returns_empty_without_replay_miss() -> None:
    broker = EventBroker(buffer_size=8)
    assert broker.replay(0) == []

    first_id = broker.publish("presence", {"gallery_id": "/room", "viewing": 1, "editing": 0})
    second_id = broker.publish("presence", {"gallery_id": "/room", "viewing": 0, "editing": 0})
    assert first_id < second_id

    miss_before = broker.diagnostics()["replay_miss_total"]
    assert broker.replay(second_id) == []
    assert broker.diagnostics()["replay_miss_total"] == miss_before

    replay = broker.replay(first_id)
    assert len(replay) == 1
    assert replay[0].get("id") == second_id


async def _run_presence_lifecycle_api(app) -> None:
    async with _test_client(app) as client:
        join = await client.post("/presence/join", json={"gallery_id": "/animals"})
        assert join.status_code == 200
        join_body = join.json()
        lease_id = join_body["lease_id"]
        client_id = join_body["client_id"]
        assert join_body["gallery_id"] == "/animals"
        assert join_body["viewing"] == 1
        assert join_body["editing"] == 0

        join_retry = await client.post(
            "/presence/join",
            json={"gallery_id": "/animals", "lease_id": lease_id},
        )
        assert join_retry.status_code == 200
        assert join_retry.json()["lease_id"] == lease_id
        assert join_retry.json()["client_id"] == client_id
        assert join_retry.json()["viewing"] == 1

        moved = await client.post(
            "/presence/move",
            json={
                "from_gallery_id": "/animals",
                "to_gallery_id": "/animals/cats",
                "lease_id": lease_id,
            },
        )
        assert moved.status_code == 200
        moved_body = moved.json()
        assert moved_body["from_scope"]["gallery_id"] == "/animals"
        assert moved_body["from_scope"]["viewing"] == 0
        assert moved_body["to_scope"]["gallery_id"] == "/animals/cats"
        assert moved_body["to_scope"]["viewing"] == 1

        bad_move = await client.post(
            "/presence/move",
            json={
                "from_gallery_id": "/animals/cats",
                "to_gallery_id": "/animals/dogs",
                "lease_id": "bad-lease",
            },
        )
        assert bad_move.status_code == 409
        assert bad_move.json()["error"] == "invalid_lease"

        bad_leave = await client.post(
            "/presence/leave",
            json={"gallery_id": "/animals/cats", "lease_id": "bad-lease"},
        )
        assert bad_leave.status_code == 409
        assert bad_leave.json()["error"] == "invalid_lease"

        leave = await client.post(
            "/presence/leave",
            json={"gallery_id": "/animals/cats", "lease_id": lease_id},
        )
        assert leave.status_code == 200
        assert leave.json()["removed"] is True
        assert leave.json()["viewing"] == 0

        leave_again = await client.post(
            "/presence/leave",
            json={"gallery_id": "/animals/cats", "lease_id": lease_id},
        )
        assert leave_again.status_code == 200
        assert leave_again.json()["removed"] is False


def test_presence_lifecycle_routes(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    asyncio.run(_run_presence_lifecycle_api(app))


def _json_response_schema_ref(operation: dict, status_code: str) -> str:
    return operation["responses"][status_code]["content"]["application/json"]["schema"]["$ref"]


def test_presence_routes_publish_modeled_openapi_contracts(tmp_path: Path) -> None:
    schema = _build_test_app(tmp_path).openapi()
    paths = schema["paths"]

    join = paths["/presence/join"]["post"]
    move = paths["/presence/move"]["post"]
    leave = paths["/presence/leave"]["post"]

    assert _json_response_schema_ref(join, "200") == "#/components/schemas/PresenceSessionResponse"
    assert _json_response_schema_ref(move, "200") == "#/components/schemas/PresenceMoveResponse"
    assert _json_response_schema_ref(leave, "200") == "#/components/schemas/PresenceLeaveResponse"
    for operation in (join, move, leave):
        assert _json_response_schema_ref(operation, "403") == "#/components/schemas/ErrorResponse"
    assert "PresenceInvalidLeaseResponse" in json.dumps(join["responses"]["409"])
    assert "PresenceInvalidLeaseResponse" in json.dumps(move["responses"]["409"])
    assert "PresenceScopeMismatchResponse" in json.dumps(move["responses"]["409"])
    assert "PresenceInvalidLeaseResponse" in json.dumps(leave["responses"]["409"])
    assert "PresenceScopeMismatchResponse" in json.dumps(leave["responses"]["409"])


async def _run_read_only_presence_mutation_rejection(app) -> None:
    async with _test_client(app) as client:
        join = await client.post("/presence/join", json={"gallery_id": "/animals"})
        assert join.status_code == 403
        assert join.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)

        move = await client.post(
            "/presence/move",
            json={
                "from_gallery_id": "/animals",
                "to_gallery_id": "/animals/cats",
                "lease_id": "lease",
            },
        )
        assert move.status_code == 403
        assert move.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)

        leave = await client.post(
            "/presence/leave",
            json={"gallery_id": "/animals", "lease_id": "lease"},
        )
        assert leave.status_code == 403
        assert leave.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)


def test_presence_mutations_follow_read_only_workspace_policy(tmp_path: Path) -> None:
    app = create_app_from_datasets({"demo": [str(tmp_path / "sample.jpg")]})
    asyncio.run(_run_read_only_presence_mutation_rejection(app))


async def _run_non_local_presence_mutation_rejection(app) -> None:
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="https://public.trycloudflare.com") as client:
            join = await client.post(
                "/presence/join",
                headers={"Host": "localhost:7070"},
                json={"gallery_id": "/animals"},
            )

    assert join.status_code == 403
    assert join.json() == mutation_denial_payload(_trusted_policy())


def test_presence_mutations_follow_origin_policy(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    asyncio.run(_run_non_local_presence_mutation_rejection(app))


async def _run_idle_prune(app, *, clock: _FakeClock) -> None:
    async with _test_client(app) as client:
        join = await client.post("/presence/join", json={"gallery_id": "/idle"})
        assert join.status_code == 200
        lease_id = join.json()["lease_id"]

        runtime = get_app_runtime(app)
        previous = runtime.presence.snapshot_counts()
        clock.advance(0.45)
        run_presence_prune_cycle(runtime.presence, runtime.broker, previous)
        broker = runtime.broker
        replay = broker.replay(0)
        idle_presence = _latest_presence_for_gallery(replay, "/idle")
        assert idle_presence is not None
        assert idle_presence["viewing"] == 0
        assert idle_presence["editing"] == 0

        leave = await client.post(
            "/presence/leave",
            json={"gallery_id": "/idle", "lease_id": lease_id},
        )
        assert leave.status_code == 200
        assert leave.json()["removed"] is False

def test_presence_prune_loop_cleans_idle_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr("lenslet.web.sync.presence.time.monotonic", clock.monotonic)
    app = _build_test_app(tmp_path, presence_view_ttl=0.2, presence_edit_ttl=0.2, presence_prune_interval=0.1)
    asyncio.run(_run_idle_prune(app, clock=clock))


def test_presence_tracker_race_move_leave_touch_is_consistent() -> None:
    tracker = PresenceTracker(view_ttl=30.0, edit_ttl=30.0)
    client_id = "race-client"
    initial_scope = "/race/a"
    alt_scope = "/race/b"
    lease_id, _ = tracker.join(initial_scope, client_id)

    lease_lock = threading.Lock()
    shared_lease = {"value": lease_id}
    start = threading.Barrier(3)
    failures: list[Exception] = []

    def read_lease() -> str:
        with lease_lock:
            return shared_lease["value"]

    def write_lease(next_lease: str) -> None:
        with lease_lock:
            shared_lease["value"] = next_lease

    def mover() -> None:
        current = initial_scope
        start.wait()
        for _ in range(160):
            lease = read_lease()
            target = alt_scope if current == initial_scope else initial_scope
            try:
                tracker.move(current, target, client_id, lease)
                current = target
            except PresenceLeaseError:
                next_lease, _ = tracker.join(current, client_id)
                write_lease(next_lease)
            except PresenceScopeError as exc:
                current = exc.actual_gallery_id
            except Exception as exc:  # pragma: no cover - defensive guard in race test
                failures.append(exc)
                return

    def toucher_and_leaver() -> None:
        current = initial_scope
        start.wait()
        for i in range(160):
            lease = read_lease()
            try:
                if i % 11 == 0:
                    removed, _ = tracker.leave(current, client_id, lease)
                    if removed:
                        next_lease, _ = tracker.join(current, client_id)
                        write_lease(next_lease)
                elif i % 2 == 0:
                    _, _ = tracker.touch_view(current, client_id, lease_id=lease)
                else:
                    _, _ = tracker.touch_edit(current, client_id, lease_id=lease)
            except PresenceLeaseError:
                next_lease, _ = tracker.join(current, client_id)
                write_lease(next_lease)
            except PresenceScopeError as exc:
                current = exc.actual_gallery_id
            except Exception as exc:  # pragma: no cover - defensive guard in race test
                failures.append(exc)
                return

    t1 = threading.Thread(target=mover, daemon=True)
    t2 = threading.Thread(target=toucher_and_leaver, daemon=True)
    t1.start()
    t2.start()
    start.wait()
    t1.join()
    t2.join()

    assert not failures

    snapshot = tracker.snapshot_counts()
    for count in snapshot.values():
        assert count.viewing >= 0
        assert count.editing >= 0

    state = tracker.debug_state()
    client_state = state["clients"].get(client_id)
    if client_state is not None:
        gallery_id = client_state["gallery_id"]
        assert client_id in state["scopes"].get(gallery_id, [])

    memberships: dict[str, int] = {}
    for members in state["scopes"].values():
        for member in members:
            memberships[member] = memberships.get(member, 0) + 1
    assert all(count == 1 for count in memberships.values())


async def _run_presence_diagnostics_counters(app) -> None:
    async with _test_client(app) as client:
        join = await client.post("/presence/join", json={"gallery_id": "/diag"})
        assert join.status_code == 200
        lease_id = join.json()["lease_id"]

        bad_move = await client.post(
            "/presence/move",
            json={
                "from_gallery_id": "/diag",
                "to_gallery_id": "/diag/sub",
                "lease_id": "bad-lease",
            },
        )
        assert bad_move.status_code == 409
        assert bad_move.json()["error"] == "invalid_lease"

        broker = get_app_runtime(app).broker
        for i in range(620):
            broker.publish("item-updated", {"path": f"/bulk/{i}.jpg", "version": i + 1})
        _ = broker.replay(1)

        diag = await client.get("/presence/diagnostics")
        assert diag.status_code == 200
        payload = diag.json()
        assert payload["active_clients"] >= 1
        assert payload["active_scopes"] >= 1
        assert payload["invalid_lease_total"] >= 1
        assert payload["replay_miss_total"] >= 1
        assert payload["replay_buffer_capacity"] >= payload["replay_buffer_size"] >= 1

        health = await client.get("/health")
        assert health.status_code == 200
        health_presence = health.json().get("presence", {})
        assert health_presence.get("invalid_lease_total", 0) >= 1
        assert health_presence.get("replay_miss_total", 0) >= 1
        assert "lifecycle_v2_enabled" not in health_presence

        leave = await client.post(
            "/presence/leave",
            json={"gallery_id": "/diag", "lease_id": lease_id},
        )
        assert leave.status_code == 200


def test_presence_diagnostics_counters(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    asyncio.run(_run_presence_diagnostics_counters(app))


async def _run_presence_multi_client_convergence(app, *, clock: _FakeClock) -> None:
    async with _test_client(app) as client:
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url=LOCAL_ORIGIN,
            headers={"Origin": LOCAL_ORIGIN},
        ) as other_client:
            join_a = await client.post("/presence/join", json={"gallery_id": "/room"})
            assert join_a.status_code == 200
            lease_a_1 = join_a.json()["lease_id"]
            client_a_id = join_a.json()["client_id"]

            join_b = await other_client.post("/presence/join", json={"gallery_id": "/room"})
            assert join_b.status_code == 200
            lease_b = join_b.json()["lease_id"]
            assert join_b.json()["client_id"] != client_a_id
            assert join_b.json()["viewing"] == 2

            refresh_a = await client.post("/presence/join", json={"gallery_id": "/room"})
            assert refresh_a.status_code == 200
            lease_a_2 = refresh_a.json()["lease_id"]
            assert refresh_a.json()["client_id"] == client_a_id
            assert lease_a_2 != lease_a_1
            assert refresh_a.json()["viewing"] == 2

            move_b = await other_client.post(
                "/presence/move",
                json={
                    "from_gallery_id": "/room",
                    "to_gallery_id": "/room/sub",
                    "lease_id": lease_b,
                },
            )
            assert move_b.status_code == 200
            move_payload = move_b.json()
            assert move_payload["from_scope"]["viewing"] == 1
            assert move_payload["to_scope"]["viewing"] == 1

            reconnect_touch = await other_client.post(
                "/presence/join",
                json={"gallery_id": "/room/sub", "lease_id": lease_b},
            )
            assert reconnect_touch.status_code == 200
            assert reconnect_touch.json()["viewing"] == 1

            leave_b = await other_client.post(
                "/presence/leave",
                json={"gallery_id": "/room/sub", "lease_id": lease_b},
            )
            assert leave_b.status_code == 200
            assert leave_b.json()["removed"] is True
            assert leave_b.json()["viewing"] == 0

            runtime = get_app_runtime(app)
            previous = runtime.presence.snapshot_counts()
            clock.advance(0.55)
            run_presence_prune_cycle(runtime.presence, runtime.broker, previous)
            broker = runtime.broker
            replay = broker.replay(0)
            room_presence = _latest_presence_for_gallery(replay, "/room")
            sub_presence = _latest_presence_for_gallery(replay, "/room/sub")
            assert room_presence is not None
            assert room_presence["viewing"] == 0
            assert sub_presence is not None
            assert sub_presence["viewing"] == 0

            diagnostics = await client.get("/presence/diagnostics")
            assert diagnostics.status_code == 200
            diag_payload = diagnostics.json()
            assert diag_payload["active_clients"] == 0
            assert diag_payload["stale_pruned_total"] >= 1

def test_presence_multi_client_refresh_move_reconnect_convergence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    monkeypatch.setattr("lenslet.web.sync.presence.time.monotonic", clock.monotonic)
    app = _build_test_app(tmp_path, presence_view_ttl=0.2, presence_edit_ttl=0.2, presence_prune_interval=0.1)
    asyncio.run(_run_presence_multi_client_convergence(app, clock=clock))
