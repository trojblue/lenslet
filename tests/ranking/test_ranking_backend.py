from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.ranking.app import create_ranking_app
from lenslet.ranking.dataset import load_ranking_dataset
from lenslet.ranking.persistence import RankingPersistenceError, RankingResultsStore, resolve_results_path


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 12), color=(30, 90, 150)).save(path, format="JPEG")


def _write_dataset(tmp_path: Path) -> Path:
    _make_image(tmp_path / "images" / "a.jpg")
    _make_image(tmp_path / "images" / "b.jpg")
    _make_image(tmp_path / "images" / "c.jpg")
    payload = [
        {
            "instance_id": "one",
            "images": ["images/a.jpg", "images/b.jpg"],
        },
        {
            "instance_id": "two",
            "images": ["images/c.jpg", "images/a.jpg"],
        },
    ]
    dataset_path = tmp_path / "ranking_dataset.json"
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")
    return dataset_path


def test_load_ranking_dataset_resolves_local_paths(tmp_path: Path) -> None:
    dataset_path = _write_dataset(tmp_path)
    dataset = load_ranking_dataset(dataset_path)

    assert dataset.instance_count == 2
    first = dataset.get_instance("one")
    assert first is not None
    assert first.image_ids == ("0", "1")
    assert first.images[0].abs_path.exists()
    assert first.images[1].abs_path.exists()


def test_results_store_collapses_latest_and_ignores_malformed_tail(tmp_path: Path) -> None:
    results_path = tmp_path / "results.jsonl"
    store = RankingResultsStore(results_path)

    store.append({"instance_id": "one", "instance_index": 0, "completed": False, "save_seq": 1})
    store.append({"instance_id": "one", "instance_index": 0, "completed": True, "save_seq": 2})
    store.append({"instance_id": "one", "instance_index": 0, "completed": False, "save_seq": 1})
    with results_path.open("a", encoding="utf-8") as handle:
        handle.write("{\"broken_json\":")
    store.append({"instance_id": "two", "instance_index": 1, "completed": True, "save_seq": 1})

    latest = store.latest_entries_by_instance()
    assert latest["one"]["completed"] is True
    assert latest["one"]["save_seq"] == 2
    assert latest["two"]["completed"] is True


def test_results_store_without_save_seq_prefers_latest_line(tmp_path: Path) -> None:
    results_path = tmp_path / "results.jsonl"
    store = RankingResultsStore(results_path)

    store.append({"instance_id": "one", "instance_index": 0, "completed": False})
    store.append({"instance_id": "one", "instance_index": 0, "completed": True})

    latest = store.latest_entries_by_instance()
    assert latest["one"]["completed"] is True


def test_results_path_validation_rejects_image_directories(tmp_path: Path) -> None:
    dataset_path = _write_dataset(tmp_path)
    dataset = load_ranking_dataset(dataset_path)
    image_dir = tmp_path / "images"

    with pytest.raises(RankingPersistenceError):
        resolve_results_path(
            dataset.dataset_path,
            dataset.all_image_paths(),
            override_path=image_dir / "results.jsonl",
        )


