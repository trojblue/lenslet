from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import lenslet.storage.local.preindex as preindex
from lenslet.storage.local.preindex import PreindexResult
from lenslet.server import LocalAppOptions, StorageAppOptions, create_app
from lenslet.storage.memory import MemoryStorage
from lenslet.storage.table import TableStorage, TableStorageOptions
from lenslet.storage.table.launch import TableLaunchRequest, TableLaunchResult
from lenslet.web.auth import READ_ONLY_MUTATION_POLICY, mutation_denial_payload
from lenslet.web.context import get_app_context
from lenslet.web.app.health import REFRESH_NOTE_TABLE_STATIC
import lenslet.web.app.local as local_app
from lenslet.web.app.factory import create_app_from_storage
from lenslet.web.thumbs import ThumbnailScheduler
from lenslet.workspace import Workspace

LOCAL_ORIGIN = "http://localhost:7070"


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(50, 100, 150)).save(path, format="JPEG")


def test_writable_workspace_without_trusted_origins_is_read_only(
    tmp_path: Path,
) -> None:
    _make_image(tmp_path / "sample.jpg")
    app = create_app(
        str(tmp_path),
        options=LocalAppOptions(trusted_write_origins=()),
    )

    with TestClient(
        app,
        base_url="https://public.trycloudflare.com",
        headers={"Origin": LOCAL_ORIGIN},
    ) as client:
        health = client.get("/health")
        response = client.put(
            "/item",
            params={"path": "/sample.jpg"},
            json={"tags": ["blocked"], "notes": "blocked", "star": 1},
        )
        item = client.get("/item", params={"path": "/sample.jpg"})

    assert health.status_code == 200
    assert health.json()["can_write"] is False
    assert response.status_code == 403
    assert response.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)
    assert item.status_code == 200
    assert item.json()["notes"] == ""


def test_allow_remote_writes_enables_health_and_view_persistence_from_public_origin(
    tmp_path: Path,
) -> None:
    _make_image(tmp_path / "sample.jpg")
    app = create_app(
        str(tmp_path),
        options=LocalAppOptions(allow_remote_writes=True),
    )
    payload = {"version": 1, "views": []}

    with TestClient(app, base_url="https://public.trycloudflare.com") as client:
        health = client.get("/health")
        saved = client.put("/views", json=payload)

    assert health.status_code == 200
    assert health.json()["can_write"] is True
    assert health.json()["labels"]["enabled"] is True
    assert saved.status_code == 200
    assert saved.json() == payload
    assert (tmp_path / ".lenslet" / "views.json").is_file()


