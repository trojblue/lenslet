from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from PIL import Image

from lenslet.storage.dataset import DatasetStorage
from lenslet.storage.memory import MemoryIndexBuildError, MemoryStorage
from lenslet.storage.search_text import (
    build_search_haystack,
    sidecar_source_fields,
    normalize_search_path,
    path_in_scope,
)
from lenslet.storage.table import TableStorage, TableStorageOptions, load_parquet_table


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 8), color=(44, 88, 132)).save(path, format="JPEG")


def _set_search_sidecar(storage: object, path: str) -> None:
    sidecar_state = storage.ensure_sidecar(path)
    sidecar_state["tags"] = ["feline", "portrait"]
    sidecar_state["notes"] = "night scout"
    storage.set_sidecar(path, sidecar_state)


def _result_paths(items: list[object]) -> set[str]:
    return {item.path.lstrip("/") for item in items}


def _table_storage(table, **options) -> TableStorage:
    return TableStorage(table, options=TableStorageOptions(**options))


def _build_memory_storage(root: Path) -> tuple[MemoryStorage, str]:
    local_cat = root / "source-token" / "cat.jpg"
    local_dog = root / "source-token" / "dog.jpg"
    _make_image(local_cat)
    _make_image(local_dog)

    storage = MemoryStorage(str(root))
    storage.load_index("/source-token")

    cat_path = "source-token/cat.jpg"
    _set_search_sidecar(storage, cat_path)
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
    storage = _table_storage(table_loaded, root=None, skip_dimension_probe=True)
    cat_path = "gallery/cat.jpg"
    _set_search_sidecar(storage, cat_path)
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
    storage = _table_storage(rows, root=None, skip_dimension_probe=True)
    cat_path = "gallery/cat.jpg"
    _set_search_sidecar(storage, cat_path)
    return storage, cat_path


def _build_dataset_storage(root: Path) -> tuple[DatasetStorage, str]:
    local_cat = root / "source-token" / "cat.jpg"
    local_dog = root / "source-token" / "dog.jpg"
    _make_image(local_cat)
    _make_image(local_dog)

    storage = DatasetStorage({"gallery": [str(local_cat), str(local_dog)]})
    cat_path = "/gallery/cat.jpg"
    _set_search_sidecar(storage, cat_path)
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
    storage.load_index("/animals/cats")
    storage.load_index("/animals/dogs")
    storage.load_index("/outside/cats")

    assert "animals/cats/tabby.jpg" in _result_paths(
        storage.search(query="animals/cats/tab", path="/animals")
    )
    assert "outside/cats/street.jpg" not in _result_paths(
        storage.search(query="cats", path="/animals")
    )
    assert "animals/cats/tabby.jpg" not in _result_paths(
        storage.search(query="tabby", path="/outside")
    )


def test_memory_search_optional_source_like_sidecar_fields(tmp_path: Path) -> None:
    image_path = tmp_path / "gallery" / "local.jpg"
    _make_image(image_path)

    storage = MemoryStorage(str(tmp_path))
    storage.load_index("/gallery")
    path = "gallery/local.jpg"
    sidecar_state = storage.ensure_sidecar(path)
    sidecar_state["source"] = "s3://bucket/source-token/local.jpg"
    sidecar_state["url"] = "https://cdn.example.com/media/local.jpg"
    storage.set_sidecar(path, sidecar_state)

    assert path in _result_paths(storage.search(query="source-token"))
    assert path in _result_paths(storage.search(query="cdn.example.com"))


def test_memory_search_raises_when_root_index_build_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_image(tmp_path / "cat.jpg")
    _make_image(tmp_path / "dog.jpg")

    storage = MemoryStorage(str(tmp_path))
    original_resolve_path = storage.local.resolve_path

    def _failing_resolve_path(path: str) -> str:
        if path.endswith("/dog.jpg"):
            raise OSError("stat blocked")
        return original_resolve_path(path)

    monkeypatch.setattr(storage.local, "resolve_path", _failing_resolve_path)

    with pytest.raises(MemoryIndexBuildError, match=r"/dog\.jpg"):
        storage.search(query="cat")


