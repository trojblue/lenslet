from __future__ import annotations

import logging
from typing import get_type_hints

from lenslet.indexing_status import (
    CliIndexingReporter,
    IndexingState,
    IndexingLifecycle,
    format_cli_indexing_message,
    indexing_state_is_terminal,
    indexing_state_requires_poll,
    normalize_indexing_payload,
)


def test_normalize_indexing_payload_clamps_progress() -> None:
    normalized = normalize_indexing_payload(
        {
            "state": "running",
            "scope": "/shots",
            "done": 12,
            "total": 9,
            "started_at": "2026-02-12T00:00:00Z",
        }
    )
    assert normalized == {
        "state": "running",
        "scope": "/shots",
        "done": 9,
        "total": 9,
        "started_at": "2026-02-12T00:00:00Z",
    }


def test_cli_reporter_emits_running_and_ready_once() -> None:
    lines: list[str] = []
    reporter = CliIndexingReporter(write=lines.append)

    reporter.handle_update({"state": "running", "scope": "/", "done": 1, "total": 4})
    reporter.handle_update({"state": "running", "scope": "/", "done": 2, "total": 4})
    reporter.handle_update({"state": "ready", "scope": "/", "done": 4, "total": 4})
    reporter.handle_update({"state": "ready", "scope": "/", "done": 4, "total": 4})

    assert lines == [
        "[lenslet] Startup indexing in progress: 1/4.",
        "[lenslet] Startup indexing ready: 4/4.",
    ]


def test_cli_reporter_emits_error_transitions_deterministically() -> None:
    lines: list[str] = []
    reporter = CliIndexingReporter(write=lines.append)

    reporter.handle_update({"state": "running", "scope": "/", "done": 1, "total": 4})
    reporter.handle_update({"state": "error", "scope": "/", "error": "forced warm index failure"})
    reporter.handle_update({"state": "error", "scope": "/", "error": "forced warm index failure"})

    assert lines == [
        "[lenslet] Startup indexing in progress: 1/4.",
        "[lenslet] Startup indexing failed: forced warm index failure",
    ]


def test_state_helpers_match_polling_contract() -> None:
    assert indexing_state_requires_poll("idle")
    assert indexing_state_requires_poll("running")
    assert not indexing_state_requires_poll("ready")
    assert not indexing_state_requires_poll("error")
    assert not indexing_state_is_terminal("running")
    assert indexing_state_is_terminal("ready")
    assert indexing_state_is_terminal("error")


def test_indexing_boundary_annotations_use_runtime_narrowing_types() -> None:
    assert get_type_hints(normalize_indexing_payload)["payload"] is object
    assert get_type_hints(format_cli_indexing_message)["payload"] is object
    assert get_type_hints(indexing_state_requires_poll)["state"] == IndexingState
    assert get_type_hints(indexing_state_is_terminal)["state"] == IndexingState


def test_cli_formatter_handles_scope_and_error_message() -> None:
    message = format_cli_indexing_message(
        {"state": "error", "scope": "/shots", "error": "forced warm index failure"}
    )
    assert message == "Startup indexing failed (/shots): forced warm index failure"


def test_indexing_lifecycle_logs_listener_failures(caplog) -> None:
    lifecycle = IndexingLifecycle(scope="/")
    delivered: list[str] = []

    def _failing_listener(payload) -> None:
        delivered.append(payload["state"])
        raise RuntimeError("listener failed")

    lifecycle.subscribe(_failing_listener)

    with caplog.at_level(logging.WARNING, logger="lenslet.indexing_status"):
        lifecycle.start()

    assert delivered == ["running"]
    assert lifecycle.snapshot()["state"] == "running"
    assert "indexing listener callback failed: listener failed" in caplog.text
