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


class MediaDecodeError(MediaError):
    """Raised when source bytes cannot be decoded as an image."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(path, "decode", reason)

    @classmethod
    def from_exception(cls, path: str, exc: BaseException) -> "MediaDecodeError":
        return cls(path, _reason_text(exc))
