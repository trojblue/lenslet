from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlparse

from scripts.perf.table_query_fixture import table_query_body
from scripts.perf.table_query_latency import parse_server_timing


_TRACKED_ENDPOINTS = frozenset({"/folders/query", "/folders/facets", "/item"})


@dataclass
class BrowserRequestEvidence:
    phase: str = "initial"
    requests: list[dict[str, Any]] = field(default_factory=list)
    responses: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    _request_phases: dict[int, str] = field(default_factory=dict, repr=False)
    _inflight_by_phase: dict[str, set[int]] = field(default_factory=dict, repr=False)

    def on_request(self, request: Any) -> None:
        endpoint = urlparse(request.url).path
        if endpoint not in _TRACKED_ENDPOINTS:
            return
        request_id = id(request)
        self._request_phases[request_id] = self.phase
        self._inflight_by_phase.setdefault(self.phase, set()).add(request_id)
        self.requests.append(
            {
                "phase": self.phase,
                "endpoint": endpoint,
                "method": request.method,
                "facet_field_count": _facet_field_count(request)
                if endpoint == "/folders/facets"
                else None,
            }
        )

    def on_response(self, response: Any) -> None:
        endpoint = urlparse(response.url).path
        if endpoint not in _TRACKED_ENDPOINTS:
            return
        phase = self._request_phase(response.request)
        headers = response.headers
        raw_length = headers.get("content-length")
        try:
            response_bytes = int(raw_length) if raw_length is not None else None
        except ValueError:
            response_bytes = None
        self.responses.append(
            {
                "phase": phase,
                "endpoint": endpoint,
                "method": response.request.method,
                "status": response.status,
                "response_bytes": response_bytes,
                "server_timing_ms": parse_server_timing(headers.get("server-timing", "")),
            }
        )

    def on_request_failed(self, request: Any) -> None:
        endpoint = urlparse(request.url).path
        if endpoint not in _TRACKED_ENDPOINTS:
            return
        phase = self._request_phase(request)
        self.failures.append(
            {
                "phase": phase,
                "endpoint": endpoint,
                "failure": request.failure,
            }
        )
        self._finish_request(request, phase)

    def on_request_finished(self, request: Any) -> None:
        endpoint = urlparse(request.url).path
        if endpoint not in _TRACKED_ENDPOINTS:
            return
        phase = self._request_phase(request)
        self._finish_request(request, phase)

    def inflight_count(self, phase: str) -> int:
        return len(self._inflight_by_phase.get(phase, ()))

    def phase_summary(self, phase: str) -> dict[str, Any]:
        requests = [entry for entry in self.requests if entry["phase"] == phase]
        responses = [entry for entry in self.responses if entry["phase"] == phase]
        failures = [entry for entry in self.failures if entry["phase"] == phase]
        return {
            "query_requests": _endpoint_count(requests, "/folders/query"),
            "facet_requests": _endpoint_count(requests, "/folders/facets"),
            "facet_field_counts": [
                int(entry["facet_field_count"])
                for entry in requests
                if entry["endpoint"] == "/folders/facets"
                and entry["facet_field_count"] is not None
            ],
            "mutation_requests": _endpoint_count(
                requests,
                "/item",
                methods=frozenset({"PATCH", "PUT"}),
            ),
            "query_response_bytes": _endpoint_bytes(responses, "/folders/query"),
            "facet_response_bytes": _endpoint_bytes(responses, "/folders/facets"),
            "failed_requests": failures,
            "responses": responses,
            "inflight_requests": self.inflight_count(phase),
        }

    def _request_phase(self, request: Any) -> str:
        return self._request_phases.get(id(request), self.phase)

    def _finish_request(self, request: Any, phase: str) -> None:
        request_id = id(request)
        self._inflight_by_phase.get(phase, set()).discard(request_id)
        self._request_phases.pop(request_id, None)


def filtered_gallery_url(base_url: str) -> str:
    body = table_query_body(["metric_000", "metric_001", "metric_002"])
    query = urlencode(
        {
            "filters": json.dumps(body["filters"], separators=(",", ":")),
            "sort": "builtin:name:asc",
        }
    )
    return f"{base_url}/?{query}#/gallery"


def run_superseded_filter_sequence(page: Any) -> dict[str, Any]:
    stale_body = table_query_body(["metric_000", "metric_001", "metric_002"])
    fresh_body = json.loads(json.dumps(stale_body))
    fresh_body["filters"]["and"][1]["metricRange"]["min"] = 0.2
    return page.evaluate(
        """async ({staleBody, freshBody}) => {
          const clientSession = sessionStorage.getItem('lenslet.client_id.session');
          if (!clientSession) throw new Error('missing Lenslet client session');
          const staleRevision = Date.now() * 1000 + 100;
          const post = (path, body, revision, signal) => fetch(path, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Lenslet-Client-Session': clientSession,
              'X-Lenslet-Query-Revision': String(revision),
            },
            body: JSON.stringify(body),
            signal,
          });
          const staleController = new AbortController();
          const stale = [
            post('/folders/query', staleBody, staleRevision, staleController.signal),
            post('/folders/facets', staleBody, staleRevision, staleController.signal),
          ];
          await new Promise(resolve => requestAnimationFrame(resolve));
          staleController.abort();
          const fresh = await Promise.all([
            post('/folders/query', freshBody, staleRevision + 1),
            post('/folders/facets', freshBody, staleRevision + 1),
          ]);
          const staleResults = await Promise.allSettled(stale);
          return {
            stale_results: staleResults.map(result => result.status),
            fresh_statuses: fresh.map(response => response.status),
          };
        }""",
        {"staleBody": stale_body, "freshBody": fresh_body},
    )