def test_default_results_path_allows_nested_workspace_under_image_root(tmp_path: Path) -> None:
    _make_image(tmp_path / "a.jpg")
    dataset_path = tmp_path / "ranking_dataset.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "instance_id": "solo",
                    "images": ["a.jpg"],
                }
            ]
        ),
        encoding="utf-8",
    )

    app = create_ranking_app(dataset_path)
    health = TestClient(app).get("/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "ranking"


def test_ranking_routes_end_to_end(tmp_path: Path) -> None:
    dataset_path = _write_dataset(tmp_path)
    app = create_ranking_app(dataset_path)
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "ranking"

    dataset_resp = client.get("/rank/dataset")
    assert dataset_resp.status_code == 200
    dataset_json = dataset_resp.json()
    assert dataset_json["instance_count"] == 2
    first_instance = dataset_json["instances"][0]
    first_image = first_instance["images"][0]

    image_resp = client.get(first_image["url"])
    assert image_resp.status_code == 200
    assert image_resp.headers["content-type"] == "image/jpeg"

    save_completed = client.post(
        "/rank/save",
        json={
            "instance_id": "one",
            "final_ranks": [["0", "1"]],
            "completed": True,
            "save_seq": 1,
        },
    )
    assert save_completed.status_code == 200

    save_partial = client.post(
        "/rank/save",
        json={
            "instance_id": "two",
            "final_ranks": [["0"]],
            "completed": False,
            "save_seq": 1,
        },
    )
    assert save_partial.status_code == 200

    progress = client.get("/rank/progress")
    assert progress.status_code == 200
    progress_json = progress.json()
    assert progress_json["completed_instance_ids"] == ["one"]
    assert progress_json["last_completed_instance_index"] == 0
    assert progress_json["resume_instance_index"] == 1

    export_all = client.get("/rank/export")
    assert export_all.status_code == 200
    assert export_all.json()["count"] == 2

    export_completed = client.get("/rank/export", params={"completed_only": True})
    assert export_completed.status_code == 200
    assert export_completed.json()["count"] == 1


def test_ranking_save_requires_local_origin(tmp_path: Path) -> None:
    dataset_path = _write_dataset(tmp_path)
    app = create_ranking_app(dataset_path)
    client = TestClient(app, base_url="https://public.trycloudflare.com")

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["can_write"] is False

    response = client.post(
        "/rank/save",
        json={
            "instance_id": "one",
            "final_ranks": [["0", "1"]],
            "completed": True,
            "save_seq": 1,
        },
    )
    assert response.status_code == 403
    assert response.json() == {
        "error": "local_origin_required",
        "message": "mutations require a local Lenslet origin",
    }


def test_save_rejects_incomplete_completed_payload(tmp_path: Path) -> None:
    dataset_path = _write_dataset(tmp_path)
    app = create_ranking_app(dataset_path)
    client = TestClient(app)

    response = client.post(
        "/rank/save",
        json={
            "instance_id": "one",
            "final_ranks": [["0"]],
            "completed": True,
        },
    )
    assert response.status_code == 400
    assert "include every image" in response.json()["detail"]


def test_save_rejects_unknown_and_duplicate_image_ids(tmp_path: Path) -> None:
    dataset_path = _write_dataset(tmp_path)
    app = create_ranking_app(dataset_path)
    client = TestClient(app)

    unknown = client.post(
        "/rank/save",
        json={
            "instance_id": "one",
            "final_ranks": [["0", "99"]],
            "completed": False,
        },
    )
    assert unknown.status_code == 400
    assert "unknown image_id" in unknown.json()["detail"]

    duplicate = client.post(
        "/rank/save",
        json={
            "instance_id": "one",
            "final_ranks": [["0", "0"]],
            "completed": False,
        },
    )
    assert duplicate.status_code == 400
    assert "duplicate image_id" in duplicate.json()["detail"]


def test_save_accepts_stale_writes_but_progress_uses_latest_seq(tmp_path: Path) -> None:
    dataset_path = _write_dataset(tmp_path)
    app = create_ranking_app(dataset_path)
    client = TestClient(app)

    first = client.post(
        "/rank/save",
        json={
            "instance_id": "one",
            "final_ranks": [["0", "1"]],
            "completed": True,
            "save_seq": 5,
        },
    )
    assert first.status_code == 200

    stale = client.post(
        "/rank/save",
        json={
            "instance_id": "one",
            "final_ranks": [["0"]],
            "completed": False,
            "save_seq": 3,
        },
    )
    assert stale.status_code == 200

    progress = client.get("/rank/progress")
    assert progress.status_code == 200
    progress_payload = progress.json()
    assert progress_payload["completed_instance_ids"] == ["one"]

    export_payload = client.get("/rank/export", params={"completed_only": True}).json()
    assert export_payload["count"] == 1
    assert export_payload["results"][0]["instance_id"] == "one"
    assert export_payload["results"][0]["save_seq"] == 5

    entries = RankingResultsStore(Path(app.state.ranking_results_path)).read_entries()
    assert len(entries) == 2


def test_save_recovers_from_malformed_tail_fragment(tmp_path: Path) -> None:
    dataset_path = _write_dataset(tmp_path)
    app = create_ranking_app(dataset_path)
    results_path = Path(app.state.ranking_results_path)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        "{\"instance_id\":\"one\",\"instance_index\":0,\"completed\":false,\"save_seq\":1}\n{\"broken\":",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/rank/save",
        json={
            "instance_id": "two",
            "final_ranks": [["0", "1"]],
            "completed": True,
            "save_seq": 2,
        },
    )
    assert response.status_code == 200

    store = RankingResultsStore(results_path)
    latest = store.latest_entries_by_instance()
    assert latest["one"]["save_seq"] == 1
    assert latest["two"]["save_seq"] == 2
