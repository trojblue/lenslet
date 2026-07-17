from __future__ import annotations

from array import array
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
import hashlib
import math
import struct
from threading import RLock
from time import monotonic
from types import MappingProxyType
from typing import Protocol

from ...browse.query import (
    DERIVED_METRIC_ID_RE,
    BrowseFilterAst,
    BrowseFilterClause,
    BrowseQuerySpec,
    BrowseSortSpec,
    CategoricalInFilter,
    DateRangeFilter,
    DerivedMetricSpec,
    DerivedMetricStatus,
    DerivedMetricZStat,
    HeightCompareFilter,
    MetricRangeFilter,
    MetricSortSpec,
    NameContainsFilter,
    NameNotContainsFilter,
    NotesContainsFilter,
    NotesNotContainsFilter,
    QueryDependencyManifest,
    StarsInFilter,
    StarsNotInFilter,
    UrlContainsFilter,
    UrlNotContainsFilter,
    WidthCompareFilter,
    browse_filter_query_key,
    browse_order_query_key,
    derived_metric_key,
    is_derived_metric_key,
    normalize_derived_metric_spec,
    normalize_filter_ast,
    parse_query_date_bound,
    query_dependency_manifest,
)
from ...metrics import coerce_finite_metric_value, normalize_metric_mapping
from ..base import SidecarState
from ..search_text import build_search_haystack, sidecar_source_fields
from ..source.paths import normalize_item_path
from .categoricals import normalize_categorical_value
from .row_store import TableRowStore


CHECKPOINT_ROWS = 256
CHECKPOINT_SECONDS = 0.025
_POINTER_BYTES = struct.calcsize("P")


class CancellationProbe(Protocol):
    def __call__(self) -> bool: ...


class TableQueryCancelled(RuntimeError):
    """Raised when columnar analysis no longer has a live subscriber."""


class TableQueryStale(RuntimeError):
    """Raised when mutable dependencies change before analysis captures its snapshot."""


@dataclass(frozen=True, slots=True)
class _NumericColumn:
    _values: memoryview

    @classmethod
    def from_buffer(cls, values: array[float]) -> _NumericColumn:
        return cls(memoryview(values).toreadonly())

    @property
    def nbytes(self) -> int:
        return self._values.nbytes

    def value(self, slot: int) -> float | None:
        value = float(self._values[slot])
        return None if math.isnan(value) else value


