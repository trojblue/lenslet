from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from ..storage.base import BrowseAppStorage
from .sync.events import EventBroker


logger = logging.getLogger(__name__)


class TableSourceMonitor:
    def __init__(
        self,
        storage: BrowseAppStorage,
        broker: EventBroker,
        *,
        poll_interval: float = 1.0,
    ) -> None:
        self._storage = storage
        self._broker = broker
        self._poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        pollable = getattr(self._storage, "source_refresh_pollable", None)
        if not callable(pollable) or not pollable():
            return
        self._task = asyncio.create_task(self._run(), name="lenslet-table-source-monitor")

    async def close(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def poll_once(self) -> bool:
        poll = getattr(self._storage, "poll_source_refresh", None)
        if not callable(poll):
            return False
        status, changed = await asyncio.to_thread(poll)
        if not changed or status is None:
            return False
        self._broker.publish("table-source", status.event_payload())
        return True

    async def _run(self) -> None:
        pollable = getattr(self._storage, "source_refresh_pollable", None)
        while callable(pollable) and pollable():
            await asyncio.sleep(self._poll_interval)
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("table source monitor failed: %s", exc)
