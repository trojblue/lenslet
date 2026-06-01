from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from lenslet.storage.memory.cache import MemoryCacheInvalidationMixin
from lenslet.storage.memory.media import MemoryMediaMixin
from lenslet.storage.sidecar_state import SidecarStateMixin
from lenslet.storage.progress_state import StorageProgressMixin


class _ProgressBar:
    def __init__(self) -> None:
        self.updated: tuple[int, int, str] | None = None

    def update(self, done: int, total: int, label: str) -> None:
        self.updated = (done, total, label)

    def snapshot(self) -> dict[str, int | str | bool | None]:
        return {"done": 3, "total": 5, "label": "local", "active": True}


class _ProgressHost(StorageProgressMixin):
    def __init__(self) -> None:
        self._progress_bar = _ProgressBar()
        self._browse_signature = "signature"


class _SidecarHost(SidecarStateMixin):
    def __init__(self) -> None:
        self._sidecars: dict[str, dict[str, Any]] = {
            "/a.jpg": {"tags": ["kept"]},
            "/nested/b.jpg": {"notes": "visible"},
        }

    def _sidecar_snapshot_key(self, path: str) -> str:
        return "/" + path.strip("/").removeprefix("./")

    def _sidecar_replace_key(self, path: str) -> str:
        return "/" + path.strip("/")


class _LeafBatch:
    def __init__(self) -> None:
        self.cleared = 0

    def clear(self) -> None:
        self.cleared += 1


class _CacheHost(MemoryCacheInvalidationMixin):
    def __init__(self) -> None:
        self.bumped = 0
        self._leaf_batch = _LeafBatch()
        self._indexes = {"": object(), "folder": object(), "folder/sub": object()}
        self._recursive_indexes = {"folder": object(), "other": object()}
        self._thumbnails = {"/folder/a.jpg": b"a", "/other/b.jpg": b"b"}
        self._sidecars = {"/folder/a.jpg": {"tags": []}, "/other/b.jpg": {"tags": []}}
        self._dimensions = {"/folder/a.jpg": (1, 2), "/other/b.jpg": (3, 4)}

    def _bump_browse_generation(self) -> None:
        self.bumped += 1

    def _normalize_path(self, path: str) -> str:
        return path.strip("/")

    def _cache_item_key(self, path: str) -> str:
        return self._canonical_sidecar_key(path)

    def _canonical_sidecar_key(self, path: str) -> str:
        return "/" + path.strip("/")


class _MediaHost(MemoryMediaMixin):
    def __init__(self, source_path: Path) -> None:
        self.source_path = source_path
        self.thumb_size = 16
        self.thumb_quality = 70
        self._dimensions: dict[str, tuple[int, int]] = {}
        self._thumbnails: dict[str, bytes] = {}

    def _abs_path(self, path: str) -> str:
        _ = path
        return str(self.source_path)

    def _cache_item_key(self, path: str) -> str:
        return "/" + path.strip("/")

    def etag(self, path: str) -> str | None:
        _ = path
        return "etag"

    def get_source_path(self, logical_path: str) -> str:
        if logical_path == "missing.jpg":
            raise FileNotFoundError(logical_path)
        return logical_path

    def read_bytes(self, path: str) -> bytes:
        _ = path
        return self.source_path.read_bytes()


def test_storage_progress_mixin_updates_and_exposes_state() -> None:
    host = _ProgressHost()

    host._progress(1, 4, "local")

    assert host._progress_bar.updated == (1, 4, "local")
    assert host.indexing_progress()["done"] == 3
    assert host.browse_cache_signature() == "signature"


def test_sidecar_state_mixin_snapshots_and_replaces_with_backend_keys() -> None:
    host = _SidecarHost()

    assert host.sidecar_items()[0][0] == "/a.jpg"
    assert host.sidecar_snapshot_for_paths(["./nested/b.jpg", "missing.jpg"]) == {
        "/nested/b.jpg": {"notes": "visible"}
    }

    host.replace_sidecars({"new.jpg": {"star": True}})

    assert host.sidecar_items() == [("/new.jpg", {"star": True})]


def test_memory_cache_invalidation_mixin_clears_exact_and_subtree_state() -> None:
    host = _CacheHost()

    host.invalidate_cache("folder/a.jpg")

    assert host.bumped == 1
    assert "/folder/a.jpg" not in host._thumbnails
    assert "/folder/a.jpg" not in host._sidecars
    assert "/folder/a.jpg" not in host._dimensions
    assert "folder" in host._indexes

    host.invalidate_subtree("folder", clear_sidecars=False)

    assert host.bumped == 2
    assert host._leaf_batch.cleared == 1
    assert "folder/sub" not in host._indexes
    assert "folder" not in host._recursive_indexes
    assert "/folder/a.jpg" not in host._thumbnails
    assert "/other/b.jpg" in host._sidecars

    host.invalidate_cache()

    assert host.bumped == 3
    assert host._indexes == {}
    assert host._recursive_indexes == {}
    assert host._sidecars == {}


def test_memory_media_mixin_caches_dimensions_thumbnails_and_keys(tmp_path: Path) -> None:
    image_path = tmp_path / "cat.jpg"
    Image.new("RGB", (13, 7), color=(44, 88, 132)).save(image_path, format="JPEG")
    host = _MediaHost(image_path)

    assert host.load_dimensions("cat.jpg") == (13, 7)
    assert host.get_dimensions("cat.jpg") == (13, 7)

    thumbnail = host.get_or_build_thumbnail("cat.jpg")

    assert thumbnail.startswith(b"RIFF")
    assert host.get_cached_thumbnail("cat.jpg") == thumbnail
    assert host.thumbnail_cache_key("cat.jpg").endswith("|16|70|etag")
    assert host.resolve_local_file_path("missing.jpg") is None
    assert host.guess_mime("cat.png") == "image/png"
