"""Reusable painted-frame tracing for browser transition checks."""

from __future__ import annotations

from typing import Any

from scripts.smoke_harness import SmokeFailure


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (percentile_value / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * fraction)


def start_painted_frame_trace(
    page: Any,
    *,
    page_id: str,
    phase: str,
    selectors: dict[str, str],
    max_frames: int = 2_400,
) -> None:
    page.evaluate(
        """(config) => {
          const existing = window.__lensletPaintedFrameTrace;
          if (existing) {
            cancelAnimationFrame(existing.rafId);
            existing.armedObserver?.disconnect();
            existing.stagedPreviewObserver?.disconnect();
            if (existing.armedClickListener) {
              document.removeEventListener('click', existing.armedClickListener, true);
            }
          }
          const tokens = new WeakMap();
          let nextToken = 1;
          const state = {
            running: true,
            pageId: config.pageId,
            phase: config.phase,
            selectors: config.selectors,
            maxFrames: config.maxFrames,
            frames: [],
            markers: [],
            marker: null,
            armedClickListener: null,
            armedObserver: null,
            stagedPreviewObserver: null,
            stagedPreviewTokens: [],
            rafId: 0,
          };
          const tokenFor = (element) => {
            let token = tokens.get(element);
            if (!token) {
              token = `node-${nextToken}`;
              nextToken += 1;
              tokens.set(element, token);
            }
            return token;
          };
          const recordStagedPreviews = (root) => {
            if (!(root instanceof Element)) return;
            const candidates = root.matches('[data-preview-candidate-path]')
              ? [root]
              : Array.from(root.querySelectorAll('[data-preview-candidate-path]'));
            for (const candidate of candidates) {
              state.stagedPreviewTokens.push({
                token: tokenFor(candidate),
                path: candidate.getAttribute('data-preview-candidate-path'),
              });
            }
          };
          state.stagedPreviewObserver = new MutationObserver((records) => {
            for (const record of records) {
              for (const node of record.addedNodes) recordStagedPreviews(node);
            }
          });
          state.stagedPreviewObserver.observe(document.documentElement, { childList: true, subtree: true });
          const capture = () => {
            if (!state.running) return;
            const surfaces = {};
            for (const [name, selector] of Object.entries(state.selectors)) {
              const element = document.querySelector(selector);
              if (!(element instanceof HTMLElement)) {
                surfaces[name] = null;
                continue;
              }
              const rect = element.getBoundingClientRect();
              const style = window.getComputedStyle(element);
              const visible = element.getClientRects().length > 0
                && rect.width > 0
                && rect.height > 0
                && style.display !== 'none'
                && style.visibility !== 'hidden'
                && style.opacity !== '0';
              const value = element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement
                ? element.value
                : null;
              const dataAttributes = {};
              for (const attributeName of element.getAttributeNames()) {
                if (!attributeName.startsWith('data-')) continue;
                dataAttributes[attributeName] = element.getAttribute(attributeName);
              }
              const facetCards = Array.from(
                element.querySelectorAll('[data-virtual-field-card]')
              ).map((virtualCard) => {
                const card = virtualCard.querySelector(
                  '[data-metric-card-host], [data-categorical-card]'
                );
                const owner = card?.closest('[data-facet-presented-field]');
                if (!(card instanceof HTMLElement) || !(owner instanceof HTMLElement)) return null;
                return {
                  key: virtualCard.getAttribute('data-field-key'),
                  requested: owner.getAttribute('data-facet-requested-field'),
                  presented: owner.getAttribute('data-facet-presented-field'),
                  state: card.getAttribute('data-facet-state'),
                  text: (card.textContent || '').replace(/\\s+/g, ' ').trim(),
                  ariaBusy: owner.getAttribute('aria-busy'),
                  ariaDisabled: owner.getAttribute('aria-disabled'),
                  inert: owner.hasAttribute('inert'),
                };
              }).filter(Boolean);
              const inspectorRows = element.hasAttribute('data-inspector-panel')
                ? Array.from(element.querySelectorAll('[data-inspector-row-id]')).map((row) => ({
                  id: row.getAttribute('data-inspector-row-id'),
                  text: (row.textContent || '').replace(/\\s+/g, ' ').trim(),
                  placeholder: row.getAttribute('aria-hidden') === 'true',
                }))
                : [];
              const inspectorInputs = element.hasAttribute('data-inspector-panel')
                ? Array.from(element.querySelectorAll('input, textarea')).map((input) => ({
                  label: input.getAttribute('aria-label'),
                  value: input.value,
                  disabled: input.disabled,
                  terminalError: Boolean(input.closest('[data-inspector-terminal-error="true"]')),
                }))
                : [];
              const inspectorSections = element.hasAttribute('data-inspector-panel')
                ? Array.from(element.querySelectorAll('[data-inspector-section-id]')).map((section) => ({
                  id: section.getAttribute('data-inspector-section-id'),
                  open: section.querySelector('button[aria-expanded]')?.getAttribute('aria-expanded'),
                }))
                : [];
              const inspectorActions = element.hasAttribute('data-inspector-panel')
                ? Array.from(element.querySelectorAll('button')).map((button) => {
                  const buttonRect = button.getBoundingClientRect();
                  const buttonStyle = window.getComputedStyle(button);
                  return {
                    label: button.getAttribute('aria-label') || (button.textContent || '').replace(/\\s+/g, ' ').trim(),
                    title: button.getAttribute('title'),
                    ariaExpanded: button.getAttribute('aria-expanded'),
                    visible: button.getClientRects().length > 0
                      && buttonRect.width > 0
                      && buttonRect.height > 0
                      && buttonStyle.visibility !== 'hidden'
                      && buttonStyle.display !== 'none',
                    disabled: button.disabled,
                  };
                })
                : [];
              const image = element.matches('.inspector-preview-card')
                ? element.querySelector('.inspector-preview-image')
                : null;
              let imageState = null;
              if (image instanceof HTMLImageElement) {
                let rgb = null;
                if (image.complete && image.naturalWidth > 0 && image.naturalHeight > 0) {
                  try {
                    const canvas = document.createElement('canvas');
                    canvas.width = 1;
                    canvas.height = 1;
                    const context = canvas.getContext('2d', { willReadFrequently: true });
                    context?.drawImage(image, 0, 0, 1, 1);
                    const pixel = context?.getImageData(0, 0, 1, 1).data;
                    if (pixel) rgb = [pixel[0], pixel[1], pixel[2]];
                  } catch {
                    rgb = null;
                  }
                }
                imageState = {
                  token: tokenFor(image),
                  path: image.getAttribute('data-preview-path'),
                  src: image.getAttribute('src'),
                  currentSrc: image.currentSrc,
                  complete: image.complete,
                  naturalWidth: image.naturalWidth,
                  naturalHeight: image.naturalHeight,
                  opacity: window.getComputedStyle(image).opacity,
                  rgb,
                };
              }
              const candidateImage = element.matches('.inspector-preview-card')
                ? element.querySelector('[data-preview-candidate-path]')
                : null;
              const candidateImageState = candidateImage instanceof HTMLImageElement
                ? {
                  token: tokenFor(candidateImage),
                  path: candidateImage.getAttribute('data-preview-candidate-path'),
                  src: candidateImage.getAttribute('src'),
                  currentSrc: candidateImage.currentSrc,
                  complete: candidateImage.complete,
                  naturalWidth: candidateImage.naturalWidth,
                  naturalHeight: candidateImage.naturalHeight,
                }
                : null;
              surfaces[name] = {
                token: tokenFor(element),
                tag: element.tagName.toLowerCase(),
                rect: {
                  top: rect.top,
                  left: rect.left,
                  width: rect.width,
                  height: rect.height,
                },
                text: (element.textContent || '').replace(/\\s+/g, ' ').trim(),
                value,
                visible,
                scrollTop: element.scrollTop,
                scrollHeight: element.scrollHeight,
                clientHeight: element.clientHeight,
                facetCards,
                inspectorRows,
                inspectorInputs,
                inspectorSections,
                inspectorActions,
                image: imageState,
                candidateImage: candidateImageState,
                attrs: {
                  ariaPressed: element.getAttribute('aria-pressed'),
                  ariaBusy: element.getAttribute('aria-busy'),
                  ariaDisabled: element.getAttribute('aria-disabled'),
                  ariaHidden: element.getAttribute('aria-hidden'),
                  role: element.getAttribute('role'),
                  inert: element.hasAttribute('inert'),
                  disabled: 'disabled' in element ? Boolean(element.disabled) : false,
                  pointerEvents: style.pointerEvents,
                  data: dataAttributes,
                },
              };
            }
            state.frames.push({
              timestamp: performance.now(),
              marker: state.marker ? { ...state.marker } : null,
              surfaces,
            });
            if (state.frames.length > state.maxFrames) state.frames.shift();
            state.rafId = requestAnimationFrame(capture);
          };
          window.__lensletPaintedFrameTrace = state;
          capture();
        }""",
        {
            "pageId": page_id,
            "phase": phase,
            "selectors": selectors,
            "maxFrames": max_frames,
        },
    )


