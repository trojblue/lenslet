from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal

Mime = Literal['image/webp','image/jpeg','image/png']

class Item(BaseModel):
    path: str
    name: str
    type: Mime
    w: int
    h: int
    size: int
    hasThumb: bool = False
    hasMeta: bool = False
    hash: str | None = None
    addedAt: str | None = None

class DirEntry(BaseModel):
    name: str
    kind: Literal['branch','leaf-real','leaf-pointer']

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
    # star rating from 1..5; None or 0 means unset
    star: int | None = None
    updated_at: str
    updated_by: str

class SearchResult(BaseModel):
    items: list[Item]
