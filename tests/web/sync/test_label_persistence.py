from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
import lenslet.workspace as workspace_module

from lenslet.web.sync.events import EventBroker, IdempotencyCache
from lenslet.web.sync.labels import LabelPersistenceError, LoadedLabelState, load_label_state
from lenslet.web.sync.persistence import LabelWriteBuffer
from lenslet.workspace import Workspace


class _Storage:
    def __init__(self) -> None:
        self.sidecars: dict[str, dict] = {}

    def ensure_sidecar(self, path: str) -> dict:
        return self.sidecars.setdefault(path, {"version": 1})

    def set_sidecar(self, path: str, sidecar: dict) -> None:
        self.sidecars[path] = dict(sidecar)


def _writer(
    workspace: Workspace,
    now: list[float],
    **kwargs,
) -> tuple[LabelWriteBuffer, EventBroker]:
    broker = EventBroker()
    writer = LabelWriteBuffer(
        workspace,
        LoadedLabelState(0, {}, {}),
        broker=broker,
        idempotency_cache=IdempotencyCache(),
        clock=lambda: now[0],
        background=False,
        **kwargs,
    )
    return writer, broker


def _event(writer: LabelWriteBuffer, event_id: int, *, note: str = "saved") -> dict[str, object]:
    identity = writer.accepted_identity(event_id)
    sidecar = {
        "v": 1,
        "tags": [],
        "notes": note,
        "star": None,
        "version": event_id + 1,
        "updated_at": "2026-07-18T00:00:00Z",
        "updated_by": "test",
    }
    mutation_payload = {
        "sidecar": sidecar,
        "mutation_id": f"idem-{event_id}",
        "accepted_event": identity,
        "persistence": "pending",
        "durable_watermark": writer.status()["durable_watermark"],
    }
    return {
        "id": event_id,
        "type": "item-updated",
        "path": "/sample.jpg",
        **sidecar,
        "mutation_id": f"idem-{event_id}",
        "accepted_event": identity,
        "mutation_result": {"status": 200, "payload": mutation_payload},
    }


def _accept_ready(writer: LabelWriteBuffer, event_id: int, *, note: str = "saved") -> dict[str, object]:
    event = _event(writer, event_id, note=note)
    writer.accept(event)
    writer.mark_ready(event_id)
    return event


def test_idle_and_continuous_flush_use_monotonic_deadlines(tmp_path: Path) -> None:
    now = [0.0]
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    writer, _broker = _writer(workspace, now)
    _accept_ready(writer, 1)

    now[0] = 0.999
    assert writer.flush_due() is False
    now[0] = 1.0
    assert writer.flush_due() is True
    assert writer.status()["durable_watermark"]["event_id"] == 1

    for event_id in range(2, 17):
        now[0] = 1.0 + (event_id - 2) * 0.9
        _accept_ready(writer, event_id, note=f"continuous-{event_id}")
    now[0] = 13.999
    assert writer.flush_due() is False
    now[0] = 14.0
    assert writer.flush_due() is True
    assert writer.status()["durable_watermark"]["event_id"] == 16


def test_admission_enforces_exact_count_and_byte_caps(tmp_path: Path) -> None:
    now = [0.0]
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    probe, _broker = _writer(workspace, now)
    encoded_size = len(
        (json.dumps(_event(probe, 1), separators=(",", ":")) + "\n").encode("utf-8")
    )

    count_writer, _ = _writer(
        workspace,
        now,
        max_pending_events=2,
        max_pending_bytes=encoded_size * 10,
    )
    count_writer.accept(_event(count_writer, 1))
    count_writer.accept(_event(count_writer, 2))
    with pytest.raises(LabelPersistenceError, match="queue is full"):
        count_writer.accept(_event(count_writer, 3))

    byte_writer, _ = _writer(
        workspace,
        now,
        max_pending_events=2,
        max_pending_bytes=encoded_size,
    )
    byte_writer.accept(_event(byte_writer, 1))
    with pytest.raises(LabelPersistenceError, match="byte capacity"):
        byte_writer.accept(_event(byte_writer, 2))


