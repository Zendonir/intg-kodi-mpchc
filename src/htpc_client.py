"""
HTTP client for the optional HTPC WiFi Control (Streacom) power device.

The ESP32-based controller exposes a simple REST API on port 80:
  GET /power/on        — power the PC on
  GET /power/off       — power the PC off (short button press)
  GET /power/forceoff  — force power off (long button press)
  GET /reset           — reset the PC
  GET /power/toggle    — toggle power
  GET /state           — {"power": "on" | "off"}

There is no push channel, so the power state is polled periodically and the
on_power callback is fired whenever it changes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

import aiohttp

_LOG = logging.getLogger(__name__)

POLL_INTERVAL = 10.0
# Short delay after a power command before re-reading /state so entities
# reflect the new state quickly without waiting for the next poll tick.
REFRESH_AFTER_CMD = 1.5

PowerCallback = Callable[[str], Awaitable[None]]
"""async def cb(power: str) -> None  — power is "on" | "off" | "unknown"."""


class HtpcClient:
    """REST client + state poller for the HTPC power-control device."""

    def __init__(self, host: str, port: int, on_power: PowerCallback | None = None) -> None:
        self._host = host
        self._port = port
        self._base_url = f"http://{host}:{port}"
        self._on_power = on_power
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._power = "unknown"

    @property
    def enabled(self) -> bool:
        return bool(self._host)

    @property
    def running(self) -> bool:
        return self._running

    @property
    def power(self) -> str:
        return self._power

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if not self.enabled:
            return
        if self._running and self._task and not self._task.done():
            return  # already polling
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(), name="htpc-poll")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def power_on(self) -> bool:
        return await self._command("/power/on")

    async def power_off(self) -> bool:
        return await self._command("/power/off")

    async def force_off(self) -> bool:
        return await self._command("/power/forceoff")

    async def reset(self) -> bool:
        return await self._command("/reset")

    async def toggle(self) -> bool:
        return await self._command("/power/toggle")

    async def _command(self, path: str) -> bool:
        ok = await self._get(path) is not None
        if ok:
            # Re-read state shortly after so entities update promptly.
            asyncio.create_task(self._refresh_after_delay())
        return ok

    async def _refresh_after_delay(self) -> None:
        try:
            await asyncio.sleep(REFRESH_AFTER_CMD)
            await self.refresh()
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    async def refresh(self) -> str:
        """Read /state and notify on change. Returns the current power value."""
        body = await self._get("/state")
        power = "unknown"
        if body:
            try:
                power = str(json.loads(body).get("power", "unknown")).lower()
            except (ValueError, AttributeError):
                power = "unknown"
        if power != self._power:
            self._power = power
            if self._on_power:
                await self._on_power(power)
        return power

    async def _poll_loop(self) -> None:
        first = True
        while self._running:
            try:
                await self.refresh()
            except asyncio.CancelledError:
                return
            except Exception as exc:  # pylint: disable=broad-except
                if first:
                    _LOG.warning(
                        "Cannot reach HTPC power device at %s — check IP/port. Error: %s",
                        self._base_url,
                        exc,
                    )
                else:
                    _LOG.debug("HTPC poll error: %s", exc)
            first = False
            await asyncio.sleep(POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _get(self, path: str) -> str | None:
        """GET a path. Returns the response body on HTTP 200, else None."""
        try:
            session = await self._get_session()
            async with session.get(
                f"{self._base_url}{path}",
                timeout=aiohttp.ClientTimeout(total=5.0),
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
                return None
        except Exception as exc:  # pylint: disable=broad-except
            _LOG.debug("HTPC GET %s failed: %s", path, exc)
            return None
