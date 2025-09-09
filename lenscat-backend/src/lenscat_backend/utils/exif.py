from __future__ import annotations
from PIL import Image
from io import BytesIO

# Minimal EXIF/dimensions; extend later.

def basic_meta(img_bytes: bytes) -> dict:
    with Image.open(BytesIO(img_bytes)) as im:
        w, h = im.size
        return {"width": w, "height": h}
