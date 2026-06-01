from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from ..context import get_request_context
from ..request_headers import last_event_id_from_request
from ..sync.events import format_sse


def register_event_routes(app: FastAPI) -> None:
    @app.get("/events")
    async def events(request: Request) -> StreamingResponse:
        broker = get_request_context(request).runtime.broker
        broker.ensure_loop()
        queue = broker.register()
        last_event_id = last_event_id_from_request(request)

        async def event_stream() -> AsyncIterator[str]:
            try:
                for record in broker.replay(last_event_id):
                    yield format_sse(record)
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        record = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield format_sse(record)
            finally:
                broker.unregister(queue)

        response = StreamingResponse(event_stream(), media_type="text/event-stream")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        return response