def mark_painted_frame_action(
    page: Any,
    *,
    action_id: str,
    expected_path: str,
    expected_star: int | None = None,
    enforce_star_invariant: bool = False,
    required_texts: tuple[str, ...] = (),
) -> None:
    page.evaluate(
        """(marker) => {
          const state = window.__lensletPaintedFrameTrace;
          if (!state || !state.running) throw new Error('painted-frame trace is not running');
          const next = { ...marker, startedAt: performance.now() };
          state.marker = next;
          state.markers.push(next);
        }""",
        {
            "actionId": action_id,
            "expectedPath": expected_path,
            "expectedStar": expected_star,
            "enforceStarInvariant": enforce_star_invariant,
            "requiredTexts": list(required_texts),
        },
    )


def arm_painted_frame_click_action(
    page: Any,
    *,
    action_id: str,
    expected_path: str,
) -> None:
    """Begin a marker in the click event turn so no pre-action frame is attributed to it."""
    page.evaluate(
        """(marker) => {
          const state = window.__lensletPaintedFrameTrace;
          if (!state || !state.running) throw new Error('painted-frame trace is not running');
          if (state.armedClickListener) {
            document.removeEventListener('click', state.armedClickListener, true);
          }
          const listener = () => {
            const next = { ...marker, startedAt: performance.now() };
            state.marker = next;
            state.markers.push(next);
            state.armedClickListener = null;
          };
          state.armedClickListener = listener;
          document.addEventListener('click', listener, { capture: true, once: true });
        }""",
        {
            "actionId": action_id,
            "expectedPath": expected_path,
            "expectedStar": None,
            "enforceStarInvariant": False,
            "requiredTexts": [],
        },
    )


