"""FastAPI server facade for Lenslet.

This module intentionally keeps stable import/monkeypatch touchpoints while delegating
runtime wiring and route-heavy logic to sibling modules.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin, UnidentifiedImageError
from pydantic import ValidationError

from . import og
from .server_browse import (
    HotpathTelemetry,
    _build_folder_index,
    _build_image_metadata,
    _build_item,
    _build_sidecar,
    _ensure_image,
    _search_results,
    _storage_from_request,
)
from .server_factory import (
    _embedding_cache_from_workspace,
    _thumb_cache_from_workspace,
    create_app,
    create_app_from_datasets,
    create_app_from_storage,
    create_app_from_table,
)
from .server_media import _file_response, _thumb_response_async, _thumb_worker_count
from .server_routes_common import RecordUpdateFn, register_common_api_routes as _register_common_api_routes
from .server_routes_embeddings import register_embedding_routes as _register_embedding_routes
from .server_routes_index import (
    NoCacheIndexStaticFiles,
    mount_frontend as _mount_frontend,
    register_index_routes as _register_index_routes,
)
from .server_routes_og import register_og_routes as _register_og_routes
from .server_routes_presence import (
    install_presence_prune_loop as _install_presence_prune_loop,
    presence_count_for_gallery as _presence_count_for_gallery,
    presence_count_payload as _presence_count_payload,
    presence_invalid_lease_payload as _presence_invalid_lease_payload,
    presence_payload_for_client as _presence_payload_for_client,
    presence_runtime_payload as _presence_runtime_payload,
    presence_scope_mismatch_payload as _presence_scope_mismatch_payload,
    publish_presence_counts as _publish_presence_counts,
    publish_presence_deltas as _publish_presence_deltas,
    register_presence_routes as _register_presence_routes,
    require_presence_client_id as _require_presence_client_id,
    touch_presence_edit as _touch_presence_edit,
)
from .server_routes_views import register_views_routes as _register_views_routes
from .server_runtime import AppRuntime, build_app_runtime
from .server_sync import (
    _apply_patch_to_meta,
    _canonical_path,
    _client_id_from_request,
    _ensure_meta_fields,
    _format_sse,
    _gallery_id_from_path,
    _last_event_id_from_request,
    _now_iso,
    _parse_if_match,
    _sidecar_from_meta,
    _sidecar_payload,
    _updated_by_from_request,
)
from .storage.table import TableStorage, load_parquet_schema, load_parquet_table
from .workspace import Workspace

# S0/T1 seam anchors (see docs/dev_notes/20260211_s0_t1_seam_map.md):
# - T3 runtime wiring: extracted to server_runtime.py and server_factory.py.
# - T4a common routes: extracted in server_routes_common.register_folder_route +
#   server_routes_common.register_common_api_routes.
# - T4b presence routes: extracted in server_routes_presence.register_presence_routes.
# - T4c embeddings/views routes: extracted in server_routes_embeddings.py +
#   server_routes_views.py.
# - T4d index/OG/media routes/helpers: extracted in server_routes_index.py +
#   server_routes_og.py + server_media.py.
# - T5 facade compatibility: keep create_app*, HotpathTelemetry,
#   _thumb_response_async, _file_response, og, and monkeypatched export helpers.


MAX_EXPORT_SOURCE_PIXELS = 64_000_000
MAX_EXPORT_STITCHED_PIXELS = 120_000_000
MAX_EXPORT_METADATA_BYTES = 32 * 1024
MAX_EXPORT_LABEL_CHARS = 120
MAX_EXPORT_GIF_LONG_SIDE = 720
MAX_EXPORT_GIF_LONG_SIDE_HIGH_QUALITY = 1_080
MAX_EXPORT_GIF_MAX_BYTES = 8 * 1024 * 1024
EXPORT_GIF_FRAME_DURATION_MS = 1_500
EXPORT_GIF_FRAME_DURATION_MS_HIGH_QUALITY = 2_000
EXPORT_COMPARISON_METADATA_KEY = "lenslet:comparison"
_UNIBOX_IMAGE_UTILS: tuple[Callable[..., Any], Callable[..., Any]] | None = None


def _error_response(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message})


def _first_validation_error_detail(exc: ValidationError) -> str:
    first = exc.errors()[0] if exc.errors() else {"msg": "invalid request payload", "loc": ()}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    msg = str(first.get("msg", "invalid request payload"))
    return f"{loc}: {msg}" if loc else msg


def _path_validation_error_response(exc: HTTPException) -> JSONResponse:
    message = str(exc.detail)
    if exc.status_code == 404:
        return _error_response(404, "file_not_found", message)
    return _error_response(400, "invalid_path", message)


def _comparison_export_error_response(exc: HTTPException) -> JSONResponse:
    detail = str(exc.detail)
    if exc.status_code == 404:
        return _error_response(404, "file_not_found", detail)
    if exc.status_code == 415:
        return _error_response(415, "unsupported_source_format", detail)
    if exc.status_code == 500 and "unibox is required" in detail:
        return _error_response(500, "unibox_missing", detail)
    if exc.status_code != 400:
        return _error_response(500, "export_failed", detail)
    if "pixel limit" in detail:
        return _error_response(400, "export_too_large", detail)
    if "size limit" in detail:
        return _error_response(400, "export_too_large", detail)
    if "metadata exceeds configured limit" in detail:
        return _error_response(400, "metadata_too_large", detail)
    if "labels" in detail:
        return _error_response(400, "invalid_labels", detail)
    return _error_response(400, "invalid_request", detail)


def _get_unibox_image_utils() -> tuple[Callable[..., Any], Callable[..., Any]]:
    global _UNIBOX_IMAGE_UTILS
    if _UNIBOX_IMAGE_UTILS is not None:
        return _UNIBOX_IMAGE_UTILS
    try:
        from unibox.utils.image_utils import add_annotation, concatenate_images_horizontally
    except ImportError as exc:
        raise RuntimeError(
            "unibox is required for comparison export. Install with: pip install unibox"
        ) from exc
    _UNIBOX_IMAGE_UTILS = (concatenate_images_horizontally, add_annotation)
    return _UNIBOX_IMAGE_UTILS


def _sanitize_export_label(raw: str) -> str:
    cleaned = "".join(ch for ch in raw if ord(ch) >= 32 and ord(ch) != 127).strip()
    if len(cleaned) > MAX_EXPORT_LABEL_CHARS:
        raise ValueError(f"labels must be <= {MAX_EXPORT_LABEL_CHARS} characters after sanitation")
    return cleaned


def _normalize_export_labels(labels: list[str] | None, *, max_labels: int) -> list[str]:
    if labels is None:
        return []
    if len(labels) > max_labels:
        raise ValueError(f"expected at most {max_labels} labels")
    return [_sanitize_export_label(value) for value in labels]


def _default_export_label(path: str, idx: int) -> str:
    name = Path(path).name.strip()
    if name:
        return name[:MAX_EXPORT_LABEL_CHARS]
    if idx < 26:
        return chr(ord("A") + idx)
    return f"Image {idx + 1}"


def _resolve_export_paths_and_labels(
    paths: list[str],
    labels: list[str],
    reverse_order: bool,
) -> tuple[list[str], list[str]]:
    path_count = len(paths)
    ordered_paths = list(paths)
    label_slots = list(labels[:path_count])
    label_slots.extend([""] * (path_count - len(label_slots)))
    if reverse_order:
        ordered_paths.reverse()
        label_slots.reverse()

    ordered_labels: list[str] = []
    for idx, path in enumerate(ordered_paths):
        label = label_slots[idx]
        ordered_labels.append(label if label else _default_export_label(path, idx))
    return ordered_paths, ordered_labels


def _load_export_image(storage, path: str) -> tuple[Image.Image, str]:
    try:
        raw = storage.read_bytes(path)
    except FileNotFoundError:
        raise HTTPException(404, f"source image not found: {path}")
    except Exception as exc:
        raise HTTPException(500, f"failed to read source image {path}: {exc}")

    try:
        with Image.open(io.BytesIO(raw)) as source:
            source.load()
            source_format = (source.format or "").upper()
            if source_format not in {"PNG", "JPEG", "WEBP"}:
                raise HTTPException(415, f"unsupported source format for {path}")
            width, height = source.size
            if width <= 0 or height <= 0:
                raise HTTPException(415, f"invalid source dimensions for {path}")
            if width * height > MAX_EXPORT_SOURCE_PIXELS:
                raise HTTPException(400, f"source image exceeds pixel limit: {path}")
            return source.copy(), source_format.lower()
    except HTTPException:
        raise
    except UnidentifiedImageError:
        raise HTTPException(415, f"unsupported source format for {path}")
    except OSError as exc:
        raise HTTPException(415, f"failed to decode source image {path}: {exc}")


def _build_export_metadata_text(
    *,
    ordered_paths: list[str],
    labels: list[str],
    source_formats: list[str],
    reversed_order: bool,
    output_format: Literal["png", "gif"],
    gif_high_quality: bool | None = None,
    gif_max_long_side: int | None = None,
    gif_frame_duration_ms: int | None = None,
) -> str:
    metadata_payload = {
        "tool": "lenslet.export_comparison",
        "version": 1,
        "paths": ordered_paths,
        "labels": labels,
        "source_formats": source_formats,
        "reversed": reversed_order,
        "output_format": output_format,
        "exported_at": _now_iso(),
    }
    if gif_high_quality is not None:
        metadata_payload["gif_high_quality"] = gif_high_quality
    if gif_max_long_side is not None:
        metadata_payload["gif_max_long_side"] = gif_max_long_side
    if gif_frame_duration_ms is not None:
        metadata_payload["gif_frame_duration_ms"] = gif_frame_duration_ms
    metadata_text = json.dumps(metadata_payload, separators=(",", ":"), ensure_ascii=True)
    metadata_size = len(metadata_text.encode("utf-8"))
    if metadata_size > MAX_EXPORT_METADATA_BYTES:
        raise HTTPException(400, "embedded metadata exceeds configured limit")
    return metadata_text


def _resize_image_max_long_side(image: Image.Image, max_long_side: int) -> Image.Image:
    if max_long_side <= 0:
        raise ValueError("max_long_side must be > 0")
    width, height = image.size
    long_side = max(width, height)
    if long_side <= max_long_side:
        return image.copy()
    scale = max_long_side / long_side
    resized_width = max(1, int(round(width * scale)))
    resized_height = max(1, int(round(height * scale)))
    return image.resize((resized_width, resized_height), resample=Image.Resampling.LANCZOS)


def _pad_export_frames(frames: list[Image.Image]) -> list[Image.Image]:
    if not frames:
        return []
    canvas_width = max(frame.width for frame in frames)
    canvas_height = max(frame.height for frame in frames)
    padded: list[Image.Image] = []
    for frame in frames:
        canvas = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))
        x = (canvas_width - frame.width) // 2
        y = (canvas_height - frame.height) // 2
        canvas.paste(frame, (x, y))
        padded.append(canvas)
    return padded


def _scale_export_frames(frames: list[Image.Image], scale: float) -> list[Image.Image]:
    if scale >= 0.999:
        return [frame.copy() for frame in frames]
    scaled_frames: list[Image.Image] = []
    for frame in frames:
        width = max(1, int(round(frame.width * scale)))
        height = max(1, int(round(frame.height * scale)))
        scaled_frames.append(frame.resize((width, height), resample=Image.Resampling.LANCZOS))
    return scaled_frames


def _encode_gif_candidate(
    frames: list[Image.Image],
    *,
    colors: int,
    dither: Image.Dither,
    duration_ms: int,
    comment: bytes | None,
) -> bytes:
    adaptive_palette = getattr(getattr(Image, "Palette", Image), "ADAPTIVE", Image.ADAPTIVE)
    palette_frames: list[Image.Image] = []
    try:
        for frame in frames:
            palette_frames.append(
                frame.convert(
                    mode="P",
                    palette=adaptive_palette,
                    colors=colors,
                    dither=dither,
                )
            )
        if not palette_frames:
            raise HTTPException(500, "failed to encode gif: no frames")

        first, *rest = palette_frames
        out = io.BytesIO()
        save_kwargs: dict[str, Any] = {
            "format": "GIF",
            "save_all": True,
            "append_images": rest,
            "duration": duration_ms,
            "loop": 0,
            "optimize": True,
            "disposal": 2,
        }
        if comment is not None:
            save_kwargs["comment"] = comment
        first.save(out, **save_kwargs)
        return out.getvalue()
    finally:
        for frame in palette_frames:
            frame.close()


def _build_export_gif(
    images: list[Image.Image],
    labels: list[str],
    *,
    embed_metadata: bool,
    high_quality: bool,
    ordered_paths: list[str],
    source_formats: list[str],
    reversed_order: bool,
) -> bytes:
    try:
        _, add_annotation = _get_unibox_image_utils()
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))

    annotated: list[Image.Image] = []
    prepped: list[Image.Image] = []
    base_frames: list[Image.Image] = []
    scaled_frames: list[Image.Image] = []
    max_long_side = MAX_EXPORT_GIF_LONG_SIDE_HIGH_QUALITY if high_quality else MAX_EXPORT_GIF_LONG_SIDE
    duration_ms = EXPORT_GIF_FRAME_DURATION_MS_HIGH_QUALITY if high_quality else EXPORT_GIF_FRAME_DURATION_MS
    try:
        for image, label in zip(images, labels):
            annotated_frame = _annotate_for_export(image, label, add_annotation=add_annotation)
            annotated.append(annotated_frame)
            resized = _resize_image_max_long_side(annotated_frame, max_long_side)
            try:
                prepped.append(resized.convert("RGB"))
            finally:
                resized.close()

        if len(prepped) != len(images):
            raise HTTPException(500, "failed to prepare all gif frames")

        base_frames = _pad_export_frames(prepped)
        if len(base_frames) != len(images):
            raise HTTPException(500, "failed to normalize gif frame dimensions")

        metadata_comment: bytes | None = None
        if embed_metadata:
            metadata_text = _build_export_metadata_text(
                ordered_paths=ordered_paths,
                labels=labels,
                source_formats=source_formats,
                reversed_order=reversed_order,
                output_format="gif",
                gif_high_quality=high_quality,
                gif_max_long_side=max_long_side,
                gif_frame_duration_ms=duration_ms,
            )
            metadata_comment = metadata_text.encode("utf-8")

        scale_steps = (1.0, 0.94, 0.88, 0.82, 0.76, 0.7, 0.64, 0.58, 0.52, 0.46, 0.4, 0.34)
        color_steps = (256, 224, 192, 160, 128, 112, 96, 80, 64, 48, 32)
        dither_steps = (Image.Dither.FLOYDSTEINBERG, Image.Dither.NONE)

        for scale in scale_steps:
            scaled_frames = _scale_export_frames(base_frames, scale)
            try:
                for color_count in color_steps:
                    for dither in dither_steps:
                        encoded = _encode_gif_candidate(
                            scaled_frames,
                            colors=color_count,
                            dither=dither,
                            duration_ms=duration_ms,
                            comment=metadata_comment,
                        )
                        if len(encoded) <= MAX_EXPORT_GIF_MAX_BYTES:
                            return encoded
            finally:
                for frame in scaled_frames:
                    frame.close()
                scaled_frames = []

        raise HTTPException(400, "gif export exceeds configured size limit")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"failed to build comparison gif: {exc}")
    finally:
        for frame in annotated:
            frame.close()
        for frame in prepped:
            frame.close()
        for frame in base_frames:
            frame.close()
        for frame in scaled_frames:
            frame.close()


def _build_export_png(
    images: list[Image.Image],
    labels: list[str],
    *,
    embed_metadata: bool,
    ordered_paths: list[str],
    source_formats: list[str],
    reversed_order: bool,
) -> bytes:
    try:
        concatenate_images_horizontally, add_annotation = _get_unibox_image_utils()
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))

    annotated: list[Image.Image] = []
    stitched: Image.Image | None = None
    try:
        for image, label in zip(images, labels):
            annotated.append(
                _annotate_for_export(
                    image,
                    label,
                    add_annotation=add_annotation,
                )
            )
        if len(annotated) != len(images):
            raise HTTPException(500, "failed to annotate all images")
        max_height = max(image.height for image in annotated)
        stitched = concatenate_images_horizontally(annotated, max_height=max_height)
        if stitched is None:
            raise HTTPException(500, "failed to stitch comparison image")
        stitched_pixels = stitched.width * stitched.height
        if stitched_pixels > MAX_EXPORT_STITCHED_PIXELS:
            raise HTTPException(400, "stitched output exceeds configured pixel limit")

        pnginfo: PngImagePlugin.PngInfo | None = None
        if embed_metadata:
            metadata_text = _build_export_metadata_text(
                ordered_paths=ordered_paths,
                labels=labels,
                source_formats=source_formats,
                reversed_order=reversed_order,
                output_format="png",
            )
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text(EXPORT_COMPARISON_METADATA_KEY, metadata_text)

        out = io.BytesIO()
        save_kwargs: dict[str, Any] = {"format": "PNG"}
        if pnginfo is not None:
            save_kwargs["pnginfo"] = pnginfo
        stitched.save(out, **save_kwargs)
        return out.getvalue()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"failed to build comparison image: {exc}")
    finally:
        if stitched is not None:
            stitched.close()
        for image in annotated:
            image.close()


def _comparison_export_filename(
    reverse_order: bool,
    *,
    output_format: Literal["png", "gif"] = "png",
) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = "_reverse" if reverse_order else ""
    extension = "gif" if output_format == "gif" else "png"
    return f"comparison{suffix}_{stamp}.{extension}"


def _annotate_for_export(
    image: Image.Image,
    label: str,
    *,
    add_annotation: Callable[..., Any],
) -> Image.Image:
    try:
        annotated = add_annotation(
            image,
            annotation=label,
            position="top",
            alignment="center",
            size="default",
        )
        if isinstance(annotated, Image.Image):
            return annotated
    except Exception:
        pass
    return _fallback_add_annotation(image, label)


def _fallback_add_annotation(image: Image.Image, label: str) -> Image.Image:
    base = image.convert("RGB")
    font = ImageFont.load_default()
    probe = ImageDraw.Draw(base)
    left, top, right, bottom = probe.textbbox((0, 0), label, font=font)
    text_width = max(1, right - left)
    text_height = max(1, bottom - top)
    padding = 8
    title_height = text_height + (padding * 2)
    canvas = Image.new("RGB", (base.width, base.height + title_height), (255, 255, 255))
    canvas.paste(base, (0, title_height))
    draw = ImageDraw.Draw(canvas)
    text_x = max(0, (canvas.width - text_width) // 2)
    text_y = max(0, (title_height - text_height) // 2)
    draw.text((text_x, text_y), label, fill=(0, 0, 0), font=font)
    return canvas
