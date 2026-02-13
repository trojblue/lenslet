from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from PIL import Image

from lenslet.storage.dataset import DatasetStorage
from lenslet.storage.memory import MemoryStorage
from lenslet.storage.search_text import (
    build_search_haystack,
    normalize_search_path,
    path_in_scope,
)
from lenslet.storage.table import TableStorage, load_parquet_table


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 8), color=(44, 88, 132)).save(path, format="JPEG")


def _set_search_meta(storage: object, path: str) -> None:
    meta = storage.get_metadata(path)
    meta["tags"] = ["feline", "portrait"]
    meta["notes"] = "night scout"
    storage.set_metadata(path, meta)


def _result_paths(items: list[object]) -> set[str]:
    return {item.path.lstrip("/") for item in items}


def _build_memory_storage(root: Path) -> tuple[MemoryStorage, str]:
    local_cat = root / "source-token" / "cat.jpg"
    local_dog = root / "source-token" / "dog.jpg"
    _make_image(local_cat)
    _make_image(local_dog)

    storage = MemoryStorage(str(root))
    storage.get_index("/source-token")

    cat_path = "source-token/cat.jpg"
    _set_search_meta(storage, cat_path)
    return storage, cat_path


def _build_table_storage_from_parquet(root: Path) -> tuple[TableStorage, str]:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")

    local_cat = root / "source-token" / "cat.jpg"
    local_dog = root / "source-token" / "dog.jpg"
    _make_image(local_cat)
    _make_image(local_dog)

    table = pa.table(
        {
            "image_id": [1, 2],
            "path": ["gallery/cat.jpg", "gallery/dog.jpg"],
            "source": [str(local_cat), str(local_dog)],
        }
    )
    pq.write_table(table, root / "items.parquet")

    table_loaded = load_parquet_table(str(root / "items.parquet"))
    storage = TableStorage(table_loaded, root=None, skip_indexing=True)
    cat_path = "gallery/cat.jpg"
    _set_search_meta(storage, cat_path)
    return storage, cat_path


def _build_table_storage(root: Path) -> tuple[TableStorage, str]:
    local_cat = root / "source-token" / "cat.jpg"
    local_dog = root / "source-token" / "dog.jpg"
    _make_image(local_cat)
    _make_image(local_dog)

    rows = [
        {"path": "gallery/cat.jpg", "source": str(local_cat)},
        {"path": "gallery/dog.jpg", "source": str(local_dog)},
    ]
    storage = TableStorage(rows, root=None, skip_indexing=True)
    cat_path = "gallery/cat.jpg"
    _set_search_meta(storage, cat_path)
    return storage, cat_path


def _build_dataset_storage(root: Path) -> tuple[DatasetStorage, str]:
    local_cat = root / "source-token" / "cat.jpg"
    local_dog = root / "source-token" / "dog.jpg"
    _make_image(local_cat)
    _make_image(local_dog)

    storage = DatasetStorage({"gallery": [str(local_cat), str(local_dog)]})
    cat_path = "/gallery/cat.jpg"
    _set_search_meta(storage, cat_path)
    return storage, cat_path


StorageFactory = Callable[[Path], tuple[object, str]]


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(_build_memory_storage, id="memory"),
        pytest.param(_build_table_storage_from_parquet, id="table-parquet"),
        pytest.param(_build_table_storage, id="table"),
        pytest.param(_build_dataset_storage, id="dataset"),
    ],
)
def test_search_contract_name_path_tags_notes(factory: StorageFactory, tmp_path: Path) -> None:
    storage, expected_cat_path = factory(tmp_path)
    expected = expected_cat_path.lstrip("/")
    scope_path = "/" + expected.split("/", 1)[0]

    assert expected in _result_paths(storage.search(query="cat"))
    assert expected in _result_paths(storage.search(query=expected))
    assert expected in _result_paths(storage.search(query="feline"))
    assert expected in _result_paths(storage.search(query="night scout"))
    assert expected in _result_paths(storage.search(query="cat", path=scope_path))
    assert expected not in _result_paths(storage.search(query="cat", path="/outside"))


