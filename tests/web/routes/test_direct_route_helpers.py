from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI

import lenslet.web.browse as browse
from lenslet.web.cache import signals
import lenslet.web.app.health as factory_health
import lenslet.web.og.data as og_data
import lenslet.web.og.rendering as og_rendering
import lenslet.web.paths as web_paths
import lenslet.web.request_headers as request_headers
import lenslet.web.routes.embeddings as embeddings
import lenslet.web.routes.folders as folder_routes
import lenslet.web.routes.items as item_routes
import lenslet.web.routes.og as og
import lenslet.web.routes.views as views
from lenslet.web.models import BrowseItemPayload, SidecarPatch
import lenslet.web.sidecars as sidecars
from lenslet.storage.sidecar_state import copy_sidecar_state


def test_common_route_helpers_copy_and_update_sidecar_state() -> None:
    original = {"tags": ["old"], "metrics": {"score": 0.5}, "version": 2}
    copied = copy_sidecar_state(original)
    copied["tags"].append("new")
    copied["metrics"]["score"] = 1.0

    assert original == {"tags": ["old"], "metrics": {"score": 0.5}, "version": 2}

    updated = item_routes._put_item_sidecar_state(
        original,
        SimpleNamespace(tags=["cat"], notes="note", star=1),
        "tester",
        ensure_sidecar_fields=lambda sidecar_state: sidecar_state,
        now_iso=lambda: "2026-05-30T00:00:00+00:00",
    )

    assert updated["tags"] == ["cat"]
    assert updated["notes"] == "note"
    assert updated["star"] == 1
    assert updated["version"] == 3
    assert updated["updated_by"] == "tester"


def test_common_route_helpers_resolve_patch_expected_version() -> None:
    assert item_routes._resolve_patch_expected_version(SidecarPatch(base_version=2), None) == (2, None)
    assert item_routes._resolve_patch_expected_version(SidecarPatch(), 'W/"3"') == (3, None)

    assert item_routes._resolve_patch_expected_version(SidecarPatch(base_version=2), "bad") == (
        None,
        (400, {"error": "invalid_if_match", "message": "If-Match must be an integer version"}),
    )
    assert item_routes._resolve_patch_expected_version(SidecarPatch(base_version=2), "3") == (
        None,
        (400, {"error": "version_mismatch", "message": "If-Match and base_version disagree"}),
    )
    assert item_routes._resolve_patch_expected_version(SidecarPatch(), None) == (
        None,
        (400, {"error": "missing_base_version", "message": "base_version or If-Match is required"}),
    )


def test_common_route_helpers_apply_sidecar_patch() -> None:
    class _Storage:
        def __init__(self) -> None:
            self.sidecar = {"tags": [], "notes": "", "star": None, "version": 1}

        def get_sidecar_readonly(self, _path: str):
            return dict(self.sidecar)

        def set_sidecar(self, _path: str, sidecar_state: dict) -> None:
            self.sidecar = dict(sidecar_state)

        def sidecar_enrichment_for_path(self, _path: str) -> dict:
            return {}

    storage = _Storage()
    commits: list[tuple[str, int]] = []

    def record_update(path: str, sidecar_state: dict, event: str, commit) -> int:
        commit()
        commits.append((event, sidecar_state["version"]))
        return 7

    result = item_routes._apply_sidecar_patch(
        storage,
        "/cat.jpg",
        SidecarPatch(base_version=1, set_notes="new"),
        1,
        "tester",
        record_update,
    )

    assert result.status == 200
    assert result.event_id == 7
    assert result.payload["notes"] == "new"
    assert result.payload["version"] == 2
    assert result.payload["updated_by"] == "tester"
    assert storage.sidecar["notes"] == "new"
    assert commits == [("item-updated", 2)]

    conflict = item_routes._apply_sidecar_patch(
        storage,
        "/cat.jpg",
        SidecarPatch(base_version=1, set_star=3),
        1,
        "tester",
        record_update,
    )

    assert conflict.status == 409
    assert conflict.event_id is None
    assert conflict.payload["error"] == "version_conflict"
    assert conflict.payload["current"]["version"] == 2


def test_web_sidecar_helpers_normalize_state_and_patch_payloads() -> None:
    assert web_paths.canonical_path(" animals//cats/ ") == "/animals/cats"
    assert request_headers.parse_if_match('W/"7"') == 7
    assert request_headers.parse_if_match("not-a-version") is None

    sidecar_state = {"tags": ["old"], "notes": "", "version": 2, "metrics": {"score": 0.5}}
    patch = SidecarPatch(base_version=2, add_tags=["new"], remove_tags=["old"], set_notes="note")

    assert sidecars.apply_patch_to_sidecar(sidecar_state, patch) is True
    assert sidecar_state["tags"] == ["new"]
    assert sidecar_state["notes"] == "note"
    payload = sidecars.sidecar_payload("cat.jpg", sidecar_state)
    assert payload == {
        "path": "/cat.jpg",
        "version": 2,
        "tags": ["new"],
        "notes": "note",
        "star": None,
        "updated_at": "",
        "updated_by": "server",
        "metrics": {"score": 0.5},
    }
    payload["tags"].append("mutated")
    payload["metrics"]["score"] = 1.0
    assert sidecar_state["tags"] == ["new"]
    assert sidecar_state["metrics"] == {"score": 0.5}