@dataclass(frozen=True, slots=True)
class TableColumnStore:
    """Immutable dense columns keyed externally by stable source row IDs."""

    source_generation: str
    row_ids: tuple[int, ...]
    paths: tuple[str, ...]
    stable_identities: tuple[str, ...]
    names: tuple[str, ...]
    sources: tuple[str | None, ...]
    urls: tuple[str | None, ...]
    static_search_text: tuple[str, ...]
    added_ms: _NumericColumn
    widths: _NumericColumn
    heights: _NumericColumn
    metrics: Mapping[str, _NumericColumn]
    categoricals: Mapping[str, tuple[str | None, ...]]
    include_source_in_search: bool
    buffer_nbytes: int
    _row_to_slot: Mapping[int, int] = field(repr=False)
    _path_to_slot: Mapping[str, int] = field(repr=False)

    @classmethod
    def build(
        cls,
        row_store: TableRowStore,
        *,
        source_generation: str,
        metric_keys: Iterable[str],
        categorical_keys: Iterable[str],
        metrics_for_row: Callable[[int], Mapping[str, object]],
        categoricals_for_row: Callable[[int], Mapping[str, object]],
        include_source_in_search: bool,
    ) -> TableColumnStore:
        row_ids = tuple(row_store.path_to_row[path] for path in row_store.paths)
        metric_names = _normalized_keys(metric_keys)
        categorical_names = _normalized_keys(categorical_keys)
        missing = math.nan
        metric_buffers = {
            key: array("d", [missing]) * len(row_ids)
            for key in metric_names
        }
        categorical_buffers: dict[str, list[str | None]] = {
            key: [None] * len(row_ids)
            for key in categorical_names
        }
        paths: list[str] = []
        identities: list[str] = []
        names: list[str] = []
        sources: list[str | None] = []
        urls: list[str | None] = []
        search_text: list[str] = []
        added_ms = array("d")
        widths = array("d")
        heights = array("d")

        for slot, row_id in enumerate(row_ids):
            path, name, _mime, width, height, _size, mtime, url, source = (
                row_store.item_fields_for_row(row_id)
            )
            canonical = _canonical_path(path)
            paths.append(path)
            identities.append(canonical)
            names.append(name)
            sources.append(source)
            urls.append(url)
            added_ms.append(mtime * 1000.0 if math.isfinite(mtime) and mtime > 0 else 0.0)
            widths.append(_finite_or_nan(width))
            heights.append(_finite_or_nan(height))
            search_text.append(
                build_search_haystack(
                    logical_path=canonical,
                    name=name,
                    tags=[],
                    notes="",
                    source=source if include_source_in_search else None,
                    url=url if include_source_in_search else None,
                    include_source_fields=include_source_in_search,
                )
            )

            row_metrics = metrics_for_row(row_id)
            for key, buffer in metric_buffers.items():
                value = coerce_finite_metric_value(row_metrics.get(key))
                if value is not None:
                    buffer[slot] = value
            row_categoricals = categoricals_for_row(row_id)
            for key, buffer in categorical_buffers.items():
                buffer[slot] = normalize_categorical_value(row_categoricals.get(key))

        numeric_columns = {
            key: _NumericColumn.from_buffer(buffer)
            for key, buffer in metric_buffers.items()
        }
        categorical_columns = {
            key: tuple(values)
            for key, values in categorical_buffers.items()
        }
        reference_slots = sum(
            len(values)
            for values in (
                paths,
                identities,
                names,
                sources,
                urls,
                search_text,
                row_ids,
                *categorical_columns.values(),
            )
        )
        numeric_nbytes = (
            added_ms.buffer_info()[1] * added_ms.itemsize
            + widths.buffer_info()[1] * widths.itemsize
            + heights.buffer_info()[1] * heights.itemsize
            + sum(column.nbytes for column in numeric_columns.values())
        )
        return cls(
            source_generation=source_generation,
            row_ids=row_ids,
            paths=tuple(paths),
            stable_identities=tuple(identities),
            names=tuple(names),
            sources=tuple(sources),
            urls=tuple(urls),
            static_search_text=tuple(search_text),
            added_ms=_NumericColumn.from_buffer(added_ms),
            widths=_NumericColumn.from_buffer(widths),
            heights=_NumericColumn.from_buffer(heights),
            metrics=MappingProxyType(numeric_columns),
            categoricals=MappingProxyType(categorical_columns),
            include_source_in_search=include_source_in_search,
            buffer_nbytes=numeric_nbytes + reference_slots * _POINTER_BYTES,
            _row_to_slot=MappingProxyType({row_id: slot for slot, row_id in enumerate(row_ids)}),
            _path_to_slot=MappingProxyType({
                normalize_item_path(path): slot
                for slot, path in enumerate(paths)
            }),
        )

    def slot_for_row(self, row_id: int) -> int:
        try:
            return self._row_to_slot[row_id]
        except KeyError as exc:
            raise KeyError(f"unknown table row ID: {row_id}") from exc

    def slot_for_path(self, path: str) -> int | None:
        return self._path_to_slot.get(normalize_item_path(path))

    def metric_value(self, slot: int, key: str) -> float | None:
        column = self.metrics.get(key)
        return column.value(slot) if column is not None else None

    def categorical_value(self, slot: int, key: str) -> str | None:
        column = self.categoricals.get(key)
        return column[slot] if column is not None else None


@dataclass(frozen=True, slots=True)
class TableDependencyStamp:
    source_generation: str
    star_generation: int = 0
    text_generation: int = 0
    dimension_generation: int = 0
    metric_generations: tuple[tuple[str, int], ...] = ()
    unknown_generation: int = 0


@dataclass(frozen=True, slots=True)
class _MutableSnapshot:
    stars: tuple[int | None, ...]
    notes: tuple[str, ...]
    search_text: tuple[str, ...]
    dimension_overrides: tuple[tuple[float | None, float | None] | None, ...]
    dynamic_metrics: tuple[tuple[tuple[str, float], ...], ...]
    available_metric_keys: frozenset[str]
    dependency_stamp: TableDependencyStamp

    def dynamic_metric_value(self, slot: int, key: str) -> float | None:
        for candidate, value in self.dynamic_metrics[slot]:
            if candidate == key:
                return value
        return None


