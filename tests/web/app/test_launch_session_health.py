from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from lenslet.server import StorageAppOptions, create_app_from_storage
from lenslet.storage.memory.storage import MemoryStorage
from lenslet.web.app.launch_session import (
    LaunchSessionFlag,
    build_launch_session_payload,
)
from lenslet.web.models import LaunchSessionPayload


def test_launch_session_payload_omitted_without_known_provenance(tmp_path: Path) -> None:
    storage = MemoryStorage(root=str(tmp_path))

    response = TestClient(create_app_from_storage(storage)).get("/health")

    assert response.status_code == 200
    assert "launch_session" not in response.json()


def test_health_exposes_supplied_launch_session_payload(tmp_path: Path) -> None:
    storage = MemoryStorage(root=str(tmp_path))
    launch_session = LaunchSessionPayload(
        kind="hf_dataset",
        loaded_from_label="Hugging Face dataset",
        target_label="owner/repo",
        title_label="owner/repo",
        detail_label="Remote table · read-only · 10 rows",
        copy_command="lenslet owner/repo",
    )

    response = TestClient(
        create_app_from_storage(
            storage,
            options=StorageAppOptions(launch_session=launch_session),
        )
    ).get("/health")

    assert response.status_code == 200
    assert response.json()["launch_session"] == {
        "kind": "hf_dataset",
        "loaded_from_label": "Hugging Face dataset",
        "target_label": "owner/repo",
        "title_label": "owner/repo",
        "detail_label": "Remote table · read-only · 10 rows",
        "copy_command": "lenslet owner/repo",
    }


def test_local_launch_session_shortens_paths_and_omits_copy_command() -> None:
    payload = build_launch_session_payload(
        kind="local_parquet",
        raw_target="/private/user/datasets/items.parquet",
        loaded_from_label="Local Parquet",
    )

    assert payload.target_label == ".../items.parquet"
    assert payload.title_label == "items.parquet"
    assert payload.copy_command is None
    serialized = payload.model_dump_json()
    assert "/private/user/datasets/items.parquet" not in serialized


def test_signed_remote_url_is_redacted_and_not_copyable() -> None:
    payload = build_launch_session_payload(
        kind="remote_parquet",
        raw_target="https://user:secret@example.test/items.parquet?X-Amz-Signature=token#frag",
        loaded_from_label="Remote Parquet",
    )

    assert payload.target_label == "https://example.test/items.parquet"
    assert payload.title_label == "https://example.test/items.parquet"
    assert payload.copy_command is None
    serialized = payload.model_dump_json()
    assert "user" not in serialized
    assert "secret" not in serialized
    assert "X-Amz-Signature" not in serialized
    assert "token" not in serialized
    assert "?" not in serialized
    assert "#frag" not in serialized


def test_hf_uri_label_strips_query_and_fragment() -> None:
    payload = build_launch_session_payload(
        kind="hf_dataset",
        raw_target="hf://datasets/owner/repo/path.parquet?token=secret#frag",
        loaded_from_label="Hugging Face dataset",
    )

    assert payload.target_label == "owner/repo/path.parquet"
    assert payload.title_label == "owner/repo/path.parquet"
    assert payload.copy_command is None
    serialized = payload.model_dump_json()
    assert "token" not in serialized
    assert "secret" not in serialized
    assert "#frag" not in serialized
    assert "?" not in serialized


def test_safe_hf_launch_session_builds_copy_command_with_table_flags() -> None:
    payload = build_launch_session_payload(
        kind="hf_dataset",
        raw_target="owner/repo",
        loaded_from_label="Hugging Face dataset",
        command_flags=(
            LaunchSessionFlag("--source-column", "image_url"),
            LaunchSessionFlag("--path-column", "display_path"),
            LaunchSessionFlag("--trust-remote-paths", True),
        ),
    )

    assert payload.target_label == "owner/repo"
    assert payload.title_label == "owner/repo"
    assert payload.copy_command == (
        "lenslet owner/repo --source-column image_url "
        "--path-column display_path --trust-remote-paths"
    )


def test_remote_copy_command_omitted_when_base_dir_would_disclose_absolute_path() -> None:
    payload = build_launch_session_payload(
        kind="hf_dataset",
        raw_target="owner/repo",
        loaded_from_label="Hugging Face dataset",
        command_flags=(LaunchSessionFlag("--base-dir", "/private/images"),),
    )

    assert payload.copy_command is None