def test_build_item_payload_is_public_factory_boundary() -> None:
    cached = SimpleNamespace(
        path="animals/cat.jpg",
        name="cat.jpg",
        mime="image/jpeg",
        width=8,
        height=6,
        size=123,
        mtime=1.0,
        url=None,
    )

    payload = browse.build_item_payload(
        cached,
        {"star": 4, "notes": "favorite", "metrics": {"score": 0.5}},
        source="s3://bucket/cat.jpg",
    )

    assert payload.path == "/animals/cat.jpg"
    assert payload.star == 4
    assert payload.notes == "favorite"
    assert payload.source == "s3://bucket/cat.jpg"
    assert payload.metrics == {"score": 0.5}


def test_common_route_helpers_collect_folder_paths() -> None:
    class _Storage:
        def __init__(self) -> None:
            self.indexes = {
                "/": SimpleNamespace(dirs=["animals"]),
                "/animals": SimpleNamespace(dirs=["cats"]),
                "/animals/cats": SimpleNamespace(dirs=[]),
            }

        def load_recursive_index(self, path: str):
            return self.indexes.get(path)

        def join(self, *parts: str) -> str:
            return "/" + "/".join(part.strip("/") for part in parts if part.strip("/"))

    assert folder_routes._collect_folder_paths(_Storage()) == ["/", "/animals", "/animals/cats"]


def test_build_folder_index_recursive_without_cache_uses_canonical_scope() -> None:
    class _Storage:
        def __init__(self) -> None:
            self.items_scope = None

        def load_recursive_index(self, path: str):
            assert path == "/animals"
            return SimpleNamespace(items=[], dirs=[], generated_at="2026-05-30T00:00:00+00:00")

        def items_in_scope(self, path: str):
            self.items_scope = path
            return [
                SimpleNamespace(
                    path="/animals/cat.jpg",
                    name="cat.jpg",
                    mime="image/jpeg",
                    width=8,
                    height=6,
                    size=123,
                    mtime=1.0,
                    metrics={"score": 0.5},
                )
            ]

    storage = _Storage()

    payload = browse.build_folder_index(
        storage,
        " animals/ ",
        lambda _storage, item: BrowseItemPayload(
            path=item.path,
            name=item.name,
            mime=item.mime,
            width=item.width,
            height=item.height,
            size=item.size,
            metrics=item.metrics,
        ),
        recursive=True,
        count_only=False,
        browse_cache=None,
    )

    assert storage.items_scope == "/animals"
    assert [item.path for item in payload.items] == ["/animals/cat.jpg"]
    assert payload.metric_keys == ["score"]


def test_build_folder_index_recursive_count_only_uses_canonical_scope_without_items() -> None:
    class _Storage:
        def __init__(self) -> None:
            self.count_scope = None

        def load_recursive_index(self, path: str):
            assert path == "/animals"
            return SimpleNamespace(items=[], dirs=[], generated_at="2026-05-30T00:00:00+00:00")

        def count_in_scope(self, path: str) -> int:
            self.count_scope = path
            return 12

        def items_in_scope(self, path: str):
            raise AssertionError(f"count_only should not materialize scoped items for {path}")

    storage = _Storage()

    def fail_item(_storage, _item):
        raise AssertionError("count_only should not build items")

    payload = browse.build_folder_index(
        storage,
        " animals/ ",
        fail_item,
        recursive=True,
        count_only=True,
        browse_cache=None,
    )

    assert storage.count_scope == "/animals"
    assert payload.items == []
    assert payload.total_items == 12
    assert payload.metric_keys == []


def test_build_folder_index_recursive_window_uses_window_loader() -> None:
    class _Storage:
        def __init__(self) -> None:
            self.window_args = None
            self.count_scope = None

        def load_recursive_index(self, path: str):
            assert path == "/animals"
            return SimpleNamespace(items=[], dirs=[], generated_at="2026-05-30T00:00:00+00:00")

        def count_in_scope(self, path: str) -> int:
            self.count_scope = path
            return 20

        def items_in_scope(self, path: str):
            raise AssertionError(f"windowed requests should not materialize scoped items for {path}")

        def items_in_scope_window(self, path: str, offset: int, limit: int):
            self.window_args = (path, offset, limit)
            return [
                SimpleNamespace(
                    path="/animals/cat.jpg",
                    name="cat.jpg",
                    mime="image/jpeg",
                    width=8,
                    height=6,
                    size=123,
                    mtime=1.0,
                    metrics={"score": 0.5},
                )
            ]

    storage = _Storage()

    payload = browse.build_folder_index(
        storage,
        " animals/ ",
        lambda _storage, item: BrowseItemPayload(
            path=item.path,
            name=item.name,
            mime=item.mime,
            width=item.width,
            height=item.height,
            size=item.size,
            metrics=item.metrics,
        ),
        recursive=True,
        count_only=False,
        offset=5,
        limit=1,
        browse_cache=None,
    )

    assert storage.count_scope == "/animals"
    assert storage.window_args == ("/animals", 5, 1)
    assert payload.total_items == 20
    assert payload.offset == 5
    assert payload.limit == 1
    assert [item.path for item in payload.items] == ["/animals/cat.jpg"]


