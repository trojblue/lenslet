from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints

import pytest
from PIL import Image

from lenslet.media_errors import RemoteMediaNotFoundError, RemoteMediaReadError
import lenslet.http_safety as http_safety
import lenslet.storage.dataset.paths as dataset_paths
from lenslet.storage.source.catalog import SourceCatalog
from lenslet.storage.source.state import SourceBackedIndexState, SourceRowIndexState
import lenslet.storage.s3 as s3
import lenslet.storage.source.backed as source_backed
import lenslet.storage.source.media as source_media
import lenslet.storage.source.paths as source_paths
import lenslet.storage.table as table_storage
import lenslet.storage.table.index as table_index
import lenslet.storage.image_media as image_media
import lenslet.storage.table.schema as table_schema
from lenslet.storage.local import LocalStorage


@dataclass(frozen=True)
class _SourceItem:
    path: str
    name: str = "image.jpg"
    mime: str = "image/jpeg"
    width: int = 10
    height: int = 8
    size: int = 80
    mtime: float = 1.0
    url: str | None = None
    source: str | None = None
    metrics: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.metrics is None:
            object.__setattr__(self, "metrics", {})


def _png_bytes(size: tuple[int, int] = (13, 7)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=(10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _table_index_context() -> table_index.TableIndexInput:
    data = table_index.TableIndexData(
        root=None,
        row_count=1,
        column_values={
            "source": ["/tmp/cat.jpg"],
            "path": ["animals/cat.jpg"],
            "metrics": [
                {
                    "score": "0.75",
                    "note": "sharp",
                    "nan_score": math.nan,
                    "infinite_score": "Infinity",
                    "__index_level_0__": 2,
                }
            ],
            "metric_score": ["0.5"],
            "quality_score": [math.inf],
            "loss_metric": [math.nan],
            "label": ["cat"],
            "__index_level_1__": ["hidden"],
        },
        columns=[
            "source",
            "path",
            "metrics",
            "metric_score",
            "quality_score",
            "loss_metric",
            "label",
            "__index_level_1__",
        ],
        source_column="source",
        path_column="path",
        name_column=None,
        mime_column=None,
        width_column=None,
        height_column=None,
        size_column=None,
        mtime_column=None,
        metrics_column="metrics",
        categorical_columns=(),
        reserved_columns={"source", "path", "metrics"},
        local_prefix=None,
        s3_prefixes={},
        s3_use_bucket=False,
        image_exts=(".jpg", ".png"),
    )
    return table_index.TableIndexInput(
        table=data,
        policy=table_index.TableIndexPolicy(
            allow_local=True,
            skip_dimension_probe=False,
            skip_local_realpath_validation=True,
        ),
        source_resolver=table_index.TableSourceResolver(
            guess_mime=lambda name: "image/jpeg",
            allows_extensionless_source_image=lambda source: False,
            resolve_local_source=lambda source: source,
            resolve_local_source_lexical=lambda source: source,
        ),
        progress=lambda _done, _total, _leaf: None,
    )


def test_image_media_reads_dimensions_from_image_bytes() -> None:
    assert image_media.read_dimensions_from_bytes(_png_bytes((13, 7)), ".png") == (13, 7)
    assert image_media.read_dimensions_from_bytes(b"not an image", ".png") is None
    assert image_media._kind_from_extension("jpeg") == "jpeg"
    assert image_media.guess_image_mime("scan.webp") == "image/webp"
    assert image_media.normalize_image_mime("image/jpg", "scan.png") == "image/jpeg"
    assert image_media.normalize_image_mime("application/octet-stream", "scan.png") == "image/png"


def test_http_safety_accepts_only_http_urls() -> None:
    assert http_safety.require_http_url("https://example.com/image.jpg") == "https://example.com/image.jpg"
    request = http_safety.http_request("http://example.com/health", method="HEAD")
    assert request.get_method() == "HEAD"

    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        http_safety.require_http_url("file:///tmp/image.jpg")
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        http_safety.http_request("s3://bucket/key")


def test_local_storage_resolve_path_preserves_commonpath_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = LocalStorage(str(tmp_path))

    def fail_commonpath(_paths: list[str]) -> str:
        raise ValueError("mixed drives")

    monkeypatch.setattr("lenslet.storage.local.storage.os.path.commonpath", fail_commonpath)

    with pytest.raises(ValueError, match="invalid path") as exc_info:
        storage.resolve_path("/image.jpg")

    assert isinstance(exc_info.value.__cause__, ValueError)
    assert "mixed drives" in str(exc_info.value.__cause__)


def test_table_schema_resolves_columns_and_coerces_values() -> None:
    columns = ["image_path", "score", "created_at"]
    data = {
        "image_path": ["cat.jpg", ""],
        "score": ["0.25", "not-a-number"],
        "created_at": ["2026-05-30T12:00:00+00:00", None],
    }

    assert table_schema.resolve_source_column(
        columns,
        data,
        None,
        loadable_threshold=0.5,
        sample_size=5,
        allow_local=True,
        is_loadable_value=lambda value: value.endswith(".jpg"),
    ) == "image_path"
    assert table_schema.resolve_named_column(columns, ("missing", "score")) == "score"
    assert table_schema.coerce_float("0.25") == 0.25
    assert table_schema.coerce_float("not-a-number") is None
    assert table_schema.coerce_int("42") == 42
    assert table_schema.coerce_timestamp(datetime(2026, 5, 30, tzinfo=timezone.utc)) is not None


def test_storage_normalizer_annotations_use_object_boundaries() -> None:
    assert get_type_hints(table_schema.coerce_float)["value"] is object
    assert get_type_hints(table_schema.coerce_int)["value"] is object
    assert get_type_hints(table_schema.coerce_timestamp)["value"] is object
    assert get_type_hints(source_paths.compute_s3_prefixes)["values"] == Iterable[object]
    assert get_type_hints(source_paths.compute_local_prefix)["values"] == Iterable[object]


def test_source_path_helpers_preserve_visible_local_prefix_and_names(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    direct = root / "batch" / "cat.tar.gz"
    sibling = root / "batch" / "dog.jpg"
    nested = root / "batch" / "nested" / "bird.jpg"
    branch_a = root / "groups" / "cats" / "one.jpg"
    branch_b = root / "groups" / "dogs" / "two.jpg"
    direct.parent.mkdir(parents=True)
    nested.parent.mkdir(parents=True)
    branch_a.parent.mkdir(parents=True)
    branch_b.parent.mkdir(parents=True)
    for path in (direct, sibling, nested, branch_a, branch_b):
        path.write_bytes(b"x")

    local_prefix = source_paths.compute_local_prefix([direct, sibling])

    assert local_prefix == str(root)
    assert source_paths.derive_logical_path(
        str(direct),
        root=None,
        local_prefix=local_prefix,
        s3_prefixes={},
        s3_use_bucket=False,
    ) == "batch/cat.tar.gz"
    assert source_paths.compute_local_prefix([direct, nested]) == str(root)
    assert source_paths.compute_local_prefix([branch_a, branch_b]) == str(root / "groups")
    assert source_paths.extract_name("https://cdn.example.test/images/cat.jpg?size=small") == "cat.jpg"
    assert source_paths.dedupe_path("batch/cat.tar.gz", {"batch/cat.tar.gz"}) == "batch/cat.tar-2.gz"


def test_table_index_extracts_metrics_and_display_fields() -> None:
    context = _table_index_context()

    assert table_index.extract_row_metrics(context, 0) == {"metric_score": 0.5}
    assert table_index.extract_row_metrics_map(context, 0) == {"score": 0.75}
    assert table_index.extract_row_display_fields(context, 0) == {
        "metrics": {"note": "sharp"},
        "label": "cat",
    }


def test_source_catalog_normalizes_candidates_and_scopes_items() -> None:
    state = SourceBackedIndexState[_SourceItem](
        items={
            "/animals/cat.jpg": _SourceItem(path="/animals/cat.jpg"),
            "/plants/oak.jpg": _SourceItem(path="/plants/oak.jpg"),
        },
        source_paths={
            "/animals/cat.jpg": "/data/cat.jpg",
            "animals/cat.jpg": "/data/cat-relative.jpg",
        },
    )
    catalog = SourceCatalog(state=state, normalize_item_path=lambda path: path.strip("/"))

    assert catalog.path_candidates("/animals/cat.jpg") == (
        "/animals/cat.jpg",
        "animals/cat.jpg",
    )
    assert catalog.lookup_source_path("animals/cat.jpg") == "/data/cat-relative.jpg"
    assert catalog.source_for_path("/animals/cat.jpg") == "/data/cat.jpg"
    assert catalog.count_in_scope("/animals") == 1
    assert [item.path for item in catalog.items_in_scope("/animals")] == ["/animals/cat.jpg"]


def test_source_backed_guess_mime_uses_image_fallbacks() -> None:
    assert source_backed.guess_mime("cat.jpg") == "image/jpeg"
    assert source_backed.guess_mime("scan.webp") == "image/webp"
    assert source_backed.guess_mime("unknown") == "image/jpeg"


def test_dataset_paths_trim_shared_remote_prefixes_and_keep_hosts_when_needed() -> None:
    sources = [
        "s3://bucket-a/batch/one/cat.jpg",
        "s3://bucket-a/batch/two/dog.jpg",
        "s3://bucket-b/batch/three/bird.jpg",
        "https://cdn.example.test/items/a.jpg",
        "https://other.example.test/items/b.jpg",
    ]

    prefixes = dataset_paths.dataset_source_prefixes(sources)

    assert dataset_paths.dataset_relative_path("s3://bucket-a/batch/one/cat.jpg", prefixes) == (
        "bucket-a/one/cat.jpg"
    )
    assert dataset_paths.dataset_relative_path("https://cdn.example.test/items/a.jpg", prefixes) == (
        "cdn.example.test/a.jpg"
    )
    assert dataset_paths.dataset_logical_relative_path("demo", "folder/cat.jpg") == "demo/folder/cat.jpg"
    assert dataset_paths.dataset_folder_norm("/demo/folder/cat.jpg") == "demo/folder"


def test_source_backed_base_provides_common_item_lookup_methods() -> None:
    class _Storage(source_backed.SourceBackedStorageBase[_SourceItem]):
        pass

    storage = _Storage()
    storage._initialize_source_backed_state(
        config=source_backed.SourceBackedConfig(
            thumb_size=64,
            thumb_quality=70,
            include_source_in_search=True,
            remote_header_bytes=128,
            remote_dim_workers=1,
            remote_dim_workers_max=1,
        ),
        services=source_backed.SourceBackedServices(
            normalize_item_path=lambda path: "/" + path.strip("/"),
            canonical_sidecar_key=lambda path: "/" + path.strip("/"),
            is_s3_uri=lambda source: source.startswith("s3://"),
            is_http_url=lambda source: source.startswith("http://") or source.startswith("https://"),
            resolve_local_source=lambda source: source,
            read_dimensions_from_bytes=lambda _raw, _name: None,
            progress=lambda _done, _total, _label: None,
        ),
    )
    storage._bind_source_state(
        SourceBackedIndexState[_SourceItem](
            items={"/cat.jpg": _SourceItem(path="/cat.jpg", size=42, mtime=7.0)},
            source_paths={"/cat.jpg": "/data/cat.jpg"},
        )
    )

    assert storage.exists("cat.jpg") is True
    assert storage.size("/cat.jpg") == 42
    assert storage.etag("cat.jpg") == "7-42"
    assert storage.row_index_for_path("cat.jpg") is None

    storage._bind_row_index_state(SourceRowIndexState(path_to_row={"/cat.jpg": 3}))
    assert storage.row_index_for_path("cat.jpg") == 3


def test_source_media_service_presigns_and_classifies_remote_errors(tmp_path: Path) -> None:
    class _Service(source_media.MediaReadService):
        def get_presigned_url(self, s3_uri: str, expires_in: int = 3600) -> str:
            return f"https://signed/{s3_uri}"

    class _RemoteException(Exception):
        def __init__(self, code: str) -> None:
            super().__init__(code)
            self.response = {"Error": {"Code": code}}

    service = _Service(
        remote_header_bytes=256,
        resolve_local_source=lambda source: str(tmp_path / source),
        is_s3_uri=lambda source: source.startswith("s3://"),
        is_http_url=lambda source: source.startswith("https://"),
        read_dimensions_from_bytes=lambda _data, _ext: None,
    )

    assert service.remote_access_url("https://example.test/cat.jpg") == "https://example.test/cat.jpg"
    assert service.remote_access_url("s3://bucket/cat.jpg") == "https://signed/s3://bucket/cat.jpg"
    assert service.remote_access_url("local/cat.jpg") is None

    class _FailingPresignService(_Service):
        def get_presigned_url(self, s3_uri: str, expires_in: int = 3600) -> str:
            raise RuntimeError(f"blocked presign: {s3_uri}")

    failing_service = _FailingPresignService(
        remote_header_bytes=256,
        resolve_local_source=lambda source: str(tmp_path / source),
        is_s3_uri=lambda source: source.startswith("s3://"),
        is_http_url=lambda source: source.startswith("https://"),
        read_dimensions_from_bytes=lambda _data, _ext: None,
    )
    assert failing_service.remote_access_url("s3://bucket/cat.jpg") is None

    with pytest.raises(RemoteMediaReadError) as permission_error:
        service._raise_remote_read_error(
            "/cat.jpg",
            "s3://bucket/cat.jpg",
            _RemoteException("AccessDenied"),
            default_category="s3",
        )
    assert permission_error.value.category == "permission"

    with pytest.raises(RemoteMediaNotFoundError):
        service._raise_remote_read_error(
            "/cat.jpg",
            "s3://bucket/cat.jpg",
            _RemoteException("NoSuchKey"),
            default_category="s3",
        )


def test_table_source_header_probe_only_swallows_expected_presign_failures() -> None:
    storage = object.__new__(table_storage.TableStorage)

    def expected_failure(_source: str) -> str:
        raise RuntimeError("credential unavailable")

    storage._get_presigned_url = expected_failure
    storage._get_safe_remote_header_info = lambda _url, _name: ((10, 10), 256)

    assert storage._source_header_is_image("s3://bucket/no-extension") is False

    def unexpected_failure(_source: str) -> str:
        raise AssertionError("programmer bug")

    storage._get_presigned_url = unexpected_failure

    with pytest.raises(AssertionError, match="programmer bug"):
        storage._source_header_is_image("s3://bucket/no-extension")


def test_s3_client_uses_session_factory_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Session:
        def client(self, service_name: str) -> tuple[str, str]:
            return ("session-client", service_name)

    fake_boto3 = SimpleNamespace(session=SimpleNamespace(Session=lambda: _Session()))
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    session, client = s3.create_s3_client()

    assert isinstance(session, _Session)
    assert client == ("session-client", "s3")