def test_table_search_source_and_url_fields_respect_toggle(tmp_path: Path) -> None:
    local_source = tmp_path / "source-token" / "local.jpg"
    _make_image(local_source)
    rows = [
        {"path": "gallery/local.jpg", "source": str(local_source)},
        {"path": "gallery/remote.jpg", "source": "https://cdn.example.com/media/remote.jpg"},
    ]

    enabled = _table_storage(rows, root=None, include_source_in_search=True, skip_dimension_probe=True)
    disabled = _table_storage(rows, root=None, include_source_in_search=False, skip_dimension_probe=True)

    assert "gallery/local.jpg" in _result_paths(enabled.search(query="source-token"))
    assert "gallery/remote.jpg" in _result_paths(enabled.search(query="cdn.example.com"))
    assert "gallery/local.jpg" not in _result_paths(disabled.search(query="source-token"))
    assert "gallery/remote.jpg" not in _result_paths(disabled.search(query="cdn.example.com"))


def test_table_search_name_cache_preserves_hits_without_materializing_misses() -> None:
    rows = [
        {
            "path": f"custom/id-{idx:04d}.jpg",
            "source": f"https://cdn.example.test/source-name-{idx:04d}.jpg",
            "width": 12,
            "height": 9,
        }
        for idx in range(50)
    ]

    storage = _table_storage(
        rows,
        root=None,
        include_source_in_search=False,
        skip_dimension_probe=True,
        allow_local=False,
    )
    row_store = storage._row_store
    assert row_store is not None
    assert row_store.materialized_item_count == 0

    assert storage.search(query="definitely-not-present") == []
    assert row_store.materialized_item_count == 0
    assert storage._search_names_lower is not None
    assert storage._search_sources_lower is None

    assert "custom/id-0007.jpg" in _result_paths(storage.search(query="source-name-0007"))
    assert row_store.materialized_item_count == 1


def test_table_search_treats_auto_http_path_as_source_alias() -> None:
    pa = pytest.importorskip("pyarrow")

    table = pa.table(
        {
            "s3key": [
                "https://img.metanomaly.co/r2/one",
                "https://img.metanomaly.co/r2/two",
            ],
            "path": [
                "img.metanomaly.co/r2/one",
                "img.metanomaly.co/r2/two",
            ],
            "width": [10, 11],
            "height": [12, 13],
        }
    )

    storage = _table_storage(
        table,
        source_column="s3key",
        skip_dimension_probe=True,
        include_source_in_search=True,
    )

    assert storage._path_column_aliases_source
    assert storage._source_search_covered_by_path()
    assert storage._index_context.table.path_column is None
    assert "img.metanomaly.co/r2/one" in _result_paths(storage.search(query="https://img.metanomaly.co/r2/one"))
    assert "img.metanomaly.co/r2/two" in _result_paths(storage.search(query="img.metanomaly.co/r2/two"))


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

    monkeypatch.setattr(DatasetStorage, "_probe_remote_dimensions", lambda self, tasks: None)

    enabled = DatasetStorage(datasets, include_source_in_search=True)
    disabled = DatasetStorage(datasets, include_source_in_search=False)

    assert "gallery/local.jpg" in _result_paths(enabled.search(query="source-token"))
    assert "gallery/remote.jpg" in _result_paths(enabled.search(query="cdn.example.com"))
    assert "gallery/local.jpg" not in _result_paths(disabled.search(query="source-token"))
    assert "gallery/remote.jpg" not in _result_paths(disabled.search(query="cdn.example.com"))


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(_build_memory_storage, id="memory"),
        pytest.param(_build_table_storage_from_parquet, id="table-parquet"),
        pytest.param(_build_table_storage, id="table"),
        pytest.param(_build_dataset_storage, id="dataset"),
    ],
)
def test_search_miss_does_not_grow_sidecar_state(factory: StorageFactory, tmp_path: Path) -> None:
    storage, _ = factory(tmp_path)

    before = dict(storage.sidecar_items())

    assert storage.search(query="definitely-not-present") == []
    assert dict(storage.sidecar_items()) == before


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
    assert sidecar_source_fields({"source_path": " s3://bucket/cat.jpg ", "source_url": " "}) == (
        "s3://bucket/cat.jpg",
        None,
    )
