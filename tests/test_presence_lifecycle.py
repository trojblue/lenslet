import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import threading
from typing import AsyncIterator

from httpx import ASGITransport, AsyncClient
from PIL import Image
import pytest

from lenslet.server import create_app
from lenslet.server_sync import PresenceLeaseError, PresenceScopeError, PresenceTracker


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


@asynccontextmanager
async def _test_client(app) -> AsyncIterator[AsyncClient]:
    await app.router.startup()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        await app.router.shutdown()


def _build_test_app(
    root: Path,
    *,
    presence_view_ttl: float = 1.0,
    presence_edit_ttl: float = 1.0,
    presence_prune_interval: float = 0.2,
    presence_lifecycle_v2: bool = True,
):
    _make_image(root / "sample.jpg")
    return create_app(
        str(root),
        presence_view_ttl=presence_view_ttl,
        presence_edit_ttl=presence_edit_ttl,
        presence_prune_interval=presence_prune_interval,
        presence_lifecycle_v2=presence_lifecycle_v2,
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


async def _run_presence_lifecycle_api(app) -> None:
    async with _test_client(app) as client:
        join = await client.post("/presence/join", json={"gallery_id": "/animals", "client_id": "tab-1"})
        assert join.status_code == 200
        join_body = join.json()
        lease_id = join_body["lease_id"]
        assert join_body["gallery_id"] == "/animals"
        assert join_body["viewing"] == 1
        assert join_body["editing"] == 0

        join_retry = await client.post(
            "/presence/join",
            json={"gallery_id": "/animals", "client_id": "tab-1", "lease_id": lease_id},
        )
        assert join_retry.status_code == 200
        assert join_retry.json()["lease_id"] == lease_id
        assert join_retry.json()["viewing"] == 1

        moved = await client.post(
            "/presence/move",
            json={
                "from_gallery_id": "/animals",
                "to_gallery_id": "/animals/cats",
                "client_id": "tab-1",
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
                "client_id": "tab-1",
                "lease_id": "bad-lease",
            },
        )
        assert bad_move.status_code == 409
        assert bad_move.json()["error"] == "invalid_lease"

        bad_leave = await client.post(
            "/presence/leave",
            json={"gallery_id": "/animals/cats", "client_id": "tab-1", "lease_id": "bad-lease"},
        )
        assert bad_leave.status_code == 409
        assert bad_leave.json()["error"] == "invalid_lease"

        leave = await client.post(
            "/presence/leave",
            json={"gallery_id": "/animals/cats", "client_id": "tab-1", "lease_id": lease_id},
        )
        assert leave.status_code == 200
        assert leave.json()["removed"] is True
        assert leave.json()["viewing"] == 0

        leave_again = await client.post(
            "/presence/leave",
            json={"gallery_id": "/animals/cats", "client_id": "tab-1", "lease_id": lease_id},
        )
        assert leave_again.status_code == 200
        assert leave_again.json()["removed"] is False


def test_presence_lifecycle_routes(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    asyncio.run(_run_presence_lifecycle_api(app))


async def _run_legacy_presence_compatibility(app) -> None:
    async with _test_client(app) as client:
        hb_1 = await client.post("/presence", json={"gallery_id": "/a", "client_id": "legacy-tab"})
        assert hb_1.status_code == 200
        lease_id = hb_1.json()["lease_id"]
        assert hb_1.json()["viewing"] == 1

        hb_2 = await client.post(
            "/presence",
            json={"gallery_id": "/b", "client_id": "legacy-tab", "lease_id": lease_id},
        )
        assert hb_2.status_code == 200
        assert hb_2.json()["gallery_id"] == "/b"
        assert hb_2.json()["viewing"] == 1

        hb_bad = await client.post(
            "/presence",
            json={"gallery_id": "/b", "client_id": "legacy-tab", "lease_id": "invalid"},
        )
        assert hb_bad.status_code == 409
        assert hb_bad.json()["error"] == "invalid_lease"

        broker = app.state.sync_broker
        replay = broker.replay(0)
        a_presence = _latest_presence_for_gallery(replay, "/a")
        b_presence = _latest_presence_for_gallery(replay, "/b")
        assert a_presence is not None
        assert a_presence["viewing"] == 0
        assert b_presence is not None
        assert b_presence["viewing"] == 1


def test_legacy_presence_heartbeat_compatibility(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    asyncio.run(_run_legacy_presence_compatibility(app))


async def _run_idle_prune(app) -> None:
    async with _test_client(app) as client:
        join = await client.post("/presence/join", json={"gallery_id": "/idle", "client_id": "ghost-tab"})
        assert join.status_code == 200
        lease_id = join.json()["lease_id"]

        await asyncio.sleep(0.45)

        broker = app.state.sync_broker
        replay = broker.replay(0)
        idle_presence = _latest_presence_for_gallery(replay, "/idle")
        assert idle_presence is not None
        assert idle_presence["viewing"] == 0
        assert idle_presence["editing"] == 0

        leave = await client.post(
            "/presence/leave",
            json={"gallery_id": "/idle", "client_id": "ghost-tab", "lease_id": lease_id},
        )
        assert leave.status_code == 200
        assert leave.json()["removed"] is False


def test_presence_prune_loop_cleans_idle_sessions(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path, presence_view_ttl=0.2, presence_edit_ttl=0.2, presence_prune_interval=0.1)
    asyncio.run(_run_idle_prune(app))


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
        join = await client.post("/presence/join", json={"gallery_id": "/diag", "client_id": "diag-tab"})
        assert join.status_code == 200
        lease_id = join.json()["lease_id"]

        bad_move = await client.post(
            "/presence/move",
            json={
                "from_gallery_id": "/diag",
                "to_gallery_id": "/diag/sub",
                "client_id": "diag-tab",
                "lease_id": "bad-lease",
            },
        )
        assert bad_move.status_code == 409
        assert bad_move.json()["error"] == "invalid_lease"

        broker = app.state.sync_broker
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
        assert health_presence.get("lifecycle_v2_enabled") is True

        leave = await client.post(
            "/presence/leave",
            json={"gallery_id": "/diag", "client_id": "diag-tab", "lease_id": lease_id},
        )
        assert leave.status_code == 200


def test_presence_diagnostics_counters(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path)
    asyncio.run(_run_presence_diagnostics_counters(app))


async def _run_presence_multi_client_convergence(app) -> None:
    async with _test_client(app) as client:
        join_a = await client.post("/presence/join", json={"gallery_id": "/room", "client_id": "tab-a"})
        assert join_a.status_code == 200
        lease_a_1 = join_a.json()["lease_id"]

        join_b = await client.post("/presence/join", json={"gallery_id": "/room", "client_id": "tab-b"})
        assert join_b.status_code == 200
        lease_b = join_b.json()["lease_id"]
        assert join_b.json()["viewing"] == 2

        refresh_a = await client.post("/presence/join", json={"gallery_id": "/room", "client_id": "tab-a"})
        assert refresh_a.status_code == 200
        lease_a_2 = refresh_a.json()["lease_id"]
        assert lease_a_2 != lease_a_1
        assert refresh_a.json()["viewing"] == 2

        move_b = await client.post(
            "/presence/move",
            json={
                "from_gallery_id": "/room",
                "to_gallery_id": "/room/sub",
                "client_id": "tab-b",
                "lease_id": lease_b,
            },
        )
        assert move_b.status_code == 200
        move_payload = move_b.json()
        assert move_payload["from_scope"]["viewing"] == 1
        assert move_payload["to_scope"]["viewing"] == 1

        reconnect_touch = await client.post(
            "/presence",
            json={"gallery_id": "/room/sub", "client_id": "tab-b", "lease_id": lease_b},
        )
        assert reconnect_touch.status_code == 200
        assert reconnect_touch.json()["viewing"] == 1

        leave_b = await client.post(
            "/presence/leave",
            json={"gallery_id": "/room/sub", "client_id": "tab-b", "lease_id": lease_b},
        )
        assert leave_b.status_code == 200
        assert leave_b.json()["removed"] is True
        assert leave_b.json()["viewing"] == 0

        await asyncio.sleep(0.55)

        broker = app.state.sync_broker
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


def test_presence_multi_client_refresh_move_reconnect_convergence(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path, presence_view_ttl=0.2, presence_edit_ttl=0.2, presence_prune_interval=0.1)
    asyncio.run(_run_presence_multi_client_convergence(app))


async def _run_presence_lifecycle_gate_legacy_mode(app) -> None:
    async with _test_client(app) as client:
        join = await client.post("/presence/join", json={"gallery_id": "/legacy", "client_id": "legacy-tab"})
        assert join.status_code == 200
        lease_id = join.json()["lease_id"]

        move = await client.post(
            "/presence/move",
            json={
                "from_gallery_id": "/wrong",
                "to_gallery_id": "/legacy/next",
                "client_id": "legacy-tab",
                "lease_id": lease_id,
            },
        )
        assert move.status_code == 200
        assert move.json()["to_scope"]["gallery_id"] == "/legacy/next"

        leave = await client.post(
            "/presence/leave",
            json={"gallery_id": "/legacy/next", "client_id": "legacy-tab", "lease_id": lease_id},
        )
        assert leave.status_code == 200
        assert leave.json()["removed"] is False
        assert leave.json()["mode"] == "legacy_heartbeat"

        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json().get("presence", {}).get("lifecycle_v2_enabled") is False


def test_presence_lifecycle_gate_legacy_mode(tmp_path: Path) -> None:
    app = _build_test_app(tmp_path, presence_lifecycle_v2=False)
    asyncio.run(_run_presence_lifecycle_gate_legacy_mode(app))
