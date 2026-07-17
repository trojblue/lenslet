"""Dataset-backed browse app mode."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from ...indexing_status import IndexingLifecycle
from ...storage.base import SourceSidecarStorage
from ...storage.dataset.storage import DatasetStorage
from ...workspace import Workspace
from ..auth import set_mutation_policy
from ..browse import build_item_payload, categoricals_for_cached_item
from ..context import get_app_context
from ..models import HealthResponse, LaunchSessionPayload
from .base import create_api_app
from .builder import BrowseAppAdapters, BrowseAppAssembly, BrowseAppContextInputs, finalize_browse_app
from .health import (
    REFRESH_NOTE_DATASET_STATIC,
    _base_health_payload,
    _indexing_health_payload,
    _workspace_id_for_dataset_storage,
)
from .options import DatasetAppOptions
from .shared import (
    build_record_update,
    initialize_runtime,
    mutation_policy_for_workspace,
    register_static_refresh_route,
)

_SOURCE_LOOKUP_ERRORS = (FileNotFoundError, LookupError, ValueError)


def create_dataset_app(
    datasets: dict[str, list[str]],
    *,
    options: DatasetAppOptions | None = None,
) -> FastAPI:
    """Create a browse app from named in-memory dataset path lists."""
    options = options or DatasetAppOptions()
    browse_options = options.browse

    app = create_api_app(description="Lightweight image gallery server (dataset mode)")
    storage = DatasetStorage(
        datasets=datasets,
        thumb_size=browse_options.thumb_size,
        thumb_quality=browse_options.thumb_quality,
        include_source_in_search=options.show_source,
    )
    workspace = Workspace.for_dataset(None, can_write=False)
    set_mutation_policy(app, mutation_policy_for_workspace(workspace))
    runtime = initialize_runtime(
        app,
        storage=storage,
        workspace=workspace,
        thumb_cache=browse_options.thumb_cache,
        presence_view_ttl=browse_options.presence_view_ttl,
        presence_edit_ttl=browse_options.presence_edit_ttl,
        presence_prune_interval=browse_options.presence_prune_interval,
    )
    indexing = IndexingLifecycle.ready(scope="/")
    if browse_options.indexing_listener is not None:
        indexing.subscribe(browse_options.indexing_listener, emit_current=True)
    adapters = build_dataset_browse_adapters(
        app,
        datasets=datasets,
        show_source=options.show_source,
        launch_session=options.launch_session,
        record_update=build_record_update(app),
    )

    return finalize_browse_app(
        app,
        BrowseAppAssembly(
            context=BrowseAppContextInputs(
                storage=storage,
                workspace=workspace,
                runtime=runtime,
                indexing=indexing,
                storage_mode="dataset",
                storage_origin="dataset",
                og_preview=False,
            ),
            adapters=adapters,
            embedding_manager=None,
        ),
    )


def build_dataset_browse_adapters(
    app: FastAPI,
    *,
    datasets: dict[str, list[str]],
    show_source: bool,
    launch_session: LaunchSessionPayload | None,
    record_update,
) -> BrowseAppAdapters:
    dataset_names = list(datasets.keys())
    total_images = sum(len(paths) for paths in datasets.values())

    def _to_item(storage: SourceSidecarStorage, cached: Any) -> Any:
        sidecar_state = storage.get_sidecar_readonly(cached.path)
        source = None
        if show_source:
            try:
                source = storage.get_source_path(cached.path)
            except _SOURCE_LOOKUP_ERRORS:
                source = None
        return build_item_payload(
            cached,
            sidecar_state,
            source=source,
            categoricals=categoricals_for_cached_item(storage, cached),
        )

    def _health_payload(request: Request) -> HealthResponse:
        context = get_app_context(app)
        return _base_health_payload(
            request=request,
            mode=context.storage_mode,
            workspace_id=_workspace_id_for_dataset_storage(context.storage),
            storage_origin=context.storage_origin,
            storage=context.storage,
            workspace=context.workspace,
            runtime=context.runtime,
            recursive_browse_cache=context.recursive_browse_cache,
            launch_session=launch_session,
        ).model_copy(
            update={
                "datasets": dataset_names,
                "total_images": total_images,
                "indexing": _indexing_health_payload(context.indexing, context.storage),
            }
        )

    return BrowseAppAdapters(
        include_index_routes=False,
        to_item=_to_item,
        record_update=record_update,
        health_payload=_health_payload,
        register_refresh_routes=lambda target_app: register_static_refresh_route(
            target_app,
            note=REFRESH_NOTE_DATASET_STATIC,
        ),
    )
