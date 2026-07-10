"""Display-safe launch provenance for browse app health payloads."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import ParseResult, urlparse, urlunparse

from ..models import LaunchSessionPayload


@dataclass(frozen=True, slots=True)
class LaunchSessionFlag:
    name: str
    value: str | bool | None = None


LOCAL_LAUNCH_KINDS = frozenset({"local_folder", "local_parquet", "local_items_parquet"})
REMOTE_COPYABLE_SCHEMES = frozenset({"hf", "http", "https", "s3"})


def build_launch_session_payload(
    *,
    kind: str,
    raw_target: str,
    loaded_from_label: str,
    detail_label: str | None = None,
    command_flags: tuple[LaunchSessionFlag, ...] = (),
) -> LaunchSessionPayload:
    target_label = redacted_launch_target(raw_target, kind=kind)
    title_label = launch_title_label(raw_target, kind=kind, target_label=target_label)
    return LaunchSessionPayload(
        kind=kind,
        loaded_from_label=loaded_from_label,
        target_label=target_label,
        title_label=title_label,
        detail_label=detail_label,
        copy_command=copyable_launch_command(
            raw_target,
            kind=kind,
            flags=command_flags,
        ),
    )


def table_detail_label(
    *,
    table_kind: str = "Table",
    workspace_mode: str | None,
    row_count: int | None = None,
) -> str:
    parts = [table_kind]
    workspace = _workspace_label(workspace_mode)
    if workspace:
        parts.append(workspace)
    if row_count is not None:
        parts.append(_format_count(row_count, "row"))
    return " · ".join(parts)


def filesystem_detail_label(*, workspace_mode: str | None) -> str:
    parts = ["Filesystem dataset"]
    workspace = _workspace_label(workspace_mode)
    if workspace:
        parts.append(workspace)
    return " · ".join(parts)


def redacted_launch_target(raw_target: str, *, kind: str) -> str:
    if kind in LOCAL_LAUNCH_KINDS:
        return _short_local_path(raw_target)
    if kind == "hf_dataset":
        return _redacted_hf_target(raw_target)
    if kind == "remote_parquet":
        return _redacted_remote_uri(raw_target)
    return _fallback_label(raw_target)


def launch_title_label(raw_target: str, *, kind: str, target_label: str | None = None) -> str:
    if kind in LOCAL_LAUNCH_KINDS:
        return Path(raw_target).name or (target_label or "local source")
    label = target_label if target_label is not None else redacted_launch_target(raw_target, kind=kind)
    return label or "source"


def copyable_launch_command(
    raw_target: str,
    *,
    kind: str,
    flags: tuple[LaunchSessionFlag, ...] = (),
) -> str | None:
    target = _copyable_target(raw_target, kind=kind)
    if target is None:
        return None
    parts = ["lenslet", target]
    for flag in flags:
        if flag.value is False or flag.value is None:
            continue
        parts.append(flag.name)
        if flag.value is True:
            continue
        value = str(flag.value)
        if not _copyable_flag_value(flag.name, value):
            return None
        parts.append(value)
    return " ".join(shlex.quote(part) for part in parts)


def table_input_row_count(table: object) -> int | None:
    value = getattr(table, "num_rows", None)
    if isinstance(value, int):
        return value
    try:
        return len(table)  # type: ignore[arg-type]
    except TypeError:
        return None


def _format_count(value: int, noun: str) -> str:
    suffix = noun if value == 1 else f"{noun}s"
    return f"{value:,} {suffix}"


def _workspace_label(workspace_mode: str | None) -> str | None:
    if workspace_mode is None:
        return None
    if workspace_mode == "parquet-sidecar":
        return "writable sidecar"
    if workspace_mode == "temp":
        return "temp workspace"
    if workspace_mode == "workspace":
        return "workspace"
    return workspace_mode


def _short_local_path(raw_target: str) -> str:
    expanded = os.path.expanduser(str(raw_target))
    name = Path(expanded).name
    if name:
        return f".../{name}"
    return "[local path]"


def _fallback_label(raw_target: str) -> str:
    text = str(raw_target).strip()
    return text if text else "source"


def _redacted_hf_target(raw_target: str) -> str:
    text = str(raw_target).strip()
    if text.startswith("hf://"):
        try:
            parsed = urlparse(text)
        except ValueError:
            path = text[len("hf://") :].split("?", 1)[0].split("#", 1)[0].strip("/")
        else:
            path = "/".join(part for part in (parsed.netloc, parsed.path.strip("/")) if part).strip("/")
        parts = path.split("/")
        if parts and parts[0] == "datasets":
            parts = parts[1:]
        if len(parts) >= 2:
            return "/".join(parts)
        return path or "Hugging Face dataset"
    return text


def _safe_netloc(parsed: ParseResult) -> str:
    host = parsed.hostname or ""
    if parsed.port is not None:
        return f"{host}:{parsed.port}"
    return host


def _redacted_remote_uri(raw_target: str) -> str:
    text = str(raw_target).strip()
    try:
        parsed = urlparse(text)
    except ValueError:
        return _fallback_label(text)
    if parsed.scheme not in REMOTE_COPYABLE_SCHEMES:
        return _fallback_label(text)
    if parsed.scheme == "hf":
        return _redacted_hf_target(text)
    return urlunparse((parsed.scheme, _safe_netloc(parsed), parsed.path, "", "", ""))


def _copyable_target(raw_target: str, *, kind: str) -> str | None:
    if kind in LOCAL_LAUNCH_KINDS:
        return None
    text = str(raw_target).strip()
    if not text:
        return None
    if kind == "hf_dataset" and "://" not in text:
        return text
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if parsed.scheme not in REMOTE_COPYABLE_SCHEMES:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    return text


def _copyable_flag_value(flag_name: str, value: str) -> bool:
    if "\x00" in value or not value.strip():
        return False
    if flag_name == "--base-dir":
        path = Path(value).expanduser()
        if path.is_absolute() or value.startswith("~"):
            return False
        return ".." not in Path(value).parts
    if "://" in value:
        try:
            parsed = urlparse(value)
        except ValueError:
            return False
        return not (parsed.username or parsed.password or parsed.query or parsed.fragment)
    return True
