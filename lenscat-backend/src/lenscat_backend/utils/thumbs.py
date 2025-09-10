from __future__ import annotations
from PIL import Image
from io import BytesIO

# Generate a WebP thumbnail with SHORT edge target and quality.
# We avoid upscaling: images smaller than the target on the short side keep original size.

def make_thumbnail(img_bytes: bytes, short_edge: int = 256, quality: int = 70) -> bytes:
    with Image.open(BytesIO(img_bytes)) as im:
        w, h = im.size
        short = min(w, h)
        if short > short_edge:
            scale = short_edge / short
            new_w = int(w * scale)
            new_h = int(h * scale)
            im = im.convert("RGB").resize((max(1,new_w), max(1,new_h)), Image.LANCZOS)
        else:
            im = im.convert("RGB")
        out = BytesIO()
        im.save(out, format="WEBP", quality=quality, method=6)
        return out.getvalue()
