from __future__ import annotations


def canonical_path(path: str | None) -> str:
    # Whitespace is part of a file name: "a.jpg " and "a.jpg" are different images.
    p = (path or "").replace("\\", "/")
    if not p:
        return "/"
    while "//" in p:
        p = p.replace("//", "/")
    p = "/" + p.lstrip("/")
    if p != "/":
        p = p.rstrip("/")
    return p
