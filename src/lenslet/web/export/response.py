"""Comparison export responses for web routes."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import HTTPException, Response
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError

from ...media_errors import MediaDecodeError, MediaReadError
from ...storage.base import BrowseStorage
from ..browse import ensure_image
from .rendering import (
    ComparisonExportRuntime,
    build_gif,
    build_png,
    comparison_export_filename,
)
from ..media import media_failure_to_http_error
from ..models import ExportComparisonRequest
from ..paths import canonical_path

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


def _default_runtime() -> ComparisonExportRuntime:
    return ComparisonExportRuntime(
        max_source_pixels=MAX_EXPORT_SOURCE_PIXELS,
        max_stitched_pixels=MAX_EXPORT_STITCHED_PIXELS,
        max_metadata_bytes=MAX_EXPORT_METADATA_BYTES,
        max_label_chars=MAX_EXPORT_LABEL_CHARS,
        max_gif_long_side=MAX_EXPORT_GIF_LONG_SIDE,
        max_gif_long_side_high_quality=MAX_EXPORT_GIF_LONG_SIDE_HIGH_QUALITY,
        max_gif_bytes=MAX_EXPORT_GIF_MAX_BYTES,
        gif_frame_duration_ms=EXPORT_GIF_FRAME_DURATION_MS,
        gif_frame_duration_ms_high_quality=EXPORT_GIF_FRAME_DURATION_MS_HIGH_QUALITY,
        metadata_key=EXPORT_COMPARISON_METADATA_KEY,
    )


def _error_response(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message})


def _path_validation_error_response(exc: HTTPException) -> JSONResponse:
    message = str(exc.detail)
    if exc.status_code == 404:
        return _error_response(404, "file_not_found", message)
    return _error_response(400, "invalid_path", message)


def _comparison_export_error_response(exc: HTTPException) -> JSONResponse:
    detail = str(exc.detail)
    if exc.status_code == 404:
        return _error_response(404, "file_not_found", detail)
    if exc.status_code in {415, 422}:
        return _error_response(exc.status_code, "unsupported_source_format", detail)
    if exc.status_code != 400:
        return _error_response(exc.status_code, "export_failed", detail)
    if "pixel limit" in detail or "size limit" in detail:
        return _error_response(400, "export_too_large", detail)
    if "embedded metadata exceeds configured limit" in detail:
        return _error_response(400, "metadata_too_large", detail)
    if "labels" in detail:
        return _error_response(400, "invalid_labels", detail)
    return _error_response(400, "invalid_request", detail)


def _sanitize_label(raw: str, *, max_label_chars: int) -> str:
    cleaned = "".join(ch for ch in raw if ord(ch) >= 32 and ord(ch) != 127).strip()
    if len(cleaned) > max_label_chars:
        raise ValueError(f"labels must be <= {max_label_chars} characters after sanitation")
    return cleaned


def _normalize_labels(
    labels: list[str] | None,
    *,
    max_labels: int,
    max_label_chars: int,
) -> list[str]:
    if labels is None:
        return []
    if len(labels) > max_labels:
        raise ValueError(f"expected at most {max_labels} labels")
    return [_sanitize_label(value, max_label_chars=max_label_chars) for value in labels]


def _default_label(path: str, idx: int) -> str:
    name = Path(path).name.strip()
    if name:
        return name[:MAX_EXPORT_LABEL_CHARS]
    if idx < 26:
        return chr(ord("A") + idx)
    return f"Image {idx + 1}"


def _resolve_paths_and_labels(
    paths: list[str],
    labels: list[str],
    reverse_order: bool,
) -> tuple[list[str], list[str]]:
    ordered_paths = list(paths)
    label_slots = list(labels[: len(paths)])
    label_slots.extend([""] * (len(paths) - len(label_slots)))
    if reverse_order:
        ordered_paths.reverse()
        label_slots.reverse()
    ordered_labels: list[str] = []
    for idx, path in enumerate(ordered_paths):
        label = label_slots[idx]
        ordered_labels.append(label if label else _default_label(path, idx))
    return ordered_paths, ordered_labels


def _load_export_image(
    storage: BrowseStorage,
    path: str,
    *,
    runtime: ComparisonExportRuntime,
) -> tuple[Image.Image, str]:
    try:
        raw = storage.read_bytes(path)
    except (FileNotFoundError, MediaReadError) as exc:
        raise media_failure_to_http_error(exc) from exc
    except Exception as exc:
        raise media_failure_to_http_error(MediaReadError.from_exception(path, exc)) from exc
    try:
        with Image.open(io.BytesIO(raw)) as source:
            source.load()
            source_format = (source.format or "").upper()
            if source_format not in {"PNG", "JPEG", "WEBP"}:
                raise HTTPException(415, f"unsupported source format for {path}")
            width, height = source.size
            if width <= 0 or height <= 0:
                raise HTTPException(415, f"invalid source dimensions for {path}")
            if width * height > runtime.max_source_pixels:
                raise HTTPException(400, f"source image exceeds pixel limit: {path}")
            return source.copy(), source_format.lower()
    except HTTPException:
        raise
    except UnidentifiedImageError as exc:
        raise media_failure_to_http_error(MediaDecodeError.from_exception(path, exc)) from exc
    except OSError as exc:
        raise media_failure_to_http_error(MediaDecodeError.from_exception(path, exc)) from exc


def export_comparison_response(storage: BrowseStorage, body: ExportComparisonRequest) -> Response:
    canonical_paths = [canonical_path(path) for path in body.paths]
    for path in canonical_paths:
        try:
            ensure_image(storage, path)
        except HTTPException as exc:
            return _path_validation_error_response(exc)
    runtime = _default_runtime()
    try:
        normalized_labels = _normalize_labels(
            body.labels,
            max_labels=len(canonical_paths),
            max_label_chars=runtime.max_label_chars,
        )
    except ValueError as exc:
        return _error_response(400, "invalid_labels", str(exc))
    ordered_paths, ordered_labels = _resolve_paths_and_labels(
        canonical_paths,
        normalized_labels,
        body.reverse_order,
    )
    images: list[Image.Image] = []
    source_formats: list[str] = []
    try:
        for path in ordered_paths:
            image, source_format = _load_export_image(storage, path, runtime=runtime)
            images.append(image)
            source_formats.append(source_format)
        if body.output_format == "gif":
            exported_content = build_gif(
                images,
                ordered_labels,
                embed_metadata=body.embed_metadata,
                high_quality=body.high_quality_gif,
                ordered_paths=ordered_paths,
                source_formats=source_formats,
                reversed_order=body.reverse_order,
                runtime=runtime,
            )
            media_type = "image/gif"
        else:
            exported_content = build_png(
                images,
                ordered_labels,
                embed_metadata=body.embed_metadata,
                ordered_paths=ordered_paths,
                source_formats=source_formats,
                reversed_order=body.reverse_order,
                runtime=runtime,
            )
            media_type = "image/png"
    except HTTPException as exc:
        return _comparison_export_error_response(exc)
    finally:
        for image in images:
            image.close()
    filename = comparison_export_filename(body.reverse_order, output_format=body.output_format)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=exported_content, media_type=media_type, headers=headers)
