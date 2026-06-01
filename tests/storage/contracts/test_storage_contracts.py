from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import TableAppOptions, create_app, create_app_from_datasets, create_app_from_table
from lenslet.storage.base import SidecarState
from lenslet.storage.dataset import DatasetStorage
from lenslet.storage.local import LocalStorage
from lenslet.storage.memory import MemoryStorage
from lenslet.storage.sidecar_state import copy_sidecar_state, ensure_sidecar_fields
from lenslet.storage.table import TableStorage, TableStorageOptions


class SidecarStateStorage(Protocol):
    def load_index(self, path: str) -> object | None:
        ...

    def load_recursive_index(self, path: str) -> object | None:
        ...

    def ensure_sidecar(self, path: str) -> SidecarState:
        ...

    def get_sidecar_readonly(self, path: str) -> SidecarState:
        ...

    def set_sidecar(self, path: str, sidecar: SidecarState) -> None:
        ...

    def join(self, *parts: str) -> str:
        ...

    def total_items(self) -> int:
        ...

    def count_in_scope(self, path: str) -> int:
        ...

    def row_index_for_path(self, path: str) -> int | None:
        ...


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 8), color=(48, 96, 144)).save(path, format="JPEG")


def _build_memory_storage(root: Path) -> tuple[SidecarStateStorage, str]:
    _make_image(root / "gallery" / "a.jpg")
    return MemoryStorage(str(root)), "gallery/a.jpg"


def _build_table_storage(root: Path) -> tuple[SidecarStateStorage, str]:
    local_path = root / "gallery" / "a.jpg"
    _make_image(local_path)
    rows = [{"path": "gallery/a.jpg", "source": str(local_path)}]
    return TableStorage(rows, options=TableStorageOptions(root=None, skip_dimension_probe=True)), "gallery/a.jpg"


def _build_dataset_storage(root: Path) -> tuple[SidecarStateStorage, str]:
    local_path = root / "gallery" / "a.jpg"
    _make_image(local_path)
    datasets = {"gallery": [str(local_path)]}
    return DatasetStorage(datasets), "/gallery/a.jpg"


StorageBuilder = Callable[[Path], tuple[SidecarStateStorage, str]]


@pytest.mark.parametrize(
    "builder",
    [
        pytest.param(_build_memory_storage, id="memory"),
        pytest.param(_build_table_storage, id="table"),
        pytest.param(_build_dataset_storage, id="dataset"),
    ],
)
def test_load_index_returns_none_for_missing_scope(builder: StorageBuilder, tmp_path: Path) -> None:
    storage, _ = builder(tmp_path)
    assert storage.load_index("/missing") is None


@pytest.mark.parametrize(
    "builder",
    [
        pytest.param(_build_memory_storage, id="memory"),
        pytest.param(_build_table_storage, id="table"),
        pytest.param(_build_dataset_storage, id="dataset"),
    ],
)
def test_load_recursive_index_returns_none_for_missing_scope(
    builder: StorageBuilder,
    tmp_path: Path,
) -> None:
    storage, _ = builder(tmp_path)
    assert storage.load_recursive_index("/missing") is None


@pytest.mark.parametrize(
    "builder",
    [
        pytest.param(_build_memory_storage, id="memory"),
        pytest.param(_build_table_storage, id="table"),
        pytest.param(_build_dataset_storage, id="dataset"),
    ],
)
def test_loaded_index_exposes_path_and_generation(
    builder: StorageBuilder,
    tmp_path: Path,
) -> None:
    storage, _ = builder(tmp_path)

    index = storage.load_index("/gallery")
    recursive_index = storage.load_recursive_index("/gallery")

    assert index is not None
    assert recursive_index is not None
    assert getattr(index, "path") == "/gallery"
    assert getattr(recursive_index, "path") == "/gallery"
    assert isinstance(getattr(index, "generated_at"), str)
    assert getattr(index, "generated_at")
    assert isinstance(getattr(recursive_index, "generated_at"), str)
    assert getattr(recursive_index, "generated_at")


