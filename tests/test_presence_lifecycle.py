import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
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
):
    _make_image(root / "sample.jpg")
    return create_app(
        str(root),
        presence_view_ttl=presence_view_ttl,
        presence_edit_ttl=presence_edit_ttl,
        presence_prune_interval=presence_prune_interval,
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
