from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Protocol, TypedDict

from .image_media import ImageMime

if TYPE_CHECKING:
    from ..browse.query import BrowseQueryResult, BrowseQuerySpec


class SidecarState(TypedDict, total=False):
    width: int
    height: int
    tags: list[str]
    notes: str
    star: int | None
    version: int
    updated_at: str
    updated_by: str
    metrics: dict[str, float]
    source: str
    source_path: str
    url: str
    source_url: str


class _SidecarPayloadRequired(TypedDict):
    path: str


class SidecarPayload(_SidecarPayloadRequired, SidecarState, total=False):
    """JSON event/log payload shape for an item sidecar."""

    mutation_id: str
    changed_fields: list[str]


class StorageWriteUnsupportedError(PermissionError):
    """Raised when a storage backend does not support raw writes."""


class Storage(Protocol):
    """Abstract read-oriented storage protocol for file operations."""

    def list_dir(self, path: str) -> tuple[list[str], list[str]]:
        """Return (files, dirs) names in path (no recursion)."""
        ...

    def read_bytes(self, path: str) -> bytes:
        ...

    def exists(self, path: str) -> bool:
        ...

    def size(self, path: str) -> int:
        ...

    def join(self, *parts: str) -> str:
        ...

    def etag(self, path: str) -> str | None:
        """Get ETag for caching."""
        ...


