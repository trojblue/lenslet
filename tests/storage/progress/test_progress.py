from __future__ import annotations

import lenslet.storage.progress as progress
import pytest


class FakeTqdm:
    instances: list[FakeTqdm] = []

    def __init__(
        self,
        *,
        total: int,
        desc: str,
        unit: str,
        leave: bool,
        initial: int = 0,
    ) -> None:
        self.total = total
        self.desc = desc
        self.unit = unit
        self.leave = leave
        self.initial = initial
        self.updates: list[int] = []
        self.descriptions: list[str] = [desc]
        self.closed = False
        self.instances.append(self)

    def update(self, delta: int) -> None:
        self.updates.append(delta)

    def set_description(self, desc: str) -> None:
        self.desc = desc
        self.descriptions.append(desc)

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _fake_tqdm(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTqdm.instances = []
    monkeypatch.setattr(progress, "tqdm", FakeTqdm)


def test_progress_bar_snapshot_and_update_contract() -> None:
    bar = progress.ProgressBar()

    bar.update(done=1, total=0, label="ignored")
    assert bar.snapshot() == {"active": False, "done": None, "total": None, "label": None}

    bar.update(done=2, total=5, label="root")
    bar.update(done=4, total=5, label="root")
    bar.update(done=3, total=5, label="root")

    fake = FakeTqdm.instances[-1]
    assert fake.total == 5
    assert fake.unit == "img"
    assert fake.desc == "[lenslet] Indexing (root)"
    assert fake.updates == [2, 2]
    assert bar.snapshot() == {"active": True, "done": 4, "total": 5, "label": "root"}

    bar.update(done=5, total=5, label="root")
    assert fake.updates == [2, 2, 1]
    assert fake.closed is True
    assert bar.snapshot() == {"active": False, "done": 5, "total": 5, "label": "root"}


def test_progress_bar_restarts_when_label_or_total_changes() -> None:
    bar = progress.ProgressBar()

    bar.update(done=1, total=5, label="root")
    first = FakeTqdm.instances[-1]
    bar.update(done=1, total=6, label="root")
    second = FakeTqdm.instances[-1]
    bar.update(done=2, total=6, label="child")
    third = FakeTqdm.instances[-1]

    assert first.closed is True
    assert second.closed is True
    assert first.updates == [1]
    assert second.updates == [1]
    assert third.updates == [2]
    assert third.desc == "[lenslet] Indexing (child)"
    assert bar.snapshot() == {"active": True, "done": 2, "total": 6, "label": "child"}


class BadCloseTqdm(FakeTqdm):
    def close(self) -> None:
        raise OSError(9, "Bad file descriptor")


def test_progress_bar_render_errors_do_not_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(progress, "tqdm", BadCloseTqdm)
    bar = progress.ProgressBar()

    bar.update(done=1, total=1, label="root")

    assert bar.snapshot() == {"active": False, "done": 1, "total": 1, "label": "root"}


def test_leaf_batch_tracker_aggregates_leaf_folder_updates() -> None:
    existing_indexes = {"parent/a"}
    list_calls: list[str] = []

    def list_dir(path: str) -> tuple[list[str], list[str]]:
        list_calls.append(path)
        children: dict[str, tuple[list[str], list[str]]] = {
            "/parent/a": (["one.jpg"], []),
            "/parent/b": (["two.jpg"], []),
            "/parent/c": (["three.jpg"], []),
            "/parent/d": (["four.jpg"], []),
            "/parent/nested": ([], ["leaf"]),
            "/parent/broken": ([], []),
        }
        if path == "/parent/broken":
            raise OSError("cannot inspect child")
        return children[path]

    tracker = progress.LeafBatchTracker(
        threshold=2,
        list_dir=list_dir,
        join=lambda path, name: f"{path.rstrip('/')}/{name}",
        normalize_path=lambda path: path.strip("/"),
        display_path=lambda path: f"/{path}",
        index_exists=existing_indexes.__contains__,
    )

    tracker.maybe_prepare("/parent", ["a", "b", "c", "d", "nested", "broken"])

    assert list_calls == [
        "/parent/a",
        "/parent/b",
        "/parent/c",
        "/parent/d",
        "/parent/nested",
        "/parent/broken",
    ]
    assert tracker.use_batch("parent/a", []) is True
    assert tracker.use_batch("parent/nested", []) is False
    assert tracker.use_batch("parent/b", ["child"]) is False

    tracker.update("parent/a")
    assert FakeTqdm.instances == []

    tracker.update("parent/b")
    batch_bar = FakeTqdm.instances[-1]
    assert batch_bar.total == 4
    assert batch_bar.unit == "folder"
    assert batch_bar.initial == 1
    assert batch_bar.updates == [1]
    assert batch_bar.desc == "updating folder: /parent/b (2/4)"

    tracker.update("parent/b")
    tracker.update("parent/c")
    tracker.update("parent/d")

    assert batch_bar.updates == [1, 1, 1]
    assert batch_bar.descriptions[-1] == "updating folder: /parent/d (4/4)"
    assert batch_bar.closed is True
    assert tracker.use_batch("parent/b", []) is False


def test_leaf_batch_tracker_clear_closes_active_batch_and_resets_checked() -> None:
    existing_indexes: set[str] = set()

    def make_tracker() -> progress.LeafBatchTracker:
        return progress.LeafBatchTracker(
            threshold=1,
            list_dir=lambda path: (["image.jpg"], []),
            join=lambda path, name: f"{path.rstrip('/')}/{name}",
            normalize_path=lambda path: path.strip("/"),
            display_path=lambda path: f"/{path}",
            index_exists=existing_indexes.__contains__,
        )

    tracker = make_tracker()
    tracker.maybe_prepare("/parent", ["a", "b"])
    tracker.update("parent/a")
    first_bar = FakeTqdm.instances[-1]

    tracker.clear()

    assert first_bar.closed is True
    assert tracker.use_batch("parent/b", []) is False

    tracker.maybe_prepare("/parent", ["a", "b"])
    tracker.update("parent/b")

    assert len(FakeTqdm.instances) == 2
    assert FakeTqdm.instances[-1] is not first_bar
