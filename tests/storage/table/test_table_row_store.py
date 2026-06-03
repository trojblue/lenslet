from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from lenslet.storage.image_media import read_dimensions_from_bytes
from lenslet.storage.source.backed import SourceBackedConfig, SourceBackedServices
from lenslet.storage.source.paths import is_http_url, is_s3_uri
from lenslet.storage.table.index import (
    TableIndexData,
    TableIndexInput,
    TableIndexPolicy,
    TableSourceResolver,
    build_index_columns,
)
from lenslet.storage.table.row_store import TableRowSourceAdapter, build_table_row_store


def _make_image(path: Path, size: tuple[int, int] = (13, 7)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(70, 90, 120)).save(path, format="JPEG")


def _context(
    values: dict[str, list[Any]],
    *,
    source_column: str = "source",
    path_column: str | None = "path",
    root: str | None = None,
    allow_local: bool = True,
    skip_dimension_probe: bool = True,
    extensionless_sources_are_images: bool = False,
) -> TableIndexInput:
    row_count = len(values[source_column])
    columns = list(values)
    return TableIndexInput(
        table=TableIndexData(
            root=root,
            row_count=row_count,
            column_values=values,
            columns=columns,
            source_column=source_column,
            path_column=path_column,
            name_column="name" if "name" in values else None,
            mime_column="mime" if "mime" in values else None,
            width_column="width" if "width" in values else None,
            height_column="height" if "height" in values else None,
            size_column="size" if "size" in values else None,
            mtime_column="mtime" if "mtime" in values else None,
            metrics_column=None,
            reserved_columns={source_column, "path", "name", "mime", "width", "height", "size", "mtime"},
            local_prefix=None,
            s3_prefixes={},
            s3_use_bucket=False,
            image_exts=(".jpg", ".jpeg", ".png", ".webp"),
            source_kind=None,
            extensionless_source_all_trusted=extensionless_sources_are_images,
        ),
        policy=TableIndexPolicy(
            allow_local=allow_local,
            skip_dimension_probe=skip_dimension_probe,
            skip_local_realpath_validation=True,
        ),
        source_resolver=TableSourceResolver(
            guess_mime=lambda _name: "image/jpeg",
            allows_extensionless_source_image=lambda _source: extensionless_sources_are_images,
            resolve_local_source=lambda source: str(Path(root or "") / source) if root else source,
            resolve_local_source_lexical=lambda source: str(Path(root or "") / source) if root else source,
        ),
        progress=lambda _done, _total, _label: None,
    )


def test_row_store_preserves_http_aliases_duplicates_scope_and_original_rows() -> None:
    first_source = "https://img.metanomaly.co/r2/encoded-image-key"
    values = {
        "s3key": [
            first_source,
            "https://img.metanomaly.co/raw/first-dup.jpg",
            "https://img.metanomaly.co/raw/second-dup.jpg",
        ],
        "path": [
            first_source,
            "logical/dup.jpg",
            "logical/dup.jpg",
        ],
        "width": [12, 10, 11],
        "height": [9, 8, 7],
        "size": [120, 100, 110],
        "mtime": [1.0, 2.0, 3.0],
    }
    context = _context(
        values,
        source_column="s3key",
        allow_local=False,
        extensionless_sources_are_images=True,
    )

    result = build_table_row_store(context, build_index_columns(context))
    store = result.store

    assert store.paths == (
        "img.metanomaly.co/r2/encoded-image-key",
        "logical/dup.jpg",
        "logical/dup-2.jpg",
    )
    assert store.path_for_row_index(0) == "img.metanomaly.co/r2/encoded-image-key"
    assert store.path_for_row_index(1) == "logical/dup.jpg"
    assert store.path_for_row_index(2) == "logical/dup-2.jpg"
    assert store.row_index_for_path("/logical/dup-2.jpg") == 2
    assert store.row_to_slot is None
    assert store.folder_dirs("/") == ("img.metanomaly.co", "logical")
    assert store.direct_rows("/logical") == (1, 2)
    assert store.count_in_scope("/logical") == 2
    assert store.rows_in_scope("/logical") == (2, 1)
    assert store.rows_in_scope_window("/logical", 1, 1) == (1,)
    assert store.materialized_item_count == 0
    assert not hasattr(store, "items")

    item = store.materialize_item(2, metrics_provider=lambda row_idx: {"row": float(row_idx)})

    assert item.path == "logical/dup-2.jpg"
    assert item.row_idx == 2
    assert item.metrics == {"row": 2.0}
    assert store.materialized_item_count == 1


def test_row_source_adapter_reads_media_and_uses_overlays_without_item_map(tmp_path: Path) -> None:
    image_path = tmp_path / "images" / "cat.jpg"
    _make_image(image_path)
    source = "images/cat.jpg"
    values = {
        "source": [source],
        "path": ["gallery/cat.jpg"],
        "width": [0],
        "height": [0],
        "size": [None],
        "mtime": [7.0],
    }
    context = _context(values, root=str(tmp_path))

    result = build_table_row_store(context, build_index_columns(context))
    store = result.store
    adapter = TableRowSourceAdapter.from_services(
        store,
        config=SourceBackedConfig(
            thumb_size=64,
            thumb_quality=70,
            include_source_in_search=True,
            remote_header_bytes=128,
            remote_dim_workers=1,
            remote_dim_workers_max=1,
        ),
        services=SourceBackedServices(
            normalize_item_path=lambda path: path.strip("/"),
            canonical_sidecar_key=lambda path: "/" + path.strip("/"),
            is_s3_uri=is_s3_uri,
            is_http_url=is_http_url,
            resolve_local_source=lambda raw_source: str(tmp_path / raw_source),
            read_dimensions_from_bytes=read_dimensions_from_bytes,
            progress=lambda _done, _total, _label: None,
        ),
    )

    assert result.skipped_local_missing == 0
    assert adapter.exists("/gallery/cat.jpg")
    assert adapter.get_source_path("gallery/cat.jpg") == source
    assert adapter.read_bytes("/gallery/cat.jpg") == image_path.read_bytes()
    assert adapter.size("/gallery/cat.jpg") == image_path.stat().st_size
    assert adapter.get_dimensions("/gallery/cat.jpg") == (0, 0)
    assert adapter.row_index_for_path("/gallery/cat.jpg") == 0
    assert adapter.etag("/gallery/cat.jpg") == f"7-{image_path.stat().st_size}"
    assert store.materialized_item_count == 0

    store.update_dimensions("/gallery/cat.jpg", (13, 7), size=321)

    assert adapter.get_dimensions("/gallery/cat.jpg") == (13, 7)
    assert adapter.size("/gallery/cat.jpg") == 321
    assert store.materialized_item_count == 0

    item = store.materialize_item(0)
    assert (item.width, item.height, item.size) == (13, 7, 321)


def test_row_store_allocates_slot_map_only_when_rows_are_skipped() -> None:
    values = {
        "source": [None, "/data/cat.jpg"],
        "path": [None, "animals/cat.jpg"],
        "width": [0, 12],
        "height": [0, 9],
    }
    context = _context(values, skip_dimension_probe=True)

    result = build_table_row_store(context, build_index_columns(context))
    store = result.store

    assert store.row_to_slot == [-1, 0]
    assert store.path_for_row_index(0) is None
    assert store.path_for_row_index(1) == "animals/cat.jpg"
    assert store.row_index_for_path("animals/cat.jpg") == 1
    assert store.materialize_item(1).name == "cat.jpg"