def arm_painted_frame_attribute_change(
    page: Any,
    *,
    action_id: str,
    expected_path: str,
    selector: str,
    attribute: str,
) -> None:
    """Begin a marker when a target attribute first commits a different value."""
    page.evaluate(
        """(config) => {
          const state = window.__lensletPaintedFrameTrace;
          if (!state || !state.running) throw new Error('painted-frame trace is not running');
          const element = document.querySelector(config.selector);
          if (!(element instanceof HTMLElement)) throw new Error('painted-frame target is absent');
          const previous = element.getAttribute(config.attribute);
          state.armedObserver?.disconnect();
          const observer = new MutationObserver(() => {
            if (element.getAttribute(config.attribute) === previous) return;
            const next = {
              actionId: config.actionId,
              expectedPath: config.expectedPath,
              expectedStar: null,
              enforceStarInvariant: false,
              requiredTexts: [],
              startedAt: performance.now(),
            };
            state.marker = next;
            state.markers.push(next);
            observer.disconnect();
            state.armedObserver = null;
          });
          state.armedObserver = observer;
          observer.observe(element, {
            attributes: true,
            attributeFilter: [config.attribute],
          });
        }""",
        {
            "actionId": action_id,
            "expectedPath": expected_path,
            "selector": selector,
            "attribute": attribute,
        },
    )


