"""Inspector jitter probe scenario."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit
from scripts.browser.gui_jitter.painted_frames import (
    mark_painted_frame_action,
    start_painted_frame_trace,
    stop_painted_frame_trace,
    summarize_painted_frame_trace,
)
from scripts.browser.gui_jitter.inspector_frames import (
    INSPECTOR_EXPECTED_CONTENT,
    exercise_inspector_hard_reset,
    inspector_input_values,
    inspector_status_geometry,
    quick_view_delta,
    set_dirty_inspector_drafts,
    snapshot_quick_view_section,
    summarize_first_visible_inspector_frame,
    summarize_inspector_identity_trace,
)
from scripts.browser.gui_jitter.inspector_requests import (
    RequestEvidence, exercise_inspector_conflict_regions,
    exercise_remote_inspector_cache_sync,
    request_attribution_violations,
    summarize_requests,
    wait_for_request_count,
)
from scripts.browser.gui_jitter.shared import (
    ProbeResult,
    set_local_storage,
    wait_for_grid,
)
from scripts.smoke_harness import SmokeFailure, import_playwright

QUICK_ZERO_PATH = "/quick_00_meta.png"
QUICK_ONE_PATH = "/quick_01_meta.png"
PLAIN_PATH = "/quick_02_plain.png"
QUICK_THREE_PATH = "/quick_03_meta.png"
INSPECTOR_TRACE_SELECTORS = {
    "panel": "[data-inspector-panel]",
    "preview_shell": ".inspector-preview-shell",
    "preview_card": ".inspector-preview-card",
    "filename": ".inspector-preview-block [title]",
    "quick_view": '[data-inspector-section-id="quickView"]',
    "basics": '[data-inspector-section-id="basics"]',
    "metadata": '[data-inspector-section-id="metadata"]',
    "notes": '[data-inspector-section-id="notes"]',
    "notes_input": 'textarea[aria-label="Notes"]',
    "tags_input": 'input[aria-label="Tags"]',
    "star_1": 'button[aria-label="1 star"]',
    "star_2": 'button[aria-label="2 stars"]',
    "star_3": 'button[aria-label="3 stars"]',
    "star_4": 'button[aria-label="4 stars"]',
    "star_5": 'button[aria-label="5 stars"]',
}
REQUIRED_INSPECTOR_SURFACES = (
    "panel",
    "preview_shell",
    "preview_card",
    "filename",
    "quick_view",
    "basics",
    "metadata",
    "notes",
)
INSPECTOR_SENTINELS = {
    QUICK_ZERO_PATH: ("quick_00_meta.png", "alpha prompt", "notes-00_meta", "tag-00_meta"),
    QUICK_ONE_PATH: ("quick_01_meta.png", "beta prompt", "notes-01_meta", "tag-01_meta"),
    QUICK_THREE_PATH: ("quick_03_meta.png", "gamma prompt", "notes-03_meta", "tag-03_meta"),
}
INSPECTOR_RGB = {
    QUICK_ZERO_PATH: (72, 36, 120),
    QUICK_ONE_PATH: (36, 126, 74),
    PLAIN_PATH: (148, 72, 34),
    QUICK_THREE_PATH: (38, 96, 154),
}

LAZY_SURFACE_FRAME_INIT_SCRIPT = r"""
(() => {
  window.__lensletLazySurfaceFrames = [];
  window.__lensletLazySurfaceTraceRunning = true;
  const sample = () => {
    if (!window.__lensletLazySurfaceTraceRunning) return;
    const inspector = document.querySelector('[data-lazy-surface="inspector"]');
    const overlay = document.querySelector('[data-lazy-surface="overlay"]');
    window.__lensletLazySurfaceFrames.push({
      now: performance.now(),
      inspectorFallback: Boolean(inspector),
      inspectorCopy: inspector?.getAttribute('data-loading-copy-visible') === 'true',
      overlayFallback: Boolean(overlay),
      overlayCopy: overlay?.getAttribute('data-loading-copy-visible') === 'true',
      text: document.body?.innerText || '',
    });
    requestAnimationFrame(sample);
  };
  requestAnimationFrame(sample);
})();
"""


class InspectorProbeFailure(SmokeFailure):
    """Inspector failure carrying bounded frame/request evidence for JSON output."""

    def __init__(self, message: str, evidence: dict[str, Any]) -> None:
        super().__init__(message)
        self.evidence = evidence


@dataclass(slots=True)
class InspectorSnapshots:
    quick_one_loaded: dict[str, Any]
    pending_quick: dict[str, Any]
    quick_three_loaded: dict[str, Any]
    pending_plain: dict[str, Any]
    plain_resolved: dict[str, Any]


def select_grid_path(page: Any, path: str, browser_timeout_ms: float) -> None:
    selector = f'[id="cell-{quote(path, safe="")}"]'
    cell = page.locator(selector).first
    if cell.count() == 0:
        visible_ids = page.locator('[role="gridcell"][id^="cell-"]').evaluate_all(
            "nodes => nodes.map((node) => node.id)"
        )
        raise SmokeFailure(f"Grid cell for {path} not found; mounted IDs={visible_ids!r}.")
    cell.click()
    page.wait_for_function(
        """(targetPath) => {
          const panel = document.querySelector('.app-right-panel');
          if (!(panel instanceof HTMLElement)) return false;
          const filename = targetPath.split('/').filter(Boolean).pop() || targetPath;
          return (panel.textContent || '').includes(filename);
        }""",
        arg=path,
        timeout=browser_timeout_ms,
    )


def inspector_storage_payload() -> dict[str, str | None]:
    return {
        "autoloadImageMetadata": "true",
        "sortSpec": json.dumps({"kind": "builtin", "key": "name", "dir": "asc"}),
        "sortKey": "name",
        "sortDir": "asc",
        "selectedMetric": None,
        "filterAst": json.dumps({"and": []}),
        "starFilters": json.dumps([]),
        "lenslet.inspector.sections": json.dumps(
            {
                "quickView": True,
                "overview": True,
                "compare": True,
                "metadata": True,
                "basics": True,
                "notes": True,
            }
        ),
    }


def prepare_inspector_page(page: Any, base_url: str, browser_timeout_ms: float) -> None:
    payload = json.dumps(inspector_storage_payload())
    page.add_init_script(
        script=f"""(() => {{
          for (const [key, value] of Object.entries({payload})) {{
            if (value === null) localStorage.removeItem(key);
            else localStorage.setItem(key, value);
          }}
        }})()"""
    )
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)
    page.reload(wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)


def summarize_inspector_trace(
    trace: dict[str, Any],
    max_delta_px: float,
    *,
    require_expected_content: bool = False,
) -> dict[str, Any]:
    summary = summarize_painted_frame_trace(
        trace,
        required_surfaces=REQUIRED_INSPECTOR_SURFACES,
        sentinels_by_path=INSPECTOR_SENTINELS,
        max_delta_px=max_delta_px,
        fallback_texts=(
            "Loading inspector...",
            "Inspector could not load.",
            "PNG metadata not loaded yet.",
            "Load meta",
        ),
        allow_retained_complete=True,
    )
    identity = summarize_inspector_identity_trace(
        trace,
        sentinels_by_path=INSPECTOR_SENTINELS,
        rgb_by_path=INSPECTOR_RGB,
        expected_content_by_path=INSPECTOR_EXPECTED_CONTENT if require_expected_content else None,
    )
    summary["identity"] = identity
    summary["violations"].extend(identity["violations"])
    return summary


def summarize_metadata_loading_timing(
    trace: dict[str, Any],
    *,
    action_id: str,
    minimum_delay_ms: float,
    expect_delayed_copy: bool,
    settled_text: str | None = None,
    include_text_samples: bool = False,
) -> dict[str, Any]:
    frames = trace.get("frames")
    markers = trace.get("markers")
    if not isinstance(frames, list) or not isinstance(markers, list):
        return {"violations": ["metadata timing trace is malformed"]}
    marker = next(
        (
            candidate
            for candidate in markers
            if isinstance(candidate, dict) and candidate.get("actionId") == action_id
        ),
        None,
    )
    if not isinstance(marker, dict):
        return {"violations": [f"metadata timing marker {action_id!r} is absent"]}
    started_at = float(marker.get("startedAt") or 0)
    loading_offsets: list[float] = []
    forbidden_frames = 0
    matching_frames = 0
    settled: bool | None = None if settled_text is None else False
    text_samples: list[dict[str, Any]] = []
    for frame in frames:
        if not isinstance(frame, dict) or not isinstance(frame.get("marker"), dict):
            continue
        if frame["marker"].get("actionId") != action_id:
            continue
        matching_frames += 1
        surfaces = frame.get("surfaces")
        metadata = surfaces.get("metadata") if isinstance(surfaces, dict) else None
        text = str(metadata.get("text") or "") if isinstance(metadata, dict) else ""
        offset_ms = float(frame.get("timestamp") or 0) - started_at
        if not text_samples or text_samples[-1]["text"] != text:
            text_samples.append({"offset_ms": offset_ms, "text": text})
        if "PNG metadata not loaded yet." in text or "Load meta" in text:
            forbidden_frames += 1
        if "Loading metadata" in text or "Loading…" in text:
            loading_offsets.append(offset_ms)
        if settled_text is not None and settled_text in text and "Copy" in text:
            settled = True
    violations: list[str] = []
    if not matching_frames:
        violations.append(f"metadata timing action {action_id!r} has no painted frames")
    if forbidden_frames:
        violations.append(
            f"autoload-on metadata painted idle fallback in {forbidden_frames} frames"
        )
    if expect_delayed_copy and not loading_offsets:
        violations.append("slow metadata transition never painted delayed neutral loading copy")
    elif loading_offsets and min(loading_offsets) < minimum_delay_ms:
        violations.append(
            f"metadata loading copy painted at {min(loading_offsets):.3f}ms before "
            f"the {minimum_delay_ms:.0f}ms delay"
        )
    elif not expect_delayed_copy and loading_offsets:
        violations.append("fast or superseded metadata transition painted loading copy")
    if settled is False:
        violations.append("slow metadata transition never painted settled target content")
    return {
        "action_id": action_id,
        "expect_delayed_copy": expect_delayed_copy,
        "minimum_delay_ms": minimum_delay_ms,
        "first_loading_copy_ms": min(loading_offsets) if loading_offsets else None,
        "forbidden_idle_frames": forbidden_frames,
        "settled_target_painted": settled,
        "frame_count": matching_frames,
        "text_samples": text_samples if include_text_samples else [],
        "violations": violations,
    }


FETCH_DELAY_INIT_SCRIPT = """(() => {
  const originalFetch = window.fetch.bind(window);
  window.__lensletDelayNextPatch = false;
  window.fetch = async (...args) => {
    const input = args[0];
    const init = args[1] || {};
    const rawUrl = typeof input === 'string' ? input : input.url;
    const url = new URL(rawUrl, window.location.href);
    const method = String(init.method || (typeof input === 'string' ? 'GET' : input.method) || 'GET').toUpperCase();
    const response = await originalFetch(...args);
    let delayMs = 0;
    const targetPath = url.searchParams.get('path');
    if (method === 'GET' && url.pathname === '/metadata') {
      const metadataDelays = {
        '/quick_00_meta.png': 320,
        '/quick_01_meta.png': 45,
        '/quick_02_plain.png': 180,
        '/quick_03_meta.png': 1250,
      };
      delayMs = metadataDelays[targetPath] || 100;
    }
    if (method === 'GET' && url.pathname === '/item/detail' && targetPath === '/quick_00_meta.png') {
      delayMs = Math.max(delayMs, 350);
    }
    if (method === 'PATCH' && url.pathname === '/item' && window.__lensletDelayNextPatch) {
      window.__lensletDelayNextPatch = false;
      delayMs = 350;
    }
    if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, delayMs));
    return response;
  };
})()"""


def wait_for_prompt(page: Any, prompt_text: str, browser_timeout_ms: float, error_message: str) -> None:
    try:
        page.wait_for_function(
            """(expectedPrompt) => {
              const section = document.querySelector('[data-inspector-section-id="quickView"]');
              if (!(section instanceof HTMLElement)) return false;
              if ((section.textContent || '').includes('Loading metadata…')) return false;
              const promptRow = Array.from(section.querySelectorAll('.ui-kv-row')).find((row) => {
                const label = row.querySelector('.ui-kv-label');
                return label instanceof HTMLElement && (label.textContent || '').trim() === 'Prompt';
              });
              if (!(promptRow instanceof HTMLElement)) return false;
              const value = promptRow.querySelector('.ui-kv-value');
              const prompt = value instanceof HTMLElement ? (value.textContent || '').trim() : '';
              return prompt.includes(expectedPrompt);
            }""",
            arg=prompt_text,
            timeout=browser_timeout_ms,
        )
    except TimeoutError as exc:
        raise SmokeFailure(error_message) from exc


def wait_for_latest_prompt(page: Any, browser_timeout_ms: float) -> None:
    try:
        page.wait_for_function(
            """() => {
              const section = document.querySelector('[data-inspector-section-id="quickView"]');
              if (!(section instanceof HTMLElement)) return false;
              const promptRow = Array.from(section.querySelectorAll('.ui-kv-row')).find((row) => {
                const label = row.querySelector('.ui-kv-label');
                return label instanceof HTMLElement && (label.textContent || '').trim() === 'Prompt';
              });
              if (!(promptRow instanceof HTMLElement)) return false;
              const value = promptRow.querySelector('.ui-kv-value');
              const promptText = value instanceof HTMLElement ? (value.textContent || '').trim() : '';
              return promptText.includes('beta prompt')
                && !promptText.includes('alpha prompt')
                && !(section.textContent || '').includes('Loading metadata…');
            }""",
            timeout=browser_timeout_ms,
        )
    except TimeoutError as exc:
        raise SmokeFailure(
            "Timed out waiting for quick-view to settle on latest selection without stale hydration."
        ) from exc


def wait_for_quick_view_absent(page: Any, browser_timeout_ms: float) -> None:
    try:
        page.wait_for_function(
            """() => !document.querySelector('[data-inspector-section-id="quickView"]')""",
            timeout=browser_timeout_ms,
        )
    except TimeoutError as exc:
        raise SmokeFailure("Timed out waiting for Quick View reservation to clear for plain metadata.") from exc


def wait_for_inspector_hydrated(page: Any, path: str, browser_timeout_ms: float) -> None:
    prompt_by_path = {
        QUICK_ZERO_PATH: "alpha prompt",
        QUICK_ONE_PATH: "beta prompt",
        QUICK_THREE_PATH: "gamma prompt",
    }
    expected_prompt = prompt_by_path.get(path)
    if expected_prompt is not None:
        wait_for_prompt(
            page,
            expected_prompt,
            browser_timeout_ms,
            f"Timed out waiting for inspector metadata for {path}.",
        )
    expected_notes = f"notes-{path.rsplit('/', 1)[-1].removeprefix('quick_').removesuffix('.png')}"
    try:
        page.wait_for_function(
            """(expected) => {
              const notes = document.querySelector('textarea[aria-label="Notes"]');
              return notes instanceof HTMLTextAreaElement && notes.value === expected;
            }""",
            arg=expected_notes,
            timeout=browser_timeout_ms,
        )
    except Exception as exc:
        current = inspector_input_values(page)
        raise SmokeFailure(
            f"Timed out waiting for sidecar draft hydration for {path}: "
            f"expected notes={expected_notes!r}, current={current!r}."
        ) from exc


def mark_and_click(
    page: Any,
    *,
    action_id: str,
    expected_path: str,
    selector: str,
    expected_star: int | None = None,
    enforce_star_invariant: bool = False,
    required_texts: tuple[str, ...] = (),
    require_expected_paint: bool = True,
    dispatch_on_target: bool = False,
    copied_feedback_owner_path: str | None = None,
) -> None:
    page.evaluate(
        """({ actionId, expectedPath, expectedStar, enforceStarInvariant, requiredTexts, requireExpectedPaint, copiedFeedbackOwnerPath, selector }) => {
          const state = window.__lensletPaintedFrameTrace;
          if (!state || !state.running) throw new Error('painted-frame trace is not running');
          const target = document.querySelector(selector);
          if (!(target instanceof HTMLElement)) throw new Error(`Missing click target ${selector}`);
          target.addEventListener('click', () => {
            const panel = document.querySelector('[data-inspector-panel]');
            const marker = {
              actionId,
              expectedPath,
              expectedStar,
              enforceStarInvariant,
              requiredTexts,
              requireExpectedPaint,
              copiedFeedbackOwnerPath,
              previousPresentedPath: panel?.getAttribute('data-inspector-presented-path') || '',
              startedAt: performance.now(),
            };
            state.marker = marker;
            state.markers.push(marker);
          }, { capture: true, once: true });
        }""",
        {
            "actionId": action_id,
            "expectedPath": expected_path,
            "expectedStar": expected_star,
            "enforceStarInvariant": enforce_star_invariant,
            "requiredTexts": list(required_texts),
            "requireExpectedPaint": require_expected_paint,
            "copiedFeedbackOwnerPath": copied_feedback_owner_path,
            "selector": selector,
        },
    )
    if dispatch_on_target:
        page.locator(selector).locator("[data-media-state]").dispatch_event("click")
    else:
        page.locator(selector).click()


def trace_violations(summary: dict[str, Any]) -> list[str]:
    raw = summary.get("violations")
    if not isinstance(raw, list):
        return ["painted-frame summary is malformed"]
    return [str(value) for value in raw]


def exercise_rating_continuity(
    browser: Any,
    base_url: str,
    max_delta_px: float,
    browser_timeout_ms: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    owner_context = browser.new_context(viewport={"width": 1280, "height": 900})
    remote_context = browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        owner = owner_context.new_page()
        remote = remote_context.new_page()
        owner.set_default_timeout(browser_timeout_ms)
        remote.set_default_timeout(browser_timeout_ms)
        owner_requests = RequestEvidence(owner, "owner")
        remote_requests = RequestEvidence(remote, "remote")
        prepare_inspector_page(owner, base_url, browser_timeout_ms)
        prepare_inspector_page(remote, base_url, browser_timeout_ms)
        select_grid_path(owner, QUICK_ONE_PATH, browser_timeout_ms)
        select_grid_path(remote, QUICK_ONE_PATH, browser_timeout_ms)
        wait_for_inspector_hydrated(owner, QUICK_ONE_PATH, browser_timeout_ms)
        wait_for_inspector_hydrated(remote, QUICK_ONE_PATH, browser_timeout_ms)

        owner_notes = "owner dirty notes"
        owner_tags = "owner-dirty-tag"
        set_dirty_inspector_drafts(owner, owner_notes, owner_tags)
        if inspector_input_values(owner) != {"notes": owner_notes, "tags": owner_tags}:
            raise SmokeFailure("Failed to establish owner dirty drafts before rating.")

        owner_requests.set_phase("local_rating")
        start_painted_frame_trace(
            owner,
            page_id="owner",
            phase="local_rating",
            selectors=INSPECTOR_TRACE_SELECTORS,
        )
        for index in range(20):
            expected_star = 1 if index % 2 == 0 else 2
            star_label = f"{expected_star} star{'s' if expected_star > 1 else ''}"
            star_selector = f'button[aria-label="{star_label}"]'
            mark_and_click(
                owner,
                action_id=f"local-rating-{index + 1}",
                expected_path=QUICK_ONE_PATH,
                expected_star=expected_star,
                required_texts=(
                    "quick_01_meta.png",
                    "beta prompt",
                    "beta-model",
                    owner_notes,
                    owner_tags,
                ),
                selector=star_selector,
            )
            owner.locator(star_selector).wait_for(state="visible")
            owner.wait_for_function(
                """(label) => document.querySelector(`button[aria-label="${label}"]`)?.getAttribute('aria-pressed') === 'true'""",
                arg=star_label,
                timeout=browser_timeout_ms,
            )
            wait_for_request_count(
                owner,
                owner_requests,
                "local_rating",
                method="PATCH",
                pathname="/item",
                expected=index + 1,
                browser_timeout_ms=browser_timeout_ms,
            )
            owner.wait_for_timeout(20)
        owner.wait_for_timeout(40)
        local_trace = stop_painted_frame_trace(owner)
        local_summary = summarize_inspector_trace(local_trace, max_delta_px)
        local_requests = summarize_requests(owner_requests, "local_rating")
        local_summary.update(
            {
                "patch_item_requests": local_requests["counts"].get("PATCH /item", 0),
                "metadata_gets_after_warmup": local_requests["counts"].get("GET /metadata", 0),
                "detail_gets_after_warmup": local_requests["counts"].get("GET /item/detail", 0),
                "dirty_drafts_preserved": inspector_input_values(owner)
                == {"notes": owner_notes, "tags": owner_tags},
                "requests": local_requests,
            }
        )
        local_summary["violations"].extend(
            request_attribution_violations(
                local_requests["records"],
                page_id="owner",
                phase="local_rating",
                allowed={
                    ("GET", "/item", QUICK_ONE_PATH),
                    ("PATCH", "/item", QUICK_ONE_PATH),
                },
                exact_counts={("PATCH", "/item", QUICK_ONE_PATH): 20},
                max_counts={("GET", "/item", QUICK_ONE_PATH): 20},
            )
        )
        if local_summary["patch_item_requests"] != 20:
            local_summary["violations"].append(
                f"local rating issued {local_summary['patch_item_requests']} PATCH /item requests instead of 20"
            )
        if local_summary["metadata_gets_after_warmup"] != 0:
            local_summary["violations"].append("local rating refetched metadata after warmup")
        if local_summary["detail_gets_after_warmup"] != 0:
            local_summary["violations"].append("local rating refetched item detail after warmup")
        if float(local_summary["paint_p95_ms"]) > 100.0:
            local_summary["violations"].append("local rating painted feedback p95 exceeded 100ms")
        if not local_summary["dirty_drafts_preserved"]:
            local_summary["violations"].append("local rating replaced dirty notes/tags drafts")

        remote_notes = "remote dirty notes"
        remote_tags = "remote-dirty-tag"
        set_dirty_inspector_drafts(remote, remote_notes, remote_tags)
        remote_requests.set_phase("remote_echo")
        owner_requests.set_phase("remote_echo")
        start_painted_frame_trace(
            remote,
            page_id="remote",
            phase="remote_echo",
            selectors=INSPECTOR_TRACE_SELECTORS,
        )
        mark_painted_frame_action(
            remote,
            action_id="remote-echo",
            expected_path=QUICK_ONE_PATH,
            expected_star=3,
            required_texts=(
                "quick_01_meta.png",
                "beta prompt",
                "beta-model",
                remote_notes,
                remote_tags,
            ),
        )
        owner.get_by_role("button", name="3 stars").click()
        wait_for_request_count(
            owner,
            owner_requests,
            "remote_echo",
            method="PATCH",
            pathname="/item",
            expected=1,
            browser_timeout_ms=browser_timeout_ms,
        )
        remote.wait_for_function(
            """() => document.querySelector('button[aria-label="3 stars"]')?.getAttribute('aria-pressed') === 'true'""",
            timeout=browser_timeout_ms,
        )
        remote.wait_for_timeout(40)
        remote_trace = stop_painted_frame_trace(remote)
        remote_summary = summarize_inspector_trace(remote_trace, max_delta_px)
        remote_page_requests = summarize_requests(remote_requests, "remote_echo")
        owner_page_requests = summarize_requests(owner_requests, "remote_echo")
        remote_summary.update(
            {
                "dirty_drafts_preserved": inspector_input_values(remote)
                == {"notes": remote_notes, "tags": remote_tags},
                "requests": remote_page_requests,
                "originating_page_requests": owner_page_requests,
            }
        )
        remote_summary["violations"].extend(
            request_attribution_violations(
                remote_summary["requests"]["records"],
                page_id="remote",
                phase="remote_echo",
                allowed=set(),
            )
        )
        remote_summary["violations"].extend(
            request_attribution_violations(
                owner_page_requests["records"],
                page_id="owner",
                phase="remote_echo",
                allowed={
                    ("GET", "/item", QUICK_ONE_PATH),
                    ("PATCH", "/item", QUICK_ONE_PATH),
                },
                exact_counts={("PATCH", "/item", QUICK_ONE_PATH): 1},
                max_counts={("GET", "/item", QUICK_ONE_PATH): 1},
            )
        )
        if not remote_summary["dirty_drafts_preserved"]:
            remote_summary["violations"].append("remote star echo replaced dirty notes/tags drafts")
        cache_sync = exercise_remote_inspector_cache_sync(
            owner,
            remote,
            owner_requests,
            remote_requests,
            path=QUICK_ONE_PATH,
            live_notes="remote cache notes",
            live_tags="remote-cache-tag",
            restore_notes="notes-01_meta",
            restore_tags="tag-01_meta",
            browser_timeout_ms=browser_timeout_ms,
        )
        remote_summary["cache_sync"] = cache_sync
        remote_summary["violations"].extend(cache_sync["violations"])
        return local_summary, remote_summary
    finally:
        owner_context.close()
        remote_context.close()


def exercise_selection_continuity(
    browser: Any,
    base_url: str,
    max_delta_px: float,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    context.add_init_script(FETCH_DELAY_INIT_SCRIPT)
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
    try:
        page = context.new_page()
        page.set_default_timeout(browser_timeout_ms)
        requests = RequestEvidence(page, "selection")
        prepare_inspector_page(page, base_url, browser_timeout_ms)
        select_grid_path(page, QUICK_ONE_PATH, browser_timeout_ms)
        wait_for_inspector_hydrated(page, QUICK_ONE_PATH, browser_timeout_ms)
        requests.set_phase("selection")
        start_painted_frame_trace(
            page,
            page_id="selection",
            phase="selection",
            selectors=INSPECTOR_TRACE_SELECTORS,
        )
        mark_and_click(
            page,
            action_id="selection-superseded-slow",
            expected_path=QUICK_THREE_PATH,
            selector=f'[id="cell-{quote(QUICK_THREE_PATH, safe="")}"]',
            require_expected_paint=False,
        )
        page.wait_for_function(
            """() => document.querySelector('[data-inspector-panel]')
              ?.getAttribute('data-inspector-requested-path') === '/quick_03_meta.png'""",
            timeout=browser_timeout_ms,
        )
        wait_for_request_count(
            page,
            requests,
            "selection",
            method="GET",
            pathname="/metadata",
            expected=1,
            browser_timeout_ms=browser_timeout_ms,
        )
        page.wait_for_timeout(200)
        mark_and_click(
            page,
            action_id="selection-superseding-fast",
            expected_path=QUICK_ONE_PATH,
            selector=f'[id="cell-{quote(QUICK_ONE_PATH, safe="")}"]',
        )
        wait_for_inspector_hydrated(page, QUICK_ONE_PATH, browser_timeout_ms)
        page.wait_for_timeout(1_150)
        page.evaluate(
            """() => {
              window.__lensletResolveClipboardWrite = null;
              window.__lensletClipboardWritePending = false;
              Object.defineProperty(navigator.clipboard, 'writeText', {
                configurable: true,
                value: () => new Promise((resolve) => {
                  window.__lensletClipboardWritePending = true;
                  window.__lensletResolveClipboardWrite = resolve;
                }),
              });
            }"""
        )
        copy_prompt = page.get_by_role("button", name="Copy Prompt")
        copy_prompt.click()
        page.wait_for_function(
            "() => window.__lensletClipboardWritePending === true",
            timeout=browser_timeout_ms,
        )
        mark_and_click(
            page,
            action_id="selection-copy-feedback",
            expected_path=QUICK_ZERO_PATH,
            selector=f'[id="cell-{quote(QUICK_ZERO_PATH, safe="")}"]',
            copied_feedback_owner_path=QUICK_ONE_PATH,
        )
        page.wait_for_function(
            """() => document.querySelector('[data-inspector-panel]')
              ?.getAttribute('data-inspector-requested-path') === '/quick_00_meta.png'""",
            timeout=browser_timeout_ms,
        )
        page.evaluate(
            """() => {
              window.__lensletResolveClipboardWrite?.();
              window.__lensletResolveClipboardWrite = null;
            }"""
        )
        wait_for_inspector_hydrated(page, QUICK_ZERO_PATH, browser_timeout_ms)
        page.wait_for_timeout(40)
        if page.locator('[title="Prompt copied"]').count() > 0:
            raise SmokeFailure("Copied Quick View feedback leaked into the target Inspector.")
        request_windows: list[dict[str, Any]] = []
        paths = [QUICK_THREE_PATH] + [
            QUICK_ZERO_PATH if index % 2 == 0 else QUICK_ONE_PATH
            for index in range(19)
        ]
        for index, path in enumerate(paths):
            selector = f'[id="cell-{quote(path, safe="")}"]'
            before_record_count = len(requests.phase_records("selection"))
            mark_and_click(
                page,
                action_id=f"selection-{index + 1}",
                expected_path=path,
                selector=selector,
            )
            try:
                page.wait_for_function(
                    """(targetPath) => {
                      const filename = targetPath.split('/').filter(Boolean).pop() || targetPath;
                      const node = document.querySelector('.inspector-preview-block [title]');
                      return node instanceof HTMLElement && (node.textContent || '').includes(filename);
                    }""",
                    arg=path,
                    timeout=browser_timeout_ms,
                )
            except Exception as exc:
                panel_text = page.locator("[data-inspector-panel]").inner_text()
                raise SmokeFailure(
                    f"Selection iteration {index + 1} did not render filename for {path}; "
                    f"panel={panel_text[:500]!r}."
                ) from exc
            wait_for_inspector_hydrated(page, path, browser_timeout_ms)
            page.wait_for_timeout(34)
            window_records = requests.phase_records("selection")[before_record_count:]
            allowed = {
                ("GET", endpoint, path)
                for endpoint in ("/item", "/item/detail", "/metadata")
            }
            request_windows.append(
                {
                    "action_id": f"selection-{index + 1}",
                    "path": path,
                    "counts": {
                        endpoint: sum(
                            1
                            for record in window_records
                            if (record["method"], record["pathname"], record["path"])
                            == ("GET", endpoint, path)
                        )
                        for endpoint in ("/item", "/item/detail", "/metadata")
                    },
                    "attribution_violations": request_attribution_violations(
                        window_records,
                        page_id="selection",
                        phase="selection",
                        allowed=allowed,
                        max_counts={identity: 1 for identity in allowed},
                    ),
                }
            )
        trace = stop_painted_frame_trace(page)
        summary = summarize_inspector_trace(
            trace,
            max_delta_px,
            require_expected_content=True,
        )
        metadata_loading_timings = [
            summarize_metadata_loading_timing(
                trace,
                action_id="selection-superseded-slow",
                minimum_delay_ms=1_000.0,
                expect_delayed_copy=False,
            ),
            summarize_metadata_loading_timing(
                trace,
                action_id="selection-superseding-fast",
                minimum_delay_ms=1_000.0,
                expect_delayed_copy=False,
            ),
            summarize_metadata_loading_timing(
                trace,
                action_id="selection-copy-feedback",
                minimum_delay_ms=1_000.0,
                expect_delayed_copy=False,
            ),
            summarize_metadata_loading_timing(
                trace,
                action_id="selection-1",
                minimum_delay_ms=1_000.0,
                expect_delayed_copy=True,
                settled_text="gamma-model",
                include_text_samples=True,
            ),
            *(
                summarize_metadata_loading_timing(
                    trace,
                    action_id=f"selection-{index}",
                    minimum_delay_ms=1_000.0,
                    expect_delayed_copy=False,
                )
                for index in range(2, 21)
            ),
        ]
        summary["metadata_loading_timings"] = metadata_loading_timings
        for timing in metadata_loading_timings:
            summary["violations"].extend(
                f"{timing['action_id']}: {violation}"
                for violation in timing["violations"]
            )
        request_summary = summarize_requests(requests, "selection")
        summary["requests"] = request_summary
        summary["request_windows"] = request_windows
        for window in request_windows:
            summary["violations"].extend(
                f"{window['action_id']}: {violation}"
                for violation in window["attribution_violations"]
            )
        return summary
    finally:
        context.close()


def exercise_delayed_response_switch(
    browser: Any,
    base_url: str,
    max_delta_px: float,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    context.add_init_script(FETCH_DELAY_INIT_SCRIPT)
    try:
        page = context.new_page()
        page.set_default_timeout(browser_timeout_ms)
        requests = RequestEvidence(page, "delayed")
        prepare_inspector_page(page, base_url, browser_timeout_ms)
        select_grid_path(page, QUICK_ONE_PATH, browser_timeout_ms)
        wait_for_inspector_hydrated(page, QUICK_ONE_PATH, browser_timeout_ms)
        requests.set_phase("delayed_rating_switch")
        start_painted_frame_trace(
            page,
            page_id="delayed",
            phase="delayed_rating_switch",
            selectors=INSPECTOR_TRACE_SELECTORS,
        )

        page.locator(f'[id="cell-{quote(QUICK_ZERO_PATH, safe="")}"]').click()
        page.wait_for_function(
            """() => (document.querySelector('.inspector-preview-block [title]')?.textContent || '').includes('quick_00_meta.png')""",
            timeout=browser_timeout_ms,
        )
        wait_for_request_count(
            page,
            requests,
            "delayed_rating_switch",
            method="GET",
            pathname="/metadata",
            expected=1,
            browser_timeout_ms=browser_timeout_ms,
        )
        mark_and_click(
            page,
            action_id="delayed-detail-switch",
            expected_path=QUICK_ONE_PATH,
            selector=f'[id="cell-{quote(QUICK_ONE_PATH, safe="")}"]',
        )
        wait_for_inspector_hydrated(page, QUICK_ONE_PATH, browser_timeout_ms)
        page.wait_for_timeout(400)

        page.evaluate("window.__lensletDelayNextPatch = true")
        page.get_by_role("button", name="5 stars").click()
        wait_for_request_count(
            page,
            requests,
            "delayed_rating_switch",
            method="PATCH",
            pathname="/item",
            expected=1,
            browser_timeout_ms=browser_timeout_ms,
        )
        mark_and_click(
            page,
            action_id="delayed-rating-switch",
            expected_path=QUICK_ZERO_PATH,
            expected_star=0,
            enforce_star_invariant=True,
            selector=f'[id="cell-{quote(QUICK_ZERO_PATH, safe="")}"]',
        )
        wait_for_inspector_hydrated(page, QUICK_ZERO_PATH, browser_timeout_ms)
        page.wait_for_timeout(400)
        trace = stop_painted_frame_trace(page)
        summary = summarize_inspector_trace(
            trace,
            max_delta_px,
            require_expected_content=True,
        )
        request_summary = summarize_requests(requests, "delayed_rating_switch")
        summary["requests"] = request_summary
        allowed = {
            ("GET", endpoint, path)
            for endpoint in ("/item", "/item/detail", "/metadata")
            for path in (QUICK_ZERO_PATH, QUICK_ONE_PATH)
        }
        allowed.add(("PATCH", "/item", QUICK_ONE_PATH))
        delayed_max_counts = {
            ("GET", "/item", QUICK_ZERO_PATH): 1,
            ("GET", "/item", QUICK_ONE_PATH): 1,
            ("GET", "/item/detail", QUICK_ZERO_PATH): 1,
            ("GET", "/item/detail", QUICK_ONE_PATH): 1,
            ("GET", "/metadata", QUICK_ZERO_PATH): 2,
            ("GET", "/metadata", QUICK_ONE_PATH): 1,
        }
        summary["violations"].extend(
            request_attribution_violations(
                request_summary["records"],
                page_id="delayed",
                phase="delayed_rating_switch",
                allowed=allowed,
                exact_counts={("PATCH", "/item", QUICK_ONE_PATH): 1},
                max_counts=delayed_max_counts,
            )
        )
        summary["target_rating_preserved"] = not trace_violations(summary)
        summary["old_path_responses_ignored"] = not trace_violations(summary)
        return summary
    finally:
        context.close()


def exercise_inspector_lifecycle(
    browser: Any,
    base_url: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    stage = "open"
    try:
        page = context.new_page()
        page.set_default_timeout(browser_timeout_ms)
        expected_order = ["notes", "quickView", "metadata", "basics", "overview", "compareMetadata"]
        expected_paths = ["persisted.first.frame"]
        payload = inspector_storage_payload()
        payload["lenslet.inspector.sections"] = json.dumps(
            {
                "quickView": True,
                "overview": True,
                "compare": True,
                "metadata": True,
                "basics": False,
                "notes": True,
            },
            separators=(",", ":"),
        )
        payload["lenslet.inspector.sectionOrder.v2"] = json.dumps(
            expected_order,
            separators=(",", ":"),
        )
        payload["lenslet.inspector.quickView.paths.v1"] = json.dumps(
            expected_paths,
            separators=(",", ":"),
        )
        payload["lenslet.inspector.metricsExpanded"] = "1"
        payload["lenslet.inspector.export.reverseOrder"] = "1"
        payload["lenslet.inspector.export.highQualityGif"] = "1"
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_grid(page, browser_timeout_ms)
        set_local_storage(page, payload)
        page.reload(wait_until="domcontentloaded")
        wait_for_grid(page, browser_timeout_ms)
        stage = "select"
        start_painted_frame_trace(
            page,
            page_id="lifecycle-cold",
            phase="lifecycle-cold",
            selectors=INSPECTOR_TRACE_SELECTORS,
        )
        mark_and_click(
            page,
            action_id="lifecycle-cold-select",
            expected_path=QUICK_ONE_PATH,
            selector=f'[id="cell-{quote(QUICK_ONE_PATH, safe="")}"]',
        )
        wait_for_inspector_hydrated(page, QUICK_ONE_PATH, browser_timeout_ms)
        page.wait_for_timeout(34)
        cold_trace = stop_painted_frame_trace(page)
        cold_frame = summarize_first_visible_inspector_frame(
            cold_trace,
            expected_section_order=expected_order,
            expected_quick_view_paths=expected_paths,
            expected_inputs={},
        )
        violations = [f"cold: {value}" for value in cold_frame["violations"]]
        root_token = cold_frame.get("frame", {}).get("token")
        stage = "edit drafts"
        page.evaluate("window.__lensletInspectorNode = document.querySelector('[data-inspector-panel]')")
        page.get_by_label("Toggle custom JSON paths").click()
        custom_paths = page.get_by_label("Quick View custom JSON paths")
        custom_paths.fill("unsaved.lifecycle.path")
        notes = page.locator('textarea[aria-label="Notes"]')
        notes.fill("unsaved lifecycle notes")
        notes.focus()
        stage = "visibility cycles"
        toggle = page.get_by_label("Toggle right panel").first
        reopen_frames: list[dict[str, Any]] = []

        for cycle in range(20):
            toggle.click()
            page.wait_for_function(
                """() => {
                  const panel = document.querySelector('[data-inspector-panel]');
                  return panel instanceof HTMLElement && panel.hidden && panel.hasAttribute('inert');
                }""",
                timeout=browser_timeout_ms,
            )
            if page.evaluate("() => document.querySelector('[data-inspector-panel]')?.contains(document.activeElement)"):
                violations.append(f"cycle {cycle + 1} retained focus inside hidden Inspector")
            start_painted_frame_trace(
                page,
                page_id=f"lifecycle-reopen-{cycle + 1}",
                phase="lifecycle-reopen",
                selectors=INSPECTOR_TRACE_SELECTORS,
            )
            mark_and_click(
                page,
                action_id=f"lifecycle-reopen-{cycle + 1}",
                expected_path=QUICK_ONE_PATH,
                selector='button[aria-label="Toggle right panel"]',
            )
            page.wait_for_function(
                """() => !document.querySelector('[data-inspector-panel]')?.hasAttribute('hidden')""",
                timeout=browser_timeout_ms,
            )
            page.wait_for_timeout(34)
            reopen = summarize_first_visible_inspector_frame(
                stop_painted_frame_trace(page),
                expected_section_order=expected_order,
                expected_quick_view_paths=expected_paths,
                expected_inputs={
                    "Notes": "unsaved lifecycle notes",
                    "Quick View custom JSON paths": "unsaved.lifecycle.path",
                },
                expected_token=str(root_token),
            )
            reopen_frames.append(reopen)
            violations.extend(
                f"cycle {cycle + 1}: {value}" for value in reopen["violations"]
            )

        start_painted_frame_trace(
            page,
            page_id="lifecycle-narrow",
            phase="lifecycle-narrow",
            selectors=INSPECTOR_TRACE_SELECTORS,
        )
        mark_painted_frame_action(
            page,
            action_id="lifecycle-narrow",
            expected_path=QUICK_ONE_PATH,
        )
        page.set_viewport_size({"width": 900, "height": 900})
        page.wait_for_function(
            """() => !document.querySelector('[data-inspector-panel]')?.hasAttribute('hidden')""",
            timeout=browser_timeout_ms,
        )
        page.wait_for_timeout(34)
        narrow_frame = summarize_first_visible_inspector_frame(
            stop_painted_frame_trace(page),
            expected_section_order=expected_order,
            expected_quick_view_paths=expected_paths,
            expected_inputs={"Notes": "unsaved lifecycle notes"},
            expected_token=str(root_token),
        )
        violations.extend(f"narrow: {value}" for value in narrow_frame["violations"])
        narrow_geometry = inspector_status_geometry(page)
        if not isinstance(narrow_geometry, dict) or not narrow_geometry.get("filenameClamped"):
            violations.append("narrow Inspector filename escaped its two-line clamp")
        if not isinstance(narrow_geometry, dict) or not narrow_geometry.get("boundedStatuses"):
            violations.append("narrow Inspector status regions escaped the panel")
        page.set_viewport_size({"width": 480, "height": 900})
        page.wait_for_function(
            """() => {
              const panel = document.querySelector('[data-inspector-panel]');
              return panel instanceof HTMLElement && panel.hidden && panel.hasAttribute('inert');
            }""",
            timeout=browser_timeout_ms,
        )
        page.set_viewport_size({"width": 1280, "height": 900})
        page.wait_for_function(
            """() => !document.querySelector('[data-inspector-panel]')?.hasAttribute('hidden')""",
            timeout=browser_timeout_ms,
        )
        state = page.evaluate(
            """() => {
              const panel = document.querySelector('[data-inspector-panel]');
              const notes = document.querySelector('textarea[aria-label="Notes"]');
              const custom = document.querySelector('textarea[aria-label="Quick View custom JSON paths"]');
              const basics = document.querySelector('[data-inspector-section-id="basics"]');
              return {
                sameNode: panel === window.__lensletInspectorNode,
                notes: notes?.value || '',
                custom: custom?.value || '',
                basicsOpen: basics?.querySelector('button[aria-expanded]')?.getAttribute('aria-expanded'),
                path: panel?.getAttribute('data-inspector-presented-path') || '',
              };
            }"""
        )
        if not state.get("sameNode"):
            violations.append("Inspector root node changed across close/responsive cycles")
        if state.get("notes") != "unsaved lifecycle notes":
            violations.append("Inspector Notes draft changed across close/responsive cycles")
        if state.get("custom") != "unsaved.lifecycle.path":
            violations.append("Inspector custom-path draft changed across close/responsive cycles")
        if state.get("basicsOpen") != "false":
            violations.append("Inspector disclosure state changed across close/responsive cycles")
        if state.get("path") != QUICK_ONE_PATH:
            violations.append("Inspector presentation identity changed across visibility cycles")
        persisted = page.evaluate(
            """(keys) => Object.fromEntries(keys.map((key) => [key, localStorage.getItem(key)]))""",
            [
                "lenslet.inspector.sections",
                "lenslet.inspector.sectionOrder.v2",
                "lenslet.inspector.quickView.paths.v1",
                "lenslet.inspector.metricsExpanded",
                "lenslet.inspector.export.reverseOrder",
                "lenslet.inspector.export.highQualityGif",
            ],
        )
        json_storage_keys = {
            "lenslet.inspector.sections",
            "lenslet.inspector.sectionOrder.v2",
            "lenslet.inspector.quickView.paths.v1",
        }
        persisted_normalized = {
            key: json.loads(value) if key in json_storage_keys and value is not None else value
            for key, value in persisted.items()
        }
        expected_persisted = {
            key: json.loads(payload[key]) if key in json_storage_keys else payload[key]
            for key in persisted
        }
        if persisted_normalized != expected_persisted:
            violations.append(
                f"Inspector lifecycle overwrote persisted state: {persisted!r}"
            )
        page.locator('textarea[aria-label="Notes"]').fill("notes-01_meta")
        page.locator('textarea[aria-label="Notes"]').blur()
        page.wait_for_timeout(500)
        hard_reset = exercise_inspector_hard_reset(
            page,
            trace_selectors=INSPECTOR_TRACE_SELECTORS,
            target_path=QUICK_ONE_PATH,
            target_rgb=(188, 42, 116),
            target_selector=f'[id="cell-{quote(QUICK_ONE_PATH, safe="")}"]',
            browser_timeout_ms=browser_timeout_ms,
        )
        violations.extend(f"hard reset: {value}" for value in hard_reset["violations"])
        return {
            "cycles": 20,
            "cold_frame": cold_frame,
            "reopen_frame_count": len(reopen_frames),
            "narrow_frame": narrow_frame,
            "narrow_geometry": narrow_geometry,
            "persisted": persisted,
            "state": state,
            "hard_reset": hard_reset,
            "violations": violations,
        }
    except Exception as exc:
        raise SmokeFailure(f"Inspector lifecycle stage {stage!r} failed: {exc}") from exc
    finally:
        context.close()


def exercise_hidden_inspector_compare(
    browser: Any,
    base_url: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        page = context.new_page()
        page.set_default_timeout(browser_timeout_ms)
        requests = RequestEvidence(page, "hidden-compare")
        prepare_inspector_page(page, base_url, browser_timeout_ms)
        select_grid_path(page, QUICK_ONE_PATH, browser_timeout_ms)
        wait_for_inspector_hydrated(page, QUICK_ONE_PATH, browser_timeout_ms)
        page.get_by_role("button", name="Toggle right panel").click()
        page.wait_for_function(
            """() => {
              const panel = document.querySelector('[data-inspector-panel]');
              return panel instanceof HTMLElement && panel.hidden && panel.hasAttribute('inert');
            }""",
            timeout=browser_timeout_ms,
        )
        requests.set_phase("hidden-compare")
        page.locator(f'[id="cell-{quote(QUICK_ZERO_PATH, safe="")}"]').click(
            modifiers=["Control"]
        )
        page.wait_for_function(
            """() => {
              const raw = document.querySelector('[data-inspector-panel]')
                ?.getAttribute('data-inspector-requested-identity');
              if (!raw) return false;
              const identity = JSON.parse(raw);
              return Array.isArray(identity?.[2]) && identity[2].length === 2;
            }""",
            timeout=browser_timeout_ms,
        )
        page.wait_for_timeout(350)
        hidden_requests = summarize_requests(requests, "hidden-compare")
        violations = request_attribution_violations(
            hidden_requests["records"],
            page_id="hidden-compare",
            phase="hidden-compare",
            allowed=set(),
        )

        requests.set_phase("hidden-compare-reopen")
        page.get_by_role("button", name="Toggle right panel").click()
        page.wait_for_function(
            """() => {
              const panel = document.querySelector('[data-inspector-panel]');
              return panel instanceof HTMLElement && !panel.hidden && !panel.hasAttribute('inert');
            }""",
            timeout=browser_timeout_ms,
        )
        wait_for_request_count(
            page,
            requests,
            "hidden-compare-reopen",
            method="GET",
            pathname="/metadata",
            expected=2,
            browser_timeout_ms=browser_timeout_ms,
        )
        page.get_by_role("button", name="Reload").wait_for(state="visible")
        reopen_requests = summarize_requests(requests, "hidden-compare-reopen")
        violations.extend(
            request_attribution_violations(
                reopen_requests["records"],
                page_id="hidden-compare",
                phase="hidden-compare-reopen",
                allowed={
                    ("GET", "/metadata", QUICK_ONE_PATH),
                    ("GET", "/metadata", QUICK_ZERO_PATH),
                },
                exact_counts={
                    ("GET", "/metadata", QUICK_ONE_PATH): 1,
                    ("GET", "/metadata", QUICK_ZERO_PATH): 1,
                },
            )
        )
        requests.set_phase("hidden-compare-unchanged")
        page.get_by_role("button", name="Toggle right panel").click()
        page.wait_for_function(
            """() => document.querySelector('[data-inspector-panel]')?.hasAttribute('inert')""",
            timeout=browser_timeout_ms,
        )
        page.get_by_role("button", name="Toggle right panel").click()
        page.wait_for_function(
            """() => !document.querySelector('[data-inspector-panel]')?.hasAttribute('inert')""",
            timeout=browser_timeout_ms,
        )
        page.wait_for_timeout(350)
        unchanged_requests = summarize_requests(requests, "hidden-compare-unchanged")
        violations.extend(
            request_attribution_violations(
                unchanged_requests["records"],
                page_id="hidden-compare",
                phase="hidden-compare-unchanged",
                allowed=set(),
            )
        )
        return {
            "hidden_requests": hidden_requests,
            "reopen_requests": reopen_requests,
            "unchanged_reopen_requests": unchanged_requests,
            "violations": violations,
        }
    finally:
        context.close()


def exercise_dirty_selection_routing(
    browser: Any,
    base_url: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for mode, owner_path, target_path, modifiers, expected_inputs in (
        (
            "single-to-single",
            QUICK_ONE_PATH,
            QUICK_ZERO_PATH,
            [],
            {"notes": "notes-00_meta", "tags": "tag-00_meta"},
        ),
        (
            "single-to-multi",
            QUICK_THREE_PATH,
            QUICK_ZERO_PATH,
            ["Control"],
            {"notes": "", "tags": ""},
        ),
    ):
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        try:
            page = context.new_page()
            page.set_default_timeout(browser_timeout_ms)
            requests = RequestEvidence(page, mode)
            prepare_inspector_page(page, base_url, browser_timeout_ms)
            select_grid_path(page, owner_path, browser_timeout_ms)
            wait_for_inspector_hydrated(page, owner_path, browser_timeout_ms)
            set_dirty_inspector_drafts(page, f"dirty notes {mode}", f"dirty-tag-{mode}")
            page.locator('textarea[aria-label="Notes"]').focus()
            requests.set_phase(mode)
            page.locator(f'[id="cell-{quote(target_path, safe="")}"]').click(
                modifiers=modifiers
            )
            if modifiers:
                page.wait_for_function(
                    """() => {
                      const raw = document.querySelector('[data-inspector-panel]')
                        ?.getAttribute('data-inspector-presented-identity');
                      if (!raw) return false;
                      const identity = JSON.parse(raw);
                      return Array.isArray(identity?.[2]) && identity[2].length === 2;
                    }""",
                    timeout=browser_timeout_ms,
                )
                labels = ("Notes for selected items", "Tags for selected items")
            else:
                wait_for_inspector_hydrated(page, target_path, browser_timeout_ms)
                labels = ("Notes", "Tags")
            wait_for_request_count(
                page,
                requests,
                mode,
                method="PATCH",
                pathname="/item",
                expected=1,
                browser_timeout_ms=browser_timeout_ms,
            )
            page.wait_for_timeout(200)
            request_summary = summarize_requests(requests, mode)
            patch_paths = [
                record["path"]
                for record in request_summary["records"]
                if record["method"] == "PATCH" and record["pathname"] == "/item"
            ]
            target_inputs = page.evaluate(
                """([notesLabel, tagsLabel]) => ({
                  notes: document.querySelector(`textarea[aria-label="${notesLabel}"]`)?.value,
                  tags: document.querySelector(`input[aria-label="${tagsLabel}"]`)?.value,
                })""",
                list(labels),
            )
            violations: list[str] = []
            if patch_paths != [owner_path]:
                violations.append(f"dirty owner patch paths were {patch_paths!r}")
            if target_inputs != expected_inputs:
                violations.append(f"dirty A leaked into target inputs: {target_inputs!r}")
            results[mode] = {
                "patch_paths": patch_paths,
                "target_inputs": target_inputs,
                "requests": request_summary,
                "violations": violations,
            }
        finally:
            context.close()
    results["violations"] = [
        f"{mode}: {violation}"
        for mode, result in results.items()
        if mode != "violations"
        for violation in result["violations"]
    ]
    return results


def exercise_inspector_autoload_off(
    browser: Any,
    base_url: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        payload = inspector_storage_payload()
        payload["autoloadImageMetadata"] = "0"
        context.add_init_script(
            script=f"""
            (() => {{
              const payload = {json.dumps(payload)};
              for (const [key, value] of Object.entries(payload)) {{
                if (value === null) localStorage.removeItem(key);
                else localStorage.setItem(key, value);
              }}
            }})();
            """
        )
        page = context.new_page()
        page.set_default_timeout(browser_timeout_ms)
        metadata_requests: list[str] = []
        page.on(
            "request",
            lambda request: metadata_requests.append(request.url)
            if urlsplit(request.url).path == "/metadata"
            else None,
        )
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_grid(page, browser_timeout_ms)
        select_grid_path(page, QUICK_ONE_PATH, browser_timeout_ms)
        page.wait_for_function(
            """() => {
              const panel = document.querySelector('[data-inspector-panel]');
              const image = document.querySelector('.inspector-preview-image');
              return panel?.getAttribute('data-inspector-presented-path') === '/quick_01_meta.png'
                && image instanceof HTMLImageElement
                && image.complete
                && image.naturalWidth > 0;
            }""",
            timeout=browser_timeout_ms,
        )
        panel_text = page.locator("[data-inspector-panel]").inner_text()
        violations: list[str] = []
        if "PNG metadata not loaded yet." not in panel_text or "Load meta" not in panel_text:
            violations.append("autoload-off Inspector did not settle in explicit idle metadata state")
        if metadata_requests:
            violations.append("autoload-off Inspector issued a metadata request")
        return {"metadata_requests": metadata_requests, "violations": violations}
    finally:
        context.close()


def exercise_inspector_dependency_failures(
    browser: Any,
    base_url: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    endpoint_by_name = {
        "detail": "/item/detail",
        "sidecar": "/item",
        "metadata": "/metadata",
        "preview": "/thumb",
    }
    for name, endpoint in endpoint_by_name.items():
        context = browser.new_context(viewport={"width": 1280, "height": 900})

        failed_endpoint = endpoint
        failure_label = name

        def fail_target(route: Any) -> None:
            parsed = urlsplit(route.request.url)
            request_path = parse_qs(parsed.query).get("path", [""])[0]
            if (
                route.request.method.upper() == "GET"
                and parsed.path == failed_endpoint
                and request_path == QUICK_ZERO_PATH
            ):
                route.fulfill(
                    status=500,
                    content_type="application/json",
                    body=json.dumps({"detail": f"forced {failure_label} failure"}),
                )
                return
            route.continue_()

        stage = "prepare"
        try:
            page = context.new_page()
            page.set_default_timeout(max(browser_timeout_ms, 12_000))
            if name == "preview":
                page.route(f"**{failed_endpoint}?*", fail_target)
            prepare_inspector_page(page, base_url, max(browser_timeout_ms, 12_000))
            select_grid_path(page, QUICK_ONE_PATH, max(browser_timeout_ms, 12_000))
            wait_for_inspector_hydrated(page, QUICK_ONE_PATH, max(browser_timeout_ms, 12_000))
            if name != "preview":
                page.route(f"**{failed_endpoint}?*", fail_target)
            stage = "target failure"
            start_painted_frame_trace(
                page,
                page_id=f"failure-{name}",
                phase=f"failure-{name}",
                selectors=INSPECTOR_TRACE_SELECTORS,
            )
            mark_and_click(
                page,
                action_id=f"failure-{name}",
                expected_path=QUICK_ZERO_PATH,
                selector=f'[id="cell-{quote(QUICK_ZERO_PATH, safe="")}"]',
                dispatch_on_target=name == "preview",
            )
            page.set_viewport_size({"width": 900, "height": 900})
            page.wait_for_function(
                """() => document.querySelector('[data-inspector-panel]')
                  ?.getAttribute('data-inspector-presented-path') === '/quick_00_meta.png'""",
                timeout=max(browser_timeout_ms, 12_000),
            )
            page.wait_for_timeout(80)
            trace = stop_painted_frame_trace(page)
            identity = summarize_inspector_identity_trace(
                trace,
                sentinels_by_path=INSPECTOR_SENTINELS,
                rgb_by_path=INSPECTOR_RGB,
                expected_content_by_path=INSPECTOR_EXPECTED_CONTENT,
            )
            panel_text = page.locator("[data-inspector-panel]").inner_text()
            violations = list(identity["violations"])
            status_geometry = inspector_status_geometry(page)
            if name != "preview" and f"forced {name} failure" not in panel_text:
                violations.append(f"{name} failure did not expose a bounded target-owned error")
            if not status_geometry.get("boundedStatuses"):
                violations.append(f"{name} failure status escaped the narrow Inspector")
            if name == "preview" and "Retry preview" not in panel_text:
                violations.append("preview failure did not expose retry")
            results[name] = {
                "identity": identity, "status_geometry": status_geometry, "violations": violations}
        except Exception as exc:
            snapshot = page.evaluate(
                """() => {
                  const panel = document.querySelector('[data-inspector-panel]');
                  return {
                    requested: panel?.getAttribute('data-inspector-requested-path') || '',
                    presented: panel?.getAttribute('data-inspector-presented-path') || '',
                    text: (panel?.textContent || '').slice(0, 500),
                  };
                }"""
            )
            raise SmokeFailure(
                f"Inspector {name} failure stage {stage!r} failed: {exc}; snapshot={snapshot!r}"
            ) from exc
        finally:
            context.close()
    results["conflict_regions"] = exercise_inspector_conflict_regions(
        browser, base_url, path=QUICK_ONE_PATH, browser_timeout_ms=browser_timeout_ms,
        multi_paths=(QUICK_ZERO_PATH, QUICK_THREE_PATH),
        prepare_page=prepare_inspector_page)
    results["violations"] = [
        f"{name}: {violation}"
        for name, summary in results.items()
        if name != "violations"
        for violation in summary["violations"]
    ]
    return results


def exercise_inspector_continuity(
    browser: Any,
    base_url: str,
    max_delta_px: float,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    try:
        local_rating, remote_echo = exercise_rating_continuity(
            browser,
            base_url,
            max_delta_px,
            browser_timeout_ms,
        )
    except Exception as exc:
        raise SmokeFailure(f"Inspector rating/remote-echo continuity phase failed: {exc}") from exc
    try:
        selection = exercise_selection_continuity(
            browser,
            base_url,
            max_delta_px,
            browser_timeout_ms,
        )
    except Exception as exc:
        raise SmokeFailure(f"Inspector selection continuity phase failed: {exc}") from exc
    try:
        delayed = exercise_delayed_response_switch(
            browser,
            base_url,
            max_delta_px,
            browser_timeout_ms,
        )
    except Exception as exc:
        raise SmokeFailure(f"Inspector delayed-response continuity phase failed: {exc}") from exc
    try:
        autoload_off = exercise_inspector_autoload_off(browser, base_url, browser_timeout_ms)
    except Exception as exc:
        raise SmokeFailure(f"Inspector autoload-off phase failed: {exc}") from exc
    try:
        dependency_failures = exercise_inspector_dependency_failures(
            browser,
            base_url,
            browser_timeout_ms,
        )
    except Exception as exc:
        raise SmokeFailure(f"Inspector dependency-failure phase failed: {exc}") from exc
    try:
        lifecycle = exercise_inspector_lifecycle(browser, base_url, browser_timeout_ms)
    except Exception as exc:
        raise SmokeFailure(f"Inspector lifecycle continuity phase failed: {exc}") from exc
    try:
        hidden_compare = exercise_hidden_inspector_compare(browser, base_url, browser_timeout_ms)
    except Exception as exc:
        raise SmokeFailure(f"Inspector hidden-compare phase failed: {exc}") from exc
    try:
        dirty_selection_routing = exercise_dirty_selection_routing(
            browser,
            base_url,
            browser_timeout_ms,
        )
    except Exception as exc:
        raise SmokeFailure(f"Inspector dirty selection-routing phase failed: {exc}") from exc
    violations = [
        f"{phase}: {violation}"
        for phase, summary in (
            ("local_rating", local_rating),
            ("remote_echo", remote_echo),
            ("selection", selection),
            ("delayed_rating_switch", delayed),
            ("lifecycle", lifecycle),
            ("autoload_off", autoload_off),
            ("dependency_failures", dependency_failures),
            ("hidden_compare", hidden_compare),
            ("dirty_selection_routing", dirty_selection_routing),
        )
        for violation in trace_violations(summary)
    ]
    return {
        "local_rating": local_rating,
        "remote_echo": remote_echo,
        "selection": selection,
        "delayed_rating_switch": delayed,
        "lifecycle": lifecycle,
        "autoload_off": autoload_off,
        "dependency_failures": dependency_failures,
        "hidden_compare": hidden_compare,
        "dirty_selection_routing": dirty_selection_routing,
        "workaround_used": False,
        "violations": violations,
    }


def exercise_inspector_probe(page: Any, browser_timeout_ms: float) -> InspectorSnapshots:
    page.goto(page.url, wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)
    set_local_storage(page, inspector_storage_payload())
    page.reload(wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)

    select_grid_path(page, QUICK_ZERO_PATH, browser_timeout_ms)
    page.wait_for_timeout(20)
    select_grid_path(page, QUICK_ONE_PATH, browser_timeout_ms)
    wait_for_latest_prompt(page, browser_timeout_ms)
    quick_one_loaded = snapshot_quick_view_section(page)
    page.wait_for_timeout(120)

    page.locator(f'[id="cell-{quote(QUICK_THREE_PATH, safe="")}"]').click()
    page.wait_for_function(
        """(path) => document.querySelector('[data-inspector-panel]')
          ?.getAttribute('data-inspector-requested-path') === path""",
        arg=QUICK_THREE_PATH,
        timeout=browser_timeout_ms,
    )
    pending_quick = snapshot_quick_view_section(page)
    wait_for_prompt(
        page,
        "gamma prompt",
        browser_timeout_ms,
        "Timed out waiting for quick-view quick->quick hydration.",
    )
    quick_three_loaded = snapshot_quick_view_section(page)
    page.wait_for_timeout(120)

    page.locator(f'[id="cell-{quote(PLAIN_PATH, safe="")}"]').click()
    page.wait_for_function(
        """(path) => document.querySelector('[data-inspector-panel]')
          ?.getAttribute('data-inspector-requested-path') === path""",
        arg=PLAIN_PATH,
        timeout=browser_timeout_ms,
    )
    pending_plain = snapshot_quick_view_section(page)
    wait_for_quick_view_absent(page, browser_timeout_ms)
    plain_resolved = snapshot_quick_view_section(page)

    return InspectorSnapshots(
        quick_one_loaded=quick_one_loaded,
        pending_quick=pending_quick,
        quick_three_loaded=quick_three_loaded,
        pending_plain=pending_plain,
        plain_resolved=plain_resolved,
    )


def inspector_violations(
    snapshots: InspectorSnapshots,
    *,
    max_delta_px: float,
    max_inspector_delta: float,
) -> list[str]:
    violations: list[str] = []
    if max_inspector_delta > max_delta_px:
        violations.append(
            f"inspector delta {max_inspector_delta:.3f}px exceeded threshold {max_delta_px:.3f}px"
        )
    if not bool(snapshots.pending_quick.get("present")):
        violations.append("quick->quick pending: expected Quick View section to remain mounted")
    if not bool(snapshots.pending_plain.get("present")):
        violations.append("quick->plain pending: expected Quick View section to remain mounted")
    if bool(snapshots.plain_resolved.get("present")):
        violations.append("quick->plain resolved: expected Quick View section to unmount after metadata settles")
    prompt_value = str(snapshots.quick_one_loaded.get("promptValue") or "")
    if "beta prompt" not in prompt_value or "alpha prompt" in prompt_value:
        violations.append("stale protection: expected quick-view prompt to match latest selection")
    return violations


def stop_lazy_surface_trace(page: Any) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => {
          window.__lensletLazySurfaceTraceRunning = false;
          return window.__lensletLazySurfaceFrames || [];
        }"""
    )


