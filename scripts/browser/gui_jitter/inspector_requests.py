"""Request attribution helpers for the Inspector painted-frame probe."""

from __future__ import annotations

import json
import time
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlsplit

from scripts.browser.gui_jitter.shared import MILLISECONDS_PER_SECOND, wait_for_grid
from scripts.smoke_harness import SmokeFailure

TRACKED_REQUEST_PATHS = {"/item", "/item/detail", "/metadata"}
RequestIdentity = tuple[str, str, str]


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
        request_path = parse_qs(parsed.query).get("path", [""])[0]
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


def exercise_remote_inspector_cache_sync(
    owner: Any,
    remote: Any,
    owner_requests: RequestEvidence,
    remote_requests: RequestEvidence,
    *,
    path: str,
    live_notes: str,
    live_tags: str,
    restore_notes: str,
    restore_tags: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    selector = f'[id="cell-{quote(path, safe="")}"]'
    for page in (owner, remote):
        page.reload(wait_until="domcontentloaded")
        wait_for_grid(page, browser_timeout_ms)
        page.locator(selector).click()
        page.wait_for_function(
            """(target) => {
              const panel = document.querySelector('[data-inspector-panel]');
              const image = document.querySelector('.inspector-preview-image');
              return panel?.getAttribute('data-inspector-presented-path') === target
                && image instanceof HTMLImageElement
                && image.complete
                && image.naturalWidth > 0;
            }""",
            arg=path,
            timeout=browser_timeout_ms,
        )
    owner_requests.set_phase("remote_cache_sync")
    remote_requests.set_phase("remote_cache_sync")
    owner.locator('input[aria-label="Tags"]').fill(live_tags)
    owner.locator('textarea[aria-label="Notes"]').fill(live_notes)
    owner.locator('textarea[aria-label="Notes"]').blur()
    wait_for_request_count(
        owner,
        owner_requests,
        "remote_cache_sync",
        method="PATCH",
        pathname="/item",
        expected=2,
        browser_timeout_ms=browser_timeout_ms,
    )
    remote.wait_for_function(
        """({ notes, tags }) => {
          const panel = document.querySelector('[data-inspector-panel]');
          const notesInput = document.querySelector('textarea[aria-label="Notes"]');
          const tagsInput = document.querySelector('input[aria-label="Tags"]');
          return panel?.getAttribute('data-inspector-item-notes') === notes
            && notesInput?.value === notes
            && tagsInput?.value === tags;
        }""",
        arg={"notes": live_notes, "tags": live_tags},
        timeout=browser_timeout_ms,
    )
    owner_summary = summarize_requests(owner_requests, "remote_cache_sync")
    remote_summary = summarize_requests(remote_requests, "remote_cache_sync")
    violations = request_attribution_violations(
        owner_summary["records"],
        page_id="owner",
        phase="remote_cache_sync",
        allowed={("GET", "/item", path), ("PATCH", "/item", path)},
        exact_counts={("PATCH", "/item", path): 2},
        max_counts={("GET", "/item", path): 2},
    )
    violations.extend(request_attribution_violations(
        remote_summary["records"],
        page_id="remote",
        phase="remote_cache_sync",
        allowed=set(),
    ))
    owner_requests.set_phase("remote_cache_sync_cleanup")
    remote_requests.set_phase("remote_cache_sync_cleanup")
    owner.locator('input[aria-label="Tags"]').fill(restore_tags)
    owner.locator('textarea[aria-label="Notes"]').fill(restore_notes)
    owner.locator('textarea[aria-label="Notes"]').blur()
    remote.wait_for_function(
        """({ notes, tags }) => document.querySelector('textarea[aria-label="Notes"]')?.value === notes
          && document.querySelector('input[aria-label="Tags"]')?.value === tags""",
        arg={"notes": restore_notes, "tags": restore_tags},
        timeout=browser_timeout_ms,
    )
    return {
        "owner_requests": owner_summary,
        "remote_requests": remote_summary,
        "item_detail_notes": live_notes,
        "sidecar": {"notes": live_notes, "tags": live_tags},
        "violations": violations,
    }


def exercise_inspector_conflict_regions(
    browser: Any,
    base_url: str,
    *,
    path: str,
    multi_paths: tuple[str, str],
    browser_timeout_ms: float,
    prepare_page: Callable[[Any, str, float], None],
) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.set_default_timeout(browser_timeout_ms)
    current = {
        "v": 1,
        "tags": ["server-tag"],
        "notes": "server notes",
        "star": None,
        "version": 999,
        "updated_at": "",
        "updated_by": "conflict-probe",
    }

    def reject_patch(route: Any) -> None:
        parsed = urlsplit(route.request.url)
        request_path = parse_qs(parsed.query).get("path", [""])[0]
        if route.request.method.upper() == "PATCH" and parsed.path == "/item" and request_path == path:
            route.fulfill(
                status=409,
                content_type="application/json",
                body=json.dumps({"error": "version_conflict", "current": current}),
            )
            return
        route.continue_()

    sidecar_failures: list[str] = []

    def reject_multi_sidecar(route: Any) -> None:
        parsed = urlsplit(route.request.url)
        request_path = parse_qs(parsed.query).get("path", [""])[0]
        if (
            route.request.method.upper() == "GET"
            and parsed.path == "/item"
            and request_path == multi_paths[0]
        ):
            sidecar_failures.append(request_path)
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"detail": "forced multi sidecar failure"}),
            )
            return
        route.continue_()

    def geometry() -> dict[str, Any]:
        return page.evaluate(
            """() => {
              const viewportRect = (element) => {
                const value = element.getBoundingClientRect();
                return { top: value.top, bottom: value.bottom, height: value.height };
              };
              const layoutRect = (element) => ({
                top: element.offsetTop,
                bottom: element.offsetTop + element.offsetHeight,
                height: element.offsetHeight,
              });
              const sections = Object.fromEntries(Array.from(
                document.querySelectorAll('[data-inspector-section-id]')
              ).map((section) => [section.getAttribute('data-inspector-section-id'), layoutRect(section)]));
              const slots = Object.fromEntries(Array.from(
                document.querySelectorAll('[data-inspector-conflict-slot]')
              ).map((slot) => {
                const bounds = slot.getBoundingClientRect();
                const controlsBounded = Array.from(slot.querySelectorAll('button')).every((button) => {
                  const control = button.getBoundingClientRect();
                  return control.top >= bounds.top - 1 && control.bottom <= bounds.bottom + 1;
                });
                return [slot.getAttribute('data-inspector-conflict-slot'), {
                  ...viewportRect(slot),
                  controlsBounded,
                  contentBounded: slot.scrollHeight <= slot.clientHeight + 1,
                }];
              }));
              return { sections, slots };
            }"""
        )

    try:
        prepare_page(page, base_url, browser_timeout_ms)
        page.locator(f'[id="cell-{quote(path, safe="")}"]').click()
        page.wait_for_function(
            """(target) => document.querySelector('[data-inspector-panel]')
              ?.getAttribute('data-inspector-presented-path') === target""",
            arg=path,
            timeout=browser_timeout_ms,
        )
        page.set_viewport_size({"width": 900, "height": 900})
        baseline = geometry()
        page.route("**/item?*", reject_patch)
        page.get_by_role("button", name="1 star", exact=True).click()
        page.get_by_text("Rating conflict.", exact=True).wait_for()
        rating_conflict = geometry()
        page.get_by_role("button", name="Keep theirs", exact=True).click()
        page.locator('textarea[aria-label="Notes"]').fill("local conflicting notes")
        page.locator('textarea[aria-label="Notes"]').blur()
        page.get_by_text("Conflicting edits detected.", exact=True).wait_for()
        notes_conflict = geometry()
        violations: list[str] = []
        for phase, snapshot in (("rating", rating_conflict), ("notes", notes_conflict)):
            if snapshot["sections"] != baseline["sections"]:
                violations.append(f"{phase} conflict shifted Inspector section geometry")
            for name, slot in snapshot["slots"].items():
                if not slot["controlsBounded"] or not slot["contentBounded"]:
                    violations.append(f"{phase} conflict overflowed the {name} slot")
        page.get_by_role("button", name="Keep theirs", exact=True).click()
        page.unroute("**/item?*", reject_patch)
        page.route("**/item?*", reject_multi_sidecar)
        page.set_viewport_size({"width": 1280, "height": 900})
        page.locator(f'[id="cell-{quote(multi_paths[0], safe="")}"]').click()
        deadline = time.monotonic() + (browser_timeout_ms / MILLISECONDS_PER_SECOND)
        while not sidecar_failures and time.monotonic() < deadline:
            page.wait_for_timeout(20)
        page.locator(f'[id="cell-{quote(multi_paths[1], safe="")}"]').click(
            modifiers=["Control"]
        )
        multi_notes = page.locator('textarea[aria-label="Notes for selected items"]')
        multi_notes.wait_for()
        page.wait_for_function(
            """() => {
              const panel = document.querySelector('[data-inspector-panel]');
              const input = document.querySelector('textarea[aria-label="Notes for selected items"]');
              return panel?.getAttribute('data-inspector-sidecar-state') === 'ready'
                && input instanceof HTMLTextAreaElement && !input.disabled;
            }""",
            timeout=browser_timeout_ms,
        )
        if not sidecar_failures:
            violations.append("multi-select did not exercise a failing first-item sidecar request")
        return {
            "width": page.locator("[data-inspector-panel]").bounding_box()["width"],
            "baseline": baseline,
            "rating": rating_conflict,
            "notes": notes_conflict,
            "multi_sidecar": {
                "failed_paths": sidecar_failures,
                "notes_enabled": multi_notes.is_enabled(),
            },
            "violations": violations,
        }
    finally:
        context.close()
