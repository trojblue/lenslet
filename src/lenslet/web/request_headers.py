from __future__ import annotations

from fastapi import Request


def parse_if_match(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.startswith("W/"):
        cleaned = cleaned[2:]
    cleaned = cleaned.strip('"')
    try:
        return int(cleaned)
    except (TypeError, ValueError):
        return None


def _parse_event_id(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def last_event_id_from_request(request: Request) -> int | None:
    header_id = _parse_event_id(request.headers.get("Last-Event-ID"))
    query_raw = request.query_params.get("last_event_id") or request.query_params.get("lastEventId")
    query_id = _parse_event_id(query_raw)
    if query_id is None:
        return header_id
    if header_id is None:
        return query_id
    return max(header_id, query_id)
