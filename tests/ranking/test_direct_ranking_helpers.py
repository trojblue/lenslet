from __future__ import annotations

from pathlib import Path
from typing import get_type_hints

import pytest

from lenslet.ranking.dataset import RankingDataset, RankingImage, RankingInstance
import lenslet.ranking.routes as routes
import lenslet.ranking.validation as validation


def _dataset(tmp_path: Path) -> RankingDataset:
    images = (
        RankingImage("0", "a.jpg", tmp_path / "a.jpg"),
        RankingImage("1", "b.jpg", tmp_path / "b.jpg"),
    )
    return RankingDataset(
        tmp_path / "dataset.json",
        [RankingInstance("case-a", 0, images)],
    )


def test_ranking_validation_accepts_complete_payload(tmp_path: Path) -> None:
    entry = validation.validate_save_payload(
        {
            "instance_id": "case-a",
            "final_ranks": [["0"], ["1"]],
            "completed": True,
            "duration_ms": 120,
        },
        _dataset(tmp_path),
    )

    assert entry["instance_id"] == "case-a"
    assert entry["completed"] is True
    assert entry["duration_ms"] == 120
    assert "missing_image_ids" not in entry


def test_ranking_validation_rejects_duplicate_or_missing_completed_images(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)

    with pytest.raises(validation.RankingValidationError, match="duplicate image_id"):
        validation.validate_save_payload(
            {"instance_id": "case-a", "final_ranks": [["0"], ["0"]]},
            dataset,
        )
    with pytest.raises(validation.RankingValidationError, match="completed ranking"):
        validation.validate_save_payload(
            {"instance_id": "case-a", "final_ranks": [["0"]], "completed": True},
            dataset,
        )


def test_ranking_validation_payload_annotation_uses_object_boundary() -> None:
    assert get_type_hints(validation.validate_save_payload)["payload"] is object


def test_ranking_progress_and_image_url_helpers(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path)

    assert validation.derive_progress(dataset, {"case-a": {"completed": True}}) == {
        "completed_instance_ids": ["case-a"],
        "last_completed_instance_index": 0,
        "resume_instance_index": 0,
        "total_instances": 1,
    }
    assert routes._rank_image_url("case/a", "image b") == (
        "/rank/image?instance_id=case%2Fa&image_id=image%20b"
    )
