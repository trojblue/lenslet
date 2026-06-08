from __future__ import annotations

from fastapi import Request

from ..metrics import normalize_metric_mapping
from ..storage.base import SidecarPayload, SidecarState
from ..storage.sidecar_state import ensure_sidecar_fields
from .auth import request_actor_id
from .models import Sidecar, SidecarPatch
from .paths import canonical_path


def _normalize_tags(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        if not isinstance(raw, str):
            continue
        val = raw.strip()
        if not val or val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def sidecar_from_state(sidecar: SidecarState) -> Sidecar:
    sidecar = ensure_sidecar_fields(sidecar)
    return Sidecar(
        tags=list(sidecar.get("tags", [])),
        notes=sidecar.get("notes", ""),
        exif={"width": sidecar.get("width", 0), "height": sidecar.get("height", 0)},
        star=sidecar.get("star"),
        version=sidecar.get("version", 1),
        updated_at=sidecar.get("updated_at", ""),
        updated_by=sidecar.get("updated_by", "server"),
    )


def sidecar_payload(path: str, sidecar: SidecarState) -> SidecarPayload:
    sidecar = ensure_sidecar_fields(sidecar)
    payload: SidecarPayload = {
        "path": canonical_path(path),
        "version": sidecar.get("version", 1),
        "tags": list(sidecar.get("tags", [])),
        "notes": sidecar.get("notes", ""),
        "star": sidecar.get("star"),
        "updated_at": sidecar.get("updated_at", ""),
        "updated_by": sidecar.get("updated_by", "server"),
    }
    if "metrics" in sidecar:
        metrics = normalize_metric_mapping(sidecar.get("metrics"))
        if metrics is not None:
            payload["metrics"] = metrics
    return payload


def updated_by_from_request(request: Request | None) -> str:
    return request_actor_id(request)


def apply_patch_to_sidecar(sidecar: SidecarState, body: SidecarPatch) -> bool:
    updated = False
    fields = body.model_fields_set

    tags = list(sidecar.get("tags", []))
    if "set_tags" in fields:
        next_tags = _normalize_tags(body.set_tags or [])
        if next_tags != tags:
            updated = True
        tags = next_tags

    add_tags = _normalize_tags(body.add_tags or [])
    remove_tags = set(_normalize_tags(body.remove_tags or []))
    if add_tags or remove_tags:
        base = [t for t in tags if t not in remove_tags]
        for tag in add_tags:
            if tag not in base:
                base.append(tag)
        if base != tags:
            updated = True
        tags = base

    if "set_star" in fields:
        if sidecar.get("star") != body.set_star:
            updated = True
        sidecar["star"] = body.set_star

    if "set_notes" in fields:
        if sidecar.get("notes") != (body.set_notes or ""):
            updated = True
        sidecar["notes"] = body.set_notes or ""

    if tags != list(sidecar.get("tags", [])):
        sidecar["tags"] = tags

    return updated