def lazy_surface_timing(
    frames: list[dict[str, Any]],
    *,
    fallback_key: str,
    copy_key: str,
) -> dict[str, Any]:
    fallback_frames = [frame for frame in frames if frame.get(fallback_key)]
    copy_frames = [frame for frame in fallback_frames if frame.get(copy_key)]
    first_fallback = min((float(frame["now"]) for frame in fallback_frames), default=0.0)
    first_copy = min((float(frame["now"]) for frame in copy_frames), default=0.0)
    return {
        "fallback_frame_count": len(fallback_frames),
        "loading_copy_frame_count": len(copy_frames),
        "first_loading_copy_offset_ms": first_copy - first_fallback if copy_frames else None,
    }


def exercise_sprint6_lazy_surfaces(
    browser: Any,
    base_url: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    def delayed_chunk(chunk_name: str):
        def handle(route: Any) -> None:
            if chunk_name in route.request.url:
                time.sleep(1.2)
            route.continue_()

        return handle

    inspector_context = browser.new_context(viewport={"width": 1280, "height": 900})
    inspector_context.add_init_script(LAZY_SURFACE_FRAME_INIT_SCRIPT)
    def handle_inspector_chunk(route: Any) -> None:
        if "CompareViewer-" in route.request.url:
            route.abort()
            return
        delayed_chunk("Inspector-")(route)

    inspector_context.route("**/*.js", handle_inspector_chunk)
    inspector_page_errors: list[str] = []
    try:
        inspector_page = inspector_context.new_page()
        inspector_page.on("pageerror", lambda error: inspector_page_errors.append(str(error)))
        inspector_page.set_default_timeout(browser_timeout_ms)
        inspector_page.goto(base_url, wait_until="domcontentloaded")
        wait_for_grid(inspector_page, browser_timeout_ms)
        select_grid_path(inspector_page, QUICK_ZERO_PATH, browser_timeout_ms)
        inspector_page.locator(".inspector-preview-shell").wait_for(
            state="visible",
            timeout=browser_timeout_ms,
        )
        inspector_page.wait_for_timeout(80)
        inspector_frames = stop_lazy_surface_trace(inspector_page)
    finally:
        inspector_context.close()

    compare_browser = browser.browser_type.launch(headless=True)
    compare_context = compare_browser.new_context(viewport={"width": 1280, "height": 900})
    compare_context.add_init_script(LAZY_SURFACE_FRAME_INIT_SCRIPT)
    compare_context.add_init_script(
        """(() => {
          window.requestIdleCallback = callback => {
            window.__lensletDeferredIdleCallback = callback;
            return 1;
          };
          window.cancelIdleCallback = () => {};
        })();"""
    )
    compare_context.route("**/*.js", delayed_chunk("CompareViewer-"))
    compare_page_errors: list[str] = []
    try:
        compare_page = compare_context.new_page()
        compare_page.on("pageerror", lambda error: compare_page_errors.append(str(error)))
        compare_page.set_default_timeout(browser_timeout_ms)
        compare_page.goto(base_url, wait_until="domcontentloaded")
        wait_for_grid(compare_page, browser_timeout_ms)
        for path in (QUICK_ZERO_PATH, QUICK_ONE_PATH):
            compare_page.locator(f'[id="cell-{quote(path, safe="")}"]').click(
                modifiers=["Control"]
            )
        compare_page.get_by_label("Compare selected images").first.click()
        compare_page.wait_for_function(
            """() => Boolean(document.querySelector('[aria-label="Compare images"]')?.getAttribute('data-compare-presented-pair'))""",
            timeout=browser_timeout_ms,
        )
        compare_page.wait_for_timeout(80)
        compare_frames = stop_lazy_surface_trace(compare_page)
    finally:
        compare_context.close()
        compare_browser.close()

    inspector_timing = lazy_surface_timing(
        inspector_frames,
        fallback_key="inspectorFallback",
        copy_key="inspectorCopy",
    )
    compare_timing = lazy_surface_timing(
        compare_frames,
        fallback_key="overlayFallback",
        copy_key="overlayCopy",
    )
    violations: list[str] = []
    for name, timing in (("Inspector", inspector_timing), ("Compare", compare_timing)):
        if timing["fallback_frame_count"] == 0:
            violations.append(f"{name} cold chunk did not reproduce a lazy fallback")
        if timing["loading_copy_frame_count"] == 0:
            violations.append(f"{name} slow chunk never painted delayed loading copy")
        offset = timing["first_loading_copy_offset_ms"]
        if offset is not None and float(offset) < 780.0:
            violations.append(f"{name} lazy loading copy painted before 800ms")
    if any(
        "Loading inspector" in str(frame.get("text", "")) and not frame.get("inspectorCopy")
        for frame in inspector_frames
    ):
        violations.append("Inspector painted loading copy before its delayed slot enabled")
    if any(
        "Loading compare" in str(frame.get("text", "")) and not frame.get("overlayCopy")
        for frame in compare_frames
    ):
        violations.append("Compare painted loading copy before its delayed slot enabled")
    if inspector_page_errors:
        violations.append(f"Inspector cold chunk raised page errors: {inspector_page_errors}")
    if compare_page_errors:
        violations.append(f"Compare cold chunk raised page errors: {compare_page_errors}")
    return {
        "inspector": inspector_timing,
        "compare": compare_timing,
        "page_errors": {
            "inspector": inspector_page_errors,
            "compare": compare_page_errors,
        },
        "violations": violations,
    }


def inspector_result(
    snapshots: InspectorSnapshots,
    continuity: dict[str, Any],
    max_delta_px: float,
) -> ProbeResult:
    quick_view_deltas = {
        "quick_to_quick_pending_delta": quick_view_delta(snapshots.quick_one_loaded, snapshots.pending_quick),
        "quick_to_quick_loaded_delta": quick_view_delta(snapshots.quick_one_loaded, snapshots.quick_three_loaded),
        "quick_to_plain_pending_delta": quick_view_delta(snapshots.quick_three_loaded, snapshots.pending_plain),
    }
    max_inspector_delta = max(quick_view_deltas.values(), default=0.0)
    violations = inspector_violations(
        snapshots,
        max_delta_px=max_delta_px,
        max_inspector_delta=max_inspector_delta,
    )
    continuity_violations = continuity.get("violations")
    if not isinstance(continuity_violations, list):
        violations.append("inspector continuity result is malformed")
    else:
        violations.extend(str(value) for value in continuity_violations)
    checks = {
            "quick_view_deltas_px": quick_view_deltas,
            "quick_one_loaded_snapshot": snapshots.quick_one_loaded,
            "pending_quick_snapshot": snapshots.pending_quick,
            "quick_three_loaded_snapshot": snapshots.quick_three_loaded,
            "pending_plain_snapshot": snapshots.pending_plain,
            "plain_resolved_snapshot": snapshots.plain_resolved,
            "inspector_continuity": continuity,
            "violations": violations,
    }
    if violations:
        raise InspectorProbeFailure("; ".join(violations), checks)
    return ProbeResult(
        scenario="inspector",
        max_delta_px=max_delta_px,
        max_inspector_delta_px=max_inspector_delta,
        checks=checks,
    )


def run_inspector_probe(base_url: str, max_delta_px: float, browser_timeout_ms: float) -> ProbeResult:
    playwright_error, playwright_timeout_error, sync_playwright = import_playwright()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            context.add_init_script(FETCH_DELAY_INIT_SCRIPT)
            page = context.new_page()
            page.set_default_timeout(browser_timeout_ms)
            page.goto(base_url, wait_until="domcontentloaded")
            try:
                snapshots = exercise_inspector_probe(page, browser_timeout_ms)
            except Exception as exc:
                raise SmokeFailure(f"Legacy Quick View inspector phase failed: {exc}") from exc
            context.close()
            continuity = exercise_inspector_continuity(
                browser,
                base_url,
                max_delta_px,
                browser_timeout_ms,
            )
            lazy_surfaces = exercise_sprint6_lazy_surfaces(
                browser,
                base_url,
                browser_timeout_ms,
            )
            continuity["lazy_surfaces"] = lazy_surfaces
            if isinstance(continuity.get("violations"), list):
                continuity["violations"].extend(lazy_surfaces["violations"])
            browser.close()
    except playwright_timeout_error as exc:
        raise SmokeFailure(f"playwright timeout: {exc}") from exc
    except playwright_error as exc:
        raise SmokeFailure(f"playwright probe failed: {exc}") from exc
    return inspector_result(snapshots, continuity, max_delta_px)
