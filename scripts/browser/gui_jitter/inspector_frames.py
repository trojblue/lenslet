"""Inspector descendant and decoded-pixel continuity checks."""

from __future__ import annotations

import json
import time
from typing import Any

from scripts.browser.gui_jitter.painted_frames import (
    mark_painted_frame_action,
    start_painted_frame_trace,
    stop_painted_frame_trace,
)
from scripts.browser.gui_jitter.shared import require_dict_snapshot

_COMMON_ACTIONS = (
    "Reorder Metadata",
    "Metadata",
    "Reorder Basics",
    "Basics",
    "Find similar",
    "1 star",
    "2 stars",
    "3 stars",
    "4 stars",
    "5 stars",
    "Reorder Notes & Tags",
    "Notes & Tags",
)
_METADATA_ACTIONS = (
    "Reorder Quick View",
    "Quick View",
    "Copy Prompt",
    "Copy Model",
    "Copy LoRA",
    "Toggle custom JSON paths",
)


def _expected_content(
    *,
    path: str,
    prompt: str,
    model: str,
    lora: str,
    score: str,
    rank: str,
    notes: str,
    tag: str,
) -> dict[str, Any]:
    return {
        "rows": {
            "quick:default:prompt": f"Prompt{prompt}",
            "quick:default:model": f"Model{model}",
            "quick:default:lora": f"LoRA{lora}",
            "basic:dimensions": "Dimensions48×32",
            "basic:type": "Typeimage/png",
            "basic:source": path.removeprefix("/"),
            "metric:probe_rank": f"probe_rank{rank}",
            "metric:probe_score": f"probe_score{score}",
        },
        "inputs": {"Notes": notes, "Tags": tag},
        "actions": _COMMON_ACTIONS,
        "metadata_actions": _METADATA_ACTIONS,
    }


INSPECTOR_EXPECTED_CONTENT = {
    "/quick_00_meta.png": _expected_content(
        path="/quick_00_meta.png",
        prompt="alpha prompt",
        model="alpha-model",
        lora="alpha-lora.safetensors (0.8)",
        score="0.000",
        rank="0.000",
        notes="notes-00_meta",
        tag="tag-00_meta",
    ),
    "/quick_01_meta.png": _expected_content(
        path="/quick_01_meta.png",
        prompt="beta prompt",
        model="beta-model",
        lora="beta-lora.safetensors (1.2)",
        score="0.143",
        rank="1.000",
        notes="notes-01_meta",
        tag="tag-01_meta",
    ),
    "/quick_03_meta.png": _expected_content(
        path="/quick_03_meta.png",
        prompt="gamma prompt",
        model="gamma-model",
        lora="gamma-lora.safetensors (0.6)",
        score="0.429",
        rank="3.000",
        notes="notes-03_meta",
        tag="tag-03_meta",
    ),
}


def set_dirty_inspector_drafts(page: Any, notes: str, tags: str) -> None:
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


def inspector_input_values(page: Any) -> dict[str, str]:
    values = page.evaluate(
        """() => ({
          notes: document.querySelector('textarea[aria-label="Notes"]')?.value ?? '',
          tags: document.querySelector('input[aria-label="Tags"]')?.value ?? '',
        })"""
    )
    if not isinstance(values, dict):
        return {"notes": "", "tags": ""}
    return {"notes": str(values.get("notes") or ""), "tags": str(values.get("tags") or "")}


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


def inspector_status_geometry(page: Any) -> dict[str, Any]:
    snapshot = page.evaluate(
        """() => {
          const panel = document.querySelector('[data-inspector-panel]');
          const filename = document.querySelector('.inspector-value-clamp[title]');
          if (!(panel instanceof HTMLElement) || !(filename instanceof HTMLElement)) return null;
          const panelRect = panel.getBoundingClientRect();
          const statuses = Array.from(panel.querySelectorAll('[role="status"]')).map((node) => {
            const rect = node.getBoundingClientRect();
            const style = window.getComputedStyle(node);
            const clipped = style.clip !== 'auto' || style.clipPath !== 'none';
            const visible = node.getClientRects().length > 0 && !clipped;
            return {
              bounded: !visible || (rect.left >= panelRect.left - 1 && rect.right <= panelRect.right + 1),
              text: (node.textContent || '').trim(),
              visible,
            };
          });
          return {
            width: panelRect.width,
            filenameClamped: filename.scrollHeight <= filename.clientHeight + 1,
            boundedStatuses: statuses.every((status) => status.bounded),
            statuses,
          };
        }"""
    )
    return require_dict_snapshot(snapshot, "Failed to capture Inspector status geometry.")