def stop_painted_frame_trace(page: Any) -> dict[str, Any]:
    result = page.evaluate(
        """() => {
          const state = window.__lensletPaintedFrameTrace;
          if (!state) return null;
          state.running = false;
          cancelAnimationFrame(state.rafId);
          state.armedObserver?.disconnect();
          state.stagedPreviewObserver?.disconnect();
          if (state.armedClickListener) {
            document.removeEventListener('click', state.armedClickListener, true);
          }
          return {
            page_id: state.pageId,
            phase: state.phase,
            frames: state.frames,
            markers: state.markers,
            staged_preview_tokens: state.stagedPreviewTokens,
          };
        }"""
    )
    if not isinstance(result, dict):
        raise SmokeFailure("Painted-frame trace was absent or malformed.")
    return result


def _surface_text(surface: Any) -> str:
    if not isinstance(surface, dict):
        return ""
    values = [surface.get("text"), surface.get("value")]
    return " ".join(value for value in values if isinstance(value, str))


def _rect_delta(baseline: Any, candidate: Any) -> float:
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        return 0.0
    deltas: list[float] = []
    for key in ("top", "left"):
        try:
            deltas.append(abs(float(baseline[key]) - float(candidate[key])))
        except (KeyError, TypeError, ValueError):
            return 0.0
    return max(deltas, default=0.0)


def _surface_is_visible(surface: Any) -> bool:
    if not isinstance(surface, dict) or surface.get("visible") is not True:
        return False
    rect = surface.get("rect")
    if not isinstance(rect, dict):
        return False
    try:
        return float(rect["width"]) > 0 and float(rect["height"]) > 0
    except (KeyError, TypeError, ValueError):
        return False


