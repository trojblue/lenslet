from __future__ import annotations


def normalize_search_path(path: str) -> str:
    """Normalize a logical path token for search scope/path comparisons."""
    normalized = (path or "").replace("\\", "/").strip()
    if not normalized or normalized == "/":
        return ""
    return normalized.strip("/")


def path_in_scope(*, logical_path: str, scope_norm: str) -> bool:
    """Return True when logical_path is within scope_norm (or equal)."""
    logical_norm = normalize_search_path(logical_path)
    if not scope_norm:
        return True
    return logical_norm == scope_norm or logical_norm.startswith(f"{scope_norm}/")


def build_search_haystack(
    *,
    logical_path: str,
    name: str,
    tags: list[str],
    notes: str,
    source: str | None,
    url: str | None,
    include_source_fields: bool,
) -> str:
    """Build one canonical lowercase search haystack."""
    parts: list[str] = [
        name or "",
        normalize_search_path(logical_path),
        " ".join(str(tag) for tag in tags if tag is not None),
        notes or "",
    ]
    if include_source_fields:
        parts.extend([
            source or "",
            url or "",
        ])
    return " ".join(part for part in parts if part).lower()
