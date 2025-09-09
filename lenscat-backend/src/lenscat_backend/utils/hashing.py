from __future__ import annotations
from blake3 import blake3

def blake3_hex(data: bytes) -> str:
    return blake3(data).hexdigest()