class _MutableColumns:
    def __init__(self, store: TableColumnStore) -> None:
        self._store = store
        self._lock = RLock()
        self._stars: list[int | None] = [None] * len(store.row_ids)
        self._notes = [""] * len(store.row_ids)
        self._search_text = list(store.static_search_text)
        self._dimension_overrides: list[tuple[float | None, float | None] | None] = [
            None for _row_id in store.row_ids
        ]
        self._dynamic_metrics: list[tuple[tuple[str, float], ...]] = [
            () for _row_id in store.row_ids
        ]
        self._dynamic_metric_counts: dict[str, int] = {}
        self._star_generation = 0
        self._text_generation = 0
        self._dimension_generation = 0
        self._metric_generations: dict[str, int] = {}
        self._mutation_generation = 0

    def update(self, path: str, sidecar: SidecarState) -> bool:
        slot = self._store.slot_for_path(path)
        if slot is None:
            return False
        star, notes, search_text, metrics = _sidecar_columns(self._store, slot, sidecar)
        with self._lock:
            changed = False
            if self._stars[slot] != star:
                self._stars[slot] = star
                self._star_generation += 1
                changed = True
            if self._notes[slot] != notes or self._search_text[slot] != search_text:
                self._notes[slot] = notes
                self._search_text[slot] = search_text
                self._text_generation += 1
                changed = True
            if self._replace_row_metrics(slot, metrics):
                changed = True
            if changed:
                self._mutation_generation += 1
        return True

    def update_dimensions(self, path: str, dimensions: tuple[int, int]) -> bool:
        slot = self._store.slot_for_path(path)
        if slot is None:
            return False
        values = (_finite_dimension(dimensions[0]), _finite_dimension(dimensions[1]))
        static = (self._store.widths.value(slot), self._store.heights.value(slot))
        override = None if values == static else values
        with self._lock:
            if self._dimension_overrides[slot] != override:
                self._dimension_overrides[slot] = override
                self._dimension_generation += 1
                self._mutation_generation += 1
        return True

    def replace(self, sidecars: Mapping[str, SidecarState]) -> None:
        stars: list[int | None] = [None] * len(self._store.row_ids)
        notes = [""] * len(self._store.row_ids)
        search_text = list(self._store.static_search_text)
        metrics: list[tuple[tuple[str, float], ...]] = [() for _row_id in self._store.row_ids]
        for path, sidecar in sidecars.items():
            slot = self._store.slot_for_path(path)
            if slot is None:
                continue
            stars[slot], notes[slot], search_text[slot], metrics[slot] = _sidecar_columns(
                self._store,
                slot,
                sidecar,
            )

        with self._lock:
            star_changed = stars != self._stars
            text_changed = notes != self._notes or search_text != self._search_text
            if star_changed:
                self._star_generation += 1
            if text_changed:
                self._text_generation += 1
            changed_metric_keys = _changed_metric_keys(self._dynamic_metrics, metrics)
            for key in changed_metric_keys:
                self._metric_generations[key] = self._metric_generations.get(key, 0) + 1
            if star_changed or text_changed or changed_metric_keys:
                self._mutation_generation += 1
            self._stars = stars
            self._notes = notes
            self._search_text = search_text
            self._dynamic_metrics = metrics
            self._dynamic_metric_counts = _metric_counts(metrics)

    def snapshot(self, spec: BrowseQuerySpec) -> _MutableSnapshot:
        requirements = _dependency_requirements(spec)
        with self._lock:
            stamp = self._dependency_stamp_locked(*requirements)
            return _MutableSnapshot(
                stars=tuple(self._stars),
                notes=tuple(self._notes),
                search_text=tuple(self._search_text),
                dimension_overrides=tuple(self._dimension_overrides),
                dynamic_metrics=tuple(self._dynamic_metrics),
                available_metric_keys=frozenset(
                    (*self._store.metrics.keys(), *self._dynamic_metric_counts.keys())
                ),
                dependency_stamp=stamp,
            )

    def dependency_stamp(self, spec: BrowseQuerySpec) -> TableDependencyStamp:
        requirements = _dependency_requirements(spec)
        with self._lock:
            return self._dependency_stamp_locked(*requirements)

    def _dependency_stamp_locked(
        self,
        star_dependency: bool,
        text_dependency: bool,
        dimension_dependency: bool,
        metric_dependencies: frozenset[str],
        unknown_dependency: bool,
    ) -> TableDependencyStamp:
        return TableDependencyStamp(
            source_generation=self._store.source_generation,
            star_generation=self._star_generation if star_dependency else 0,
            text_generation=self._text_generation if text_dependency else 0,
            dimension_generation=(
                self._dimension_generation if dimension_dependency else 0
            ),
            metric_generations=tuple(
                (key, self._metric_generations.get(key, 0))
                for key in sorted(metric_dependencies)
            ),
            unknown_generation=self._mutation_generation if unknown_dependency else 0,
        )

    def _replace_row_metrics(
        self,
        slot: int,
        metrics: tuple[tuple[str, float], ...],
    ) -> bool:
        previous = self._dynamic_metrics[slot]
        if previous == metrics:
            return False
        previous_map = dict(previous)
        next_map = dict(metrics)
        for key in previous_map.keys() | next_map.keys():
            if previous_map.get(key) == next_map.get(key):
                continue
            self._metric_generations[key] = self._metric_generations.get(key, 0) + 1
        for key in previous_map:
            count = self._dynamic_metric_counts[key] - 1
            if count:
                self._dynamic_metric_counts[key] = count
            else:
                self._dynamic_metric_counts.pop(key, None)
        for key in next_map:
            self._dynamic_metric_counts[key] = self._dynamic_metric_counts.get(key, 0) + 1
        self._dynamic_metrics[slot] = metrics
        return True


@dataclass(frozen=True, slots=True)
class TableFilterKey:
    semantic_key: str
    source_generation: str
    dependency_stamp: TableDependencyStamp


@dataclass(frozen=True, slots=True)
class TableOrderKey:
    filter_key: TableFilterKey
    semantic_key: str


