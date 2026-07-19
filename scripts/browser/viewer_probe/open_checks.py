from __future__ import annotations

from typing import Any

from scripts.browser.viewer_probe.config import VIEWER_LOADER_DELAY_MS

LOADER_DELAY_TOLERANCE_MS = 10
VISIBLE_OPACITY_THRESHOLD = 0.01
READY_OPACITY_THRESHOLD = 0.5
OPAQUE_OPACITY_THRESHOLD = 0.99
PIXEL_TOLERANCE = 18
FIXTURE_RGB = {
    "alpha_00_wide.jpg": (48, 90, 140),
    "alpha_01_tall.jpg": (122, 74, 150),
    "alpha_02_square.jpg": (65, 128, 104),
    "beta_00_wide.jpg": (154, 91, 62),
    "beta_01_tall.jpg": (70, 118, 165),
    "beta_02_square.jpg": (143, 116, 50),
}


def summarize_open_samples(samples: dict[str, Any]) -> dict[str, Any]:
    frames = samples.get("samples")
    if not isinstance(frames, list):
        return {}
    summary = _empty_open_sample_summary()
    for frame in frames:
        if isinstance(frame, dict):
            _update_open_sample_summary(summary, frame)
    return summary


def viewer_acceptance_failures(raw_scenarios: Any) -> list[str]:
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        return ["viewer: missing viewer-open scenarios"]
    failures: list[str] = []
    for scenario in raw_scenarios:
        failures.extend(_scenario_acceptance_failures(scenario))
    return failures


def viewer_image_like_failures(name: str, scenario: dict[str, Any], opened_path: Any) -> list[str]:
    samples = _scenario_frames(scenario)
    if not samples:
        return [f"viewer:{name}: missing open samples"]

    failures: list[str] = []
    for frame in samples:
        if isinstance(frame, dict):
            failures.extend(_frame_image_like_failures(
                name,
                frame,
                opened_path,
                scenario.get("navigation"),
                bool(scenario.get("reducedMotion")),
            ))
    return failures


def delayed_loader_observed(scenario: dict[str, Any]) -> bool:
    return any(_delayed_loader_frame(frame) for frame in _scenario_frames(scenario))


def loader_observed(scenario: dict[str, Any]) -> bool:
    return any(_loader_visible_or_loading(frame) for frame in _scenario_frames(scenario))


def visible_element_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    rect = payload.get("rect")
    return (
        isinstance(rect, dict)
        and float(rect.get("width") or 0) > 0
        and float(rect.get("height") or 0) > 0
        and float(payload.get("opacity") or 0) > VISIBLE_OPACITY_THRESHOLD
        and payload.get("display") != "none"
        and payload.get("visibility") != "hidden"
    )


def _empty_open_sample_summary() -> dict[str, bool]:
    return {
        "thumbObserved": False,
        "fallbackObserved": False,
        "fullImageCrossfadeObserved": False,
        "duplicateVisibleImageObserved": False,
        "invisibleFullImageObserved": False,
        "openFadeClassObserved": False,
    }


def _update_open_sample_summary(summary: dict[str, bool], frame: dict[str, Any]) -> None:
    _update_thumb_summary(summary, frame)
    summary["fallbackObserved"] = summary["fallbackObserved"] or isinstance(frame.get("fallback"), dict)
    _update_viewer_summary(summary, frame.get("viewer"))
    _update_dialog_summary(summary, frame.get("dialog"))


def _update_thumb_summary(summary: dict[str, bool], frame: dict[str, Any]) -> None:
    thumb = frame.get("thumb")
    if not isinstance(thumb, dict):
        return
    summary["thumbObserved"] = True
    thumb_visible = float(thumb.get("opacity") or 0) > VISIBLE_OPACITY_THRESHOLD
    if thumb_visible and frame.get("visibleImageCount", 0) > 1:
        summary["duplicateVisibleImageObserved"] = True


def _update_viewer_summary(summary: dict[str, bool], viewer: Any) -> None:
    if not isinstance(viewer, dict):
        return
    opacity = float(viewer.get("opacity") or 0)
    if 0 < opacity < 0.99:
        summary["fullImageCrossfadeObserved"] = True
    if opacity <= VISIBLE_OPACITY_THRESHOLD:
        summary["invisibleFullImageObserved"] = True


def _update_dialog_summary(summary: dict[str, bool], dialog: Any) -> None:
    if not isinstance(dialog, dict):
        return
    class_name = str(dialog.get("className") or "")
    summary["openFadeClassObserved"] = summary["openFadeClassObserved"] or "transition-opacity" in class_name


