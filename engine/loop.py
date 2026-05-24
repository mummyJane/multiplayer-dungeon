import asyncio
import logging
from typing import Callable, Awaitable

from .time_scale import TimeScaler

log = logging.getLogger(__name__)


class GameLoop:
    def __init__(self, tick_callback: Callable[[], Awaitable[None]]):
        self._callback = tick_callback
        self._scaler = TimeScaler()
        self._running = False
        self._tick_count = 0

    def set_player_count(self, count: int):
        self._scaler.set_player_count(count)

    async def start(self):
        self._running = True
        log.info("Game loop started")
        while self._running:
            interval = self._scaler.tick_interval()
            await asyncio.sleep(interval)
            self._tick_count += 1
            try:
                await self._callback()
            except Exception:
                log.exception("Error in game tick %d", self._tick_count)

    def stop(self):
        self._running = False
        log.info("Game loop stopped after %d ticks", self._tick_count)

    @property
    def tick_count(self) -> int:
        return self._tick_count
