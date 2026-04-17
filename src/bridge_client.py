"""
WebSocket client for the kodi-mpchc-bridge hub.

Receives state pushes and fires an on_state callback with the
complete unified state dict.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

import aiohttp

_LOG = logging.getLogger(__name__)

RECONNECT_DELAY = 5.0

StateCallback = Callable[[dict[str, Any], bool], Awaitable[None]]
"""Signature: async def cb(state: dict, is_full: bool) -> None"""


class BridgeClient:
    """
    Connects to the bridge WebSocket and provides a REST command sender.

    :param host: Bridge hostname/IP
    :param port: Bridge port (default 13580)
    :param on_state: Called with (state_dict, is_full) on every push
    """

    def __init__(self, host: str, port: int, on_state: StateCallback) -> None:
        self._ws_url = f"ws://{host}:{port}/api/ws"
        self._cmd_url = f"http://{host}:{port}/api/command"
        self._state_url = f"http://{host}:{port}/api/state"
        self._on_state = on_state
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._connect_loop(), name="bridge-ws")

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
        self._connected = False

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def send_command(self, cmd: str, value: object = None) -> bool:
        """POST a command to the bridge. Returns True on success."""
        payload: dict[str, Any] = {"cmd": cmd}
        if value is not None:
            payload["value"] = value
        try:
            session = await self._get_session()
            async with session.post(
                self._cmd_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=3.0),
            ) as resp:
                return resp.status == 200
        except Exception as exc:
            _LOG.debug("Command %s failed: %s", cmd, exc)
            return False

    async def fetch_state(self) -> dict[str, Any] | None:
        """GET the current full state from the bridge."""
        try:
            session = await self._get_session()
            async with session.get(
                self._state_url,
                timeout=aiohttp.ClientTimeout(total=3.0),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _connect_loop(self) -> None:
        while self._running:
            try:
                await self._connect()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                _LOG.debug("Bridge WS error: %s", exc)

            self._connected = False

            if not self._running:
                return

            _LOG.info("Bridge disconnected, reconnecting in %ss…", RECONNECT_DELAY)
            await asyncio.sleep(RECONNECT_DELAY)

    async def _connect(self) -> None:
        session = await self._get_session()
        _LOG.info("Connecting to bridge at %s", self._ws_url)

        async with session.ws_connect(
            self._ws_url,
            heartbeat=30,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as ws:
            self._connected = True
            _LOG.info("Bridge WebSocket connected")

            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        msg_type = data.get("type", "")
                        payload = data.get("data", {})

                        if msg_type == "state_full":
                            await self._on_state(payload, True)
                        elif msg_type == "state_patch":
                            await self._on_state(payload, False)
                    except Exception as exc:
                        _LOG.warning("WS message parse error: %s", exc)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
