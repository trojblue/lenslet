from __future__ import annotations

from collections.abc import Iterable
import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any
from ..base import SidecarState, StorageWriteUnsupportedError, join_storage_path
from ..local.storage import LocalStorage
from .cache import MemoryCacheInvalidationMixin
from .index import (
    BuiltMemoryItem,
    IndexBuildState,
    MemoryBrowseIndex,
    MemoryBrowseItem,
    MemoryIndexBuildError,
    local_index_worker_count,
    root_entry_signature,
)
from .media import MemoryMediaMixin
from ..sidecar_state import SidecarStateMixin, copy_sidecar_state, default_sidecar_state
from ..progress import LeafBatchTracker, ProgressBar
from ..progress_state import StorageProgressMixin
from ..search_text import build_search_haystack, sidecar_source_fields, normalize_search_path, path_in_scope
from ..image_media import guess_image_mime


class MemoryStorage(SidecarStateMixin, MemoryCacheInvalidationMixin, MemoryMediaMixin, StorageProgressMixin):
    """Read-only local storage with in-memory indexes, thumbnails, and sidecar state."""

    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
    LOCAL_INDEX_WORKERS = 16
    LOCAL_INDEX_PARALLEL_MIN_IMAGES = 24
    LOCAL_PROGRESS_MIN_IMAGES = 64
    LEAF_BATCH_MAX_DIRS = 128
    LEAF_BATCH_THRESHOLD = 10
    RECURSIVE_ITEMS_HARD_LIMIT = 10_000

    def __init__(self, root: str, thumb_size: int = 256, thumb_quality: int = 70):
        self.local = LocalStorage(root)
        self.root = root
        self.thumb_size = thumb_size
        self.thumb_quality = thumb_quality
        self._progress_bar = ProgressBar()
        self._leaf_batch = LeafBatchTracker(
            threshold=self.LEAF_BATCH_THRESHOLD,
            list_dir=self.list_dir,
            join=self.join,
            normalize_path=self._normalize_path,
            display_path=self._display_path,
            index_exists=self._index_exists,
        )

        # In-memory caches
        self._indexes: dict[str, MemoryBrowseIndex] = {}
        self._recursive_indexes: dict[str, MemoryBrowseIndex] = {}
        self._thumbnails: dict[str, bytes] = {}  # path -> thumbnail bytes
        self._sidecars: dict[str, SidecarState] = {}  # path -> sidecar state
        self._dimensions: dict[str, tuple[int, int]] = {}  # path -> (w, h)
        self._browse_generation = 0
        self._browse_signature = self._compute_browse_signature()
        self._path_to_row: dict[str, int] = {}
        self._row_index_generation = -1

    def _normalize_path(self, path: str) -> str:
        return path.strip("/") if path else ""

    def _normalize_item_path(self, path: str) -> str:
        return self._normalize_path(path)

    def _canonical_sidecar_key(self, path: str) -> str:
        """Canonical key for sidecar maps (leading slash, no trailing)."""
        p = (path or "").replace("\\", "/").strip()
        if not p:
            return "/"
        p = "/" + p.lstrip("/")
        if p != "/":
            p = p.rstrip("/")
        return p

    def _sidecar_replace_key(self, path: str) -> str:
        return self._canonical_sidecar_key(path)

    def _display_path(self, norm: str) -> str:
        return f"/{norm}" if norm else "/"

    def _cache_item_key(self, path: str) -> str:
        return self._display_path(self._normalize_path(path))

    def _index_exists(self, norm: str) -> bool:
        return norm in self._indexes or norm in self._recursive_indexes

    def _cached_index(self, norm: str, *, recursive: bool) -> MemoryBrowseIndex | None:
        index = self._indexes.get(norm)
        if index is not None:
            return index
        if recursive:
            return self._recursive_indexes.get(norm)
        return None

    def _store_index(self, norm: str, index: MemoryBrowseIndex, *, lightweight: bool) -> None:
        if lightweight:
            self._recursive_indexes[norm] = index
        else:
            self._indexes[norm] = index
            self._recursive_indexes.pop(norm, None)

    def _compute_browse_signature(self) -> str:
        root = self.local.root_real
        try:
            signatures: list[str] = []
            with os.scandir(root) as iterator:
                for entry in iterator:
                    signature = root_entry_signature(entry)
                    if signature is not None:
                        signatures.append(signature)
            signatures.sort()
            payload = "|".join([root, *signatures]).encode("utf-8")
            return hashlib.sha256(payload).hexdigest()
        except OSError as exc:
            logging.getLogger(__name__).debug("Falling back to root path browse signature for %s: %s", root, exc)
            return root

    def _bump_browse_generation(self) -> None:
        self._browse_generation += 1
        self._browse_signature = self._compute_browse_signature()

    def _abs_path(self, path: str) -> str:
        return self.local.resolve_path(path)

    def _is_supported_image(self, name: str) -> bool:
        return name.lower().endswith(self.IMAGE_EXTS)

    def list_dir(self, path: str) -> tuple[list[str], list[str]]:
        """List directory, filtering out auxiliary cache/state files."""
        files, dirs = self.local.list_dir(path)
        # Filter out local auxiliary files from gallery listings.
        files = [
            f for f in files
            if not f.endswith(".json")
            and not f.endswith(".thumbnail")
            and not f.startswith("_")
        ]
        dirs = [d for d in dirs if not d.startswith("_")]
        return files, dirs

    def read_bytes(self, path: str) -> bytes:
        return self.local.read_bytes(path)

    def write_bytes(self, path: str, data: bytes) -> None:
        raise StorageWriteUnsupportedError("memory storage does not support raw writes")

    def exists(self, path: str) -> bool:
        return self.local.exists(path)

    def size(self, path: str) -> int:
        return self.local.size(path)

    def join(self, *parts: str) -> str:
        return join_storage_path(*parts)

    def etag(self, path: str) -> str | None:
        return self.local.etag(path)

    def load_index(self, path: str) -> MemoryBrowseIndex | None:
        """Load a full folder index, building and caching it when absent."""
        norm = self._normalize_path(path)
        cached = self._cached_index(norm, recursive=False)
        if cached is not None:
            return cached
        try:
            return self._build_index(path, lightweight=False)
        except (FileNotFoundError, ValueError):
            return None

    def load_recursive_index(self, path: str) -> MemoryBrowseIndex | None:
        """Load a lightweight recursive index, building and caching it when absent."""
        norm = self._normalize_path(path)
        cached = self._cached_index(norm, recursive=True)
        if cached is not None:
            return cached
        try:
            return self._build_index(path, lightweight=True)
        except (FileNotFoundError, ValueError):
            return None

    def validate_image_path(self, path: str) -> None:
        """Ensure path is a supported image and exists on disk."""
        if not path:
            raise ValueError("empty path")
        if not self._is_supported_image(path):
            raise ValueError("unsupported file type")
        # Resolve to catch traversal attempts even if file is missing
        self._abs_path(path)
        if not self.exists(path):
            raise FileNotFoundError(path)

    def _resolve_build_item_path(
        self,
        full: str,
        *,
        include_dimensions: bool,
        include_file_stat: bool,
    ) -> str | None:
        if not (include_dimensions or include_file_stat):
            return None
        try:
            return self._abs_path(full)
        except (OSError, ValueError) as exc:
            raise MemoryIndexBuildError.from_exception(full, "path resolution", exc) from exc

    def _build_item_file_state(self, full: str, abs_path: str | None, *, include_file_stat: bool) -> tuple[int, float]:
        if not include_file_stat or abs_path is None:
            return 0, 0.0
        try:
            stat = os.stat(abs_path)
        except OSError as exc:
            raise MemoryIndexBuildError.from_exception(full, "stat", exc) from exc
        return stat.st_size, stat.st_mtime

    def _build_item_dimensions(
        self,
        full: str,
        abs_path: str | None,
        *,
        include_dimensions: bool,
    ) -> tuple[int, int, tuple[int, int] | None]:
        width, height = self._dimensions.get(full, (0, 0))
        if not include_dimensions or (width and height) or abs_path is None:
            return width, height, None
        try:
            dims = self._read_dimensions_fast(abs_path)
        except (OSError, ValueError) as exc:
            raise MemoryIndexBuildError.from_exception(full, "dimension probe", exc) from exc
        if dims is None:
            return width, height, None
        return dims[0], dims[1], dims

    def _build_item(
        self,
        path: str,
        name: str,
        idx: int,
        *,
        include_dimensions: bool,
        include_file_stat: bool,
    ) -> BuiltMemoryItem:
        """Build a browse item for a single image file."""
        full = self.join(path, name)
        abs_path = self._resolve_build_item_path(
            full,
            include_dimensions=include_dimensions,
            include_file_stat=include_file_stat,
        )
        size, mtime = self._build_item_file_state(full, abs_path, include_file_stat=include_file_stat)
        width, height, dims = self._build_item_dimensions(
            full,
            abs_path,
            include_dimensions=include_dimensions,
        )
        item = MemoryBrowseItem(
            path=full,
            name=name,
            mime=guess_image_mime(name),
            width=width,
            height=height,
            size=size,
            mtime=mtime,
            source=full,
        )
        return idx, item, dims

    def browse_generation(self) -> int:
        return self._browse_generation

    def _effective_workers(self, total: int) -> int:
        return local_index_worker_count(
            total,
            max_workers=self.LOCAL_INDEX_WORKERS,
            cpu_count=os.cpu_count,
        )

    def _prepare_leaf_batch(self, path: str, norm: str, dirs: list[str], *, lightweight: bool) -> bool:
        # Avoid expensive eager probing when a folder has very high fanout.
        # The probe only drives progress-bar grouping and should not block indexing.
        if (not lightweight) and len(dirs) <= self.LEAF_BATCH_MAX_DIRS:
            self._leaf_batch.maybe_prepare(path, dirs)
        return (not lightweight) and self._leaf_batch.use_batch(norm, dirs)

    def _show_local_index_progress(self, *, lightweight: bool, total: int, use_leaf_batch: bool) -> bool:
        return (not lightweight) and total >= self.LOCAL_PROGRESS_MIN_IMAGES and not use_leaf_batch

    def _index_worker_count(self, *, lightweight: bool, total: int) -> int:
        if lightweight or total < self.LOCAL_INDEX_PARALLEL_MIN_IMAGES:
            return 0
        return self._effective_workers(total)

    def _build_index_item_result(self, path: str, name: str, idx: int, *, lightweight: bool) -> BuiltMemoryItem:
        return self._build_item(
            path,
            name,
            idx,
            include_dimensions=not lightweight,
            include_file_stat=not lightweight,
        )

    def _consume_index_item(self, state: IndexBuildState, result: BuiltMemoryItem) -> None:
        state.consume(
            result,
            dimensions=self._dimensions,
            progress=self._progress,
        )

    def _build_index_items_serial(self, path: str, image_files: list[str], *, lightweight: bool, state: IndexBuildState) -> None:
        for idx, name in enumerate(image_files):
            self._consume_index_item(
                state,
                self._build_index_item_result(path, name, idx, lightweight=lightweight),
            )

    def _build_index_items_parallel(
        self,
        path: str,
        image_files: list[str],
        *,
        lightweight: bool,
        workers: int,
        state: IndexBuildState,
    ) -> None:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self._build_index_item_result, path, name, idx, lightweight=lightweight)
                for idx, name in enumerate(image_files)
            ]
            for future in as_completed(futures):
                self._consume_index_item(state, future.result())

    def _build_index_items(self, path: str, image_files: list[str], *, lightweight: bool, show_progress: bool) -> list[MemoryBrowseItem]:
        state = IndexBuildState.create(len(image_files), show_progress=show_progress)
        if show_progress:
            self._progress(0, state.total, "local")
        workers = self._index_worker_count(lightweight=lightweight, total=state.total)
        if workers:
            self._build_index_items_parallel(path, image_files, lightweight=lightweight, workers=workers, state=state)
        else:
            self._build_index_items_serial(path, image_files, lightweight=lightweight, state=state)
        return state.completed_items()

    def _build_index(self, path: str, *, lightweight: bool) -> MemoryBrowseIndex:
        """Build and cache folder index. Fast - no image reading."""
        norm = self._normalize_path(path)
        files, dirs = self.list_dir(path)
        use_leaf_batch = self._prepare_leaf_batch(path, norm, dirs, lightweight=lightweight)

        image_files = [f for f in files if self._is_supported_image(f)]
        total = len(image_files)
        show_progress = self._show_local_index_progress(
            lightweight=lightweight,
            total=total,
            use_leaf_batch=use_leaf_batch,
        )
        items = self._build_index_items(path, image_files, lightweight=lightweight, show_progress=show_progress)

        index = MemoryBrowseIndex(
            path=path,
            generated_at=datetime.now(timezone.utc).isoformat(),
            items=items,
            dirs=dirs,
        )
        self._store_index(norm, index, lightweight=lightweight)
        if use_leaf_batch:
            self._leaf_batch.update(norm)
        return index

    def _all_items(self) -> list[MemoryBrowseItem]:
        """Return cached items; build root index if nothing is cached yet."""
        if self._indexes:
            return [it for idx in self._indexes.values() for it in idx.items]
        index = self.load_index("/")
        if index is None:
            return []
        return list(index.items)

    def search(self, query: str = "", path: str = "/", limit: int = 100) -> list[MemoryBrowseItem]:
        """Simple in-memory search over cached indexes."""
        q = (query or "").lower()
        scope_norm = normalize_search_path(path)

        results: list[MemoryBrowseItem] = []
        for item in self._all_items():
            if not path_in_scope(logical_path=item.path, scope_norm=scope_norm):
                continue
            sidecar_state = self.get_sidecar_readonly(item.path)
            source, url = sidecar_source_fields(sidecar_state)
            haystack = build_search_haystack(
                logical_path=item.path,
                name=item.name,
                tags=sidecar_state.get("tags", []),
                notes=sidecar_state.get("notes", ""),
                source=source,
                url=url,
                include_source_fields=bool(source or url),
            )
            if q in haystack:
                results.append(item)
                if len(results) >= limit:
                    break
        return results

    def ensure_sidecar(self, path: str) -> SidecarState:
        """Get or create sidecar state for an image (in-memory only)."""
        key = self._canonical_sidecar_key(path)
        sidecar = self._sidecars.get(key)
        if sidecar is not None:
            return sidecar

        sidecar = self.get_sidecar_readonly(path)
        self._sidecars[key] = sidecar
        return sidecar

    def get_sidecar_readonly(self, path: str) -> SidecarState:
        key = self._canonical_sidecar_key(path)
        sidecar = self._sidecars.get(key)
        if sidecar is not None:
            return copy_sidecar_state(sidecar)

        w, h = self.get_dimensions(path)
        return default_sidecar_state(width=w, height=h)

    def set_sidecar(self, path: str, sidecar: SidecarState) -> None:
        """Update in-memory sidecar state (session-only, lost on restart)."""
        key = self._canonical_sidecar_key(path)
        self._sidecars[key] = copy_sidecar_state(sidecar)

    def get_source_path(self, logical_path: str) -> str:
        norm = self._normalize_item_path(logical_path)
        if not self.exists(norm):
            raise FileNotFoundError(logical_path)
        return norm

    def _walk_scope_indexes(self, path: str) -> Iterable[MemoryBrowseIndex]:
        pending = [path or "/"]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            norm = self._normalize_path(current)
            if norm in seen:
                continue
            seen.add(norm)
            index = self.load_recursive_index(current)
            if index is None:
                continue
            yield index
            for child in index.dirs:
                pending.append(self.join(current, child))

    def total_items(self) -> int:
        return sum(len(index.items) for index in self._walk_scope_indexes("/"))

    def items_in_scope(self, path: str) -> list[MemoryBrowseItem]:
        items: list[MemoryBrowseItem] = []
        for index in self._walk_scope_indexes(path):
            items.extend(index.items)
        items.sort(key=lambda item: item.path)
        return items

    def count_in_scope(self, path: str) -> int:
        return len(self.items_in_scope(path))

    def _rebuild_row_index(self) -> None:
        self._path_to_row = {
            self._normalize_item_path(item.path): idx
            for idx, item in enumerate(self.items_in_scope("/"))
        }
        self._row_index_generation = self._browse_generation

    def row_index_for_path(self, path: str) -> int | None:
        norm = self._normalize_item_path(path)
        if not norm:
            return None
        if self._row_index_generation != self._browse_generation:
            self._rebuild_row_index()
        return self._path_to_row.get(norm)

    def sidecar_enrichment_for_path(self, path: str) -> dict[str, Any]:
        _ = path
        return {}

    def recursive_items_hard_limit(self) -> int | None:
        return self.RECURSIVE_ITEMS_HARD_LIMIT

    def refresh_subtree(self, path: str, *, preserve_sidecars: bool = True) -> None:
        target = self._abs_path(path)
        if not os.path.isdir(target):
            raise FileNotFoundError(path)
        self.invalidate_subtree(path, clear_sidecars=not preserve_sidecars)
