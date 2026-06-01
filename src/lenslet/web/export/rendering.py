"""Image rendering and serialization for comparison exports."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from ..time import now_iso


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


def comparison_export_filename(reverse_order: bool, *, output_format: Literal["png", "gif"]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = "_reverse" if reverse_order else ""
    extension = "gif" if output_format == "gif" else "png"
    return f"comparison{suffix}_{stamp}.{extension}"


def build_gif(
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
    annotated: list[Image.Image] = []
    prepared: list[Image.Image] = []
    base_frames: list[Image.Image] = []
    scaled_frames: list[Image.Image] = []
    max_long_side = runtime.max_gif_long_side_high_quality if high_quality else runtime.max_gif_long_side
    duration_ms = runtime.gif_frame_duration_ms_high_quality if high_quality else runtime.gif_frame_duration_ms
    try:
        for image, label in zip(images, labels):
            annotated_frame = _annotate_for_export(image, label)
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
        raise HTTPException(500, f"failed to build comparison gif: {exc}") from exc
    finally:
        for frame in (*annotated, *prepared, *base_frames, *scaled_frames):
            frame.close()


def build_png(
    images: list[Image.Image],
    labels: list[str],
    *,
    embed_metadata: bool,
    ordered_paths: list[str],
    source_formats: list[str],
    reversed_order: bool,
    runtime: ComparisonExportRuntime,
) -> bytes:
    annotated: list[Image.Image] = []
    stitched: Image.Image | None = None
    try:
        for image, label in zip(images, labels):
            annotated.append(_annotate_for_export(image, label))
        if len(annotated) != len(images):
            raise HTTPException(500, "failed to annotate all images")
        stitched = _stitch_images_horizontally(annotated)
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
        raise HTTPException(500, f"failed to build comparison image: {exc}") from exc
    finally:
        if stitched is not None:
            stitched.close()
        for image in annotated:
            image.close()


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


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB" and "transparency" not in image.info:
        return image.copy()
    if "A" in image.getbands() or "transparency" in image.info:
        rgba = image.convert("RGBA")
        try:
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            try:
                flattened = Image.alpha_composite(background, rgba)
                try:
                    return flattened.convert("RGB")
                finally:
                    flattened.close()
            finally:
                background.close()
        finally:
            rgba.close()
    return image.convert("RGB")


def _load_annotation_font(size: int) -> Any:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # pragma: no cover - Pillow 12 supports sized defaults.
        return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: Any) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text or " ", font=font)
    return max(1, right - left), max(1, bottom - top)


def _split_token_to_width(
    token: str,
    *,
    draw: ImageDraw.ImageDraw,
    font: Any,
    max_width: int,
) -> list[str]:
    chunks: list[str] = []
    current = ""
    for char in token:
        candidate = f"{current}{char}"
        if current and _text_size(draw, candidate, font)[0] > max_width:
            chunks.append(current)
            current = char
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [""]


def _wrap_annotation_lines(
    label: str,
    *,
    draw: ImageDraw.ImageDraw,
    font: Any,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in label.split():
        for chunk_index, chunk in enumerate(
            _split_token_to_width(word, draw=draw, font=font, max_width=max_width),
        ):
            separator = " " if current and chunk_index == 0 else ""
            candidate = f"{current}{separator}{chunk}" if current else chunk
            if current and _text_size(draw, candidate, font)[0] > max_width:
                lines.append(current)
                current = chunk
            else:
                current = candidate
    if current:
        lines.append(current)
    return lines or [label]


def _annotation_text_layout(label: str, image_width: int) -> tuple[Any, list[str], int]:
    padding = min(10, max(1, image_width // 12))
    max_text_width = max(1, image_width - (padding * 2))
    probe = Image.new("RGB", (1, 1), (255, 255, 255))
    try:
        draw = ImageDraw.Draw(probe)
        for size in range(14, 0, -1):
            font = _load_annotation_font(size)
            if size >= 6 and _text_size(draw, label, font)[0] <= max_text_width:
                return font, [label], padding
            lines = _wrap_annotation_lines(label, draw=draw, font=font, max_width=max_text_width)
            if len(lines) <= 6 and all(_text_size(draw, line, font)[0] <= max_text_width for line in lines):
                return font, lines, padding
        font = _load_annotation_font(1)
        return font, _wrap_annotation_lines(label, draw=draw, font=font, max_width=max_text_width), padding
    finally:
        probe.close()


def _annotate_for_export(image: Image.Image, label: str) -> Image.Image:
    base = _flatten_to_rgb(image)
    try:
        font, lines, padding = _annotation_text_layout(label, base.width)
        probe = ImageDraw.Draw(base)
        line_sizes = [_text_size(probe, line, font) for line in lines]
        line_spacing = max(1, line_sizes[0][1] // 4)
        text_height = sum(height for _, height in line_sizes) + (line_spacing * max(0, len(lines) - 1))
        title_height = text_height + (padding * 2)
        canvas = Image.new("RGB", (base.width, base.height + title_height), (255, 255, 255))
        canvas.paste(base, (0, title_height))
        draw = ImageDraw.Draw(canvas)
        y = max(0, (title_height - text_height) // 2)
        for line, (text_width, line_height) in zip(lines, line_sizes):
            draw.text((max(0, (canvas.width - text_width) // 2), y), line, fill=(0, 0, 0), font=font)
            y += line_height + line_spacing
        return canvas
    finally:
        base.close()


def _stitch_images_horizontally(images: list[Image.Image]) -> Image.Image:
    total_width = sum(image.width for image in images)
    canvas_height = max(image.height for image in images)
    stitched = Image.new("RGB", (total_width, canvas_height), (255, 255, 255))
    x_offset = 0
    for image in images:
        stitched.paste(image, (x_offset, 0))
        x_offset += image.width
    return stitched
