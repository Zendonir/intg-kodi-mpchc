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

# On EXIT_STANDBY the UC Remote may deliver the event before its Wi-Fi route
# is usable again. Retry quickly for a short window instead of waiting for the
# regular RECONNECT_DELAY (pattern from albaintor/integration-kodi v1.21.2).
WAKE_RECONNECT_RETRIES = 10
WAKE_RECONNECT_INTERVAL = 0.5

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
        _base = f"http://{host}:{port}"
        self._base_url = _base
        self._ws_url = f"ws://{host}:{port}/api/ws"
        self._cmd_url = f"{_base}/api/command"
        self._state_url = f"{_base}/api/state"
        self._external_play_url = f"{_base}/api/external_play"
        self._browse_url = f"{_base}/api/browse"
        self._browse_play_url = f"{_base}/api/browse/play"
        self._on_state = on_state
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._connected = False
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        # Set to cut the reconnect back-off short (see wake()).
        self._wake_event = asyncio.Event()
        # Remaining reconnect attempts that use the short wake interval.
        self._fast_retries = 0

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._running and self._task and not self._task.done():
            return  # already running — do not create a second loop
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

    async def wake(self) -> None:
        """Re-establish the bridge link quickly after the UC Remote woke up.

        * Not connected: interrupt the reconnect back-off and retry every
          ~500 ms for a few attempts while the remote's network comes back.
        * Connected: verify the link with a state fetch. If the bridge does not
          answer, the socket is most likely half-open after the remote slept —
          drop it so the reconnect loop takes over with fast retries.
          Otherwise the fresh state is pushed to the entities.
        """
        if not self._running:
            self.start()
        if self._connected:
            current = await self.fetch_state()
            if current is not None:
                await self._on_state(current, True)
                return
            _LOG.info("Bridge did not answer after wake — forcing reconnect")
            if self._ws is not None and not self._ws.closed:
                await self._ws.close()
        self._fast_retries = WAKE_RECONNECT_RETRIES
        self._wake_event.set()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    # Integration-side virtual command names that map to dedicated kiosk
    # REST endpoints instead of the generic /api/command route.
    _KIOSK_ROUTES: dict[str, str] = {
        "switch_to_kodi": "/api/kiosk/kodi",
        "switch_to_desktop": "/api/kiosk/windows",
        "restart_kodi": "/api/kiosk/restart",
        # ON / OFF map to focus Kodi / restore Windows
        "launch": "/api/kiosk/kodi",
        "quit": "/api/kiosk/windows",
    }
    # Commands that don't exist in the bridge but have a valid equivalent.
    _CMD_REMAP: dict[str, str] = {
        "toggle": "kodi_windows",
    }

    async def send_command(self, cmd: str, value: object = None) -> bool:
        """POST a command to the bridge. Returns True on success."""
        # Route kiosk-style virtual commands to their own REST endpoints.
        kiosk_path = self._KIOSK_ROUTES.get(cmd)
        if kiosk_path:
            try:
                session = await self._get_session()
                async with session.post(
                    f"{self._base_url}{kiosk_path}",
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as resp:
                    return resp.status == 200
            except Exception as exc:
                _LOG.debug("Kiosk command %s failed: %s", cmd, exc)
                return False

        # Remap commands that have been renamed in the bridge API.
        cmd = self._CMD_REMAP.get(cmd, cmd)

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

    async def play_episode(self, filepath: str) -> bool:
        """POST /api/external_play to start playback of a specific file.

        The bridge shows a resume dialog when applicable and launches the
        external player (MPC-HC) at the saved resume position.
        """
        try:
            session = await self._get_session()
            async with session.post(
                self._external_play_url,
                json={"filepath": filepath},
                timeout=aiohttp.ClientTimeout(total=5.0),
            ) as resp:
                return resp.status == 200
        except Exception as exc:
            _LOG.debug("play_episode failed: %s", exc)
            return False

    async def browse(self, item_id: str) -> dict[str, Any] | None:
        """GET /api/browse — Kodi favourites / PVR / add-ons listing.

        Returns ``None`` when the folder is unknown, the bridge is unreachable
        or the bridge is too old to provide the browse API.
        """
        try:
            session = await self._get_session()
            async with session.get(
                self._browse_url,
                params={"id": item_id},
                timeout=aiohttp.ClientTimeout(total=8.0),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                _LOG.debug("browse %s → HTTP %s", item_id, resp.status)
        except Exception as exc:
            _LOG.debug("browse %s failed: %s", item_id, exc)
        return None

    async def browse_play(self, item_id: str) -> bool:
        """POST /api/browse/play — start a browse item (channel, add-on, favourite)."""
        try:
            session = await self._get_session()
            async with session.post(
                self._browse_play_url,
                json={"id": item_id},
                timeout=aiohttp.ClientTimeout(total=5.0),
            ) as resp:
                return resp.status == 200
        except Exception as exc:
            _LOG.debug("browse_play %s failed: %s", item_id, exc)
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
        attempt = 0
        while self._running:
            try:
                attempt += 1
                await self._connect()
                attempt = 0  # reset on clean disconnect
            except asyncio.CancelledError:
                return
            except Exception as exc:
                if attempt == 1:
                    _LOG.warning(
                        "Cannot reach bridge at %s — check host/port and firewall. Error: %s",
                        self._ws_url,
                        exc,
                    )
                else:
                    _LOG.debug("Bridge WS error (attempt %d): %s", attempt, exc)

            self._connected = False
            self._ws = None

            if not self._running:
                return

            if self._fast_retries > 0:
                self._fast_retries -= 1
                delay = WAKE_RECONNECT_INTERVAL
            else:
                delay = RECONNECT_DELAY
            _LOG.info("Bridge disconnected, retry #%d in %ss…", attempt, delay)
            await self._backoff(delay)

    async def _backoff(self, delay: float) -> None:
        """Sleep *delay* seconds, or less if wake() asks for an immediate retry."""
        try:
            await asyncio.wait_for(self._wake_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass
        self._wake_event.clear()

    async def _connect(self) -> None:
        session = await self._get_session()
        _LOG.info("Connecting to bridge at %s", self._ws_url)

        async with session.ws_connect(
            self._ws_url,
            heartbeat=30,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as ws:
            self._ws = ws
            self._connected = True
            self._fast_retries = 0
            self._wake_event.clear()
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