def test_memory_search_partial_path_tokens_respect_scope(tmp_path: Path) -> None:
    _make_image(tmp_path / "animals" / "cats" / "tabby.jpg")
    _make_image(tmp_path / "animals" / "dogs" / "beagle.jpg")
    _make_image(tmp_path / "outside" / "cats" / "street.jpg")

    storage = MemoryStorage(str(tmp_path))
    storage.get_index("/animals/cats")
    storage.get_index("/animals/dogs")
    storage.get_index("/outside/cats")

    assert "animals/cats/tabby.jpg" in _result_paths(
        storage.search(query="animals/cats/tab", path="/animals")
    )
    assert "outside/cats/street.jpg" not in _result_paths(
        storage.search(query="cats", path="/animals")
    )
    assert "animals/cats/tabby.jpg" not in _result_paths(
        storage.search(query="tabby", path="/outside")
    )


def test_memory_search_optional_source_like_metadata_fields(tmp_path: Path) -> None:
    image_path = tmp_path / "gallery" / "local.jpg"
    _make_image(image_path)

    storage = MemoryStorage(str(tmp_path))
    storage.get_index("/gallery")
    path = "gallery/local.jpg"
    meta = storage.get_metadata(path)
    meta["source"] = "s3://bucket/source-token/local.jpg"
    meta["url"] = "https://cdn.example.com/media/local.jpg"
    storage.set_metadata(path, meta)

    assert path in _result_paths(storage.search(query="source-token"))
    assert path in _result_paths(storage.search(query="cdn.example.com"))


def test_table_search_source_and_url_fields_respect_toggle(tmp_path: Path) -> None:
    local_source = tmp_path / "source-token" / "local.jpg"
    _make_image(local_source)
    rows = [
        {"path": "gallery/local.jpg", "source": str(local_source)},
        {"path": "gallery/remote.jpg", "source": "https://cdn.example.com/media/remote.jpg"},
    ]

    enabled = TableStorage(rows, root=None, include_source_in_search=True, skip_indexing=True)
    disabled = TableStorage(rows, root=None, include_source_in_search=False, skip_indexing=True)

    assert "gallery/local.jpg" in _result_paths(enabled.search(query="source-token"))
    assert "gallery/remote.jpg" in _result_paths(enabled.search(query="cdn.example.com"))
    assert "gallery/local.jpg" not in _result_paths(disabled.search(query="source-token"))
    assert "gallery/remote.jpg" not in _result_paths(disabled.search(query="cdn.example.com"))


def test_dataset_search_source_and_url_fields_respect_toggle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_source = tmp_path / "source-token" / "local.jpg"
    _make_image(local_source)
    datasets = {
        "gallery": [
            str(local_source),
            "https://cdn.example.com/media/remote.jpg",
        ]
    }

    monkeypatch.setattr(DatasetStorage, "_probe_remote_dimensions", lambda self, tasks, label: None)

    enabled = DatasetStorage(datasets, include_source_in_search=True)
    disabled = DatasetStorage(datasets, include_source_in_search=False)

    assert "gallery/local.jpg" in _result_paths(enabled.search(query="source-token"))
    assert "gallery/remote.jpg" in _result_paths(enabled.search(query="cdn.example.com"))
    assert "gallery/local.jpg" not in _result_paths(disabled.search(query="source-token"))
    assert "gallery/remote.jpg" not in _result_paths(disabled.search(query="cdn.example.com"))


def test_search_text_helpers_cover_scope_and_haystack_contract() -> None:
    assert normalize_search_path("/") == ""
    assert normalize_search_path("\\gallery\\cat.jpg") == "gallery/cat.jpg"
    assert path_in_scope(
        logical_path="/gallery/sub/cat.jpg",
        scope_norm=normalize_search_path("/gallery"),
    )
    assert not path_in_scope(
        logical_path="/gallery/sub/cat.jpg",
        scope_norm=normalize_search_path("/other"),
    )

    haystack = build_search_haystack(
        logical_path="/gallery/sub/cat.jpg",
        name="cat.jpg",
        tags=["feline", "tabby"],
        notes="night scout",
        source="s3://bucket/source-token/cat.jpg",
        url="https://cdn.example.com/media/cat.jpg",
        include_source_fields=True,
    )
    assert "gallery/sub/cat.jpg" in haystack
    assert "feline tabby" in haystack
    assert "source-token" in haystack
    assert "cdn.example.com" in haystack
