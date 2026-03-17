"""Comparison export helpers for web routes."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import HTTPException, Response
from fastapi.responses import JSONResponse
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin, UnidentifiedImageError
from pydantic import ValidationError

from ..storage.base import BrowseStorage
from .browse import ensure_image
from .models import ExportComparisonRequest
from .sync import canonical_path, now_iso

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


@dataclass(frozen=True)
class ComparisonExportRuntime:
    max_source_pixels: int
    max_stitched_pixels: int
    max_metadata_bytes: int
    max_label_chars: int
    max_gif_long_side: int
    max_gif_long_side_high_quality: int
    max_gif_bytes: int
    gif_frame_duration_ms: int
    gif_frame_duration_ms_high_quality: int
    metadata_key: str
    load_unibox_image_utils: Callable[[], tuple[Callable[..., Any], Callable[..., Any]]]


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
        load_unibox_image_utils=_get_unibox_image_utils,
    )


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
    if "pixel limit" in detail or "size limit" in detail:
        return _error_response(400, "export_too_large", detail)
    if "embedded metadata exceeds configured limit" in detail:
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
            "unibox is required for comparison export. Install with: pip install unibox",
        ) from exc
    _UNIBOX_IMAGE_UTILS = (concatenate_images_horizontally, add_annotation)
    return _UNIBOX_IMAGE_UTILS


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
            if width * height > runtime.max_source_pixels:
                raise HTTPException(400, f"source image exceeds pixel limit: {path}")
            return source.copy(), source_format.lower()
    except HTTPException:
        raise
    except UnidentifiedImageError:
        raise HTTPException(415, f"unsupported source format for {path}")
    except OSError as exc:
        raise HTTPException(415, f"failed to decode source image {path}: {exc}")


def _build_metadata_text(
    *,
    ordered_paths: list[str],
    labels: list[str],
    source_formats: list[str],
    reversed_order: bool,
    output_format: Literal["png", "gif"],
    runtime: ComparisonExportRuntime,
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
        "exported_at": now_iso(),
    }
    if gif_high_quality is not None:
        metadata_payload["gif_high_quality"] = gif_high_quality
    if gif_max_long_side is not None:
        metadata_payload["gif_max_long_side"] = gif_max_long_side
    if gif_frame_duration_ms is not None:
        metadata_payload["gif_frame_duration_ms"] = gif_frame_duration_ms
    metadata_text = json.dumps(metadata_payload, separators=(",", ":"), ensure_ascii=True)
    if len(metadata_text.encode("utf-8")) > runtime.max_metadata_bytes:
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


def _pad_frames(frames: list[Image.Image]) -> list[Image.Image]:
    if not frames:
        return []
    canvas_width = max(frame.width for frame in frames)
    canvas_height = max(frame.height for frame in frames)
    padded: list[Image.Image] = []
    for frame in frames:
        canvas = Image.new("RGB", (canvas_width, canvas_height), (255, 255, 255))
        canvas.paste(frame, ((canvas_width - frame.width) // 2, (canvas_height - frame.height) // 2))
        padded.append(canvas)
    return padded


def _scale_frames(frames: list[Image.Image], scale: float) -> list[Image.Image]:
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
                frame.convert(mode="P", palette=adaptive_palette, colors=colors, dither=dither),
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


def _comparison_export_filename(reverse_order: bool, *, output_format: Literal["png", "gif"]) -> str:
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
    draw.text((max(0, (canvas.width - text_width) // 2), max(0, (title_height - text_height) // 2)), label, fill=(0, 0, 0), font=font)
    return canvas


def _build_gif(
    images: list[Image.Image],
    labels: list[str],
    *,
    embed_metadata: bool,
    high_quality: bool,
    ordered_paths: list[str],
    source_formats: list[str],
    reversed_order: bool,
    runtime: ComparisonExportRuntime,
) -> bytes:
    try:
        _, add_annotation = runtime.load_unibox_image_utils()
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    annotated: list[Image.Image] = []
    prepared: list[Image.Image] = []
    base_frames: list[Image.Image] = []
    scaled_frames: list[Image.Image] = []
    max_long_side = runtime.max_gif_long_side_high_quality if high_quality else runtime.max_gif_long_side
    duration_ms = (
        runtime.gif_frame_duration_ms_high_quality if high_quality else runtime.gif_frame_duration_ms
    )
    try:
        for image, label in zip(images, labels):
            annotated_frame = _annotate_for_export(image, label, add_annotation=add_annotation)
            annotated.append(annotated_frame)
            resized = _resize_image_max_long_side(annotated_frame, max_long_side)
            try:
                prepared.append(resized.convert("RGB"))
            finally:
                resized.close()
        if len(prepared) != len(images):
            raise HTTPException(500, "failed to prepare all gif frames")
        base_frames = _pad_frames(prepared)
        if len(base_frames) != len(images):
            raise HTTPException(500, "failed to normalize gif frame dimensions")
        metadata_comment: bytes | None = None
        if embed_metadata:
            metadata_comment = _build_metadata_text(
                ordered_paths=ordered_paths,
                labels=labels,
                source_formats=source_formats,
                reversed_order=reversed_order,
                output_format="gif",
                runtime=runtime,
                gif_high_quality=high_quality,
                gif_max_long_side=max_long_side,
                gif_frame_duration_ms=duration_ms,
            ).encode("utf-8")
        for scale in (1.0, 0.94, 0.88, 0.82, 0.76, 0.7, 0.64, 0.58, 0.52, 0.46, 0.4, 0.34):
            scaled_frames = _scale_frames(base_frames, scale)
            try:
                for color_count in (256, 224, 192, 160, 128, 112, 96, 80, 64, 48, 32):
                    for dither in (Image.Dither.FLOYDSTEINBERG, Image.Dither.NONE):
                        encoded = _encode_gif_candidate(
                            scaled_frames,
                            colors=color_count,
                            dither=dither,
                            duration_ms=duration_ms,
                            comment=metadata_comment,
                        )
                        if len(encoded) <= runtime.max_gif_bytes:
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
        for frame in (*annotated, *prepared, *base_frames, *scaled_frames):
            frame.close()


def _build_png(
    images: list[Image.Image],
    labels: list[str],
    *,
    embed_metadata: bool,
    ordered_paths: list[str],
    source_formats: list[str],
    reversed_order: bool,
    runtime: ComparisonExportRuntime,
) -> bytes:
    try:
        concatenate_images_horizontally, add_annotation = runtime.load_unibox_image_utils()
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    annotated: list[Image.Image] = []
    stitched: Image.Image | None = None
    try:
        for image, label in zip(images, labels):
            annotated.append(_annotate_for_export(image, label, add_annotation=add_annotation))
        if len(annotated) != len(images):
            raise HTTPException(500, "failed to annotate all images")
        stitched = concatenate_images_horizontally(annotated, max_height=max(image.height for image in annotated))
        if stitched is None:
            raise HTTPException(500, "failed to stitch comparison image")
        if stitched.width * stitched.height > runtime.max_stitched_pixels:
            raise HTTPException(400, "stitched output exceeds configured pixel limit")
        pnginfo: PngImagePlugin.PngInfo | None = None
        if embed_metadata:
            metadata_text = _build_metadata_text(
                ordered_paths=ordered_paths,
                labels=labels,
                source_formats=source_formats,
                reversed_order=reversed_order,
                output_format="png",
                runtime=runtime,
            )
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text(runtime.metadata_key, metadata_text)
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


def export_comparison_response(storage: BrowseStorage, payload: Any) -> Response:
    try:
        body = ExportComparisonRequest.model_validate(payload)
    except ValidationError as exc:
        return _error_response(400, "invalid_request", _first_validation_error_detail(exc))
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
            exported_content = _build_gif(
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
            exported_content = _build_png(
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
    filename = _comparison_export_filename(body.reverse_order, output_format=body.output_format)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=exported_content, media_type=media_type, headers=headers)
