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
from pathlib import Path

from lenslet.embeddings.embedder import EmbedConfig, embed_parquet


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


def main() -> None:
    args = _parse_args()
    cfg = EmbedConfig(
        embedding_column=args.embedding_column,
        model=args.model,
        batch_size=args.batch_size,
        parquet_batch_size=args.parquet_batch_size,
        device=args.device,
        base_dir=args.base_dir,
        normalize=args.normalize,
        limit=args.limit,
        error_policy=args.error_policy,
        num_workers=args.num_workers,
    )
    output = embed_parquet(
        parquet_path=Path(args.parquet),
        image_column=args.image_column,
        output_path=args.output,
        config=cfg,
    )
    print(f"Wrote embeddings to {output}")


if __name__ == "__main__":
    main()
