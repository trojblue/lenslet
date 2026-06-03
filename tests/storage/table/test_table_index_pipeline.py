from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from lenslet.storage.source import paths as source_paths
from lenslet.storage.table import TableStorage, TableStorageOptions
from lenslet.storage.source.paths import LocalSourcePathError, resolve_local_source, resolve_local_source_lexical


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 9), color=(60, 90, 120)).save(path, format="JPEG")


def _root_items(storage: TableStorage) -> list:
    index = storage.load_index("/")
    assert index is not None
    return list(index.items)


def _table_storage(table, **options) -> TableStorage:
    return TableStorage(table, options=TableStorageOptions(**options))


def test_metrics_column_overrides_scalar_metric_values(tmp_path: Path) -> None:
    image_path = tmp_path / "one.jpg"
    _make_image(image_path)

    rows = [
        {
            "source": str(image_path),
            "path": "one.jpg",
            "clip_aesthetic": 0.11,
            "metrics": {
                "clip_aesthetic": 0.91,
                "quality_score": 0.42,
            },
        }
    ]

    storage = _table_storage(rows, skip_dimension_probe=True)
    item = _root_items(storage)[0]

    assert abs(item.metrics["clip_aesthetic"] - 0.91) < 1e-9
    assert abs(item.metrics["quality_score"] - 0.42) < 1e-9


def test_internal_scalar_metric_columns_are_filtered(tmp_path: Path) -> None:
    image_path = tmp_path / "one.jpg"
    _make_image(image_path)

    rows = [
        {
            "source": str(image_path),
            "path": "one.jpg",
            "__index_level_0__": 17,
            "quality_score": 0.42,
        }
    ]

    storage = _table_storage(rows, skip_dimension_probe=True)
    item = _root_items(storage)[0]

    assert item.path == "one.jpg"
    assert item.metrics == {"quality_score": 0.42}


def test_internal_metrics_map_entries_are_filtered(tmp_path: Path) -> None:
    image_path = tmp_path / "one.jpg"
    _make_image(image_path)

    rows = [
        {
            "source": str(image_path),
            "path": "one.jpg",
            "metrics": {
                "__index_level_0__": 17,
                "quality_score": 0.42,
            },
        }
    ]

    storage = _table_storage(rows, skip_dimension_probe=True)
    item = _root_items(storage)[0]

    assert item.path == "one.jpg"
    assert item.metrics == {"quality_score": 0.42}


def test_table_metric_candidates_ignore_ids_and_bookkeeping_fields(tmp_path: Path) -> None:
    image_path = tmp_path / "one.jpg"
    _make_image(image_path)

    rows = [
        {
            "source": str(image_path),
            "path": "one.jpg",
            "left_image_id": "123",
            "hamming_distance": 2,
            "quality_score": 0.42,
            "q1_form_structural_quality__confidence": 0.91,
            "q1_form_structural_quality__pending_gpt_q4_value_view": 1,
        }
    ]

    storage = _table_storage(rows, skip_dimension_probe=True)
    item = _root_items(storage)[0]

    assert item.metrics == {
        "hamming_distance": 2.0,
        "quality_score": 0.42,
        "q1_form_structural_quality__confidence": 0.91,
    }
    assert storage.sidecar_enrichment_for_path("/one.jpg") == {
        "table_fields": {
            "left_image_id": "123",
            "q1_form_structural_quality__pending_gpt_q4_value_view": 1,
        }
    }


def test_string_classification_columns_stay_in_table_fields(tmp_path: Path) -> None:
    first = tmp_path / "one.jpg"
    second = tmp_path / "two.jpg"
    _make_image(first)
    _make_image(second)

    rows = [
        {
            "source": str(first),
            "path": "one.jpg",
            "l0p_style_family": "anime",
        },
        {
            "source": str(second),
            "path": "two.jpg",
            "l0p_style_family": "photographic",
        },
    ]

    storage = _table_storage(rows, skip_dimension_probe=True)
    items = _root_items(storage)

    assert items[0].metrics == {}
    assert items[0].metric_labels == {}
    assert items[1].metrics == {}
    assert items[1].metric_labels == {}
    assert storage.sidecar_enrichment_for_path("/one.jpg") == {
        "table_fields": {"l0p_style_family": "anime"}
    }


