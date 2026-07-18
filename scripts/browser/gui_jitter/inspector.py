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
from scripts.browser.gui_jitter.shared import (
    MILLISECONDS_PER_SECOND,
    ProbeResult,
    require_dict_snapshot,
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
}
TRACKED_REQUEST_PATHS = {"/item", "/item/detail", "/metadata"}
RequestIdentity = tuple[str, str, str]


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


class RequestEvidence:
    def __init__(self, page: Any, page_id: str) -> None:
        self.page_id = page_id
        self.phase = "setup"
        self.records: list[dict[str, str]] = []
        page.on("request", self._record)

    def _record(self, request: Any) -> None:
        parsed = urlsplit(request.url)
        if parsed.path not in TRACKED_REQUEST_PATHS:
            return
        query = parse_qs(parsed.query)
        request_path = query.get("path", [""])[0]
        self.records.append(
            {
                "page_id": self.page_id,
                "phase": self.phase,
                "method": request.method.upper(),
                "pathname": parsed.path,
                "path": request_path,
            }
        )

    def set_phase(self, phase: str) -> None:
        self.phase = phase

    def phase_records(self, phase: str) -> list[dict[str, str]]:
        return [record for record in self.records if record["phase"] == phase]

    def count(self, phase: str, *, method: str, pathname: str, path: str | None = None) -> int:
        return sum(
            1
            for record in self.phase_records(phase)
            if record["method"] == method
            and record["pathname"] == pathname
            and (path is None or record["path"] == path)
        )


def snapshot_quick_view_section(page: Any) -> dict[str, Any]:
    snapshot = page.evaluate(
        """() => {
          const section = document.querySelector('[data-inspector-section-id="quickView"]');
          if (!(section instanceof HTMLElement)) {
            return {
              present: false,
              top: null,
              height: null,
              rowCount: 0,
              placeholderRowCount: 0,
              loading: false,
              promptValue: null,
            };
          }

          const rect = section.getBoundingClientRect();
          const rows = Array.from(section.querySelectorAll('.ui-kv-row'));
          const visibleRows = rows.filter((row) => row.getAttribute('aria-hidden') !== 'true');
          const placeholderRows = rows.filter((row) => row.getAttribute('aria-hidden') === 'true');
          let promptValue = null;

          for (const row of visibleRows) {
            const label = row.querySelector('.ui-kv-label');
            const value = row.querySelector('.ui-kv-value');
            if (!(label instanceof HTMLElement) || !(value instanceof HTMLElement)) continue;
            if ((label.textContent || '').trim() !== 'Prompt') continue;
            promptValue = (value.textContent || '').trim();
            break;
          }

          return {
            present: true,
            top: rect.top,
            height: rect.height,
            rowCount: visibleRows.length,
            placeholderRowCount: placeholderRows.length,
            loading: (section.textContent || '').includes('Loading metadata…'),
            promptValue,
          };
        }"""
    )
    return require_dict_snapshot(snapshot, "Failed to capture Quick View snapshot.")


def quick_view_delta(lhs: dict[str, Any], rhs: dict[str, Any]) -> float:
    if not bool(lhs.get("present")) or not bool(rhs.get("present")):
        return 0.0
    try:
        top_delta = abs(float(lhs.get("top")) - float(rhs.get("top")))
        height_delta = abs(float(lhs.get("height")) - float(rhs.get("height")))
    except (TypeError, ValueError):
        return 0.0
    return max(top_delta, height_delta)


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
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)
    set_local_storage(page, inspector_storage_payload())
    page.reload(wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)


def set_dirty_drafts(page: Any, notes: str, tags: str) -> None:
    page.evaluate(
        """({ notes, tags }) => {
          const update = (selector, value, prototype) => {
            const element = document.querySelector(selector);
            if (!(element instanceof HTMLElement)) throw new Error(`Missing ${selector}`);
            const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
            if (!setter) throw new Error(`Missing value setter for ${selector}`);
            setter.call(element, value);
            element.dispatchEvent(new Event('input', { bubbles: true }));
          };
          update('textarea[aria-label="Notes"]', notes, HTMLTextAreaElement.prototype);
          update('input[aria-label="Tags"]', tags, HTMLInputElement.prototype);
        }""",
        {"notes": notes, "tags": tags},
    )


def input_values(page: Any) -> dict[str, str]:
    values = page.evaluate(
        """() => ({
          notes: document.querySelector('textarea[aria-label="Notes"]')?.value ?? '',
          tags: document.querySelector('input[aria-label="Tags"]')?.value ?? '',
        })"""
    )
    if not isinstance(values, dict):
        raise SmokeFailure("Failed to read inspector notes/tags drafts.")
    return {"notes": str(values.get("notes") or ""), "tags": str(values.get("tags") or "")}


def wait_for_request_count(
    page: Any,
    evidence: RequestEvidence,
    phase: str,
    *,
    method: str,
    pathname: str,
    expected: int,
    browser_timeout_ms: float,
) -> None:
    deadline = time.monotonic() + (browser_timeout_ms / MILLISECONDS_PER_SECOND)
    while time.monotonic() < deadline:
        if evidence.count(phase, method=method, pathname=pathname) >= expected:
            return
        page.wait_for_timeout(20)
    raise SmokeFailure(
        f"Timed out waiting for {expected} {method} {pathname} requests in {phase}; "
        f"observed {evidence.count(phase, method=method, pathname=pathname)}."
    )