def test_memory_load_index_makes_lazy_building_explicit(tmp_path: Path) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")
    storage = MemoryStorage(str(tmp_path))

    assert "gallery" not in storage._indexes
    index = storage.load_index("/gallery")

    assert index is not None
    assert index.path == "/gallery"
    assert "gallery" in storage._indexes


@pytest.mark.parametrize(
    "builder",
    [
        pytest.param(_build_memory_storage, id="memory"),
        pytest.param(_build_table_storage, id="table"),
        pytest.param(_build_dataset_storage, id="dataset"),
    ],
)
def test_get_sidecar_readonly_returns_detached_snapshot(
    builder: StorageBuilder,
    tmp_path: Path,
) -> None:
    storage, item_path = builder(tmp_path)
    sidecar_state = storage.ensure_sidecar(item_path)
    sidecar_state["notes"] = "persisted"
    sidecar_state["tags"] = ["kept"]
    sidecar_state["metrics"] = {"score": 0.75}
    storage.set_sidecar(item_path, sidecar_state)

    readonly = storage.get_sidecar_readonly(item_path)
    readonly["notes"] = "mutated outside storage"
    readonly["tags"].append("mutated")
    readonly["metrics"]["score"] = 0.1

    stored = storage.ensure_sidecar(item_path)
    assert stored["notes"] == "persisted"
    assert stored["tags"] == ["kept"]
    assert stored["metrics"] == {"score": 0.75}


def test_memory_sidecar_snapshot_accepts_path_iterables(tmp_path: Path) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")
    storage = MemoryStorage(str(tmp_path))
    item_path = "gallery/a.jpg"
    sidecar_state = storage.ensure_sidecar(item_path)
    sidecar_state["notes"] = "persisted"
    sidecar_state["tags"] = ["kept"]
    sidecar_state["metrics"] = {"score": 0.75}
    storage.set_sidecar(item_path, sidecar_state)

    snapshot = storage.sidecar_snapshot_for_paths(path for path in [item_path])
    snapshot["/gallery/a.jpg"]["tags"].append("mutated")
    snapshot["/gallery/a.jpg"]["metrics"]["score"] = 0.1

    assert set(snapshot) == {"/gallery/a.jpg"}
    assert snapshot["/gallery/a.jpg"]["notes"] == "persisted"
    stored = storage.ensure_sidecar(item_path)
    assert stored["tags"] == ["kept"]
    assert stored["metrics"] == {"score": 0.75}


def test_sidecar_state_helpers_copy_nested_typed_fields() -> None:
    sidecar_state: SidecarState = {"tags": ["kept"], "metrics": {"score": 0.75}}
    normalized = ensure_sidecar_fields(sidecar_state)

    copied = copy_sidecar_state(normalized)
    copied["tags"].append("mutated")
    copied["metrics"]["score"] = 0.1

    assert normalized["tags"] == ["kept"]
    assert normalized["metrics"] == {"score": 0.75}
    assert normalized["notes"] == ""
    assert normalized["version"] == 1


@pytest.mark.parametrize(
    "build_app",
    [
        pytest.param(lambda root: create_app(str(root)), id="memory-app"),
        pytest.param(
            lambda root: create_app_from_table(
                [{"path": "gallery/a.jpg", "source": str(root / "gallery" / "a.jpg")}],
                options=TableAppOptions(base_dir=None),
            ),
            id="table-app",
        ),
        pytest.param(
            lambda root: create_app_from_datasets({"gallery": [str(root / "gallery" / "a.jpg")]}),
            id="dataset-app",
        ),
    ],
)
def test_missing_folder_route_still_maps_absent_index_to_404(
    tmp_path: Path,
    build_app: Callable[[Path], object],
) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")

    with TestClient(build_app(tmp_path)) as client:
        response = client.get("/folders", params={"path": "/missing"})

    assert response.status_code == 404
    assert response.json()["detail"] == "folder not found"