def test_table_browse_cache_signature_tracks_payload_metric_changes(tmp_path: Path) -> None:
    image_path = tmp_path / "one.jpg"
    _make_image(image_path)

    def make_storage(score: float) -> TableStorage:
        return _table_storage(
            [
                {
                    "source": str(image_path),
                    "path": "one.jpg",
                    "quality_score": score,
                }
            ],
            skip_dimension_probe=True,
        )

    first = make_storage(0.42)
    second = make_storage(0.84)

    assert first.browse_cache_signature() != second.browse_cache_signature()


def test_duplicate_logical_paths_keep_stable_row_mappings(tmp_path: Path) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    _make_image(first)
    _make_image(second)

    rows = [
        {"source": str(first), "path": "dup.jpg"},
        {"source": str(second), "path": "dup.jpg"},
    ]

    storage = _table_storage(rows, skip_dimension_probe=True)

    assert storage.path_for_row_index(0) == "dup.jpg"
    assert storage.path_for_row_index(1) == "dup-2.jpg"
    assert storage.row_index_for_path("dup.jpg") == 0
    assert storage.row_index_for_path("dup-2.jpg") == 1

    root_index = storage.load_index("/")
    assert [item.path for item in root_index.items] == ["dup.jpg", "dup-2.jpg"]


def test_table_storage_startup_and_counts_do_not_materialize_row_items() -> None:
    rows = [
        {
            "source": f"https://example.test/gallery/img_{idx:04d}.jpg",
            "path": f"gallery/img_{idx:04d}.jpg",
            "width": 12,
            "height": 9,
        }
        for idx in range(25)
    ]

    storage = _table_storage(rows, skip_dimension_probe=True, allow_local=False)
    row_store = storage._row_store

    assert row_store is not None
    assert row_store.materialized_item_count == 0
    assert storage._items == {}
    assert storage._indexes == {}
    assert storage.count_in_scope("/gallery") == 25
    assert row_store.materialized_item_count == 0

    window = storage.items_in_scope_window("/gallery", 5, 7)

    assert [item.path for item in window] == [
        f"gallery/img_{idx:04d}.jpg"
        for idx in range(5, 12)
    ]
    assert row_store.materialized_item_count == 7


def test_local_resolution_uses_realpath_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "one.jpg"
    _make_image(image_path)
    stat = image_path.stat()
    rows = [
        {
            "source": "one.jpg",
            "path": "one.jpg",
            "size": int(stat.st_size),
            "mtime": float(stat.st_mtime),
            "width": 12,
            "height": 9,
        }
    ]

    def _boom(self: TableStorage, source: str) -> str:
        raise AssertionError("strict local resolver called")

    monkeypatch.setattr(TableStorage, "_resolve_local_source", _boom)
    with pytest.raises(AssertionError, match="strict local resolver called"):
        _table_storage(
            rows,
            root=str(tmp_path),
            source_column="source",
            path_column="path",
            skip_dimension_probe=True,
        )


def test_skip_local_realpath_validation_bypasses_strict_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_path = tmp_path / "one.jpg"
    _make_image(image_path)
    stat = image_path.stat()
    rows = [
        {
            "source": "one.jpg",
            "path": "one.jpg",
            "size": int(stat.st_size),
            "mtime": float(stat.st_mtime),
            "width": 12,
            "height": 9,
        }
    ]

    def _boom(self: TableStorage, source: str) -> str:
        raise AssertionError("strict local resolver called")

    monkeypatch.setattr(TableStorage, "_resolve_local_source", _boom)
    storage = _table_storage(
        rows,
        root=str(tmp_path),
        source_column="source",
        path_column="path",
        skip_dimension_probe=True,
        skip_local_realpath_validation=True,
    )
    assert storage.exists("one.jpg")


def test_skip_local_realpath_validation_still_blocks_lexical_escape(tmp_path: Path) -> None:
    rows = [
        {
            "source": "../outside.jpg",
            "path": "outside.jpg",
            "size": 0,
            "mtime": 0.0,
            "width": 0,
            "height": 0,
        }
    ]
    storage = _table_storage(
        rows,
        root=str(tmp_path),
        source_column="source",
        path_column="path",
        skip_dimension_probe=True,
        skip_local_realpath_validation=True,
    )
    assert not storage.exists("outside.jpg")


def test_local_source_path_errors_chain_commonpath_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_commonpath(_paths: list[str]) -> str:
        raise ValueError("mixed path roots")

    monkeypatch.setattr(source_paths.os.path, "commonpath", fail_commonpath)

    with pytest.raises(LocalSourcePathError) as strict_error:
        resolve_local_source(
            "one.jpg",
            root=str(tmp_path),
            root_real=str(tmp_path.resolve()),
            allow_local=True,
        )
    assert strict_error.value.reason == "invalid"
    assert isinstance(strict_error.value.__cause__, ValueError)

    with pytest.raises(LocalSourcePathError) as lexical_error:
        resolve_local_source_lexical(
            "one.jpg",
            root=str(tmp_path),
            allow_local=True,
        )
    assert lexical_error.value.reason == "invalid"
    assert isinstance(lexical_error.value.__cause__, ValueError)


