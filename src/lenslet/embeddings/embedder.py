from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pyarrow as pa
import pyarrow.parquet as pq


@dataclass(frozen=True)
class EmbedConfig:
    embedding_column: str = "embedding_mobilenet_v3_small"
    model: str = "mobilenet_v3_small"
    batch_size: int = 32
    parquet_batch_size: int = 256
    device: str = "cpu"
    base_dir: str | None = None
    normalize: bool = False
    limit: int | None = None
    error_policy: str = "zero"
    num_workers: int = 8
    show_progress: bool = True


def embed_parquet(
    parquet_path: str | Path,
    image_column: str,
    output_path: str | Path | None = None,
    config: EmbedConfig | None = None,
) -> Path:
    cfg = config or EmbedConfig()
    parquet_path = Path(parquet_path)
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

    if output_path is None:
        stem = parquet_path.with_suffix("").name
        output_path = parquet_path.with_name(f"{stem}_with_{cfg.embedding_column}.parquet")
    output_path = Path(output_path)

    model, preprocess, dim = _build_model(cfg.model, cfg.device)
    embed_type = pa.list_(pa.float32(), dim)

    pf = pq.ParquetFile(str(parquet_path))
    if image_column not in pf.schema.names:
        raise ValueError(f"Column not found: {image_column}")

    total_rows = pf.metadata.num_rows if pf.metadata else None
    if cfg.limit is not None:
        total_rows = min(total_rows or cfg.limit, cfg.limit)

    tqdm = _lazy_import_tqdm() if cfg.show_progress else None
    progress = tqdm(total=total_rows, unit="rows") if tqdm else None

    writer = None
    processed = 0
    for batch in _iter_batches(str(parquet_path), cfg.parquet_batch_size, cfg.limit):
        paths_raw = batch.column(image_column).to_pylist()
        paths = [_resolve_path(p, cfg.base_dir) for p in paths_raw]

        embeddings = _encode_batch(
            paths=paths,
            model=model,
            preprocess=preprocess,
            dim=dim,
            device=cfg.device,
            batch_size=cfg.batch_size,
            error_policy=cfg.error_policy,
            normalize=cfg.normalize,
            num_workers=cfg.num_workers,
        )

        embed_array = pa.array(embeddings.tolist(), type=embed_type)
        out_batch = batch.append_column(cfg.embedding_column, embed_array)
        if writer is None:
            writer = pq.ParquetWriter(str(output_path), out_batch.schema)
        writer.write_batch(out_batch)
        processed += out_batch.num_rows
        if progress:
            progress.update(out_batch.num_rows)

    if writer is not None:
        writer.close()
    if progress:
        progress.close()

    return output_path


def _lazy_import_torch():
    try:
        import torch
        import torchvision
        from torchvision import transforms
        from torchvision.models import (
            MobileNet_V3_Small_Weights,
            ResNet18_Weights,
            EfficientNet_B0_Weights,
            mobilenet_v3_small,
            resnet18,
            efficientnet_b0,
        )
    except Exception as exc:
        raise RuntimeError(
            "Embedding requires torch + torchvision. Install: pip install torch torchvision"
        ) from exc

    return {
        "torch": torch,
        "torchvision": torchvision,
        "transforms": transforms,
        "weights": {
            "mobilenet_v3_small": (MobileNet_V3_Small_Weights, mobilenet_v3_small),
            "resnet18": (ResNet18_Weights, resnet18),
            "efficientnet_b0": (EfficientNet_B0_Weights, efficientnet_b0),
        },
    }


def _lazy_import_pil():
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError("Embedding requires pillow. Install: pip install pillow") from exc
    return Image


def _lazy_import_boto3():
    try:
        import boto3
    except Exception as exc:
        raise RuntimeError("boto3 is required for s3:// URIs. Install: pip install boto3") from exc
    return boto3


def _lazy_import_tqdm():
    try:
        from tqdm import tqdm
    except Exception:
        return None
    return tqdm


