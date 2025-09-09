from __future__ import annotations
from PIL import Image
from io import BytesIO

# Generate a WebP thumbnail with long edge limit and quality.

def make_thumbnail(img_bytes: bytes, long_edge: int = 256, quality: int = 70) -> bytes:
    with Image.open(BytesIO(img_bytes)) as im:
        w, h = im.size
        if w >= h:
            new_w = long_edge
            new_h = int(h * (long_edge / w))
        else:
            new_h = long_edge
            new_w = int(w * (long_edge / h))
        im = im.convert("RGB").resize((max(1,new_w), max(1,new_h)), Image.LANCZOS)
        out = BytesIO()
        im.save(out, format="WEBP", quality=quality, method=6)
        return out.getvalue()
