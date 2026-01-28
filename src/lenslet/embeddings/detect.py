from __future__ import annotations

from dataclasses import dataclass

import pyarrow as pa

from .config import EmbeddingConfig


@dataclass(frozen=True)
class EmbeddingSpec:
    name: str
    dimension: int
    dtype: str
    metric: str


@dataclass(frozen=True)
class EmbeddingRejected:
    name: str
    reason: str


@dataclass
class EmbeddingDetection:
    available: list[EmbeddingSpec]
    rejected: list[EmbeddingRejected]
    list_columns: list[str]
    fixed_size_columns: list[str]

    def by_name(self) -> dict[str, EmbeddingSpec]:
        return {spec.name: spec for spec in self.available}

    @classmethod
    def empty(cls) -> "EmbeddingDetection":
        return cls(available=[], rejected=[], list_columns=[], fixed_size_columns=[])


def _is_list_like(dtype: pa.DataType) -> bool:
    return (
        pa.types.is_list(dtype)
        or pa.types.is_large_list(dtype)
        or pa.types.is_fixed_size_list(dtype)
    )


def _is_bfloat16_type(dtype: pa.DataType) -> bool:
    checker = getattr(pa.types, "is_bfloat16", None)
    if callable(checker):
        try:
            return checker(dtype)
        except Exception:
            return False
    return str(dtype) == "bfloat16"


def _supports_bfloat16() -> bool:
    return hasattr(pa, "bfloat16")


def _dtype_name(dtype: pa.DataType) -> str:
    return str(dtype)


def _supported_value_type(dtype: pa.DataType) -> tuple[bool, str | None]:
    if pa.types.is_float16(dtype) or pa.types.is_float32(dtype) or pa.types.is_float64(dtype):
        return True, None
    if _is_bfloat16_type(dtype):
        if _supports_bfloat16():
            return True, None
        return False, "bfloat16 not supported by this pyarrow build"
    return False, "embedding values must be float16/float32/float64/bfloat16"


def _inspect_field(field: pa.Field, metric: str) -> tuple[EmbeddingSpec | None, EmbeddingRejected | None]:
    dtype = field.type
    if not pa.types.is_fixed_size_list(dtype):
        return None, EmbeddingRejected(field.name, "variable-length list; fixed-size list required")
    value_type = dtype.value_type
    supported, reason = _supported_value_type(value_type)
    if not supported:
        return None, EmbeddingRejected(field.name, reason or "unsupported value type")
    return (
        EmbeddingSpec(
            name=field.name,
            dimension=dtype.list_size,
            dtype=_dtype_name(value_type),
            metric=metric,
        ),
        None,
    )


def detect_embeddings(schema: pa.Schema, config: EmbeddingConfig) -> EmbeddingDetection:
    list_columns = [field.name for field in schema if _is_list_like(field.type)]
    fixed_size_columns = [field.name for field in schema if pa.types.is_fixed_size_list(field.type)]
    available: list[EmbeddingSpec] = []
    rejected: list[EmbeddingRejected] = []

    explicit = config.explicit_columns
    if explicit:
        for name in explicit:
            if name not in schema.names:
                rejected.append(EmbeddingRejected(name, "column not found"))
                continue
            field = schema.field(name)
            spec, reject = _inspect_field(field, config.metric_for(name))
            if spec:
                available.append(spec)
            if reject:
                rejected.append(reject)
    else:
        for field in schema:
            if not _is_list_like(field.type):
                continue
            spec, reject = _inspect_field(field, config.metric_for(field.name))
            if spec:
                available.append(spec)
            if reject:
                rejected.append(reject)

    return EmbeddingDetection(
        available=available,
        rejected=rejected,
        list_columns=list_columns,
        fixed_size_columns=fixed_size_columns,
    )


def columns_without_embeddings(schema: pa.Schema, detection: EmbeddingDetection) -> list[str]:
    excluded = set(detection.fixed_size_columns)
    return [name for name in schema.names if name not in excluded]