def test_unexpected_local_resolver_value_error_is_not_converted_to_boundary_skip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "source": "one.jpg",
            "path": "one.jpg",
            "size": 0,
            "mtime": 0.0,
            "width": 0,
            "height": 0,
        }
    ]

    def fail_resolver(self: TableStorage, _source: str) -> str:
        raise ValueError("unexpected resolver failure")

    monkeypatch.setattr(TableStorage, "_resolve_local_source", fail_resolver)
    with pytest.raises(ValueError, match="unexpected resolver failure"):
        _table_storage(
            rows,
            root=str(tmp_path),
            source_column="source",
            path_column="path",
            skip_dimension_probe=True,
        )


def test_s3_rows_honor_explicit_path_column(tmp_path: Path) -> None:
    rows = [
        {
            "source": "s3://bucket/raw/first.jpg",
            "display_path": "logical/alpha.jpg",
        },
        {
            "source": "s3://bucket/raw/nested/second.jpg",
            "display_path": "logical/nested/beta.jpg",
        },
    ]

    storage = _table_storage(
        rows,
        root=str(tmp_path),
        source_column="source",
        path_column="display_path",
        skip_dimension_probe=True,
    )

    assert [item.path for item in storage.items_in_scope("/")] == [
        "logical/alpha.jpg",
        "logical/nested/beta.jpg",
    ]
    assert storage.path_for_row_index(0) == "logical/alpha.jpg"
    assert storage.path_for_row_index(1) == "logical/nested/beta.jpg"


def test_s3key_source_column_allows_extensionless_urls_without_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_probe(self: TableStorage, source: str) -> bool:
        raise AssertionError(f"s3key should not need an extensionless probe: {source}")

    monkeypatch.setattr(TableStorage, "_source_header_is_image", _fail_probe)
    rows = [
        {
            "s3key": "https://images.example.test/r2/encoded-image-key",
            "width": 12,
            "height": 9,
        }
    ]

    storage = _table_storage(rows, skip_dimension_probe=True)

    assert storage.count_in_scope("/") == 1
    assert storage.path_for_row_index(0) == "images.example.test/r2/encoded-image-key"


def test_remote_url_path_column_is_normalized_to_lenslet_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_probe(self: TableStorage, source: str) -> bool:
        raise AssertionError(f"s3key should not need an extensionless probe: {source}")

    source_url = "https://img.metanomaly.co/r2/encoded-image-key"
    monkeypatch.setattr(TableStorage, "_source_header_is_image", _fail_probe)

    storage = _table_storage(
        [
            {
                "s3key": source_url,
                "path": source_url,
                "width": 12,
                "height": 9,
            }
        ],
        skip_dimension_probe=True,
    )

    item = storage.items_in_scope("/")[0]
    assert item.path == "img.metanomaly.co/r2/encoded-image-key"
    assert item.source == source_url
    assert item.url == source_url
    assert storage.path_for_row_index(0) == "img.metanomaly.co/r2/encoded-image-key"
    assert storage.get_source_path("/img.metanomaly.co/r2/encoded-image-key") == source_url


def test_explicit_extensionless_source_column_uses_one_image_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probed: list[str] = []

    def _probe(self: TableStorage, source: str) -> bool:
        probed.append(source)
        return True

    monkeypatch.setattr(TableStorage, "_source_header_is_image", _probe)
    rows = [
        {
            "asset_url": "https://images.example.test/r2/encoded-image-key",
            "width": 12,
            "height": 9,
        },
        {
            "asset_url": "https://images.example.test/r2/second-encoded-key",
            "width": 11,
            "height": 8,
        },
    ]

    storage = _table_storage(rows, source_column="asset_url", skip_dimension_probe=True)

    assert probed == ["https://images.example.test/r2/encoded-image-key"]
    assert storage.count_in_scope("/") == 2


