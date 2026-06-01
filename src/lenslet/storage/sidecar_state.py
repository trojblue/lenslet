from __future__ import annotations

from collections.abc import Iterable

from .base import SidecarState


def copy_sidecar_state(sidecar: SidecarState) -> SidecarState:
    copied = dict(sidecar)
    if isinstance(copied.get("tags"), list):
        copied["tags"] = list(copied["tags"])
    if isinstance(copied.get("metrics"), dict):
        copied["metrics"] = dict(copied["metrics"])
    return copied


def default_sidecar_state(width: int = 0, height: int = 0) -> SidecarState:
    return {
        "width": width,
        "height": height,
        "tags": [],
        "notes": "",
        "star": None,
        "version": 1,
        "updated_at": "",
        "updated_by": "server",
    }


def ensure_sidecar_fields(sidecar: SidecarState) -> SidecarState:
    if "tags" not in sidecar or not isinstance(sidecar.get("tags"), list):
        sidecar["tags"] = []
    if "notes" not in sidecar or not isinstance(sidecar.get("notes"), str):
        sidecar["notes"] = ""
    if "star" not in sidecar:
        sidecar["star"] = None
    if "version" not in sidecar or not isinstance(sidecar.get("version"), int):
        sidecar["version"] = 1
    if "updated_at" not in sidecar or not isinstance(sidecar.get("updated_at"), str):
        sidecar["updated_at"] = ""
    if "updated_by" not in sidecar or not isinstance(sidecar.get("updated_by"), str):
        sidecar["updated_by"] = "server"
    return sidecar


class SidecarStateMixin:
    _sidecars: dict[str, SidecarState]

    def _sidecar_snapshot_key(self, path: str) -> str:
        return self._sidecar_replace_key(path)

    def _sidecar_replace_key(self, path: str) -> str:
        raise NotImplementedError

    def sidecar_items(self) -> list[tuple[str, SidecarState]]:
        return [(path, copy_sidecar_state(sidecar)) for path, sidecar in self._sidecars.items()]

    def sidecar_snapshot_for_paths(self, paths: Iterable[str]) -> dict[str, SidecarState]:
        snapshot: dict[str, SidecarState] = {}
        for path in paths:
            key = self._sidecar_snapshot_key(path)
            sidecar = self._sidecars.get(key)
            if sidecar is not None:
                snapshot[key] = copy_sidecar_state(sidecar)
        return snapshot

    def replace_sidecars(self, sidecars: dict[str, SidecarState]) -> None:
        self._sidecars = {
            self._sidecar_replace_key(path): copy_sidecar_state(sidecar)
            for path, sidecar in sidecars.items()
        }
