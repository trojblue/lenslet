#!/usr/bin/env python3
"""
Add a fixed-size embedding column to a Parquet table of image paths/URIs.

Example:
  python scripts/embed_parquet_embeddings.py \
    /path/to/items.parquet \
    --image-column image_path \
    --output /path/to/items_with_embed.parquet
"""
from __future__ import annotations

import argparse
import io
import math
import os
from pathlib import Path
from typing import Iterable, Iterator
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pyarrow as pa
import pyarrow.parquet as pq


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
            "This script requires torch + torchvision. Install: pip install torch torchvision"
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
        raise RuntimeError("This script requires pillow. Install: pip install pillow") from exc
    return Image


def _lazy_import_boto3():
    try:
        import boto3
    except Exception as exc:
        raise RuntimeError(
            "boto3 is required for s3:// URIs. Install: pip install boto3"
        ) from exc
    return boto3


def _lazy_import_tqdm():
    try:
        from tqdm import tqdm
    except Exception:
        return None
    return tqdm


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add image embeddings to a parquet table")
    parser.add_argument("parquet", type=str, help="Input parquet path")
    parser.add_argument("--image-column", required=True, help="Column containing image paths/URIs")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output parquet path (defaults to <input>_with_<embed>.parquet)",
    )
    parser.add_argument(
        "--embedding-column",
        type=str,
        default="embedding_mobilenet_v3_small",
        help="Embedding column name to add",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="mobilenet_v3_small",
        choices=["mobilenet_v3_small", "resnet18", "efficientnet_b0"],
        help="Backbone used for embeddings",
    )
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding batch size")
    parser.add_argument(
        "--parquet-batch-size",
        type=int,
        default=512,
        help="Rows per parquet batch",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="Torch device (default: cpu)",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=None,
        help="Base directory for resolving relative paths",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="L2 normalize embeddings before writing",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N rows",
    )
    parser.add_argument(
        "--error-policy",
        choices=["zero", "raise"],
        default="zero",
        help="On image load error: fill zeros or raise",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="Parallel image loading workers (0=disable)",
    )
    return parser.parse_args()


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


def main() -> None:
    args = _parse_args()
    parquet_path = Path(args.parquet)
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

    output_path = Path(args.output) if args.output else None
    if output_path is None:
        stem = parquet_path.with_suffix("").name
        output_path = parquet_path.with_name(f"{stem}_with_{args.embedding_column}.parquet")

    model, preprocess, dim = _build_model(args.model, args.device)
    embed_type = pa.list_(pa.float32(), dim)

    pf = pq.ParquetFile(str(parquet_path))
    if args.image_column not in pf.schema.names:
        raise ValueError(f"Column not found: {args.image_column}")

    total_rows = pf.metadata.num_rows if pf.metadata else None
    if args.limit is not None:
        total_rows = min(total_rows or args.limit, args.limit)

    tqdm = _lazy_import_tqdm()
    progress = tqdm(total=total_rows, unit="rows") if tqdm else None

    writer = None
    processed = 0
    for batch in _iter_batches(str(parquet_path), args.parquet_batch_size, args.limit):
        paths_raw = batch.column(args.image_column).to_pylist()
        paths = [_resolve_path(p, args.base_dir) for p in paths_raw]

        embeddings = _encode_batch(
            paths=paths,
            model=model,
            preprocess=preprocess,
            dim=dim,
            device=args.device,
            batch_size=args.batch_size,
            error_policy=args.error_policy,
            normalize=args.normalize,
            num_workers=args.num_workers,
        )

        embed_array = pa.array(embeddings.tolist(), type=embed_type)
        out_batch = batch.append_column(args.embedding_column, embed_array)
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

    print(f"Wrote {processed} rows to {output_path}")


if __name__ == "__main__":
    main()