def test_explicit_extensionless_probe_trust_is_limited_to_sample_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(TableStorage, "_source_header_is_image", lambda self, source: True)
    rows = [
        {
            "asset_url": "https://images.example.test/r2/encoded-image-key",
            "width": 12,
            "height": 9,
        },
        {
            "asset_url": "https://other.example.test/r2/second-encoded-key",
            "width": 11,
            "height": 8,
        },
    ]

    storage = _table_storage(rows, source_column="asset_url", skip_dimension_probe=True)

    assert storage.count_in_scope("/") == 1
    assert storage.path_for_row_index(0) == "images.example.test/r2/encoded-image-key"
    assert storage.path_for_row_index(1) is None


def test_auto_detected_extensionless_source_column_uses_one_image_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probed: list[str] = []

    def _probe(self: TableStorage, source: str) -> bool:
        probed.append(source)
        return True

    monkeypatch.setattr(TableStorage, "_source_header_is_image", _probe)
    rows = [
        {
            "asset_url": "https://images.example.test/r2/encoded-image-key",
            "width": 12,
            "height": 9,
            "deepghs_ai_prob": 0.91,
        },
        {
            "asset_url": "https://images.example.test/r2/second-encoded-key",
            "width": 11,
            "height": 8,
            "larry_ai_prob": 0.82,
        }
    ]

    storage = _table_storage(rows, skip_dimension_probe=True)

    assert probed == ["https://images.example.test/r2/encoded-image-key"]
    assert storage.count_in_scope("/") == 2
    items = list(storage.items_in_scope("/"))
    assert items[0].metrics == {"deepghs_ai_prob": 0.91}
    assert items[1].metrics == {"larry_ai_prob": 0.82}


def test_explicit_extensionless_source_column_skips_rows_when_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(TableStorage, "_source_header_is_image", lambda self, source: False)
    rows = [
        {
            "asset_url": "https://images.example.test/r2/encoded-image-key",
            "width": 12,
            "height": 9,
        }
    ]

    storage = _table_storage(rows, source_column="asset_url", skip_dimension_probe=True)

    assert storage.count_in_scope("/") == 0


def test_absolute_local_source_outside_root_is_blocked(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.jpg"
    _make_image(outside)

    rows = [
        {
            "source": str(outside),
            "path": "outside.jpg",
            "size": int(outside.stat().st_size),
            "mtime": float(outside.stat().st_mtime),
            "width": 12,
            "height": 9,
        }
    ]

    storage = _table_storage(
        rows,
        root=str(tmp_path),
        source_column="source",
        path_column="path",
        skip_dimension_probe=True,
    )

    assert not storage.exists("outside.jpg")


def test_absolute_local_source_outside_root_reports_boundary(tmp_path: Path, capsys) -> None:
    outside = tmp_path.parent / "outside-reported.jpg"
    _make_image(outside)

    _table_storage(
        [
            {
                "source": str(outside),
                "path": "outside-reported.jpg",
                "size": int(outside.stat().st_size),
                "mtime": float(outside.stat().st_mtime),
                "width": 12,
                "height": 9,
            }
        ],
        root=str(tmp_path),
        source_column="source",
        path_column="path",
        skip_dimension_probe=True,
    )

    captured = capsys.readouterr()
    assert "outside base_dir boundary" in captured.out
    assert str(tmp_path) in captured.out


def test_local_symlink_target_outside_root_reports_resolved_boundary(
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "gallery"
    outside = tmp_path / "source-images" / "outside.jpg"
    symlink = root / "linked.jpg"
    _make_image(outside)
    symlink.parent.mkdir(parents=True, exist_ok=True)
    symlink.symlink_to(outside)

    storage = _table_storage(
        [
            {
                "source": "linked.jpg",
                "path": "linked.jpg",
                "size": int(outside.stat().st_size),
                "mtime": float(outside.stat().st_mtime),
                "width": 12,
                "height": 9,
            }
        ],
        root=str(root),
        source_column="source",
        path_column="path",
        skip_dimension_probe=True,
    )

    captured = capsys.readouterr()
    assert not storage.exists("linked.jpg")
    assert "inside base_dir but resolve outside it" in captured.out
    assert "symlinks point outside the launched directory" in captured.out
    assert str(root) in captured.out


def test_skip_local_realpath_validation_blocks_absolute_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-lexical.jpg"
    _make_image(outside)

    rows = [
        {
            "source": str(outside),
            "path": "outside-lexical.jpg",
            "size": int(outside.stat().st_size),
            "mtime": float(outside.stat().st_mtime),
            "width": 12,
            "height": 9,
        }
    ]

    storage = _table_storage(
        rows,
        root=str(tmp_path),
        source_column="source",
        path_column="path",
        skip_dimension_probe=True,
        skip_local_realpath_validation=True,
    )

    assert not storage.exists("outside-lexical.jpg")