def test_failure_retains_pending_state_and_retry_recovers(tmp_path: Path, monkeypatch) -> None:
    now = [0.0]
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    writer, _broker = _writer(workspace, now)
    _accept_ready(writer, 1)
    original_append = workspace.append_labels_log_batch

    monkeypatch.setattr(
        workspace,
        "append_labels_log_batch",
        lambda _entries: (_ for _ in ()).throw(OSError("disk full")),
    )
    assert writer.flush_due(force=True) is False
    assert writer.status()["state"] == "failed"
    assert writer.status()["pending_count"] == 1
    with pytest.raises(LabelPersistenceError, match="unavailable"):
        writer.accept(_event(writer, 2))

    monkeypatch.setattr(workspace, "append_labels_log_batch", original_append)
    now[0] = 1.0
    assert writer.flush_due(force=True) is True
    status = writer.status()
    assert status["state"] == "saved"
    assert status["durable_watermark"]["event_id"] == 1


def test_slow_success_latches_deadline_breach_until_distinct_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    now = [0.0]
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    writer, broker = _writer(workspace, now)
    _accept_ready(writer, 1)
    original_append = workspace.append_labels_log_batch

    def slow_append(entries: list[dict]) -> None:
        original_append(entries)
        now[0] += 2.1

    monkeypatch.setattr(workspace, "append_labels_log_batch", slow_append)
    now[0] = 13.0
    assert writer.flush_due() is False
    status = writer.status()
    assert status["state"] == "failed"
    assert status["pending_count"] == 1
    assert status["deadline_breach_total"] == 1
    states = [record["data"]["state"] for record in broker.replay(0)]
    assert states[-1:] == ["failed"]

    monkeypatch.setattr(workspace, "append_labels_log_batch", original_append)
    assert writer.flush_due(force=True) is True
    assert writer.status()["state"] == "saved"
    assert [entry["id"] for entry in workspace.read_labels_log()] == [1]


def test_deadline_flush_completes_within_reserved_io_margin(tmp_path: Path, monkeypatch) -> None:
    now = [0.0]
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    writer, _broker = _writer(workspace, now)
    _accept_ready(writer, 1)
    original_append = workspace.append_labels_log_batch

    def bounded_append(entries: list[dict]) -> None:
        original_append(entries)
        now[0] += 1.9

    monkeypatch.setattr(workspace, "append_labels_log_batch", bounded_append)
    now[0] = 13.0

    assert writer.flush_due() is True
    status = writer.status()
    assert status["durable_watermark"]["event_id"] == 1
    assert status["deadline_breach_total"] == 0
    assert now[0] == pytest.approx(14.9)


def test_blocked_io_watchdog_rejects_admission_at_deadline(tmp_path: Path, monkeypatch) -> None:
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    broker = EventBroker()
    writer = LabelWriteBuffer(
        workspace,
        LoadedLabelState(0, {}, {}),
        broker=broker,
        idempotency_cache=IdempotencyCache(),
        idle_flush_seconds=0.01,
        deadline_start_seconds=0.02,
        hard_deadline_seconds=0.1,
        io_margin_seconds=0.1,
        retry_seconds=0.01,
        background=False,
    )
    _accept_ready(writer, 1)
    original_append = workspace.append_labels_log_batch
    entered = threading.Event()
    release = threading.Event()

    def blocked_append(entries: list[dict]) -> None:
        entered.set()
        assert release.wait(timeout=1.0)
        original_append(entries)

    monkeypatch.setattr(workspace, "append_labels_log_batch", blocked_append)
    result: list[bool] = []
    thread = threading.Thread(target=lambda: result.append(writer.flush_due(force=True)), daemon=True)
    thread.start()
    assert entered.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while writer.status()["state"] != "failed" and time.monotonic() < deadline:
        time.sleep(0.005)
    assert writer.status()["state"] == "failed"
    with pytest.raises(LabelPersistenceError, match="unavailable"):
        writer.accept(_event(writer, 2))

    release.set()
    thread.join(timeout=1.0)
    assert result == [False]
    monkeypatch.setattr(workspace, "append_labels_log_batch", original_append)
    assert writer.flush_due(force=True) is True
    assert writer.status()["state"] == "saved"
    assert [entry["id"] for entry in workspace.read_labels_log()] == [1]


