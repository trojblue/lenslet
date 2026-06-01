from __future__ import annotations

from ..storage.base import BrowseGenerationStorage


def build_browse_generation_token(storage: BrowseGenerationStorage) -> str:
    parts: list[str] = []
    signature = str(storage.browse_cache_signature()).strip()
    if signature:
        parts.append(signature)

    generation = str(storage.browse_generation()).strip()
    if generation:
        parts.append(generation)

    if not parts:
        return "default"
    return "|".join(parts)
