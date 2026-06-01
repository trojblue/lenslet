from __future__ import annotations


def canonical_path(path: str | None) -> str:
    p = (path or "").replace("\\", "/").strip()
    if not p:
        return "/"
    while "//" in p:
        p = p.replace("//", "/")
    p = "/" + p.lstrip("/")
    if p != "/":
        p = p.rstrip("/")
    return p