def visible_paths(page: Any) -> list[str]:
    return page.locator('[role="gridcell"][id^="cell-"]').evaluate_all(
        """elements => elements.map(element => {
            const encoded = element.id.slice(5);
            try { return decodeURIComponent(encoded); } catch { return encoded; }
        })"""
    )


def install_projection_probe(page: Any, target_path: str) -> None:
    page.evaluate(
        """targetPath => {
            const previous = window.__lensletAnnotationLatencyProbe;
            previous?.observer?.disconnect();
            if (previous?.clickListener) {
              document.removeEventListener('click', previous.clickListener, true);
            }
            const gallery = document.querySelector('[role="grid"][aria-label="Gallery"]');
            if (!gallery) throw new Error('gallery root is unavailable');
            const targetId = `cell-${encodeURIComponent(targetPath)}`;
            const state = {
              gallery,
              targetId,
              armed: false,
              inputTimestamp: null,
              inputEpochMs: null,
              projectionTimestamp: null,
              projectionEpochMs: null,
              loadingStates: [],
              scrollTopBefore: gallery.scrollTop,
            };
            const recordLoading = () => {
              const sentinel = gallery.querySelector('[data-grid-state]');
              const value = {
                grid_state: sentinel?.getAttribute('data-grid-state') ?? 'unknown',
                aria_busy: gallery.getAttribute('aria-busy') === 'true',
                visible_cell_count: gallery.querySelectorAll('[role="gridcell"][id^="cell-"]').length,
              };
              const previous = state.loadingStates[state.loadingStates.length - 1];
              if (!previous || JSON.stringify(previous) !== JSON.stringify(value)) {
                state.loadingStates.push(value);
              }
            };
            const recordProjection = () => {
              if (!state.armed || state.projectionTimestamp != null) return;
              if (document.getElementById(targetId)) return;
              requestAnimationFrame(() => {
                state.projectionTimestamp = performance.now();
                state.projectionEpochMs = performance.timeOrigin + state.projectionTimestamp;
                recordLoading();
              });
            };
            const observer = new MutationObserver(() => {
              recordLoading();
              recordProjection();
            });
            observer.observe(gallery, {
              subtree: true,
              childList: true,
              attributes: true,
              attributeFilter: ['aria-busy', 'data-grid-state'],
            });
            const clickListener = event => {
              const button = event.target instanceof Element
                ? event.target.closest('button[aria-label="1 star"]')
                : null;
              if (!button || state.inputTimestamp != null) return;
              state.armed = true;
              state.inputTimestamp = performance.now();
              state.inputEpochMs = performance.timeOrigin + state.inputTimestamp;
              recordLoading();
              recordProjection();
            };
            state.observer = observer;
            state.clickListener = clickListener;
            document.addEventListener('click', clickListener, true);
            recordLoading();
            window.__lensletAnnotationLatencyProbe = state;
          }""",
        target_path,
    )


def arm_projection_probe(page: Any) -> None:
    page.evaluate(
        """() => {
            const state = window.__lensletAnnotationLatencyProbe;
            if (!state) throw new Error('annotation latency probe is not installed');
            state.armed = true;
            state.inputTimestamp = performance.now();
            state.inputEpochMs = performance.timeOrigin + state.inputTimestamp;
          }"""
    )


def projection_snapshot(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const state = window.__lensletAnnotationLatencyProbe;
            if (!state) throw new Error('annotation latency probe is not installed');
            const currentGallery = document.querySelector('[role="grid"][aria-label="Gallery"]');
            return {
              input_timestamp_ms: state.inputTimestamp,
              input_epoch_ms: state.inputEpochMs,
              projection_timestamp_ms: state.projectionTimestamp,
              projection_epoch_ms: state.projectionEpochMs,
              projection_latency_ms: state.inputTimestamp == null || state.projectionTimestamp == null
                ? null
                : state.projectionTimestamp - state.inputTimestamp,
              loading_states: [...state.loadingStates],
              gallery_root_replaced: currentGallery !== state.gallery,
              scroll_top_before: state.scrollTopBefore,
              scroll_top_after: currentGallery?.scrollTop ?? null,
              target_still_visible: document.getElementById(state.targetId) != null,
            };
          }"""
    )


def _endpoint_count(
    entries: list[dict[str, Any]],
    endpoint: str,
    *,
    methods: frozenset[str] | None = None,
) -> int:
    return sum(
        1
        for entry in entries
        if entry["endpoint"] == endpoint and (methods is None or entry["method"] in methods)
    )


def _endpoint_bytes(entries: list[dict[str, Any]], endpoint: str) -> int:
    return sum(
        int(entry["response_bytes"])
        for entry in entries
        if entry["endpoint"] == endpoint and entry["response_bytes"] is not None
    )


def _facet_field_count(request: Any) -> int | None:
    try:
        body = json.loads(request.post_data or "{}")
        fields = body.get("facet_fields")
        if not isinstance(fields, dict):
            return None
        return len(fields.get("metric_keys", [])) + len(fields.get("categorical_keys", []))
    except (TypeError, ValueError):
        return None