def summarize_first_visible_inspector_frame(
    trace: dict[str, Any],
    *,
    expected_section_order: list[str],
    expected_quick_view_paths: list[str],
    expected_inputs: dict[str, str],
    expected_token: str | None = None,
) -> dict[str, Any]:
    frames = trace.get("frames")
    if not isinstance(frames, list):
        return {"violations": ["lifecycle trace has no frames"], "frame": None}
    panel: dict[str, Any] | None = None
    for frame in frames:
        surfaces = frame.get("surfaces") if isinstance(frame, dict) else None
        candidate = _surface(surfaces, "panel")
        if candidate.get("visible") is True:
            panel = candidate
            break
    if panel is None:
        return {"violations": ["lifecycle trace has no visible Inspector frame"], "frame": None}

    violations: list[str] = []
    if expected_token is not None and panel.get("token") != expected_token:
        violations.append("Inspector root token changed before the first visible frame")
    if _data_attribute(panel, "data-inspector-section-order") != json.dumps(
        expected_section_order,
        separators=(",", ":"),
    ):
        violations.append("first visible frame did not use persisted section order")
    expected_paths = json.dumps(expected_quick_view_paths, separators=(",", ":"))
    if _data_attribute(panel, "data-inspector-quick-view-paths") != expected_paths:
        violations.append("first visible frame did not use persisted Quick View paths")
    if _data_attribute(panel, "data-inspector-export-reverse") != "true":
        violations.append("first visible frame did not restore reverse export order")
    if _data_attribute(panel, "data-inspector-export-high-quality") != "true":
        violations.append("first visible frame did not restore high-quality GIF state")

    sections = {
        section.get("id"): section
        for section in panel.get("inspectorSections") or []
        if isinstance(section, dict)
    }
    if sections and sections.get("basics", {}).get("open") != "false":
        violations.append("Basics disclosure was not closed on the first visible frame")
    inputs = {
        input_state.get("label"): str(input_state.get("value") or "")
        for input_state in panel.get("inspectorInputs") or []
        if isinstance(input_state, dict)
    }
    for label, expected_value in expected_inputs.items():
        if inputs.get(label) != expected_value:
            violations.append(f"first visible frame had {label!r} value {inputs.get(label)!r}")
    return {
        "violations": violations,
        "frame": {
            "token": panel.get("token"),
            "inputs": inputs,
            "sections": sections,
        },
    }


def _surface(surfaces: Any, name: str) -> dict[str, Any]:
    if not isinstance(surfaces, dict):
        return {}
    value = surfaces.get(name)
    return value if isinstance(value, dict) else {}


def _data_attribute(surface: dict[str, Any], name: str) -> str:
    attrs = surface.get("attrs")
    data = attrs.get("data") if isinstance(attrs, dict) else None
    value = data.get(name) if isinstance(data, dict) else None
    return value if isinstance(value, str) else ""


def _rgb_matches(actual: Any, expected: tuple[int, int, int], tolerance: int = 4) -> bool:
    if not isinstance(actual, list) or len(actual) != 3:
        return False
    try:
        return all(abs(int(channel) - target) <= tolerance for channel, target in zip(actual, expected))
    except (TypeError, ValueError):
        return False


