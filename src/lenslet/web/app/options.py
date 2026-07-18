from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from ...embeddings.config import EmbeddingConfig
from ...indexing_status import IndexingListener
from ...workspace import Workspace
from ..models import LaunchSessionPayload

StorageRefreshMode: TypeAlias = Literal["static", "subtree"]
StorageMode: TypeAlias = Literal["memory", "table", "dataset", "storage"]
TableSourceRefreshMode: TypeAlias = Literal["untracked", "restart-required"]


@dataclass(frozen=True, slots=True)
class BrowseAppOptions:
    thumb_size: int = 256
    thumb_quality: int = 70
    thumb_cache: bool = True
    presence_view_ttl: float = 75.0
    presence_edit_ttl: float = 60.0
    presence_prune_interval: float = 5.0
    indexing_listener: IndexingListener | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingAppOptions:
    config: EmbeddingConfig | None = None
    cache: bool = True
    cache_dir: str | None = None
    preload: bool = False


@dataclass(frozen=True, slots=True)
class LocalAppOptions:
    browse: BrowseAppOptions = field(default_factory=BrowseAppOptions)
    embedding: EmbeddingAppOptions = field(default_factory=EmbeddingAppOptions)
    no_write: bool = False
    source_column: str | None = None
    skip_dimension_probe: bool = False
    og_preview: bool = False
    workspace: Workspace | None = None
    preindex_signature: str | None = None
    path_column: str | None = None
    launch_session: LaunchSessionPayload | None = None
    trusted_write_origins: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DatasetAppOptions:
    browse: BrowseAppOptions = field(default_factory=BrowseAppOptions)
    show_source: bool = True
    launch_session: LaunchSessionPayload | None = None


@dataclass(frozen=True, slots=True)
class TableAppOptions:
    browse: BrowseAppOptions = field(default_factory=BrowseAppOptions)
    embedding: EmbeddingAppOptions = field(default_factory=EmbeddingAppOptions)
    base_dir: str | None = None
    source_column: str | None = None
    path_column: str | None = None
    skip_dimension_probe: bool = False
    allow_local: bool = True
    show_source: bool = True
    og_preview: bool = False
    workspace: Workspace | None = None
    embedding_table_path: str | None = None
    launch_session: LaunchSessionPayload | None = None
    source_refresh: TableSourceRefreshMode = "untracked"
    trusted_write_origins: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StorageAppOptions:
    browse: BrowseAppOptions = field(default_factory=BrowseAppOptions)
    embedding: EmbeddingAppOptions = field(default_factory=EmbeddingAppOptions)
    show_source: bool = True
    og_preview: bool = False
    workspace: Workspace | None = None
    embedding_table_path: str | None = None
    storage_mode: StorageMode | None = None
    storage_origin: str | None = None
    refresh: StorageRefreshMode | None = None
    launch_session: LaunchSessionPayload | None = None
    trusted_write_origins: tuple[str, ...] = ()
