import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin

from lenslet.server import create_app


def _make_png_with_metadata(
    path: Path,
    *,
    text_chunks: dict[str, str] | None = None,
    itxt_chunks: dict[str, str] | None = None,
) -> None:
    img = Image.new("RGB", (4, 4), color=(128, 20, 20))
    meta = PngImagePlugin.PngInfo()
    for key, value in (text_chunks or {}).items():
        meta.add_text(key, value)
    for key, value in (itxt_chunks or {}).items():
        meta.add_itxt(key, value)
    img.save(path, format="PNG", pnginfo=meta)


def _make_png_with_text(path: Path, text: str) -> None:
    _make_png_with_metadata(path, text_chunks={"parameters": text})


def test_metadata_endpoint_reads_png_text_chunks():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        png_path = root / "sample.png"
        _make_png_with_text(png_path, "steps=20, cfg=7.0")

        app = create_app(str(root))
        client = TestClient(app)

        resp = client.get("/metadata", params={"path": f"/{png_path.name}"})
        assert resp.status_code == 200

        payload = resp.json()
        assert payload["format"] == "png"
        assert payload["path"].endswith("sample.png")
        meta = payload["meta"]
        assert meta["quick_fields"]["parameters"] == "steps=20, cfg=7.0"
        assert any(chunk.get("keyword") == "parameters" for chunk in meta["found_text_chunks"])
        assert meta["quick_view_defaults"] == {
            "prompt": "steps=20, cfg=7.0",
            "model": "",
            "lora": "",
        }


def test_metadata_endpoint_reads_quick_view_defaults_from_fixture_qfty_meta():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fixture_src = Path(__file__).resolve().parents[1] / "docs" / "test_meta.png"
        fixture_dst = root / "test_meta.png"
        fixture_dst.write_bytes(fixture_src.read_bytes())

        app = create_app(str(root))
        client = TestClient(app)

        resp = client.get("/metadata", params={"path": f"/{fixture_dst.name}"})
        assert resp.status_code == 200

        payload = resp.json()
        meta = payload["meta"]
        defaults = meta["quick_view_defaults"]
        assert defaults["prompt"].startswith("character: isekaijoucho.")
        assert defaults["model"] == "Qwen/Qwen-Image"
        assert defaults["lora"] == "ai_cls_s110.safetensors (2.0)"


def test_metadata_endpoint_handles_invalid_qfty_meta_quick_view_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        png_path = root / "broken_qfty.png"
        _make_png_with_metadata(png_path, itxt_chunks={"qfty_meta": "{not-json}"})

        app = create_app(str(root))
        client = TestClient(app)

        resp = client.get("/metadata", params={"path": f"/{png_path.name}"})
        assert resp.status_code == 200

        payload = resp.json()
        meta = payload["meta"]
        assert meta["quick_view_defaults"] == {
            "prompt": "",
            "model": "",
            "lora": "",
        }


def test_metadata_endpoint_accepts_jpeg():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jpg_path = root / "sample.jpg"
        Image.new("RGB", (4, 4), color=(0, 0, 0)).save(jpg_path, format="JPEG")

        app = create_app(str(root))
        client = TestClient(app)

        resp = client.get("/metadata", params={"path": f"/{jpg_path.name}"})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["format"] == "jpeg"
