from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Mime = Literal["image/webp", "image/jpeg", "image/png"]


class Item(BaseModel):
    path: str
    name: str
    type: Mime
    w: int
    h: int
    size: int
    hasThumb: bool = True  # Always true in memory mode
    hasMeta: bool = True   # Always true in memory mode
    hash: str | None = None
    addedAt: str | None = None
    star: int | None = None
    comments: str | None = None
    url: str | None = None
    source: str | None = None
    metrics: dict[str, float] | None = None


class DirEntry(BaseModel):
    name: str
    kind: Literal["branch", "leaf-real", "leaf-pointer"] = "branch"


class FolderIndex(BaseModel):
    v: int = 1
    path: str
    generatedAt: str
    items: list[Item] = Field(default_factory=list)
    dirs: list[DirEntry] = Field(default_factory=list)
    page: int | None = None
    pageCount: int | None = None


class Sidecar(BaseModel):
    v: int = 1
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    exif: dict | None = None
    hash: str | None = None
    original_position: str | None = None
    star: int | None = None
    version: int = 1
    updated_at: str = ""
    updated_by: str = "server"


class SidecarPatch(BaseModel):
    base_version: int | None = None
    set_star: int | None = None
    set_notes: str | None = None
    set_tags: list[str] | None = None
    add_tags: list[str] = Field(default_factory=list)
    remove_tags: list[str] = Field(default_factory=list)


class PresencePayload(BaseModel):
    gallery_id: str
    client_id: str


class SearchResult(BaseModel):
    items: list[Item]


class ImageMetadataResponse(BaseModel):
    path: str
    format: Literal["png", "jpeg", "webp"]
    meta: dict


class ViewsPayload(BaseModel):
    version: int = 1
    views: list[dict] = Field(default_factory=list)


class EmbeddingSpecPayload(BaseModel):
    name: str
    dimension: int
    dtype: str
    metric: str


class EmbeddingRejectedPayload(BaseModel):
    name: str
    reason: str


class EmbeddingsResponse(BaseModel):
    embeddings: list[EmbeddingSpecPayload] = Field(default_factory=list)
    rejected: list[EmbeddingRejectedPayload] = Field(default_factory=list)


class EmbeddingSearchRequest(BaseModel):
    embedding: str
    query_path: str | None = None
    query_vector_b64: str | None = None
    top_k: int = 50
    min_score: float | None = None


class EmbeddingSearchItem(BaseModel):
    row_index: int
    path: str
    score: float


class EmbeddingSearchResponse(BaseModel):
    embedding: str
    items: list[EmbeddingSearchItem] = Field(default_factory=list)
