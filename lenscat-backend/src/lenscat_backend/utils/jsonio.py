from __future__ import annotations
import orjson
from typing import Any

OPT = orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS

def dumps(obj: Any) -> bytes:
    return orjson.dumps(obj, option=OPT)

def loads(b: bytes | bytearray | memoryview):
    return orjson.loads(b)
