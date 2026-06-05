"""Hugging Face parquet table loading for the browse CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..storage.table.input import TableInput
from ..storage.table.launch_sources import detect_source_column
from ..storage.table.pyarrow_runtime import require_pyarrow


@dataclass(frozen=True, slots=True)
class HfTableUri:
    repo_id: str
    path_in_repo: str
    revision: str


@dataclass(frozen=True, slots=True)
class RemoteTableLoadResult:
    table: TableInput
    source_column: str | None = None


def is_hf_table_uri(uri: str) -> bool:
    return uri.startswith("hf://")


def parse_hf_table_uri(uri: str) -> HfTableUri:
    if not is_hf_table_uri(uri):
        raise ValueError("Hugging Face table URI must start with 'hf://'")

    trimmed = uri[len("hf://") :].strip("/")
    if not trimmed:
        raise ValueError("Hugging Face table URI must include owner/repo")

    parts = trimmed.split("/")
    if parts[0] == "datasets":
        parts = parts[1:]
    elif parts[0] in {"models", "spaces"}:
        raise ValueError("Hugging Face table loading supports dataset repos only")

    if len(parts) < 2:
        raise ValueError("Hugging Face table URI must include owner/repo")

    owner = parts[0]
    repo_and_revision = parts[1]
    repo_name, separator, revision = repo_and_revision.partition("@")
    if not repo_name:
        raise ValueError("Hugging Face table URI is missing the repo name")

    return HfTableUri(
        repo_id=f"{owner}/{repo_name}",
        path_in_repo="/".join(parts[2:]),
        revision=revision if separator and revision else "main",
    )


def select_hf_parquet_files(files: list[str], path_in_repo: str) -> tuple[str, ...]:
    parquet_files = sorted(file for file in files if file.endswith(".parquet"))
    if not path_in_repo:
        selected = parquet_files
    elif path_in_repo.endswith(".parquet"):
        selected = [path_in_repo] if path_in_repo in files else []
    elif path_in_repo in files:
        selected = []
    else:
        prefix = path_in_repo.rstrip("/") + "/"
        selected = [file for file in parquet_files if file.startswith(prefix)]

    if selected:
        return tuple(selected)
    if path_in_repo:
        raise ValueError(f"No parquet files found in Hugging Face repo path '{path_in_repo}'")
    raise ValueError("No parquet files found in Hugging Face dataset repo")


def load_hf_parquet_table(
    uri: str,
    *,
    preferred_source_column: str | None = None,
) -> RemoteTableLoadResult:
    parsed = parse_hf_table_uri(uri)
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError as exc:
        raise ImportError(
            'Hugging Face table loading requires huggingface_hub. Install with: pip install "lenslet[remote]"'
        ) from exc

    try:
        files = HfApi().list_repo_files(
            parsed.repo_id,
            repo_type="dataset",
            revision=parsed.revision,
        )
    except Exception as exc:
        raise RuntimeError(f"failed to list Hugging Face dataset files: {exc}") from exc

    parquet_files = select_hf_parquet_files(files, parsed.path_in_repo)
    local_paths = _download_hf_parquet_files(
        repo_id=parsed.repo_id,
        revision=parsed.revision,
        parquet_files=parquet_files,
        hf_hub_download=hf_hub_download,
    )
    try:
        source_column = preferred_source_column or _detect_hf_parquet_source_column(local_paths)
        table = _read_hf_parquet_files(local_paths)
    except Exception as exc:
        raise RuntimeError(f"failed to read Hugging Face parquet table: {exc}") from exc
    return RemoteTableLoadResult(table=table, source_column=source_column)


def _download_hf_parquet_files(
    *,
    repo_id: str,
    revision: str,
    parquet_files: tuple[str, ...],
    hf_hub_download,
) -> tuple[Path, ...]:
    local_paths: list[Path] = []
    for filename in parquet_files:
        try:
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                repo_type="dataset",
                revision=revision,
            )
        except Exception as exc:
            raise RuntimeError(f"failed to download Hugging Face parquet file '{filename}': {exc}") from exc
        local_paths.append(Path(local_path))
    return tuple(local_paths)


def _detect_hf_parquet_source_column(local_paths: tuple[Path, ...]) -> str | None:
    for local_path in local_paths:
        source_column = detect_source_column(str(local_path), base_dir=None)
        if source_column:
            return source_column
    return None


def _read_hf_parquet_files(local_paths: tuple[Path, ...]) -> TableInput:
    pyarrow, parquet = require_pyarrow()
    tables = [parquet.read_table(str(path)) for path in local_paths]
    if len(tables) == 1:
        return tables[0]
    return pyarrow.concat_tables(tables, promote_options="default")