@dataclass(frozen=True, slots=True)
class TableWindowKey:
    order_key: TableOrderKey
    offset: int
    limit: int
    metric_keys: tuple[str, ...] = ()
    categorical_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TableFilterAnalysis:
    key: TableFilterKey
    source_generation: str
    dependency_stamp: TableDependencyStamp
    row_ids: tuple[int, ...]
    metric_keys: tuple[str, ...]
    derived_scores: Mapping[int, float]
    derived_metric_status: DerivedMetricStatus
    _mutable: _MutableSnapshot = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class TableOrderAnalysis:
    key: TableOrderKey
    ordered_row_ids: tuple[int, ...]


class TableQueryEngine:
    """Columnar filtering, derived analysis, and ordering for table rows."""

    def __init__(
        self,
        columns: TableColumnStore,
        *,
        sidecars: Mapping[str, SidecarState] | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.columns = columns
        self._mutable = _MutableColumns(columns)
        self._clock = clock
        if sidecars:
            self._mutable.replace(sidecars)

    @classmethod
    def from_row_store(
        cls,
        row_store: TableRowStore,
        *,
        source_generation: str,
        metric_keys: Iterable[str],
        categorical_keys: Iterable[str],
        metrics_for_row: Callable[[int], Mapping[str, object]],
        categoricals_for_row: Callable[[int], Mapping[str, object]],
        include_source_in_search: bool,
        sidecars: Mapping[str, SidecarState] | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> TableQueryEngine:
        columns = TableColumnStore.build(
            row_store,
            source_generation=source_generation,
            metric_keys=metric_keys,
            categorical_keys=categorical_keys,
            metrics_for_row=metrics_for_row,
            categoricals_for_row=categoricals_for_row,
            include_source_in_search=include_source_in_search,
        )
        return cls(columns, sidecars=sidecars, clock=clock)

    def update_sidecar(self, path: str, sidecar: SidecarState) -> bool:
        return self._mutable.update(path, sidecar)

    def update_dimensions(self, path: str, dimensions: tuple[int, int]) -> bool:
        return self._mutable.update_dimensions(path, dimensions)

    def replace_sidecars(self, sidecars: Mapping[str, SidecarState]) -> None:
        self._mutable.replace(sidecars)

    def dependency_stamp(self, spec: BrowseQuerySpec) -> TableDependencyStamp:
        return self._mutable.dependency_stamp(spec)

    def filter_key(self, spec: BrowseQuerySpec) -> TableFilterKey:
        stamp = self._mutable.dependency_stamp(spec)
        return self._filter_key(spec, stamp)

    def order_key(
        self,
        analysis: TableFilterAnalysis,
        spec: BrowseQuerySpec,
    ) -> TableOrderKey:
        return TableOrderKey(
            filter_key=analysis.key,
            semantic_key=browse_order_query_key(spec),
        )

    def window_key(
        self,
        order: TableOrderAnalysis,
        spec: BrowseQuerySpec,
        *,
        metric_keys: Iterable[str] = (),
        categorical_keys: Iterable[str] = (),
    ) -> TableWindowKey:
        return TableWindowKey(
            order_key=order.key,
            offset=max(0, spec.offset),
            limit=max(0, spec.limit),
            metric_keys=_normalized_keys(metric_keys),
            categorical_keys=_normalized_keys(categorical_keys),
        )

    def refresh_analysis(
        self,
        analysis: TableFilterAnalysis,
        spec: BrowseQuerySpec,
    ) -> TableFilterAnalysis:
        mutable = self._mutable.snapshot(spec)
        key = self._filter_key(spec, mutable.dependency_stamp)
        if key != analysis.key:
            raise TableQueryStale("table query dependencies changed")
        return replace(
            analysis,
            metric_keys=tuple(sorted(mutable.available_metric_keys)),
            _mutable=mutable,
        )

    def project_metrics(
        self,
        analysis: TableFilterAnalysis,
        row_id: int,
        metric_keys: Iterable[str],
    ) -> dict[str, float]:
        slot = self.columns.slot_for_row(row_id)
        values: dict[str, float] = {}
        for key in metric_keys:
            value = self._analysis_metric_value(analysis, row_id, slot, key)
            if value is not None:
                values[key] = value
        return values

    def project_sidecar(
        self,
        analysis: TableFilterAnalysis,
        row_id: int,
    ) -> SidecarState:
        slot = self.columns.slot_for_row(row_id)
        return {
            "star": analysis._mutable.stars[slot],
            "notes": analysis._mutable.notes[slot],
        }

    def project_dimensions(
        self,
        analysis: TableFilterAnalysis,
        row_id: int,
    ) -> tuple[int, int]:
        slot = self.columns.slot_for_row(row_id)
        return (
            int(self._dimension_value(slot, "width", analysis._mutable) or 0),
            int(self._dimension_value(slot, "height", analysis._mutable) or 0),
        )

    def iter_metric_values(
        self,
        analysis: TableFilterAnalysis,
        key: str,
    ) -> Iterator[float]:
        for row_id in analysis.row_ids:
            slot = self.columns.slot_for_row(row_id)
            value = self._analysis_metric_value(analysis, row_id, slot, key)
            if value is not None:
                yield value

    def iter_categorical_values(
        self,
        analysis: TableFilterAnalysis,
        key: str,
    ) -> Iterator[str]:
        for row_id in analysis.row_ids:
            slot = self.columns.slot_for_row(row_id)
            value = self.columns.categorical_value(slot, key)
            if value is not None:
                yield value

    def analyze_filter(
        self,
        row_ids: Iterable[int],
        spec: BrowseQuerySpec,
        cancel: CancellationProbe | None = None,
        *,
        expected_key: TableFilterKey | None = None,
    ) -> TableFilterAnalysis:
        checkpoint = _CancellationCheckpoint(cancel, self._clock)
        checkpoint.force()
        filters = normalize_filter_ast(spec.filters)
        base_filters, derived_filters = _split_derived_filters(filters)
        text_query = _normalize_text(spec.text_query)
        mutable = self._mutable.snapshot(spec)
        key = self._filter_key(spec, mutable.dependency_stamp)
        if expected_key is not None and key != expected_key:
            raise TableQueryStale("table query dependencies changed")
        base_filtered: list[int] = []
        for row_id in row_ids:
            slot = self.columns.slot_for_row(row_id)
            if (
                _matches_text(mutable.search_text[slot], text_query)
                and self._matches_filters(slot, base_filters, mutable, None, None)
            ):
                base_filtered.append(row_id)
            checkpoint.step()

        if spec.derived_metric is not None or _references_derived(spec):
            derived_scores, derived_status = self._evaluate_derived(
                base_filtered,
                spec.derived_metric,
                mutable,
                checkpoint,
            )
        else:
            derived_scores = MappingProxyType({})
            derived_status = DerivedMetricStatus()

        filtered: list[int] = []
        status_key = derived_status.key
        for row_id in base_filtered:
            slot = self.columns.slot_for_row(row_id)
            if self._matches_filters(
                slot,
                derived_filters,
                mutable,
                derived_scores,
                status_key,
            ):
                filtered.append(row_id)
            checkpoint.step()
        checkpoint.force()
        return TableFilterAnalysis(
            key=key,
            source_generation=self.columns.source_generation,
            dependency_stamp=mutable.dependency_stamp,
            row_ids=tuple(filtered),
            metric_keys=tuple(sorted(mutable.available_metric_keys)),
            derived_scores=derived_scores,
            derived_metric_status=derived_status,
            _mutable=mutable,
        )

    def order(
        self,
        analysis: TableFilterAnalysis,
        sort: BrowseSortSpec,
        *,
        random_seed: str | None = None,
        cancel: CancellationProbe | None = None,
        key: TableOrderKey | None = None,
    ) -> TableOrderAnalysis:
        checkpoint = _CancellationCheckpoint(cancel, self._clock)
        checkpoint.force()
        rows = analysis.row_ids
        if isinstance(sort, MetricSortSpec):
            ordered = sorted(
                rows,
                key=lambda row_id: self._metric_sort_key(row_id, sort, analysis),
            )
        elif sort.key == "random":
            seed = str(random_seed if random_seed is not None else "")
            ordered = sorted(
                rows,
                key=lambda row_id: (
                    _random_key(seed, self._identity(row_id)),
                    self._identity(row_id),
                ),
            )
        elif sort.key == "name":
            ordered = sorted(rows, key=lambda row_id: self._name_sort_key(row_id, sort.direction))
        else:
            ordered = sorted(rows, key=lambda row_id: self._added_sort_key(row_id, sort.direction))
        checkpoint.force()
        if key is None:
            key = TableOrderKey(
                filter_key=analysis.key,
                semantic_key=_order_semantic_key(sort, random_seed=random_seed),
            )
        return TableOrderAnalysis(key=key, ordered_row_ids=tuple(ordered))

    def _filter_key(
        self,
        spec: BrowseQuerySpec,
        stamp: TableDependencyStamp,
    ) -> TableFilterKey:
        return TableFilterKey(
            semantic_key=browse_filter_query_key(spec),
            source_generation=self.columns.source_generation,
            dependency_stamp=stamp,
        )

    def _matches_filters(
        self,
        slot: int,
        filters: BrowseFilterAst,
        mutable: _MutableSnapshot,
        derived_scores: Mapping[int, float] | None,
        derived_key: str | None,
    ) -> bool:
        return all(
            self._matches_clause(slot, clause, mutable, derived_scores, derived_key)
            for clause in filters.and_clauses
        )

    def _matches_clause(
        self,
        slot: int,
        clause: BrowseFilterClause,
        mutable: _MutableSnapshot,
        derived_scores: Mapping[int, float] | None,
        derived_key: str | None,
    ) -> bool:
        if isinstance(clause, StarsInFilter):
            return (mutable.stars[slot] if mutable.stars[slot] is not None else 0) in clause.values
        if isinstance(clause, StarsNotInFilter):
            return (mutable.stars[slot] if mutable.stars[slot] is not None else 0) not in clause.values
        if isinstance(clause, NameContainsFilter):
            return clause.value.lower() in self.columns.names[slot].lower()
        if isinstance(clause, NameNotContainsFilter):
            return clause.value.lower() not in self.columns.names[slot].lower()
        if isinstance(clause, NotesContainsFilter):
            notes = mutable.notes[slot]
            return bool(notes) and clause.value.lower() in notes.lower()
        if isinstance(clause, NotesNotContainsFilter):
            notes = mutable.notes[slot]
            return bool(notes) and clause.value.lower() not in notes.lower()
        if isinstance(clause, (UrlContainsFilter, UrlNotContainsFilter)):
            value = self.columns.sources[slot] or self.columns.urls[slot]
            if not value:
                return False
            contains = clause.value.lower() in value.lower()
            return contains if isinstance(clause, UrlContainsFilter) else not contains
        if isinstance(clause, DateRangeFilter):
            return _matches_date(self.columns.added_ms.value(slot), clause)
        if isinstance(clause, WidthCompareFilter):
            value = self._dimension_value(slot, "width", mutable)
            return _matches_dimension(value, clause.op, clause.value)
        if isinstance(clause, HeightCompareFilter):
            value = self._dimension_value(slot, "height", mutable)
            return _matches_dimension(value, clause.op, clause.value)
        if isinstance(clause, MetricRangeFilter):
            if is_derived_metric_key(clause.key):
                row_id = self.columns.row_ids[slot]
                value = derived_scores.get(row_id) if derived_scores and clause.key == derived_key else None
            else:
                value = self._metric_value(slot, clause.key, mutable)
            return value is not None and clause.min_value <= value <= clause.max_value
        if isinstance(clause, CategoricalInFilter):
            value = self.columns.categorical_value(slot, clause.key)
            return bool(value) and value in clause.values
        return True

    def _evaluate_derived(
        self,
        row_ids: list[int],
        raw_spec: DerivedMetricSpec | None,
        mutable: _MutableSnapshot,
        checkpoint: _CancellationCheckpoint,
    ) -> tuple[Mapping[int, float], DerivedMetricStatus]:
        population = len(row_ids)
        spec = normalize_derived_metric_spec(raw_spec)
        if raw_spec is None:
            return MappingProxyType({}), DerivedMetricStatus()
        if spec is None:
            raw_id = _normalize_text(raw_spec.id)
            raw_name = _normalize_text(raw_spec.name)
            key = derived_metric_key(raw_id) if raw_id and DERIVED_METRIC_ID_RE.fullmatch(raw_id) else None
            return MappingProxyType({}), DerivedMetricStatus(
                key=key,
                display_name=raw_name,
                status="invalid",
                score_population_count=population,
                invalid_count=population,
            )

        missing_numeric = tuple(
            sorted({
                term.key
                for term in spec.numeric_terms
                if term.key not in mutable.available_metric_keys
            })
        )
        missing_categorical = tuple(
            sorted({
                term.key
                for term in spec.categorical_terms
                if term.key not in self.columns.categoricals
            })
        )
        key = derived_metric_key(spec)
        if missing_numeric or missing_categorical:
            return MappingProxyType({}), DerivedMetricStatus(
                key=key,
                display_name=spec.name,
                status="unavailable",
                score_scope="query_filtered",
                score_population_count=population,
                invalid_count=population,
                missing_numeric_inputs=missing_numeric,
                unavailable_categorical_inputs=missing_categorical,
            )

        checkpoint.force()
        z_stats = self._derived_z_stats(row_ids, spec, mutable, checkpoint)
        checkpoint.force()
        scores: dict[int, float] = {}
        invalid_count = 0
        for row_id in row_ids:
            slot = self.columns.slot_for_row(row_id)
            score = self._derived_score(slot, spec, mutable, z_stats)
            if score is None:
                invalid_count += 1
            else:
                scores[row_id] = score
            checkpoint.step()
        checkpoint.force()
        return MappingProxyType(scores), DerivedMetricStatus(
            key=key,
            display_name=spec.name,
            status="applied",
            score_scope="query_filtered",
            score_population_count=population,
            valid_count=len(scores),
            invalid_count=invalid_count,
            z_stats=MappingProxyType(z_stats),
        )

    def _derived_z_stats(
        self,
        row_ids: list[int],
        spec: DerivedMetricSpec,
        mutable: _MutableSnapshot,
        checkpoint: _CancellationCheckpoint,
    ) -> dict[str, DerivedMetricZStat]:
        keys = {term.key for term in spec.numeric_terms if term.z_normalize}
        sums = {key: 0.0 for key in keys}
        sums_sq = {key: 0.0 for key in keys}
        counts = {key: 0 for key in keys}
        for row_id in row_ids:
            slot = self.columns.slot_for_row(row_id)
            for key in keys:
                value = self._metric_value(slot, key, mutable)
                if value is None:
                    continue
                sums[key] += value
                sums_sq[key] += value * value
                counts[key] += 1
            checkpoint.step()
        stats: dict[str, DerivedMetricZStat] = {}
        for key in keys:
            count = counts[key]
            if count <= 0:
                continue
            mean = sums[key] / count
            variance = max(0.0, sums_sq[key] / count - mean * mean)
            stats[key] = DerivedMetricZStat(mean=mean, std=math.sqrt(variance), count=count)
        return stats

    def _derived_score(
        self,
        slot: int,
        spec: DerivedMetricSpec,
        mutable: _MutableSnapshot,
        z_stats: Mapping[str, DerivedMetricZStat],
    ) -> float | None:
        score = spec.intercept
        for term in spec.numeric_terms:
            value = self._metric_value(slot, term.key, mutable)
            if value is None:
                if term.missing == "invalid":
                    return None
                continue
            if term.z_normalize:
                stats = z_stats.get(term.key)
                value = 0.0 if stats is None or stats.std <= 0 else (value - stats.mean) / stats.std
            score += value * term.weight
        for term in spec.categorical_terms:
            if self.columns.categorical_value(slot, term.key) == term.value:
                score += term.weight
        return score if math.isfinite(score) else None

    def _metric_value(self, slot: int, key: str, mutable: _MutableSnapshot) -> float | None:
        dynamic = mutable.dynamic_metric_value(slot, key)
        return dynamic if dynamic is not None else self.columns.metric_value(slot, key)

    def _analysis_metric_value(
        self,
        analysis: TableFilterAnalysis,
        row_id: int,
        slot: int,
        key: str,
    ) -> float | None:
        if key == analysis.derived_metric_status.key:
            return analysis.derived_scores.get(row_id)
        return self._metric_value(slot, key, analysis._mutable)

    def _dimension_value(
        self,
        slot: int,
        axis: str,
        mutable: _MutableSnapshot,
    ) -> float | None:
        override = mutable.dimension_overrides[slot]
        if override is not None:
            return override[0] if axis == "width" else override[1]
        column = self.columns.widths if axis == "width" else self.columns.heights
        return column.value(slot)

    def _identity(self, row_id: int) -> str:
        return self.columns.stable_identities[self.columns.slot_for_row(row_id)]

    def _name_sort_key(self, row_id: int, direction: str) -> tuple[str, str]:
        slot = self.columns.slot_for_row(row_id)
        name = self.columns.names[slot]
        identity = self.columns.stable_identities[slot]
        if direction == "desc":
            return _reverse_text(name), _reverse_text(identity)
        return name, identity

    def _added_sort_key(self, row_id: int, direction: str) -> tuple[float, str, str]:
        slot = self.columns.slot_for_row(row_id)
        added = self.columns.added_ms.value(slot) or 0.0
        name = self.columns.names[slot]
        identity = self.columns.stable_identities[slot]
        if direction == "desc":
            return -added, _reverse_text(name), _reverse_text(identity)
        return added, name, identity

    def _metric_sort_key(
        self,
        row_id: int,
        sort: MetricSortSpec,
        analysis: TableFilterAnalysis,
    ) -> tuple[int, float, str, str]:
        slot = self.columns.slot_for_row(row_id)
        value = self._analysis_metric_value(analysis, row_id, slot, sort.key)
        name = self.columns.names[slot]
        identity = self.columns.stable_identities[slot]
        if value is None:
            return 1, 0.0, name, identity
        return 0, -value if sort.direction == "desc" else value, name, identity


class _CancellationCheckpoint:
    def __init__(self, probe: CancellationProbe | None, clock: Callable[[], float]) -> None:
        self._probe = probe
        self._clock = clock
        self._rows = 0
        self._deadline = clock() + CHECKPOINT_SECONDS if probe is not None else 0.0

    def force(self) -> None:
        if self._probe is not None and self._probe():
            raise TableQueryCancelled("table query analysis cancelled")

    def step(self) -> None:
        if self._probe is None:
            return
        self._rows += 1
        now = self._clock()
        if self._rows < CHECKPOINT_ROWS and now < self._deadline:
            return
        self.force()
        self._rows = 0
        self._deadline = now + CHECKPOINT_SECONDS


def _canonical_path(path: str) -> str:
    normalized = normalize_item_path(path)
    return f"/{normalized}" if normalized else "/"


def _normalized_keys(keys: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(key.strip() for key in keys if isinstance(key, str) and key.strip()))


def _finite_or_nan(value: object) -> float:
    number = coerce_finite_metric_value(value)
    return number if number is not None else math.nan


def _finite_dimension(value: object) -> float | None:
    number = coerce_finite_metric_value(value)
    return number if number is not None and number > 0 else None


def _normalize_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _sidecar_columns(
    store: TableColumnStore,
    slot: int,
    sidecar: SidecarState,
) -> tuple[int | None, str, str, tuple[tuple[str, float], ...]]:
    raw_star = sidecar.get("star")
    star = raw_star if isinstance(raw_star, int) and 0 <= raw_star <= 5 else None
    raw_notes = sidecar.get("notes", "")
    notes = raw_notes if isinstance(raw_notes, str) else ""
    raw_tags = sidecar.get("tags", [])
    tags = raw_tags if isinstance(raw_tags, list) else []
    sidecar_source, sidecar_url = sidecar_source_fields(sidecar)
    row_source = store.sources[slot] if store.include_source_in_search else None
    row_url = store.urls[slot] if store.include_source_in_search else None
    search_source = " ".join(value for value in (row_source, sidecar_source) if value) or None
    search_url = " ".join(value for value in (row_url, sidecar_url) if value) or None
    search_text = build_search_haystack(
        logical_path=store.stable_identities[slot],
        name=store.names[slot],
        tags=tags,
        notes=notes,
        source=search_source,
        url=search_url,
        include_source_fields=store.include_source_in_search or bool(
            sidecar_source or sidecar_url
        ),
    )
    metrics = normalize_metric_mapping(sidecar.get("metrics")) or {}
    return star, notes, search_text, tuple(sorted(metrics.items()))


def _changed_metric_keys(
    previous: list[tuple[tuple[str, float], ...]],
    current: list[tuple[tuple[str, float], ...]],
) -> set[str]:
    changed: set[str] = set()
    for before, after in zip(previous, current):
        if before == after:
            continue
        before_map = dict(before)
        after_map = dict(after)
        for key in before_map.keys() | after_map.keys():
            if before_map.get(key) != after_map.get(key):
                changed.add(key)
    return changed


def _metric_counts(rows: Iterable[tuple[tuple[str, float], ...]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for metrics in rows:
        for key, _value in metrics:
            counts[key] = counts.get(key, 0) + 1
    return counts


def _dependency_requirements(
    spec: BrowseQuerySpec,
) -> tuple[bool, bool, bool, frozenset[str], bool]:
    manifest: QueryDependencyManifest = query_dependency_manifest(spec)
    star = "star" in manifest.fields
    text = bool(_normalize_text(spec.text_query)) or any(
        isinstance(clause, (NotesContainsFilter, NotesNotContainsFilter))
        for clause in normalize_filter_ast(spec.filters).and_clauses
    )
    dimensions = bool({"width", "height"} & manifest.fields)
    metric_keys = frozenset(key for key in manifest.metric_keys if not is_derived_metric_key(key))
    return star, text, dimensions, metric_keys, manifest.unknown


def _split_derived_filters(filters: BrowseFilterAst) -> tuple[BrowseFilterAst, BrowseFilterAst]:
    base: list[BrowseFilterClause] = []
    derived: list[BrowseFilterClause] = []
    for clause in filters.and_clauses:
        target = derived if isinstance(clause, MetricRangeFilter) and is_derived_metric_key(clause.key) else base
        target.append(clause)
    return BrowseFilterAst(tuple(base)), BrowseFilterAst(tuple(derived))


def _references_derived(spec: BrowseQuerySpec) -> bool:
    if isinstance(spec.sort, MetricSortSpec) and is_derived_metric_key(spec.sort.key):
        return True
    return any(
        isinstance(clause, MetricRangeFilter) and is_derived_metric_key(clause.key)
        for clause in spec.filters.and_clauses
    )


def _matches_text(search_text: str, query: str | None) -> bool:
    return query is None or query.lower() in search_text.lower()


def _matches_date(value_ms: float | None, clause: DateRangeFilter) -> bool:
    if value_ms is None or value_ms <= 0:
        return False
    try:
        from_ms = parse_query_date_bound(clause.from_value, as_end=False)
        to_ms = parse_query_date_bound(clause.to_value, as_end=True)
    except (TypeError, ValueError):
        return False
    return not (
        (from_ms is not None and value_ms < from_ms)
        or (to_ms is not None and value_ms > to_ms)
    )


def _matches_dimension(value: float | None, op: str, target: float) -> bool:
    if value is None or value <= 0:
        return False
    if op == "<":
        return value < target
    if op == "<=":
        return value <= target
    if op == ">":
        return value > target
    if op == ">=":
        return value >= target
    return True


def _random_key(seed: str, stable_identity: str) -> int:
    digest = hashlib.sha256(f"{seed}\0{stable_identity}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _order_semantic_key(sort: BrowseSortSpec, *, random_seed: str | None) -> str:
    active_seed = (
        str(random_seed if random_seed is not None else "")
        if not isinstance(sort, MetricSortSpec) and sort.key == "random"
        else None
    )
    raw = repr((sort, active_seed)).encode("utf-8")
    return f"oq_{hashlib.sha256(raw).hexdigest()[:24]}"


def _reverse_text(value: str) -> str:
    return "".join(chr(0x10FFFF - ord(char)) for char in value)
