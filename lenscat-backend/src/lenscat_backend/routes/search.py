from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from ..models import SearchResult, Item
from ..utils import jsonio

router = APIRouter()

@router.get("/search", response_model=SearchResult)
def search(request: Request, q: str = "", limit: int = 100):
    storage = request.state.storage
    if storage is None:
        raise HTTPException(500, "Storage not configured")
    rollup_path = "_rollup.json"
    try:
        if not storage.exists(rollup_path):
            return SearchResult(items=[])
        data = jsonio.loads(storage.read_bytes(rollup_path))
    except ValueError:
        return SearchResult(items=[])
    items = []
    ql = q.lower()
    for it in data.get('items', []):
        hay = (it.get('name','') + ' ' + ' '.join(it.get('tags',[])) + ' ' + it.get('notes','')).lower()
        if ql in hay:
            items.append(Item(**{
                'path': it['path'], 'name': it.get('name',''), 'type': it.get('type','image/jpeg'),
                'w': it.get('w',0), 'h': it.get('h',0), 'size': it.get('size',0),
                'hasThumb': it.get('hasThumb', False), 'hasMeta': True, 'hash': it.get('hash')
            }))
            if len(items) >= limit: break
    return SearchResult(items=items)
