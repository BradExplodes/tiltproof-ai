"""
Thread-safe fan-out of engine events to WebSocket clients.

The `CoachRunner` runs in a worker thread and calls `publish_threadsafe` from
there; events are marshalled onto the asyncio loop and pushed to every subscriber
queue. The most recent event of a few "stateful" types is cached so a freshly
connected client can be brought up to date immediately.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aicoach import events as ev

logger = logging.getLogger(__name__)

_QUEUE_MAXSIZE = 1000

# Event types whose latest value represents current state worth replaying to
# a newly connected client.
_SNAPSHOT_TYPES = (ev.STATUS, ev.SESSION, ev.COST, ev.CONFIG)


class EventBus:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._snapshot: dict[str, dict[str, Any]] = {}

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def snapshot(self) -> list[dict[str, Any]]:
        """Latest stateful events, ordered, for replay on connect."""
        return [self._snapshot[t] for t in _SNAPSHOT_TYPES if t in self._snapshot]

    def publish_threadsafe(self, event: dict[str, Any]) -> None:
        """Safe to call from any thread (e.g. the runner worker thread)."""
        try:
            self._loop.call_soon_threadsafe(self._publish, event)
        except RuntimeError:
            # Loop is shutting down; drop the event.
            logger.debug("event loop closed; dropping event %s", event.get("type"))

    def publish(self, event: dict[str, Any]) -> None:
        """Publish from within the event loop thread."""
        self._publish(event)

    def _publish(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type in _SNAPSHOT_TYPES:
            self._snapshot[event_type] = event
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("subscriber queue full; dropping event")