def summarize_requests(evidence: RequestEvidence, phase: str) -> dict[str, Any]:
    records = evidence.phase_records(phase)
    counts: dict[str, int] = {}
    by_path: dict[str, dict[str, int]] = {}
    for record in records:
        key = f"{record['method']} {record['pathname']}"
        counts[key] = counts.get(key, 0) + 1
        path_counts = by_path.setdefault(record["path"], {})
        path_counts[key] = path_counts.get(key, 0) + 1
    return {
        "page_id": evidence.page_id,
        "phase": phase,
        "counts": counts,
        "by_path": by_path,
        "records": records,
    }


def request_attribution_violations(
    records: list[dict[str, str]],
    *,
    page_id: str,
    phase: str,
    allowed: set[RequestIdentity],
    exact_counts: dict[RequestIdentity, int] | None = None,
    max_counts: dict[RequestIdentity, int] | None = None,
) -> list[str]:
    """Fail closed when tracked requests cannot be assigned to the intended action."""

    violations: list[str] = []
    observed: dict[RequestIdentity, int] = {}
    for index, record in enumerate(records):
        if record.get("page_id") != page_id or record.get("phase") != phase:
            violations.append(
                f"request {index} has attribution {(record.get('page_id'), record.get('phase'))!r}; "
                f"expected {(page_id, phase)!r}"
            )
            continue
        identity = (
            str(record.get("method") or ""),
            str(record.get("pathname") or ""),
            str(record.get("path") or ""),
        )
        observed[identity] = observed.get(identity, 0) + 1
        if identity not in allowed:
            violations.append(f"request {index} has unexpected identity {identity!r}")

    for identity, expected in (exact_counts or {}).items():
        actual = observed.get(identity, 0)
        if actual != expected:
            violations.append(
                f"request identity {identity!r} occurred {actual} times instead of {expected}"
            )
    for identity, maximum in (max_counts or {}).items():
        actual = observed.get(identity, 0)
        if actual > maximum:
            violations.append(
                f"request identity {identity!r} occurred {actual} times; maximum is {maximum}"
            )
    return violations


def summarize_inspector_trace(trace: dict[str, Any], max_delta_px: float) -> dict[str, Any]:
    return summarize_painted_frame_trace(
        trace,
        required_surfaces=REQUIRED_INSPECTOR_SURFACES,
        sentinels_by_path=INSPECTOR_SENTINELS,
        max_delta_px=max_delta_px,
    )


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
        '/quick_03_meta.png': 260,
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
        current = input_values(page)
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
) -> None:
    page.evaluate(
        """({ actionId, expectedPath, expectedStar, enforceStarInvariant, requiredTexts, selector }) => {
          const state = window.__lensletPaintedFrameTrace;
          if (!state || !state.running) throw new Error('painted-frame trace is not running');
          const target = document.querySelector(selector);
          if (!(target instanceof HTMLElement)) throw new Error(`Missing click target ${selector}`);
          target.addEventListener('click', () => {
            const marker = {
              actionId,
              expectedPath,
              expectedStar,
              enforceStarInvariant,
              requiredTexts,
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
            "selector": selector,
        },
    )
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
        set_dirty_drafts(owner, owner_notes, owner_tags)
        if input_values(owner) != {"notes": owner_notes, "tags": owner_tags}:
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
                "dirty_drafts_preserved": input_values(owner)
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
        set_dirty_drafts(remote, remote_notes, remote_tags)
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
                "dirty_drafts_preserved": input_values(remote)
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
        request_windows: list[dict[str, Any]] = []
        for index in range(20):
            path = QUICK_ZERO_PATH if index % 2 == 0 else QUICK_ONE_PATH
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
        summary = summarize_inspector_trace(trace, max_delta_px)
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
        summary = summarize_inspector_trace(trace, max_delta_px)
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
    violations = [
        f"{phase}: {violation}"
        for phase, summary in (
            ("local_rating", local_rating),
            ("remote_echo", remote_echo),
            ("selection", selection),
            ("delayed_rating_switch", delayed),
        )
        for violation in trace_violations(summary)
    ]
    return {
        "local_rating": local_rating,
        "remote_echo": remote_echo,
        "selection": selection,
        "delayed_rating_switch": delayed,
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

    select_grid_path(page, QUICK_THREE_PATH, browser_timeout_ms)
    pending_quick = snapshot_quick_view_section(page)
    wait_for_prompt(
        page,
        "gamma prompt",
        browser_timeout_ms,
        "Timed out waiting for quick-view quick->quick hydration.",
    )
    quick_three_loaded = snapshot_quick_view_section(page)
    page.wait_for_timeout(120)

    select_grid_path(page, PLAIN_PATH, browser_timeout_ms)
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
            browser.close()
    except playwright_timeout_error as exc:
        raise SmokeFailure(f"playwright timeout: {exc}") from exc
    except playwright_error as exc:
        raise SmokeFailure(f"playwright probe failed: {exc}") from exc
    return inspector_result(snapshots, continuity, max_delta_px)