def test_default_local_app_does_not_trust_default_port_origin(tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")
    app = create_app(str(tmp_path))

    with TestClient(app, base_url="http://localhost:9090", headers={"Origin": LOCAL_ORIGIN}) as client:
        health = client.get("/health")
        response = client.put(
            "/item",
            params={"path": "/sample.jpg"},
            json={"tags": ["blocked"], "notes": "blocked", "star": 1},
        )

    assert health.status_code == 200
    assert health.json()["can_write"] is False
    assert response.status_code == 403
    assert response.json() == mutation_denial_payload(READ_ONLY_MUTATION_POLICY)


def test_create_app_raises_when_items_parquet_is_invalid(tmp_path: Path) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")
    (tmp_path / "items.parquet").write_text("not a parquet file", encoding="utf-8")

    with pytest.raises(RuntimeError, match="failed to initialize table dataset"):
        create_app(str(tmp_path))


def test_create_app_raises_when_workspace_init_fails(monkeypatch, tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")
    workspace = Workspace.for_dataset(str(tmp_path), can_write=True)

    def _raise(self) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Workspace, "ensure", _raise)

    with pytest.raises(RuntimeError, match="failed to initialize workspace: disk full"):
        create_app(str(tmp_path))


def test_preindex_does_not_downgrade_writable_workspace_failures(monkeypatch, tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")
    workspace = Workspace.for_dataset(str(tmp_path), can_write=True)

    def _raise(self) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Workspace, "ensure", _raise)

    with pytest.raises(OSError, match="disk full"):
        preindex.ensure_local_preindex(tmp_path, workspace)


def test_create_app_raises_when_preindex_build_fails(monkeypatch, tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")

    def _raise(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(local_app, "ensure_local_preindex", _raise)

    with pytest.raises(RuntimeError, match="preindex build failed: disk full"):
        create_app(str(tmp_path))


def test_create_app_empty_dataset_falls_back_to_memory_mode(tmp_path: Path) -> None:
    with TestClient(create_app(str(tmp_path))) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["mode"] == "memory"


def test_create_app_raises_when_preindex_reload_returns_no_storage(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _make_image(tmp_path / "sample.jpg")
    workspace = Workspace.for_dataset(str(tmp_path), can_write=True)

    def _result(*_args, **_kwargs) -> PreindexResult:
        return PreindexResult(
            workspace=workspace,
            paths=preindex.preindex_paths(workspace),
            signature="sig-1",
            image_count=1,
            format="json",
            reused=False,
        )

    monkeypatch.setattr(local_app, "ensure_local_preindex", _result)
    monkeypatch.setattr(local_app, "load_preindex_storage", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="preindex build completed but produced no readable storage"):
        create_app(str(tmp_path))


def test_create_app_consumes_prebuilt_table_launch_without_reloading(
    monkeypatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "image.jpg"
    _make_image(image_path)
    storage = TableStorage(
        [{"path": "gallery/image.jpg", "source": str(image_path)}],
        options=TableStorageOptions(root=None, skip_dimension_probe=True),
    )
    launch_result = TableLaunchResult(
        storage=storage,
        effective_root=str(tmp_path),
        default_root=str(tmp_path),
    )

    def _unexpected_prepare(*_args, **_kwargs):
        raise AssertionError("prebuilt table launch should be consumed directly")

    monkeypatch.setattr(local_app, "prepare_table_launch", _unexpected_prepare)

    app = local_app.create_local_app(
        str(tmp_path),
        options=LocalAppOptions(
            trusted_write_origins=(LOCAL_ORIGIN,),
        ),
        table_launch=launch_result,
    )
    context = get_app_context(app)

    assert context.storage is storage
    assert context.storage_mode == "table"
    assert context.storage_origin == "parquet"
    with TestClient(app, base_url=LOCAL_ORIGIN, headers={"Origin": LOCAL_ORIGIN}) as client:
        refresh = client.post("/refresh", params={"path": "/"})
    assert refresh.status_code == 200
    assert refresh.json()["note"] == REFRESH_NOTE_TABLE_STATIC


def test_local_storage_startup_consumes_prebuilt_table_launch(tmp_path: Path) -> None:
    image_path = tmp_path / "image.jpg"
    _make_image(image_path)
    storage = TableStorage(
        [{"path": "gallery/image.jpg", "source": str(image_path)}],
        options=TableStorageOptions(root=None, skip_dimension_probe=True),
    )
    workspace = Workspace.for_dataset(str(tmp_path), can_write=True)
    launch_result = TableLaunchResult(
        storage=storage,
        effective_root=str(tmp_path),
        default_root=str(tmp_path),
    )
    options = LocalAppOptions()

    startup = local_app.resolve_local_storage_startup(
        str(tmp_path),
        workspace,
        options=options,
        browse_options=options.browse,
        embedding_options=options.embedding,
        table_launch=launch_result,
    )

    assert startup.storage is storage
    assert startup.workspace is workspace
    assert startup.storage_mode == "table"
    assert startup.storage_origin == "parquet"
    assert startup.table_parquet_path is None


def test_local_storage_startup_uses_memory_when_preindex_absent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workspace = Workspace.for_dataset(str(tmp_path), can_write=True)
    options = LocalAppOptions(preindex_signature="sig-1")

    monkeypatch.setattr(
        local_app,
        "ensure_preindex_storage",
        lambda *_args, **_kwargs: (None, workspace, "sig-1"),
    )

    startup = local_app.resolve_local_storage_startup(
        str(tmp_path),
        workspace,
        options=options,
        browse_options=options.browse,
        embedding_options=options.embedding,
    )

    assert isinstance(startup.storage, MemoryStorage)
    assert startup.workspace is workspace
    assert startup.storage_mode == "memory"
    assert startup.storage_origin == "memory"
    assert startup.preindex_signature == "sig-1"


def test_create_app_prepares_items_parquet_with_table_launch_helper(
    monkeypatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "items.parquet").write_bytes(b"unused by fake launch")
    image_path = tmp_path / "image.jpg"
    _make_image(image_path)
    storage = TableStorage(
        [{"path": "gallery/image.jpg", "source": str(image_path)}],
        options=TableStorageOptions(root=None, skip_dimension_probe=True),
    )
    launch_result = TableLaunchResult(
        storage=storage,
        effective_root=str(tmp_path),
        default_root=str(tmp_path),
    )
    captured: dict[str, object] = {}

    def _fake_prepare_table_launch(request: TableLaunchRequest):
        captured["request"] = request
        return launch_result

    monkeypatch.setattr(local_app, "prepare_table_launch", _fake_prepare_table_launch)

    app = create_app(
        str(tmp_path),
        options=LocalAppOptions(
            source_column="source",
            path_column="path",
            skip_dimension_probe=True,
        ),
    )

    assert get_app_context(app).storage is storage
    request = captured["request"]
    assert isinstance(request, TableLaunchRequest)
    assert request.parquet_path == tmp_path / "items.parquet"
    assert request.base_dir == str(tmp_path)
    assert request.source_column == "source"
    assert request.path_column == "path"
    assert request.cache_dimensions is False
    assert request.dimension_cache_dir == (tmp_path / ".lenslet" / "dimensions")
    assert request.skip_dimension_probe is True


def test_create_app_defers_background_work_until_lifespan(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _make_image(tmp_path / "sample.jpg")
    thumb_starts: list[str] = []
    warmup_states: list[str] = []

    def _record_thumb_start(self) -> None:
        thumb_starts.append(type(self).__name__)

    def _record_index_warmup(storage, indexing, *, warmup_errors) -> None:
        _ = storage, warmup_errors
        warmup_states.append(indexing.snapshot()["state"])
        indexing.mark_ready()

    monkeypatch.setattr(ThumbnailScheduler, "start", _record_thumb_start)
    monkeypatch.setattr(local_app, "_start_index_warmup", _record_index_warmup)

    app = create_app(str(tmp_path))

    assert thumb_starts == []
    assert warmup_states == []

    with TestClient(app) as client:
        health = client.get("/health")

    assert health.status_code == 200
    assert thumb_starts == ["ThumbnailScheduler"]
    assert warmup_states == ["running"]
    assert health.json()["indexing"]["state"] == "ready"


def test_create_app_from_storage_can_advertise_mutable_memory_refresh(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    _make_image(root / "first.jpg")
    storage = MemoryStorage(str(root))
    workspace = Workspace.for_dataset(str(root), can_write=True)
    app = create_app_from_storage(
        storage,
        options=StorageAppOptions(
            storage_mode="memory",
            storage_origin="memory",
            refresh="subtree",
            workspace=workspace,
            trusted_write_origins=(LOCAL_ORIGIN,),
        ),
    )

    with TestClient(app, base_url=LOCAL_ORIGIN, headers={"Origin": LOCAL_ORIGIN}) as client:
        before = client.get("/folders", params={"path": "/"})
        assert before.status_code == 200
        assert len(before.json()["items"]) == 1
        health = client.get("/health").json()
        assert health["mode"] == "memory"
        assert health["refresh"]["enabled"] is True

        _make_image(root / "second.jpg")
        refresh = client.post("/refresh", params={"path": "/"})
        assert refresh.status_code == 200
        assert refresh.json()["ok"] is True
        after = client.get("/folders", params={"path": "/"})

    assert len(after.json()["items"]) == 2
