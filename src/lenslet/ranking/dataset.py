from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class RankingDatasetError(ValueError):
    """Raised when ranking dataset input is invalid."""


@dataclass(frozen=True)
class RankingImage:
    image_id: str
    source_path: str
    abs_path: Path


@dataclass(frozen=True)
class RankingInstance:
    instance_id: str
    instance_index: int
    images: tuple[RankingImage, ...]

    @property
    def image_ids(self) -> tuple[str, ...]:
        return tuple(image.image_id for image in self.images)


class RankingDataset:
    def __init__(self, dataset_path: Path, instances: list[RankingInstance]) -> None:
        self.dataset_path = dataset_path
        self.instances = tuple(instances)
        self._instance_by_id = {instance.instance_id: instance for instance in self.instances}

    @property
    def instance_count(self) -> int:
        return len(self.instances)

    def get_instance(self, instance_id: str) -> RankingInstance | None:
        return self._instance_by_id.get(instance_id)

    def get_image(self, instance_id: str, image_id: str) -> RankingImage | None:
        instance = self.get_instance(instance_id)
        if instance is None:
            return None
        for image in instance.images:
            if image.image_id == image_id:
                return image
        return None

    def all_image_paths(self) -> tuple[Path, ...]:
        return tuple(image.abs_path for instance in self.instances for image in instance.images)

    def to_response_payload(
        self,
        image_url_for: Callable[[str, str], str],
    ) -> dict[str, Any]:
        instances_payload: list[dict[str, Any]] = []
        for instance in self.instances:
            images_payload: list[dict[str, Any]] = []
            for image in instance.images:
                images_payload.append(
                    {
                        "image_id": image.image_id,
                        "source_path": image.source_path,
                        "url": image_url_for(instance.instance_id, image.image_id),
                    }
                )
            instances_payload.append(
                {
                    "instance_id": instance.instance_id,
                    "instance_index": instance.instance_index,
                    "max_ranks": len(instance.images),
                    "images": images_payload,
                }
            )

        return {
            "dataset_path": str(self.dataset_path),
            "instance_count": len(instances_payload),
            "instances": instances_payload,
        }


def load_ranking_dataset(dataset_path: str | Path) -> RankingDataset:
    path = Path(dataset_path).expanduser().resolve()
    if not path.exists():
        raise RankingDatasetError(f"dataset file does not exist: {path}")
    if not path.is_file():
        raise RankingDatasetError(f"dataset path must be a file: {path}")

    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RankingDatasetError(f"dataset JSON is invalid: {exc}") from exc

    raw_instances = _extract_instances(raw_payload)
    instances: list[RankingInstance] = []
    seen_instance_ids: set[str] = set()
    dataset_dir = path.parent

    for idx, raw_instance in enumerate(raw_instances):
        if not isinstance(raw_instance, dict):
            raise RankingDatasetError(f"instance #{idx} must be an object")
        instance_id = _coerce_instance_id(raw_instance.get("instance_id"), idx)
        if instance_id in seen_instance_ids:
            raise RankingDatasetError(f"duplicate instance_id detected: {instance_id}")
        seen_instance_ids.add(instance_id)

        raw_images = raw_instance.get("images")
        if not isinstance(raw_images, list) or not raw_images:
            raise RankingDatasetError(f"instance '{instance_id}' must include non-empty images[]")

        images: list[RankingImage] = []
        seen_abs_images: set[Path] = set()
        for image_idx, raw_image in enumerate(raw_images):
            if not isinstance(raw_image, str) or not raw_image.strip():
                raise RankingDatasetError(
                    f"instance '{instance_id}' image #{image_idx} must be a non-empty string",
                )
            resolved_image = _resolve_image_path(raw_image, dataset_dir)
            if resolved_image in seen_abs_images:
                raise RankingDatasetError(
                    f"instance '{instance_id}' includes duplicate image path: {raw_image}",
                )
            seen_abs_images.add(resolved_image)
            images.append(
                RankingImage(
                    image_id=str(image_idx),
                    source_path=raw_image,
                    abs_path=resolved_image,
                )
            )

        instances.append(
            RankingInstance(
                instance_id=instance_id,
                instance_index=idx,
                images=tuple(images),
            )
        )

    return RankingDataset(path, instances)


def _extract_instances(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        instances = payload.get("instances")
        if isinstance(instances, list):
            return instances
    raise RankingDatasetError("dataset root must be a list or an object with instances[]")


def _coerce_instance_id(value: Any, idx: int) -> str:
    if value is None:
        raise RankingDatasetError(f"instance #{idx} is missing instance_id")
    text = str(value).strip()
    if not text:
        raise RankingDatasetError(f"instance #{idx} has empty instance_id")
    return text


def _resolve_image_path(raw_path: str, dataset_dir: Path) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = dataset_dir / candidate
    resolved = candidate.resolve()
    dataset_root = dataset_dir.resolve()
    if not resolved.is_relative_to(dataset_root):
        raise RankingDatasetError(f"image path must stay under dataset directory: {raw_path}")
    if not resolved.exists():
        raise RankingDatasetError(f"image does not exist: {raw_path}")
    if not resolved.is_file():
        raise RankingDatasetError(f"image path is not a file: {raw_path}")
    return resolved