def test_embedding_payload_preserves_available_and_rejected_specs() -> None:
    manager = SimpleNamespace(
        available=[
            SimpleNamespace(name="clip", dimension=3, dtype="float32", metric="cosine"),
        ],
        rejected=[
            SimpleNamespace(name="bad", reason="wrong shape"),
        ],
    )

    payload = embeddings._build_embeddings_payload(manager)

    assert payload.embeddings[0].name == "clip"
    assert payload.embeddings[0].dimension == 3
    assert payload.rejected[0].reason == "wrong shape"


def test_og_route_helpers_build_stable_cache_keys_and_fallback_paths(tmp_path: Path) -> None:
    workspace = SimpleNamespace(root=tmp_path, views_override=None)
    key = og._og_cache_key(workspace, "summary", "signature", "/animals/cat.jpg")

    assert key == "og:summary:signature:/animals/cat.jpg"
    assert og._og_path_from_request(None, None) == "/"
    assert og.dataset_count(SimpleNamespace(total_items=lambda: 12)) == 12
    assert og.dataset_label(SimpleNamespace(root=tmp_path / "dataset" / ".lenslet", views_override=None)) == "dataset"


def test_og_data_helpers_select_samples_and_count_subtrees() -> None:
    class _Storage:
        def __init__(self) -> None:
            self.indexes = {
                "/": SimpleNamespace(items=[], dirs=["animals"]),
                "/animals": SimpleNamespace(
                    items=[
                        SimpleNamespace(path="/animals/old.jpg", mtime=1.0),
                        SimpleNamespace(path="/animals/new.jpg", mtime=3.0),
                    ],
                    dirs=[],
                ),
            }

        def load_index(self, path: str):
            try:
                return self.indexes[path]
            except KeyError as exc:
                raise FileNotFoundError(path) from exc

        def join(self, *parts: str) -> str:
            return "/" + "/".join(part.strip("/") for part in parts if part.strip("/"))

    storage = _Storage()

    assert og_data.normalize_path("animals/") == "/animals"
    assert og_data.sample_paths(storage, "/missing", 2) == ["/animals/new.jpg", "/animals/old.jpg"]
    assert og_data.subtree_image_count(storage, "/") == 2


def test_og_rendering_helpers_build_fallback_png_and_reject_unknown_style() -> None:
    data = og_rendering.fallback_og_image("demo", width=120, height=64)

    assert data.startswith(b"\x89PNG")
    assert og_rendering.resolve_style(None) == og_rendering.OG_STYLE
    try:
        og_rendering.resolve_style("unknown")
    except ValueError as exc:
        assert "unsupported style" in str(exc)
    else:
        raise AssertionError("expected unsupported OG style to fail")


def test_factory_health_helpers_report_static_and_mutable_refresh_states() -> None:
    static_refresh = factory_health._refresh_health_payload(
        mode="dataset",
        storage_origin="dataset",
        writes_enabled=False,
    )
    mutable_refresh = factory_health._refresh_health_payload(
        mode="memory",
        storage_origin="memory",
        writes_enabled=True,
    )
    browse_cache = factory_health._browse_cache_health_payload(None)

    assert isinstance(static_refresh, factory_health.RefreshStatusPayload)
    assert isinstance(browse_cache, factory_health.BrowseCacheHealthPayload)
    assert static_refresh.model_dump(exclude_none=True) == {
        "enabled": False,
        "note": factory_health.REFRESH_NOTE_DATASET_STATIC,
    }
    assert mutable_refresh.model_dump(exclude_none=True) == {"enabled": True}
    assert browse_cache.model_dump() == {
        "enabled": False,
        "persisted": False,
        "path": None,
        "max_bytes": 0,
        "pending_warms": 0,
    }


def test_views_routes_register_expected_paths() -> None:
    app = FastAPI()
    views.register_views_routes(app)

    registered = {(route.path, tuple(sorted(route.methods))) for route in app.routes if hasattr(route, "methods")}

    assert ("/views", ("GET",)) in registered
    assert ("/views", ("PUT",)) in registered


def test_cache_failure_records_reason_and_logs_target(caplog) -> None:
    class _Cache(signals.BestEffortCacheMixin):
        def __init__(self) -> None:
            self._cache_name = "probe"
            self._last_failure = None

    cache = _Cache()

    with caplog.at_level(logging.WARNING):
        cache._record_failure("read", target="/tmp/cache", exc=OSError("denied"))

    assert cache.last_failure == signals.CacheFailure(
        cache_name="probe",
        operation="read",
        target="/tmp/cache",
        reason="OSError: denied",
    )
    assert "probe cache read failed for /tmp/cache" in caplog.text
