from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import create_app, create_app_from_datasets, create_app_from_table
from lenslet.storage.dataset import DatasetStorage
from lenslet.storage.local import LocalStorage
from lenslet.storage.memory import MemoryStorage
from lenslet.storage.table import TableStorage


class MetadataStorage(Protocol):
    def get_index(self, path: str) -> object | None:
        ...

    def get_recursive_index(self, path: str) -> object | None:
        ...

    def ensure_metadata(self, path: str) -> dict[str, Any]:
        ...

    def get_metadata_readonly(self, path: str) -> dict[str, Any]:
        ...

    def set_metadata(self, path: str, meta: dict[str, Any]) -> None:
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


def _build_memory_storage(root: Path) -> tuple[MetadataStorage, str]:
    _make_image(root / "gallery" / "a.jpg")
    return MemoryStorage(str(root)), "gallery/a.jpg"


def _build_table_storage(root: Path) -> tuple[MetadataStorage, str]:
    local_path = root / "gallery" / "a.jpg"
    _make_image(local_path)
    rows = [{"path": "gallery/a.jpg", "source": str(local_path)}]
    return TableStorage(rows, root=None, skip_indexing=True), "gallery/a.jpg"


def _build_dataset_storage(root: Path) -> tuple[MetadataStorage, str]:
    local_path = root / "gallery" / "a.jpg"
    _make_image(local_path)
    datasets = {"gallery": [str(local_path)]}
    return DatasetStorage(datasets), "/gallery/a.jpg"


StorageBuilder = Callable[[Path], tuple[MetadataStorage, str]]


@pytest.mark.parametrize(
    "builder",
    [
        pytest.param(_build_memory_storage, id="memory"),
        pytest.param(_build_table_storage, id="table"),
        pytest.param(_build_dataset_storage, id="dataset"),
    ],
)
def test_get_index_returns_none_for_missing_scope(builder: StorageBuilder, tmp_path: Path) -> None:
    storage, _ = builder(tmp_path)
    assert storage.get_index("/missing") is None


@pytest.mark.parametrize(
    "builder",
    [
        pytest.param(_build_memory_storage, id="memory"),
        pytest.param(_build_table_storage, id="table"),
        pytest.param(_build_dataset_storage, id="dataset"),
    ],
)
def test_get_recursive_index_returns_none_for_missing_scope(
    builder: StorageBuilder,
    tmp_path: Path,
) -> None:
    storage, _ = builder(tmp_path)
    assert storage.get_recursive_index("/missing") is None


@pytest.mark.parametrize(
    "builder",
    [
        pytest.param(_build_memory_storage, id="memory"),
        pytest.param(_build_table_storage, id="table"),
        pytest.param(_build_dataset_storage, id="dataset"),
    ],
)
def test_get_metadata_readonly_returns_detached_snapshot(
    builder: StorageBuilder,
    tmp_path: Path,
) -> None:
    storage, item_path = builder(tmp_path)
    meta = storage.ensure_metadata(item_path)
    meta["notes"] = "persisted"
    storage.set_metadata(item_path, meta)

    readonly = storage.get_metadata_readonly(item_path)
    readonly["notes"] = "mutated outside storage"

    assert storage.ensure_metadata(item_path)["notes"] == "persisted"


@pytest.mark.parametrize(
    "build_app",
    [
        pytest.param(lambda root: create_app(str(root)), id="memory-app"),
        pytest.param(
            lambda root: create_app_from_table(
                [{"path": "gallery/a.jpg", "source": str(root / "gallery" / "a.jpg")}],
                base_dir=None,
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
                root=None,
                skip_indexing=True,
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
        pytest.param(_build_memory_storage, None, id="memory"),
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


@pytest.mark.parametrize(
    "storage",
    [
        pytest.param(lambda root: MemoryStorage(str(root)), id="memory"),
        pytest.param(
            lambda root: TableStorage(
                [{"path": "gallery/a.jpg", "source": str(root / "gallery" / "a.jpg")}],
                root=None,
                skip_indexing=True,
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