def summarize_inspector_hard_reset_trace(
    trace: dict[str, Any],
    *,
    previous_reset_key: str,
    expected_path: str,
    expected_rgb: tuple[int, int, int],
) -> dict[str, Any]:
    frames = trace.get("frames")
    if not isinstance(frames, list):
        return {"violations": ["Inspector hard-reset trace has no frames"]}
    violations: list[str] = []
    neutral_frames = 0
    target_frames = 0
    staged_image_tokens: set[str] = set()
    for staged in trace.get("staged_preview_tokens", []):
        if (
            isinstance(staged, dict)
            and staged.get("path") == expected_path
            and isinstance(staged.get("token"), str)
        ):
            staged_image_tokens.add(staged["token"])
    saw_new_reset = False
    for frame_index, frame in enumerate(frames):
        marker = frame.get("marker") if isinstance(frame, dict) else None
        if not isinstance(marker, dict):
            continue
        surfaces = frame.get("surfaces")
        panel = _surface(surfaces, "panel")
        requested_reset = _data_attribute(panel, "data-inspector-requested-reset-key")
        if not requested_reset or requested_reset == previous_reset_key:
            continue
        saw_new_reset = True
        preview = _surface(surfaces, "preview_card")
        candidate_image = preview.get("candidateImage")
        if (
            isinstance(candidate_image, dict)
            and candidate_image.get("path") == expected_path
            and isinstance(candidate_image.get("token"), str)
        ):
            staged_image_tokens.add(candidate_image["token"])
        presented_reset = _data_attribute(panel, "data-inspector-presented-reset-key")
        presented_path = _data_attribute(panel, "data-inspector-presented-path")
        if not presented_reset:
            neutral_frames += 1
            if presented_path:
                violations.append(f"frame {frame_index}: hard-reset neutral shell retained a path")
            continue
        target_frames += 1
        if presented_reset != requested_reset:
            violations.append(f"frame {frame_index}: hard reset mixed requested/presented scopes")
        if presented_path != expected_path:
            violations.append(f"frame {frame_index}: hard reset presented the wrong path")
        image = preview.get("image")
        if not isinstance(image, dict) or not (
            image.get("complete") is True
            and int(image.get("naturalWidth") or 0) > 0
            and int(image.get("naturalHeight") or 0) > 0
            and _rgb_matches(image.get("rgb"), expected_rgb)
        ):
            violations.append(f"frame {frame_index}: hard-reset target preview was not decoded")
        elif image.get("token") not in staged_image_tokens:
            violations.append(
                f"frame {frame_index}: hard-reset preview did not promote its staged image node"
            )
    if not saw_new_reset:
        violations.append("Inspector hard-reset key did not change")
    if target_frames == 0:
        violations.append("Inspector hard reset never painted the target scope")
    if not staged_image_tokens:
        violations.append("Inspector hard reset never captured a staged preview image node")
    return {
        "neutral_frames": neutral_frames,
        "target_frames": target_frames,
        "staged_image_tokens": sorted(staged_image_tokens),
        "violations": violations,
    }


