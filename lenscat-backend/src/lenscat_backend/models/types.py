"""Core data models matching frontend types."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class MimeType(str, Enum):
    """Supported image MIME types."""
    WEBP = "image/webp"
    JPEG = "image/jpeg"
    PNG = "image/png"


class DirKind(str, Enum):
    """Directory types."""
    BRANCH = "branch"
    LEAF_REAL = "leaf-real"
    LEAF_POINTER = "leaf-pointer"


class StorageType(str, Enum):
    """Storage backend types."""
    LOCAL = "local"
    S3 = "s3"


class Item(BaseModel):
    """Image item metadata."""
    path: str
    name: str
    type: MimeType
    w: int
    h: int
    size: int
    hasThumb: bool = Field(alias="has_thumb")
    hasMeta: bool = Field(alias="has_meta")
    hash: Optional[str] = None

    class Config:
        allow_population_by_field_name = True


class DirEntry(BaseModel):
    """Directory entry."""
    name: str
    kind: DirKind


class ExifData(BaseModel):
    """Basic EXIF metadata."""
    width: Optional[int] = None
    height: Optional[int] = None
    createdAt: Optional[datetime] = Field(alias="created_at", default=None)

    class Config:
        allow_population_by_field_name = True


class Sidecar(BaseModel):
    """Sidecar metadata file."""
    v: int = 1
    tags: List[str] = Field(default_factory=list)
    notes: str = ""
    exif: Optional[ExifData] = None
    hash: Optional[str] = None
    updatedAt: datetime = Field(alias="updated_at")
    updatedBy: str = Field(alias="updated_by")

    class Config:
        allow_population_by_field_name = True


class FolderIndex(BaseModel):
    """Folder manifest (_index.json)."""
    v: int = 1
    path: str
    generatedAt: datetime = Field(alias="generated_at")
    items: List[Item] = Field(default_factory=list)
    dirs: List[DirEntry] = Field(default_factory=list)
    page: Optional[int] = None
    pageCount: Optional[int] = Field(alias="page_count", default=None)

    class Config:
        allow_population_by_field_name = True


class RollupItem(BaseModel):
    """Flattened item for search."""
    path: str
    name: str
    tags: List[str] = Field(default_factory=list)
    notes: str = ""


class RollupManifest(BaseModel):
    """Search rollup manifest (_rollup.json)."""
    v: int = 1
    generatedAt: datetime = Field(alias="generated_at")
    items: List[RollupItem] = Field(default_factory=list)

    class Config:
        allow_population_by_field_name = True


class PointerTarget(BaseModel):
    """Pointer folder target configuration."""
    type: StorageType
    bucket: Optional[str] = None
    prefix: Optional[str] = None
    region: Optional[str] = None
    path: Optional[str] = None


class PointerConfig(BaseModel):
    """Pointer folder configuration (.lenscat.folder.json)."""
    version: int = 1
    kind: str = "pointer"
    target: PointerTarget
    label: Optional[str] = None
    readonly: bool = False


class SearchResult(BaseModel):
    """Search API response."""
    items: List[RollupItem]
    total: int = 0


class HealthStatus(BaseModel):
    """Health check response."""
    status: str = "healthy"
    backend: Dict[str, Any] = Field(default_factory=dict)
    workers: Dict[str, Any] = Field(default_factory=dict)
    storage: Dict[str, Any] = Field(default_factory=dict)