def summarize_painted_frame_trace(
    trace: Any,
    *,
    required_surfaces: tuple[str, ...],
    sentinels_by_path: dict[str, tuple[str, ...]],
    max_delta_px: float,
    fallback_texts: tuple[str, ...] = ("Loading inspector...", "Inspector could not load."),
    allow_retained_complete: bool = False,
) -> dict[str, Any]:
    violations: list[str] = []
    if not isinstance(trace, dict):
        return {"violations": ["trace is not an object"]}
    frames = trace.get("frames")
    markers = trace.get("markers")
    if not isinstance(frames, list) or not frames:
        return {"violations": ["trace has no painted frames"]}
    if not isinstance(markers, list) or not markers:
        violations.append("trace has no action markers")
        markers = []

    baseline_frame = next(
        (
            frame
            for frame in frames
            if isinstance(frame, dict)
            and isinstance(frame.get("surfaces"), dict)
            and all(_surface_is_visible(frame["surfaces"].get(name)) for name in required_surfaces)
        ),
        None,
    )
    if baseline_frame is None:
        violations.append("trace has no complete baseline frame")
        baseline_surfaces: dict[str, Any] = {}
    else:
        baseline_surfaces = baseline_frame["surfaces"]

    missing_frames = 0
    replaced_surfaces: set[str] = set()
    stale_frames = 0
    blank_or_fallback_frames = 0
    missing_expected_content_frames = 0
    max_anchor_delta_px = 0.0
    max_anchor_surface: str | None = None
    anchor_deltas_px = {name: 0.0 for name in required_surfaces}
    marker_frame_counts: dict[str, int] = {}
    first_paint_ms: list[float] = []
    failing_frames: list[dict[str, Any]] = []

    for frame_index, frame in enumerate(frames):
        frame_failed = False
        if not isinstance(frame, dict) or not isinstance(frame.get("surfaces"), dict):
            violations.append("trace contains a malformed frame")
            if len(failing_frames) < 20:
                failing_frames.append({"frame_index": frame_index, "frame": frame})
            continue
        surfaces = frame["surfaces"]
        marker = frame.get("marker")
        action_id = marker.get("actionId") if isinstance(marker, dict) else None
        if isinstance(action_id, str):
            marker_frame_counts[action_id] = marker_frame_counts.get(action_id, 0) + 1

        if any(not _surface_is_visible(surfaces.get(name)) for name in required_surfaces):
            missing_frames += 1
            frame_failed = True
            if action_id is not None:
                blank_or_fallback_frames += 1
        for name in required_surfaces:
            baseline = baseline_surfaces.get(name)
            candidate = surfaces.get(name)
            if not isinstance(baseline, dict) or not isinstance(candidate, dict):
                continue
            if baseline.get("token") != candidate.get("token"):
                replaced_surfaces.add(name)
                frame_failed = True
            candidate_delta = _rect_delta(baseline.get("rect"), candidate.get("rect"))
            anchor_deltas_px[name] = max(anchor_deltas_px[name], candidate_delta)
            if candidate_delta > max_anchor_delta_px:
                max_anchor_delta_px = candidate_delta
                max_anchor_surface = name
            if candidate_delta > max_delta_px:
                frame_failed = True

        panel_text = _surface_text(surfaces.get("panel"))
        if any(text in panel_text for text in fallback_texts):
            blank_or_fallback_frames += 1
            frame_failed = True
        if action_id is not None and not panel_text.strip():
            blank_or_fallback_frames += 1
            frame_failed = True
        if isinstance(marker, dict):
            expected_path = marker.get("expectedPath")
            all_surface_text = " ".join(_surface_text(surface) for surface in surfaces.values())
            if isinstance(expected_path, str) and not allow_retained_complete:
                stale_sentinels = (
                    sentinel
                    for path, sentinels in sentinels_by_path.items()
                    if path != expected_path
                    for sentinel in sentinels
                )
                if any(sentinel and sentinel in all_surface_text for sentinel in stale_sentinels):
                    stale_frames += 1
                    frame_failed = True
            required_texts = marker.get("requiredTexts")
            if isinstance(required_texts, list) and any(
                isinstance(required_text, str)
                and required_text
                and required_text not in all_surface_text
                for required_text in required_texts
            ):
                missing_expected_content_frames += 1
                frame_failed = True
        if frame_failed and len(failing_frames) < 20:
            failing_frames.append({"frame_index": frame_index, "frame": frame})

    marker_by_id = {
        marker.get("actionId"): marker
        for marker in markers
        if isinstance(marker, dict) and isinstance(marker.get("actionId"), str)
    }
    for action_id, marker in marker_by_id.items():
        if marker_frame_counts.get(action_id, 0) == 0:
            violations.append(f"action {action_id!r} has no post-action painted frame")
            continue
        expected_star = marker.get("expectedStar")
        expected_path = marker.get("expectedPath")
        started_at = marker.get("startedAt")
        matching_frame: dict[str, Any] | None = None
        for frame in frames:
            if not isinstance(frame, dict) or not isinstance(frame.get("marker"), dict):
                continue
            if frame["marker"].get("actionId") != action_id:
                continue
            surfaces = frame.get("surfaces")
            if not isinstance(surfaces, dict):
                continue
            if isinstance(expected_star, int):
                if not all(
                    _surface_is_visible(surfaces.get(f"star_{star}"))
                    for star in range(1, 6)
                ):
                    continue
                if expected_star == 0:
                    star_pressed = any(
                        isinstance(surfaces.get(f"star_{star}"), dict)
                        and isinstance(surfaces[f"star_{star}"].get("attrs"), dict)
                        and surfaces[f"star_{star}"]["attrs"].get("ariaPressed") == "true"
                        for star in range(1, 6)
                    )
                    if not star_pressed:
                        matching_frame = frame
                        break
                else:
                    star_surface = surfaces.get(f"star_{expected_star}")
                    attrs = star_surface.get("attrs") if isinstance(star_surface, dict) else None
                    if isinstance(attrs, dict) and attrs.get("ariaPressed") == "true":
                        matching_frame = frame
                        break
            elif isinstance(expected_path, str):
                filename = expected_path.rsplit("/", 1)[-1]
                if filename and filename in _surface_text(surfaces.get("filename")):
                    matching_frame = frame
                    break
        if matching_frame is None:
            if marker.get("requireExpectedPaint") is not False:
                violations.append(f"action {action_id!r} never painted its expected state")
                for frame_index in range(len(frames) - 1, -1, -1):
                    candidate = frames[frame_index]
                    if (
                        isinstance(candidate, dict)
                        and isinstance(candidate.get("marker"), dict)
                        and candidate["marker"].get("actionId") == action_id
                    ):
                        if len(failing_frames) < 20:
                            failing_frames.append(
                                {
                                    "frame_index": frame_index,
                                    "reason": "expected state was never painted",
                                    "frame": candidate,
                                }
                            )
                        break
        else:
            try:
                first_paint_ms.append(float(matching_frame["timestamp"]) - float(started_at))
            except (KeyError, TypeError, ValueError):
                violations.append(f"action {action_id!r} has invalid paint timing")
        if marker.get("enforceStarInvariant") is True and isinstance(expected_star, int):
            for frame_index, frame in enumerate(frames):
                if not isinstance(frame, dict) or not isinstance(frame.get("marker"), dict):
                    continue
                if frame["marker"].get("actionId") != action_id:
                    continue
                surfaces = frame.get("surfaces")
                if not isinstance(surfaces, dict):
                    continue
                expected_filename = str(expected_path).rsplit("/", 1)[-1]
                if expected_filename not in _surface_text(surfaces.get("filename")):
                    continue
                if not all(
                    _surface_is_visible(surfaces.get(f"star_{star}"))
                    for star in range(1, 6)
                ):
                    violations.append(
                        f"action {action_id!r} violated its rating invariant: "
                        "star controls were absent or invisible"
                    )
                    if len(failing_frames) < 20:
                        failing_frames.append({"frame_index": frame_index, "frame": frame})
                    break
                pressed = [
                    star
                    for star in range(1, 6)
                    if isinstance(surfaces.get(f"star_{star}"), dict)
                    and isinstance(surfaces[f"star_{star}"].get("attrs"), dict)
                    and surfaces[f"star_{star}"]["attrs"].get("ariaPressed") == "true"
                ]
                if pressed != ([] if expected_star == 0 else [expected_star]):
                    violations.append(
                        f"action {action_id!r} violated its rating invariant: pressed={pressed!r}"
                    )
                    if len(failing_frames) < 20:
                        failing_frames.append({"frame_index": frame_index, "frame": frame})
                    break

    if missing_frames:
        violations.append(f"required inspector surfaces were absent in {missing_frames} painted frames")
    if replaced_surfaces:
        violations.append(f"required nodes were replaced: {sorted(replaced_surfaces)!r}")
    if max_anchor_delta_px > max_delta_px:
        violations.append(
            f"anchor delta {max_anchor_delta_px:.3f}px at {max_anchor_surface!r} "
            f"exceeded {max_delta_px:.3f}px; per-surface={anchor_deltas_px!r}"
        )
    if blank_or_fallback_frames:
        violations.append(f"blank or fallback inspector painted in {blank_or_fallback_frames} frames")
    if stale_frames:
        violations.append(f"stale path sentinel painted in {stale_frames} frames")
    if missing_expected_content_frames:
        violations.append(
            "required current-path content was absent in "
            f"{missing_expected_content_frames} painted frames"
        )

    return {
        "page_id": trace.get("page_id"),
        "phase": trace.get("phase"),
        "iterations": len(marker_by_id),
        "frame_count": len(frames),
        "paint_p95_ms": percentile(first_paint_ms, 95.0),
        "max_anchor_delta_px": max_anchor_delta_px,
        "max_anchor_surface": max_anchor_surface,
        "anchor_deltas_px": anchor_deltas_px,
        "missing_required_surface_frames": missing_frames,
        "root_or_required_nodes_replaced": bool(replaced_surfaces),
        "replaced_surfaces": sorted(replaced_surfaces),
        "stale_text_frames": stale_frames,
        "blank_or_fallback_frames": blank_or_fallback_frames,
        "missing_expected_content_frames": missing_expected_content_frames,
        "violations": violations,
        "failing_frames": failing_frames,
    }


def assert_painted_frame_summary(summary: dict[str, Any]) -> None:
    violations = summary.get("violations")
    if not isinstance(violations, list):
        raise SmokeFailure("Painted-frame summary is malformed.")
    if violations:
        raise SmokeFailure("; ".join(str(violation) for violation in violations))