class WritableStorage(Storage, Protocol):
    """Optional raw-write extension for storage backends."""

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write file contents or raise StorageWriteUnsupportedError."""
        ...


class BrowseItem(Protocol):
    """Shared cached-item shape exposed by browse-capable backends."""

    path: str
    name: str
    mime: ImageMime
    width: int
    height: int
    size: int
    mtime: float
    url: str | None
    source: str | None
    metrics: dict[str, float]


class BrowseIndex(Protocol):
    """Minimal folder-index contract shared by browse storage backends."""

    path: str
    generated_at: str
    items: list[BrowseItem]
    dirs: list[str]


class BrowseStorage(Storage, Protocol):
    """Common browse-tree contract shared by all gallery backends."""

    def load_index(self, path: str) -> BrowseIndex | None:
        """Load a folder index, building/cache-warming as needed.

        Returns None when the path is outside the browse tree.
        """
        ...

    def load_recursive_index(self, path: str) -> BrowseIndex | None:
        """Load the recursive-traversal index, building/cache-warming as needed.

        Returns None when the path is outside the browse tree.
        """
        ...

    def items_in_scope(self, path: str) -> list[BrowseItem]:
        """Return all items beneath a logical scope."""
        ...

    def count_in_scope(self, path: str) -> int:
        """Return the total number of items beneath a logical scope."""
        ...

    def validate_image_path(self, path: str) -> None:
        """Raise when the path does not resolve to a valid image item."""
        ...

    def guess_mime(self, path: str) -> ImageMime:
        ...


class BrowseWindowStorage(Protocol):
    """Optional efficient scoped-window capability for large recursive browse payloads."""

    def items_in_scope_window(self, path: str, offset: int, limit: int) -> list[BrowseItem]:
        """Return a bounded item window beneath a logical scope."""
        ...


class BrowseQueryStorage(Protocol):
    """Optional authoritative browse-query window capability."""

    def query_browse_scope(self, spec: BrowseQuerySpec) -> BrowseQueryResult[BrowseItem]:
        """Return a filtered and sorted browse window for a logical scope."""
        ...


class SidecarStateStorage(Protocol):
    """Mutable per-item sidecar state capability."""

    def get_sidecar_readonly(self, path: str) -> SidecarState:
        ...

    def ensure_sidecar(self, path: str) -> SidecarState:
        """Return mutable sidecar state for the requested item, creating cache state when needed."""
        ...

    def set_sidecar(self, path: str, sidecar: SidecarState) -> None:
        ...


class SourcePathStorage(Protocol):
    """Logical path to original source path lookup capability."""

    def get_source_path(self, logical_path: str) -> str:
        ...


class ThumbnailStorage(Protocol):
    """Thumbnail and dimension lookup/generation capability."""

    def get_or_build_thumbnail(self, path: str) -> bytes:
        """Return thumbnail bytes, reading source data and updating caches when needed.

        Unlike get_cached_thumbnail(), this may perform I/O, generate WebP bytes,
        and populate thumbnail and dimension cache state.
        """
        ...

    def get_cached_thumbnail(self, path: str) -> bytes | None:
        """Return an in-memory thumbnail if present, without generating one."""
        ...

    def get_dimensions(self, path: str) -> tuple[int, int]:
        """Return cached dimensions without reading source bytes."""
        ...

    def load_dimensions(self, path: str) -> tuple[int, int]:
        """Return dimensions, reading source bytes and updating cache state when needed."""
        ...


class ThumbnailCacheKeyStorage(Protocol):
    """Stable thumbnail cache-key capability."""

    def thumbnail_cache_key(self, path: str) -> str | None:
        ...


class LocalFileStorage(Protocol):
    """Local-file fast path capability for media streaming."""

    def resolve_local_file_path(self, path: str) -> str | None:
        """Return a local file path when the item is backed by a local file."""
        ...


class SidecarInventoryStorage(SidecarStateStorage, Protocol):
    """Bulk sidecar state inventory/replacement capability."""

    def sidecar_items(self) -> list[tuple[str, SidecarState]]:
        ...

    def sidecar_snapshot_for_paths(
        self,
        paths: Iterable[str],
    ) -> dict[str, SidecarState]:
        """Return a canonicalized sidecar snapshot limited to the supplied logical paths."""
        ...

    def replace_sidecars(self, sidecars: dict[str, SidecarState]) -> None:
        """Replace storage sidecar entries from a caller-owned snapshot."""
        ...


class TotalItemsStorage(Protocol):
    """Dataset-wide item count capability."""

    def total_items(self) -> int:
        ...


class EmbeddingRowLookupStorage(Protocol):
    """Logical path to embedding row-index lookup capability."""

    def row_index_for_path(self, path: str) -> int | None:
        """Return the row index backing a logical path, or None when unavailable."""
        ...


class SidecarEnrichmentStorage(Protocol):
    """Optional sidecar enrichment fields exposed by table-like backends."""

    def sidecar_enrichment_for_path(self, path: str) -> dict[str, Any]:
        ...


class IndexingProgressStorage(Protocol):
    """Indexing progress diagnostics capability."""

    def indexing_progress(self) -> dict[str, int | str | bool | None]:
        ...


class BrowseGenerationStorage(Protocol):
    """Browse-cache invalidation token capability."""

    def browse_generation(self) -> int:
        ...

    def browse_cache_signature(self) -> str:
        ...


class RecursiveLimitStorage(Protocol):
    """Recursive browse safety-limit capability."""

    def recursive_items_hard_limit(self) -> int | None:
        ...


class SearchStorage(BrowseStorage, Protocol):
    """Browse storage with text search capability."""

    def search(self, query: str = "", path: str = "/", limit: int = 100) -> list[BrowseItem]:
        ...


class S3DiagnosticsStorage(Protocol):
    """S3 media-read diagnostics capability."""

    def s3_client_creations(self) -> int | None:
        """Return the number of lazily-created S3 clients, when applicable."""
        ...


class MediaStorage(BrowseStorage, ThumbnailStorage, ThumbnailCacheKeyStorage, LocalFileStorage, Protocol):
    """Storage capability set needed by media and thumbnail responses."""


class SidecarStorage(SidecarStateStorage, SidecarEnrichmentStorage, Protocol):
    """Storage capability set needed by item sidecar responses."""


class SourceSidecarStorage(SidecarStateStorage, SourcePathStorage, Protocol):
    """Storage capability set needed to expose original source paths with item sidecars."""


class ItemRouteStorage(BrowseStorage, SidecarStorage, SidecarInventoryStorage, Protocol):
    """Storage capability set needed by item read/write routes and label snapshots."""


class EmbeddingSearchStorage(BrowseStorage, EmbeddingRowLookupStorage, Protocol):
    """Storage capability set needed by embedding search routes."""


class BrowseAppStorage(
    ItemRouteStorage,
    MediaStorage,
    SearchStorage,
    TotalItemsStorage,
    BrowseGenerationStorage,
    RecursiveLimitStorage,
    Protocol,
):
    """Storage capability set required by the full browse FastAPI app."""


class RefreshableBrowseStorage(BrowseStorage, Protocol):
    """Browse storage that can refresh a subtree in place."""

    def refresh_subtree(self, path: str, *, preserve_sidecars: bool = True) -> None:
        """Refresh a folder subtree, optionally retaining mutable sidecar state."""
        ...


def join_storage_path(*parts: str) -> str:
    """Join logical browse paths into one rooted POSIX-style path."""

    joined = "/".join(part.strip("/") for part in parts if part and part.strip("/"))
    return f"/{joined}" if joined else "/"
