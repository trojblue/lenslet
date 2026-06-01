from __future__ import annotations


def _reason_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or type(exc).__name__


class MediaError(RuntimeError):
    """Base class for media read/decode failures."""

    def __init__(self, path: str, operation: str, reason: str) -> None:
        self.path = path
        self.operation = operation
        self.reason = reason
        super().__init__(f"{operation} failed for {path}: {reason}")


class MediaReadError(MediaError):
    """Raised when source bytes cannot be loaded for an item."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(path, "read", reason)

    @classmethod
    def from_exception(cls, path: str, exc: BaseException) -> "MediaReadError":
        return cls(path, _reason_text(exc))


class RemoteMediaNotFoundError(FileNotFoundError):
    """Raised when a remote source explicitly reports a missing object."""

    def __init__(self, path: str, source: str, reason: str) -> None:
        self.path = path
        self.source = source
        self.reason = reason
        super().__init__(f"remote source not found for {path}: {reason}")


class RemoteMediaReadError(MediaReadError):
    """Raised when a remote source cannot be read for a typed non-404 reason."""

    def __init__(self, path: str, source: str, category: str, reason: str) -> None:
        self.source = source
        self.category = category
        super().__init__(path, f"{category}: {reason}")


class MediaDecodeError(MediaError):
    """Raised when source bytes cannot be decoded as an image."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(path, "decode", reason)

    @classmethod
    def from_exception(cls, path: str, exc: BaseException) -> "MediaDecodeError":
        return cls(path, _reason_text(exc))