def _scenario_acceptance_failures(scenario: Any) -> list[str]:
    if not isinstance(scenario, dict):
        return ["viewer: malformed viewer-open scenario"]
    name = str(scenario.get("name") or "<unnamed>")
    summary = scenario.get("riskSummary")
    if not isinstance(summary, dict):
        return [f"viewer:{name}: missing risk summary"]

    failures = _risk_summary_failures(name, summary)
    failures.extend(_loader_policy_failures(name, scenario))
    failures.extend(viewer_image_like_failures(name, scenario, scenario.get("openedPath")))
    failures.extend(_settled_state_failures(name, scenario))
    return failures


def _risk_summary_failures(name: str, summary: dict[str, Any]) -> list[str]:
    risky_keys = (
        "thumbObserved",
        "fallbackObserved",
        "fullImageCrossfadeObserved",
        "duplicateVisibleImageObserved",
        "openFadeClassObserved",
    )
    return [f"viewer:{name}: {key} is still true" for key in risky_keys if summary.get(key)]


def _loader_policy_failures(name: str, scenario: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if scenario.get("loaderExpected") and not delayed_loader_observed(scenario):
        failures.append(f"viewer:{name}: delayed neutral loader was not observed")
    if scenario.get("loaderForbidden") and loader_observed(scenario):
        failures.append(f"viewer:{name}: neutral loader appeared in loader-forbidden scenario")
    return failures


def _settled_state_failures(name: str, scenario: dict[str, Any]) -> list[str]:
    settled = scenario.get("settled")
    opened_path = scenario.get("openedPath")
    if not isinstance(settled, dict) or settled.get("missing"):
        return [f"viewer:{name}: settled full image is missing"]
    if scenario.get("terminalExpected") == "error":
        failures: list[str] = []
        if settled.get("dialogPath") != opened_path or settled.get("loadingState") != "error":
            failures.append(f"viewer:{name}: corrupt target did not settle to its own error")
        if settled.get("imagePath") is not None or int(settled.get("imageCount") or 0) > 1:
            failures.append(f"viewer:{name}: corrupt target retained visible or unbounded media")
        return failures
    failures = _settled_path_failures(name, settled, opened_path)
    if float(settled.get("opacity") or 0) <= READY_OPACITY_THRESHOLD:
        failures.append(f"viewer:{name}: settled full image is not visibly ready")
    if settled.get("loadingState") != "ready":
        failures.append(f"viewer:{name}: settled loading state is not ready")
    if settled.get("neutralLoaderVisible"):
        failures.append(f"viewer:{name}: neutral loader remained visible after readiness")
    if int(settled.get("imageCount") or 0) != 1:
        failures.append(f"viewer:{name}: settled Viewer did not retire to one media node")
    return failures


def _settled_path_failures(name: str, settled: dict[str, Any], opened_path: Any) -> list[str]:
    if settled.get("dialogPath") == opened_path and settled.get("imagePath") == opened_path:
        return []
    return [
        f"viewer:{name}: settled path mismatch "
        f"dialog={settled.get('dialogPath')!r} image={settled.get('imagePath')!r} opened={opened_path!r}"
    ]


def _scenario_frames(scenario: dict[str, Any]) -> list[Any]:
    samples = (scenario.get("samples") or {}).get("samples")
    return samples if isinstance(samples, list) else []


def _frame_image_like_failures(
    name: str,
    frame: dict[str, Any],
    opened_path: Any,
    navigation: Any,
    reduced_motion: bool,
) -> list[str]:
    frame_id = frame.get("frame")
    failures = _frame_loader_failures(name, frame)
    if (
        isinstance(navigation, dict)
        and int(frame.get("visibleImageCount") or 0) == 0
        and frame.get("loadingState") not in {"error", "unsupported"}
    ):
        failures.append(f"viewer:{name}: frame {frame_id}: navigation painted zero visible images")
    failures.extend(_visible_image_failures(
        name, frame, opened_path, frame_id, navigation, reduced_motion,
    ))
    failures.extend(_image_like_scan_failures(name, frame, frame_id))
    return failures


def _frame_loader_failures(name: str, frame: dict[str, Any]) -> list[str]:
    frame_id = frame.get("frame")
    elapsed_ms = int(frame.get("elapsedMs") or 0)
    failures: list[str] = []
    if elapsed_ms < VIEWER_LOADER_DELAY_MS - LOADER_DELAY_TOLERANCE_MS and frame.get("loadingState") == "loading":
        failures.append(f"viewer:{name}: frame {frame_id}: neutral loader appeared before delay ({elapsed_ms}ms)")
    if frame.get("loadingState") == "loading" and not frame.get("neutralLoaderVisible"):
        failures.append(f"viewer:{name}: frame {frame_id}: loading state has no visible neutral loader")
    return failures


def _visible_image_failures(
    name: str,
    frame: dict[str, Any],
    opened_path: Any,
    frame_id: Any,
    navigation: Any,
    reduced_motion: bool,
) -> list[str]:
    visible_images = frame.get("visibleImages")
    if not isinstance(visible_images, list):
        return [f"viewer:{name}: frame {frame_id}: missing visible image list"]
    allowed_paths = {opened_path}
    if isinstance(navigation, dict):
        allowed_paths.add(navigation.get("from"))
    if len(visible_images) > 1:
        return [f"viewer:{name}: frame {frame_id}: multiple viewer images were visible"]
    failures: list[str] = []
    for image in visible_images:
        failures.extend(_visible_image_payload_failures(
            name, image, allowed_paths, frame_id, navigation, reduced_motion,
        ))
    return failures


def _visible_image_payload_failures(
    name: str,
    image: Any,
    allowed_paths: set[Any],
    frame_id: Any,
    navigation: Any,
    reduced_motion: bool,
) -> list[str]:
    if not isinstance(image, dict):
        return [f"viewer:{name}: frame {frame_id}: malformed visible image"]
    path = image.get("currentPath")
    failures: list[str] = []
    if image.get("viewerImage") != "full" or path not in allowed_paths:
        failures.append(
            f"viewer:{name}: frame {frame_id}: visible non-presented image "
            f"viewerImage={image.get('viewerImage')!r} path={path!r}"
        )
    if (
        not image.get("complete")
        or int(image.get("naturalWidth") or 0) <= 0
        or float(image.get("opacity") or 0) < OPAQUE_OPACITY_THRESHOLD
        or not isinstance(image.get("rgb"), list)
    ):
        failures.append(f"viewer:{name}: frame {frame_id}: visible image was not decoded and opaque")
    expected_label = f"Image viewer: {str(path).rsplit('/', 1)[-1]}"
    if image.get("alt") != expected_label:
        failures.append(f"viewer:{name}: frame {frame_id}: label did not match presented pixels")
    if isinstance(navigation, dict):
        retained_transform = navigation.get("retainedTransform")
        if path == navigation.get("from") and retained_transform and image.get("transform") != retained_transform:
            failures.append(f"viewer:{name}: frame {frame_id}: retained pixels lost their transform")
        if path == navigation.get("to") and retained_transform and image.get("transform") == retained_transform:
            failures.append(f"viewer:{name}: frame {frame_id}: target pixels inherited the prior transform")
    if reduced_motion and image.get("transitionDuration") not in {None, "0s", "0ms"}:
        failures.append(f"viewer:{name}: frame {frame_id}: reduced-motion image retained a transition")
    expected_rgb = FIXTURE_RGB.get(str(path).rsplit("/", 1)[-1])
    rgb = image.get("rgb")
    if expected_rgb and (
        not isinstance(rgb, list)
        or len(rgb) < 3
        or max(abs(int(rgb[index]) - expected_rgb[index]) for index in range(3)) > PIXEL_TOLERANCE
    ):
        failures.append(f"viewer:{name}: frame {frame_id}: pixels did not match presented path")
    return failures


def _image_like_scan_failures(name: str, frame: dict[str, Any], frame_id: Any) -> list[str]:
    image_like = frame.get("imageLikeElements")
    if not isinstance(image_like, dict):
        return [f"viewer:{name}: frame {frame_id}: missing image-like element scan"]
    failures = _nonzero_image_like_count_failures(name, image_like, frame_id)
    failures.extend(_visible_background_failures(name, image_like, frame_id))
    return failures


def _nonzero_image_like_count_failures(name: str, image_like: dict[str, Any], frame_id: Any) -> list[str]:
    failures: list[str] = []
    for key in ("canvasCount", "pictureCount"):
        if int(image_like.get(key) or 0) > 0:
            failures.append(f"viewer:{name}: frame {frame_id}: {key} is nonzero")
    return failures


def _visible_background_failures(name: str, image_like: dict[str, Any], frame_id: Any) -> list[str]:
    backgrounds = image_like.get("backgroundImages")
    if not isinstance(backgrounds, list):
        return []
    visible_backgrounds = [item for item in backgrounds if visible_element_payload(item)]
    if not visible_backgrounds:
        return []
    return [f"viewer:{name}: frame {frame_id}: visible background-image placeholder count {len(visible_backgrounds)}"]


def _delayed_loader_frame(frame: Any) -> bool:
    if not isinstance(frame, dict):
        return False
    elapsed_ms = int(frame.get("elapsedMs") or 0)
    return (
        elapsed_ms >= VIEWER_LOADER_DELAY_MS - LOADER_DELAY_TOLERANCE_MS
        and frame.get("loadingState") == "loading"
        and frame.get("neutralLoaderVisible")
    )


def _loader_visible_or_loading(frame: Any) -> bool:
    return isinstance(frame, dict) and (
        frame.get("loadingState") == "loading" or bool(frame.get("neutralLoaderVisible"))
    )
