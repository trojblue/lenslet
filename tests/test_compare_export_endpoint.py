import io
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import lenslet.server as server_mod
from lenslet.metadata import read_png_info
from lenslet.server import create_app


def _make_png(path: Path, *, size: tuple[int, int] = (12, 8), color=(64, 64, 64), mode: str = "RGB") -> None:
    image = Image.new(mode, size, color=color)
    image.save(path, format="PNG")


def _export_payload(**overrides):
    payload = {
        "v": 1,
        "paths": ["/a.png", "/b.png"],
        "labels": ["Prompt A", "Prompt B"],
        "embed_metadata": True,
        "reverse_order": False,
    }
    payload.update(overrides)
    return payload


def _read_comparison_metadata(raw: bytes) -> dict | None:
    parsed = read_png_info(io.BytesIO(raw))
    for chunk in parsed.get("found_text_chunks", []):
        if chunk.get("keyword") == server_mod.EXPORT_COMPARISON_METADATA_KEY:
            text = chunk.get("text", "")
            return json.loads(text) if text else None
    return None


def test_export_comparison_success_with_embedded_metadata(tmp_path: Path) -> None:
    _make_png(tmp_path / "a.png", size=(20, 10), color=(255, 0, 0))
    _make_png(tmp_path / "b.png", size=(12, 10), color=(0, 255, 0))

    client = TestClient(create_app(str(tmp_path)))
    response = client.post("/export-comparison", json=_export_payload())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    disposition = response.headers["content-disposition"]
    assert re.search(r'attachment; filename="comparison_\d{8}_\d{6}\.png"', disposition)

    with Image.open(io.BytesIO(response.content)) as exported:
        assert exported.width == 32
        assert exported.height > 10

    metadata_payload = _read_comparison_metadata(response.content)
    assert metadata_payload is not None
    assert metadata_payload["paths"] == ["/a.png", "/b.png"]
    assert metadata_payload["labels"] == ["Prompt A", "Prompt B"]
    assert metadata_payload["reversed"] is False


def test_export_comparison_reverse_swaps_order_and_labels(tmp_path: Path) -> None:
    _make_png(tmp_path / "a.png", size=(12, 8), color=(100, 10, 10))
    _make_png(tmp_path / "b.png", size=(18, 8), color=(10, 10, 100))

    client = TestClient(create_app(str(tmp_path)))
    response = client.post(
        "/export-comparison",
        json=_export_payload(reverse_order=True, labels=["Left", "Right"]),
    )

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert re.search(r'attachment; filename="comparison_reverse_\d{8}_\d{6}\.png"', disposition)

    metadata_payload = _read_comparison_metadata(response.content)
    assert metadata_payload is not None
    assert metadata_payload["paths"] == ["/b.png", "/a.png"]
    assert metadata_payload["labels"] == ["Right", "Left"]
    assert metadata_payload["reversed"] is True


def test_export_comparison_omits_metadata_when_disabled(tmp_path: Path) -> None:
    _make_png(tmp_path / "a.png")
    _make_png(tmp_path / "b.png")

    client = TestClient(create_app(str(tmp_path)))
    response = client.post(
        "/export-comparison",
        json=_export_payload(embed_metadata=False),
    )

    assert response.status_code == 200
    assert _read_comparison_metadata(response.content) is None


def test_export_comparison_rejects_invalid_paths_with_parity_checks(tmp_path: Path) -> None:
    _make_png(tmp_path / "a.png")
    _make_png(tmp_path / "b.png")

    client = TestClient(create_app(str(tmp_path)))
    response = client.post(
        "/export-comparison",
        json=_export_payload(paths=["../../etc/passwd", "/b.png"]),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["error"] == "invalid_path"


def test_export_comparison_returns_404_for_missing_source(tmp_path: Path) -> None:
    _make_png(tmp_path / "a.png")

    client = TestClient(create_app(str(tmp_path)))
    response = client.post(
        "/export-comparison",
        json=_export_payload(paths=["/a.png", "/missing.png"]),
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"] == "file_not_found"


def test_export_comparison_returns_415_for_unsupported_source_payload(tmp_path: Path) -> None:
    _make_png(tmp_path / "a.png")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not-an-image")

    client = TestClient(create_app(str(tmp_path)))
    response = client.post(
        "/export-comparison",
        json=_export_payload(paths=["/a.png", "/bad.png"]),
    )

    assert response.status_code == 415
    payload = response.json()
    assert payload["error"] == "unsupported_source_format"


def test_export_comparison_sanitizes_labels_and_rejects_overlong_labels(tmp_path: Path) -> None:
    _make_png(tmp_path / "a.png")
    _make_png(tmp_path / "b.png")

    client = TestClient(create_app(str(tmp_path)))

    sanitized = client.post(
        "/export-comparison",
        json=_export_payload(labels=["\u0000  Prompt A\u0007  ", "Prompt B"]),
    )
    assert sanitized.status_code == 200
    meta = _read_comparison_metadata(sanitized.content)
    assert meta is not None
    assert meta["labels"] == ["Prompt A", "Prompt B"]

    too_long = client.post(
        "/export-comparison",
        json=_export_payload(labels=["x" * 121, "ok"]),
    )
    assert too_long.status_code == 400
    payload = too_long.json()
    assert payload["error"] == "invalid_labels"


def test_export_comparison_enforces_pixel_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_png(tmp_path / "a.png", size=(20, 20), color=(10, 10, 10))
    _make_png(tmp_path / "b.png", size=(20, 20), color=(20, 20, 20))

    client = TestClient(create_app(str(tmp_path)))

    monkeypatch.setattr(server_mod, "MAX_EXPORT_SOURCE_PIXELS", 200)
    source_limit = client.post("/export-comparison", json=_export_payload())
    assert source_limit.status_code == 400
    assert source_limit.json()["error"] == "export_too_large"

    monkeypatch.setattr(server_mod, "MAX_EXPORT_SOURCE_PIXELS", 64_000_000)
    monkeypatch.setattr(server_mod, "MAX_EXPORT_STITCHED_PIXELS", 500)
    stitched_limit = client.post("/export-comparison", json=_export_payload())
    assert stitched_limit.status_code == 400
    assert stitched_limit.json()["error"] == "export_too_large"


def test_export_comparison_returns_500_when_unibox_is_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_png(tmp_path / "a.png")
    _make_png(tmp_path / "b.png")

    def _raise_missing():
        raise RuntimeError("unibox is required for comparison export. Install with: pip install unibox")

    monkeypatch.setattr(server_mod, "_get_unibox_image_utils", _raise_missing)

    client = TestClient(create_app(str(tmp_path)))
    response = client.post("/export-comparison", json=_export_payload())

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "unibox_missing"


def test_export_comparison_flattens_alpha_to_rgb(tmp_path: Path) -> None:
    _make_png(tmp_path / "a.png", size=(8, 8), color=(255, 0, 0, 0), mode="RGBA")
    _make_png(tmp_path / "b.png", size=(8, 8), color=(0, 255, 0, 128), mode="RGBA")

    client = TestClient(create_app(str(tmp_path)))
    response = client.post("/export-comparison", json=_export_payload(embed_metadata=False))

    assert response.status_code == 200
    with Image.open(io.BytesIO(response.content)) as exported:
        assert exported.mode == "RGB"