def exercise_inspector_hard_reset(
    page: Any,
    *,
    trace_selectors: dict[str, str],
    target_path: str,
    target_rgb: tuple[int, int, int],
    target_selector: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    previous_reset_key = page.locator("[data-inspector-panel]").get_attribute(
        "data-inspector-requested-reset-key"
    )
    start_painted_frame_trace(
        page,
        page_id="lifecycle-hard-reset",
        phase="lifecycle-hard-reset",
        selectors=trace_selectors,
    )
    mark_painted_frame_action(
        page,
        action_id="lifecycle-hard-reset-target",
        expected_path=target_path,
    )
    def delay_thumbnail(route: Any) -> None:
        time.sleep(0.15)
        route.continue_()

    page.route("**/thumb?*", delay_thumbnail)
    page.locator('button[aria-label^="Settings ("]').click()
    page.get_by_label("Image column").click()
    page.get_by_role("option", name="source_alt", exact=True).click()
    page.wait_for_function(
        """(previous) => document.querySelector('[data-inspector-panel]')
          ?.getAttribute('data-inspector-requested-reset-key') !== previous""",
        arg=previous_reset_key,
        timeout=max(browser_timeout_ms, 12_000),
    )
    page.locator(target_selector).click()
    page.wait_for_function(
        """(target) => {
          const panel = document.querySelector('[data-inspector-panel]');
          const image = document.querySelector('.inspector-preview-image');
          return panel?.getAttribute('data-inspector-presented-path') === target
            && image instanceof HTMLImageElement
            && image.complete
            && image.naturalWidth > 0;
        }""",
        arg=target_path,
        timeout=max(browser_timeout_ms, 12_000),
    )
    page.wait_for_timeout(34)
    page.unroute("**/thumb?*", delay_thumbnail)
    summary = summarize_inspector_hard_reset_trace(
        stop_painted_frame_trace(page),
        previous_reset_key=previous_reset_key or "",
        expected_path=target_path,
        expected_rgb=target_rgb,
    )
    if not previous_reset_key:
        summary["violations"].append("Inspector lifecycle exposed no hard-reset identity")
    return summary
def summarize_inspector_identity_trace(
    trace: dict[str, Any],
    *,
    sentinels_by_path: dict[str, tuple[str, ...]],
    rgb_by_path: dict[str, tuple[int, int, int]],
    expected_content_by_path: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    frames = trace.get("frames")
    if not isinstance(frames, list):
        return {"violations": ["Inspector identity trace has no frames"]}
    violations: list[str] = []
    failing_frames: list[dict[str, Any]] = []
    coherent_a_frames = 0
    coherent_b_frames = 0
    decoded_pixel_frames = 0
    placeholder_frames = 0

    for frame_index, frame in enumerate(frames):
        marker = frame.get("marker") if isinstance(frame, dict) else None
        if not isinstance(marker, dict):
            continue
        surfaces = frame.get("surfaces")
        panel = _surface(surfaces, "panel")
        preview = _surface(surfaces, "preview_card")
        filename = _surface(surfaces, "filename")
        expected_path = marker.get("expectedPath")
        if not isinstance(expected_path, str):
            continue
        previous_path = marker.get("previousPresentedPath")
        if not isinstance(previous_path, str) or not previous_path:
            previous_path = expected_path
        requested_path = _data_attribute(panel, "data-inspector-requested-path")
        presented_path = _data_attribute(panel, "data-inspector-presented-path")
        frame_violations: list[str] = []

        if requested_path != expected_path:
            frame_violations.append(
                f"requested path {requested_path!r} did not match marker {expected_path!r}"
            )
        if presented_path not in {previous_path, expected_path}:
            frame_violations.append(
                f"presented path {presented_path!r} was neither retained {previous_path!r} "
                f"nor target {expected_path!r}"
            )
        elif presented_path == previous_path and previous_path != expected_path:
            coherent_a_frames += 1
        elif presented_path == expected_path:
            coherent_b_frames += 1

        panel_text = str(panel.get("text") or "")
        filename_text = str(filename.get("text") or "")
        if presented_path:
            expected_filename = presented_path.rsplit("/", 1)[-1]
            if expected_filename not in filename_text:
                frame_violations.append("filename did not match the presented path")
            stale_values = (
                sentinel
                for sentinel_path, sentinels in sentinels_by_path.items()
                if sentinel_path != presented_path
                for sentinel in sentinels
            )
            if any(value and value in panel_text for value in stale_values):
                frame_violations.append("panel mixed content from another Inspector identity")

        metadata_error = _data_attribute(panel, "data-inspector-metadata-state") == "error"
        item_error = _data_attribute(panel, "data-inspector-item-state") == "error"
        sidecar_error = _data_attribute(panel, "data-inspector-sidecar-state") == "error"
        expected_content = (expected_content_by_path or {}).get(presented_path)
        if expected_content_by_path is not None and expected_content is None:
            frame_violations.append("presented path had no expected-content specification")

        rows = panel.get("inspectorRows")
        if isinstance(rows, list) and any(
            isinstance(row, dict) and row.get("placeholder") is True for row in rows
        ):
            placeholder_frames += 1
            frame_violations.append("placeholder row replaced a settled Inspector row")
        rows_by_id = {
            row.get("id"): str(row.get("text") or "")
            for row in rows or []
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        }
        if expected_content:
            for row_id, expected_value in expected_content.get("rows", {}).items():
                if metadata_error and row_id.startswith("quick:"):
                    terminal_value = rows_by_id.get(row_id)
                    if terminal_value is None:
                        frame_violations.append(f"terminal metadata row {row_id!r} was missing")
                    elif "—" not in terminal_value:
                        frame_violations.append(
                            f"terminal metadata row {row_id!r} did not expose an unavailable value"
                        )
                    continue
                if item_error and (row_id.startswith("basic:") or row_id.startswith("metric:")):
                    continue
                actual_value = rows_by_id.get(row_id)
                if actual_value is None:
                    frame_violations.append(f"required row {row_id!r} was missing")
                elif str(expected_value) not in actual_value:
                    frame_violations.append(
                        f"row {row_id!r} did not contain {expected_value!r}"
                    )
        inputs = panel.get("inspectorInputs")
        inputs_by_label = {
            input_state.get("label"): input_state
            for input_state in inputs or []
            if isinstance(input_state, dict) and isinstance(input_state.get("label"), str)
        }
        expected_inputs = expected_content.get("inputs", {}) if expected_content else {}
        for label in ("Notes", "Tags"):
            input_state = inputs_by_label.get(label)
            if input_state is None:
                frame_violations.append(f"required {label} control was missing")
                continue
            if sidecar_error:
                if not (
                    input_state.get("disabled") is True
                    and input_state.get("terminalError") is True
                ):
                    frame_violations.append(f"{label} did not expose its terminal error state")
                continue
            expected_value = expected_inputs.get(label)
            actual_value = str(input_state.get("value") or "")
            if expected_value is not None and actual_value != expected_value:
                frame_violations.append(
                    f"{label} value {actual_value!r} did not match {expected_value!r}"
                )
            elif expected_value is None and not actual_value.strip():
                frame_violations.append(f"{label} painted blank")

        preview_state = _data_attribute(preview, "data-preview-state")
        image = preview.get("image")
        if preview_state == "ready":
            if not isinstance(image, dict):
                frame_violations.append("ready preview had no image element")
            else:
                if image.get("path") != presented_path:
                    frame_violations.append("preview path did not match presented path")
                if (
                    image.get("complete") is not True
                    or int(image.get("naturalWidth") or 0) <= 0
                    or int(image.get("naturalHeight") or 0) <= 0
                    or str(image.get("opacity")) != "1"
                ):
                    frame_violations.append("preview image was visible before decoded readiness")
                expected_rgb = rgb_by_path.get(presented_path)
                if expected_rgb and not _rgb_matches(image.get("rgb"), expected_rgb):
                    frame_violations.append("preview pixels did not match presented path")
                else:
                    decoded_pixel_frames += 1
        elif preview_state != "error":
            frame_violations.append(f"settled presentation exposed preview state {preview_state!r}")

        actions = panel.get("inspectorActions")
        visible_actions = {
            action.get("label")
            for action in actions or []
            if isinstance(action, dict) and action.get("visible") is True
        }
        if expected_content:
            required_actions = set(expected_content.get("actions", ()))
            required_actions.update(expected_content.get("metadata_actions", ()))
            for missing_action in sorted(required_actions - visible_actions):
                frame_violations.append(f"required action {missing_action!r} disappeared")
        copied_feedback_owner = marker.get("copiedFeedbackOwnerPath")
        if isinstance(copied_feedback_owner, str) and presented_path != copied_feedback_owner:
            if any(
                isinstance(action, dict)
                and str(action.get("title") or "").lower().endswith(" copied")
                for action in actions or []
            ):
                frame_violations.append("copied feedback leaked into another Inspector identity")
        visible_star_actions = {
            action.get("label")
            for action in actions or []
            if isinstance(action, dict)
            and action.get("visible") is True
            and action.get("label") in {"1 star", "2 stars", "3 stars", "4 stars", "5 stars"}
        }
        if len(visible_star_actions) != 5:
            frame_violations.append("one or more star actions disappeared")

        if frame_violations:
            violations.extend(f"frame {frame_index}: {value}" for value in frame_violations)
            if len(failing_frames) < 20:
                failing_frames.append(
                    {"frame_index": frame_index, "violations": frame_violations, "frame": frame}
                )

    return {
        "coherent_retained_frames": coherent_a_frames,
        "coherent_target_frames": coherent_b_frames,
        "decoded_pixel_frames": decoded_pixel_frames,
        "placeholder_frames": placeholder_frames,
        "violations": violations,
        "failing_frames": failing_frames,
    }