def test_partial_batch_retry_truncates_tail_and_does_not_duplicate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    now = [0.0]
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    writer, _broker = _writer(workspace, now)
    _accept_ready(writer, 1)
    _accept_ready(writer, 2)
    original_append_and_sync = workspace_module._append_and_sync

    def partial_append(handle, payload: bytes) -> None:
        first_line_end = payload.index(b"\n") + 1
        handle.write(payload[: first_line_end + 20])
        handle.flush()
        raise OSError("partial write")

    monkeypatch.setattr(workspace_module, "_append_and_sync", partial_append)
    assert writer.flush_due(force=True) is False
    monkeypatch.setattr(workspace_module, "_append_and_sync", original_append_and_sync)
    assert writer.flush_due(force=True) is True

    result = workspace.read_labels_log_result()
    assert result.status == "ok"
    assert [entry["id"] for entry in result.value] == [1, 2]


def test_fsync_retry_reuses_complete_batch_without_duplicate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    now = [0.0]
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    writer, _broker = _writer(workspace, now)
    _accept_ready(writer, 1)
    original_append_and_sync = workspace_module._append_and_sync

    def fail_after_write(handle, payload: bytes) -> None:
        handle.write(payload)
        handle.flush()
        raise OSError("fsync failed")

    monkeypatch.setattr(workspace_module, "_append_and_sync", fail_after_write)
    assert writer.flush_due(force=True) is False
    monkeypatch.setattr(workspace_module, "_append_and_sync", original_append_and_sync)
    assert writer.flush_due(force=True) is True

    result = workspace.read_labels_log_result()
    assert result.status == "ok"
    assert [entry["id"] for entry in result.value] == [1]


def test_restart_recovers_durable_prefix_and_repairs_crash_partial_tail(tmp_path: Path) -> None:
    now = [0.0]
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    writer, _broker = _writer(workspace, now)
    _accept_ready(writer, 1)
    writer.flush_all()
    log_path = workspace.labels_log_path()
    assert log_path is not None
    with log_path.open("ab") as handle:
        handle.write(b'{"id":2,"accepted_event":{"boot_epoch":"crashed"')

    storage = _Storage()
    loaded = load_label_state(storage, workspace)
    assert loaded.last_event_id == 1
    assert storage.sidecars["/sample.jpg"]["notes"] == "saved"

    restarted = LabelWriteBuffer(
        workspace,
        loaded,
        broker=EventBroker(),
        idempotency_cache=IdempotencyCache(),
        clock=lambda: now[0],
        background=False,
    )
    _accept_ready(restarted, 2, note="after-restart")
    restarted.flush_all()
    result = workspace.read_labels_log_result()
    assert result.status == "ok"
    assert [entry["id"] for entry in result.value] == [1, 2]


def test_restart_loads_only_durable_events_and_idempotency(tmp_path: Path) -> None:
    now = [0.0]
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    writer, _broker = _writer(workspace, now)
    _accept_ready(writer, 1, note="pending")

    before = load_label_state(_Storage(), workspace)
    assert before.last_event_id == 0
    assert before.items == {}
    assert before.mutations == {}

    writer.flush_all()
    storage = _Storage()
    after = load_label_state(storage, workspace)
    assert after.last_event_id == 1
    assert after.items["/sample.jpg"]["notes"] == "pending"
    assert after.mutations["idem-1"]["payload"]["mutation_id"] == "idem-1"
    assert after.mutations["idem-1"]["payload"]["persistence"] == "saved"
    assert storage.sidecars["/sample.jpg"]["notes"] == "pending"


def test_close_forces_a_final_flush(tmp_path: Path) -> None:
    now = [0.0]
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    writer, _broker = _writer(workspace, now)
    _accept_ready(writer, 1)

    writer.close()

    assert workspace.read_labels_log()[0]["id"] == 1
    assert workspace.read_labels_snapshot()["last_event_id"] == 1


def test_broker_reservations_publish_in_order_without_holding_the_lock() -> None:
    broker = EventBroker()
    first_id = broker.reserve()
    second_id = broker.publish("presence", {"gallery_id": "/", "viewing": 1, "editing": 0})
    assert broker.replay(0) == []

    broker.publish_reserved(first_id, "persistence", {"state": "pending"})

    assert [record["id"] for record in broker.replay(0)] == [first_id, second_id]


def test_cancelled_broker_reservation_releases_later_events() -> None:
    broker = EventBroker()
    cancelled_id = broker.reserve()
    published_id = broker.publish("presence", {"gallery_id": "/", "viewing": 1, "editing": 0})

    broker.cancel_reserved(cancelled_id)

    assert [record["id"] for record in broker.replay(0)] == [published_id]
