import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin

from lenslet.server import create_app


def _make_png_with_text(path: Path, text: str) -> None:
    img = Image.new("RGB", (4, 4), color=(128, 20, 20))
    meta = PngImagePlugin.PngInfo()
    meta.add_text("parameters", text)
    img.save(path, format="PNG", pnginfo=meta)


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
