import asyncio
from pathlib import Path

from httpx import AsyncClient, ASGITransport
from PIL import Image

from lenslet.server import create_app, create_app_from_datasets


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="JPEG")


def test_patch_requires_idempotency_and_base_version(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)

    app = create_app(str(tmp_path))
    dataset_app = create_app_from_datasets({"demo": [str(image_path)]})

    async def _run(app, path: str) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.patch("/item", params={"path": path}, json={"base_version": 1})
            assert resp.status_code == 400

            resp = await client.patch(
                "/item",
                params={"path": path},
                headers={"Idempotency-Key": "idem-test"},
                json={},
            )
            assert resp.status_code == 400
            body = resp.json()
            assert body.get("error") == "missing_base_version"

    asyncio.run(_run(app, "/sample.jpg"))
    asyncio.run(_run(dataset_app, "/demo/sample.jpg"))


def test_patch_idempotency_and_conflict(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = create_app(str(tmp_path))

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            assert base.status_code == 200
            base_version = base.json().get("version", 1)

            headers = {"Idempotency-Key": "idem-1", "If-Match": str(base_version)}
            body = {"base_version": base_version, "set_notes": "hello"}
            first = await client.patch("/item", params={"path": "/sample.jpg"}, headers=headers, json=body)
            assert first.status_code == 200
            first_payload = first.json()

            second = await client.patch("/item", params={"path": "/sample.jpg"}, headers=headers, json=body)
            assert second.status_code == 200
            assert second.json() == first_payload

            latest = await client.get("/item", params={"path": "/sample.jpg"})
            assert latest.status_code == 200
            assert latest.json()["version"] == base_version + 1

            conflict_headers = {"Idempotency-Key": "idem-2", "If-Match": str(base_version)}
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


def test_sse_replay_last_event_id(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = create_app(str(tmp_path))

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            base_version = base.json().get("version", 1)

            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers={"Idempotency-Key": "idem-a", "If-Match": str(base_version)},
                json={"base_version": base_version, "set_notes": "first"},
            )

            broker = app.state.sync_broker
            replay = broker.replay(0)
            assert replay
            event1_id = replay[-1].get("id")
            assert replay[-1].get("event") == "item-updated"
            assert isinstance(event1_id, int)

            base2 = await client.get("/item", params={"path": "/sample.jpg"})
            base_version2 = base2.json().get("version", 1)
            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers={"Idempotency-Key": "idem-b", "If-Match": str(base_version2)},
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
    app = create_app(str(tmp_path))

    async def _run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            base = await client.get("/item", params={"path": "/sample.jpg"})
            base_version = base.json().get("version", 1)
            await client.patch(
                "/item",
                params={"path": "/sample.jpg"},
                headers={"Idempotency-Key": "idem-persist", "If-Match": str(base_version)},
                json={"base_version": base_version, "set_notes": "persisted", "set_star": 4},
            )

    asyncio.run(_run())

    snapshot_path = tmp_path / ".lenslet" / "labels.snapshot.json"
    log_path = tmp_path / ".lenslet" / "labels.log.jsonl"
    assert snapshot_path.exists()
    assert log_path.exists()

    app2 = create_app(str(tmp_path))

    async def _verify() -> None:
        transport = ASGITransport(app=app2)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/item", params={"path": "/sample.jpg"})
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["notes"] == "persisted"
            assert payload["star"] == 4

    asyncio.run(_verify())
