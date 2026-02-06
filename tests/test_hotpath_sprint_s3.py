import asyncio
import sys
import threading
import time
import types
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import HotpathTelemetry, _thumb_response_async, create_app
from lenslet.storage.dataset import DatasetStorage
from lenslet.storage.table import TableStorage
from lenslet.thumbs import ThumbnailScheduler


def _install_fake_boto(monkeypatch):
    counts = {"session": 0, "client": 0, "presign": 0}

    class FakeBotoCoreError(Exception):
        pass

    class FakeClientError(Exception):
        pass

    class FakeNoCredentialsError(Exception):
        pass

    class FakeS3Client:
        def generate_presigned_url(self, operation_name, Params, ExpiresIn):
            counts["presign"] += 1
            assert operation_name == "get_object"
            return f"https://example.invalid/{Params['Bucket']}/{Params['Key']}?exp={ExpiresIn}"

    class FakeSession:
        def client(self, name: str):
            assert name == "s3"
            counts["client"] += 1
            return FakeS3Client()

    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.session = types.SimpleNamespace(
        Session=lambda: _session_factory(counts, FakeSession),
    )

    fake_botocore_exceptions = types.ModuleType("botocore.exceptions")
    fake_botocore_exceptions.BotoCoreError = FakeBotoCoreError
    fake_botocore_exceptions.ClientError = FakeClientError
    fake_botocore_exceptions.NoCredentialsError = FakeNoCredentialsError

    fake_botocore = types.ModuleType("botocore")
    fake_botocore.exceptions = fake_botocore_exceptions

    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    monkeypatch.setitem(sys.modules, "botocore.exceptions", fake_botocore_exceptions)
    return counts


def _session_factory(counts, session_cls):
    counts["session"] += 1
    return session_cls()


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 12), color=(40, 90, 140)).save(path, format="JPEG")


def test_dataset_storage_reuses_s3_client_per_instance(monkeypatch) -> None:
    counts = _install_fake_boto(monkeypatch)
    storage = DatasetStorage({"demo": []})

    first = storage._get_presigned_url("s3://bucket/a.jpg")
    second = storage._get_presigned_url("s3://bucket/b.jpg")

    assert "bucket/a.jpg" in first
    assert "bucket/b.jpg" in second
    assert counts["session"] == 1
    assert counts["client"] == 1
    assert counts["presign"] == 2
    assert storage.s3_client_creations() == 1
    assert HotpathTelemetry().snapshot(storage)["counters"]["s3_client_create_total"] == 1


def test_table_storage_reuses_s3_client_per_instance(tmp_path: Path, monkeypatch) -> None:
    counts = _install_fake_boto(monkeypatch)
    local_image = tmp_path / "seed.jpg"
    _make_image(local_image)

    storage = TableStorage([{"source": str(local_image)}], root=None)
    first = storage._get_presigned_url("s3://bucket/c.jpg")
    second = storage._get_presigned_url("s3://bucket/d.jpg")

    assert "bucket/c.jpg" in first
    assert "bucket/d.jpg" in second
    assert counts["session"] == 1
    assert counts["client"] == 1
    assert counts["presign"] == 2
    assert storage.s3_client_creations() == 1
    assert HotpathTelemetry().snapshot(storage)["counters"]["s3_client_create_total"] == 1


def test_thumb_disconnect_cancels_queued_work_and_updates_metrics() -> None:
    queue: ThumbnailScheduler[bytes | None] = ThumbnailScheduler(max_workers=1)
    try:
        started = threading.Event()
        release = threading.Event()
        metrics = HotpathTelemetry()

        def _block_worker():
            started.set()
            release.wait(timeout=2.0)
            return b"block"

        block_future = queue.submit("__block__", _block_worker)
        assert started.wait(timeout=1.0)

        class Request:
            async def is_disconnected(self) -> bool:
                return True

        class Storage:
            def __init__(self):
                self.calls = 0

            def get_thumbnail(self, _path: str) -> bytes:
                self.calls += 1
                return b"thumb"

        storage = Storage()
        response = asyncio.run(
            _thumb_response_async(
                storage,
                "/queued.jpg",
                Request(),
                queue,
                hotpath_metrics=metrics,
            )
        )

        release.set()
        assert block_future.result(timeout=1.0) == b"block"
        assert response.status_code == 204
        assert storage.calls == 0
        counters = metrics.snapshot()["counters"]
        assert counters["thumb_disconnect_cancel_total"] == 1
        assert counters["thumb_disconnect_cancel_queued_total"] == 1
        assert queue.stats()["inflight"] == 0
    finally:
        queue.close()


def test_thumb_disconnect_cancels_inflight_work_and_worker_stays_healthy() -> None:
    queue: ThumbnailScheduler[bytes | None] = ThumbnailScheduler(max_workers=1)
    try:
        started = threading.Event()
        release = threading.Event()
        metrics = HotpathTelemetry()

        class Request:
            async def is_disconnected(self) -> bool:
                return started.is_set()

        class Storage:
            def __init__(self):
                self.calls = 0

            def get_thumbnail(self, _path: str) -> bytes:
                self.calls += 1
                started.set()
                release.wait(timeout=2.0)
                return b"thumb"

        storage = Storage()
        response = asyncio.run(
            _thumb_response_async(
                storage,
                "/inflight.jpg",
                Request(),
                queue,
                hotpath_metrics=metrics,
            )
        )
        assert response.status_code == 204
        release.set()
        time.sleep(0.05)

        probe = queue.submit("__probe__", lambda: b"ok")
        assert probe.result(timeout=1.0) == b"ok"
        assert storage.calls == 1
        counters = metrics.snapshot()["counters"]
        assert counters["thumb_disconnect_cancel_total"] == 1
        assert counters["thumb_disconnect_cancel_inflight_total"] == 1
        assert queue.stats()["inflight"] == 0
    finally:
        queue.close()


def test_health_exposes_hotpath_metrics(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.jpg"
    _make_image(image_path)
    app = create_app(str(tmp_path))
    client = TestClient(app)

    folders = client.get("/folders", params={"path": "/", "recursive": 1})
    assert folders.status_code == 200

    file_default = client.get("/file", params={"path": "/sample.jpg"})
    assert file_default.status_code == 200
    file_prefetch = client.get(
        "/file",
        params={"path": "/sample.jpg"},
        headers={"x-lenslet-prefetch": "viewer"},
    )
    assert file_prefetch.status_code == 200

    health = client.get("/health")
    assert health.status_code == 200
    payload = health.json()
    hotpath = payload["hotpath"]
    counters = hotpath["counters"]
    timers = hotpath["timers_ms"]

    assert counters["folders_recursive_requests_total"] >= 1
    assert counters["folders_recursive_items_total"] >= 1
    assert counters["file_response_local_stream_total"] >= 2
    assert counters["file_prefetch_viewer_total"] >= 1
    assert timers["folders_recursive_traversal_ms"]["count"] >= 1