def _resolve_path(raw: str, base_dir: str | None) -> str:
    if raw is None:
        return ""
    text = str(raw)
    if text.startswith("s3://") or text.startswith("http://") or text.startswith("https://"):
        return text
    if base_dir and not os.path.isabs(text):
        return str(Path(base_dir) / text)
    return text


def _read_bytes(uri: str) -> bytes:
    if uri.startswith("s3://"):
        boto3 = _lazy_import_boto3()
        parsed = urlparse(uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError(f"Invalid s3 URI: {uri}")
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()
    if uri.startswith("http://") or uri.startswith("https://"):
        req = Request(uri, headers={"User-Agent": "lenslet-embedder/1.0"})
        with urlopen(req, timeout=30) as resp:
            return resp.read()
    with open(uri, "rb") as handle:
        return handle.read()


def _load_image(uri: str):
    Image = _lazy_import_pil()
    raw = _read_bytes(uri)
    image = Image.open(io.BytesIO(raw))
    return image.convert("RGB")


def _build_model(model_name: str, device: str):
    lib = _lazy_import_torch()
    torch = lib["torch"]
    weights_enum, model_fn = lib["weights"][model_name]
    weights = weights_enum.DEFAULT
    model = model_fn(weights=weights)

    if model_name == "mobilenet_v3_small":
        model.classifier = torch.nn.Identity()
    elif model_name == "resnet18":
        model.fc = torch.nn.Identity()
    elif model_name == "efficientnet_b0":
        model.classifier = torch.nn.Identity()

    model.eval().to(device)
    preprocess = weights.transforms()

    input_size = weights.meta.get("input_size", (3, 224, 224))
    dummy = torch.zeros((1, *input_size), device=device)
    with torch.no_grad():
        dim = int(model(dummy).shape[1])

    return model, preprocess, dim


def _iter_batches(parquet_path: str, batch_size: int, limit: int | None) -> Iterator[pa.RecordBatch]:
    pf = pq.ParquetFile(parquet_path)
    remaining = limit
    for batch in pf.iter_batches(batch_size=batch_size):
        if remaining is None:
            yield batch
            continue
        if remaining <= 0:
            break
        if batch.num_rows > remaining:
            yield batch.slice(0, remaining)
            break
        yield batch
        remaining -= batch.num_rows


def _encode_batch(
    paths: list[str],
    model,
    preprocess,
    dim: int,
    device: str,
    batch_size: int,
    error_policy: str,
    normalize: bool,
    num_workers: int,
):
    lib = _lazy_import_torch()
    torch = lib["torch"]
    import numpy as np

    output = np.zeros((len(paths), dim), dtype=np.float32)
    valid_indices: list[int] = []
    valid_tensors = []

    def load_one(uri: str):
        try:
            img = _load_image(uri)
            return preprocess(img), None
        except Exception as exc:
            return None, exc

    if num_workers > 0:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            for idx, (tensor, exc) in enumerate(executor.map(load_one, paths)):
                if exc is not None:
                    if error_policy == "raise":
                        raise RuntimeError(f"Failed to load image: {paths[idx]}") from exc
                    continue
                if tensor is None:
                    continue
                valid_indices.append(idx)
                valid_tensors.append(tensor)
    else:
        for idx, uri in enumerate(paths):
            tensor, exc = load_one(uri)
            if exc is not None:
                if error_policy == "raise":
                    raise RuntimeError(f"Failed to load image: {uri}") from exc
                continue
            if tensor is None:
                continue
            valid_indices.append(idx)
            valid_tensors.append(tensor)

    if valid_tensors:
        for start in range(0, len(valid_tensors), batch_size):
            chunk = valid_tensors[start : start + batch_size]
            idxs = valid_indices[start : start + batch_size]
            batch = torch.stack(chunk).to(device)
            with torch.no_grad():
                vecs = model(batch).detach().cpu().numpy().astype(np.float32)
            output[idxs] = vecs

    if normalize:
        norms = np.linalg.norm(output, axis=1, keepdims=True)
        mask = norms > 0
        output[mask] = output[mask] / norms[mask]

    return output