@pytest.mark.parametrize(
    ("storage", "expected"),
    [
        pytest.param(lambda root: MemoryStorage(str(root)), "/gallery/a.jpg", id="memory"),
        pytest.param(
            lambda root: TableStorage(
                [{"path": "gallery/a.jpg", "source": str(root / "gallery" / "a.jpg")}],
                options=TableStorageOptions(root=None, skip_dimension_probe=True),
            ),
            "/gallery/a.jpg",
            id="table",
        ),
        pytest.param(
            lambda root: DatasetStorage({"gallery": [str(root / "gallery" / "a.jpg")]}),
            "/gallery/a.jpg",
            id="dataset",
        ),
        pytest.param(lambda root: LocalStorage(str(root)), "/gallery/a.jpg", id="local"),
    ],
)
def test_join_returns_rooted_logical_paths(
    tmp_path: Path,
    storage: Callable[[Path], Any],
    expected: str,
) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")
    assert storage(tmp_path).join("/gallery", "a.jpg") == expected


@pytest.mark.parametrize(
    "builder",
    [
        pytest.param(_build_memory_storage, id="memory"),
        pytest.param(_build_table_storage, id="table"),
        pytest.param(_build_dataset_storage, id="dataset"),
    ],
)
def test_total_items_matches_root_index_count(builder: StorageBuilder, tmp_path: Path) -> None:
    storage, _ = builder(tmp_path)
    assert storage.total_items() == 1


@pytest.mark.parametrize(
    "builder",
    [
        pytest.param(_build_memory_storage, id="memory"),
        pytest.param(_build_table_storage, id="table"),
        pytest.param(_build_dataset_storage, id="dataset"),
    ],
)
def test_count_in_scope_matches_total_items_for_root(
    builder: StorageBuilder,
    tmp_path: Path,
) -> None:
    storage, _ = builder(tmp_path)
    assert storage.count_in_scope("/") == storage.total_items()


@pytest.mark.parametrize(
    ("builder", "expected"),
    [
        pytest.param(_build_memory_storage, 0, id="memory"),
        pytest.param(_build_table_storage, 0, id="table"),
        pytest.param(_build_dataset_storage, 0, id="dataset"),
    ],
)
def test_row_index_for_path_contract(
    builder: StorageBuilder,
    expected: int | None,
    tmp_path: Path,
) -> None:
    storage, item_path = builder(tmp_path)
    assert storage.row_index_for_path(item_path) == expected


def test_memory_row_index_for_path_uses_stable_global_item_order(tmp_path: Path) -> None:
    _make_image(tmp_path / "gallery" / "b.jpg")
    _make_image(tmp_path / "gallery" / "nested" / "c.jpg")
    _make_image(tmp_path / "gallery" / "a.jpg")
    storage = MemoryStorage(str(tmp_path))

    assert storage.row_index_for_path("gallery/a.jpg") == 0
    assert storage.row_index_for_path("/gallery/b.jpg") == 1
    assert storage.row_index_for_path("gallery/nested/c.jpg") == 2
    assert storage.row_index_for_path("/gallery/missing.jpg") is None
    assert storage.row_index_for_path("/gallery/a.jpg") == storage.row_index_for_path("gallery/a.jpg")


@pytest.mark.parametrize(
    "storage",
    [
        pytest.param(lambda root: MemoryStorage(str(root)), id="memory"),
        pytest.param(
            lambda root: TableStorage(
                [{"path": "gallery/a.jpg", "source": str(root / "gallery" / "a.jpg")}],
                options=TableStorageOptions(root=None, skip_dimension_probe=True),
            ),
            id="table",
        ),
        pytest.param(
            lambda root: DatasetStorage({"gallery": [str(root / "gallery" / "a.jpg")]}),
            id="dataset",
        ),
        pytest.param(lambda root: LocalStorage(str(root)), id="local"),
    ],
)
def test_size_raises_for_missing_item(
    tmp_path: Path,
    storage: Callable[[Path], Any],
) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")
    with pytest.raises(FileNotFoundError):
        storage(tmp_path).size("/gallery/missing.jpg")


def test_memory_resolve_local_file_path_returns_none_for_missing_item(tmp_path: Path) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")
    storage = MemoryStorage(str(tmp_path))
    assert storage.resolve_local_file_path("/gallery/missing.jpg") is None
