"""
UC Remote media player entity backed by the bridge hub.
"""

from __future__ import annotations

import logging
from typing import Any

from ucapi import MediaPlayer, StatusCodes
from ucapi.media_player import (
    Attributes,
    Commands,
    DeviceClasses,
    Features,
    MediaContentType,
    States,
)

from bridge_client import BridgeClient
from config import DeviceConfig

_LOG = logging.getLogger(__name__)

_FEATURES = [
    Features.ON_OFF,
    Features.TOGGLE,
    Features.PLAY_PAUSE,
    Features.STOP,
    Features.NEXT,
    Features.PREVIOUS,
    Features.FAST_FORWARD,
    Features.REWIND,
    Features.MEDIA_DURATION,
    Features.MEDIA_POSITION,
    Features.MEDIA_TITLE,
    Features.MEDIA_ARTIST,
    Features.MEDIA_ALBUM,
    Features.MEDIA_IMAGE_URL,
    Features.MEDIA_TYPE,
    Features.VOLUME,
    Features.VOLUME_UP_DOWN,
    Features.MUTE_TOGGLE,
    Features.SHUFFLE,
    Features.REPEAT,
    Features.SEEK,
    Features.DPAD,
    Features.NUMPAD,
    Features.CONTEXT_MENU,
    Features.INFO,
    Features.SETTINGS,
]

# bridge unified state → ucapi state
_STATE_MAP = {
    "playing": States.PLAYING,
    "paused": States.PAUSED,
    "stopped": States.STANDBY,
    "idle": States.STANDBY,
}

# bridge media_type → ucapi MediaContentType
_MEDIA_TYPE_MAP = {
    "movie": MediaContentType.MOVIE,
    "episode": MediaContentType.TV_SHOW,
    "music": MediaContentType.MUSIC,
    "other": MediaContentType.VIDEO,
    "": MediaContentType.VIDEO,
}


class BridgeMediaPlayer(MediaPlayer):
    """UC Remote MediaPlayer entity connected to the bridge hub."""

    def __init__(self, cfg: DeviceConfig, client: BridgeClient) -> None:
        self._cfg = cfg
        self._client = client
        self._state: dict[str, Any] = {}

        entity_id = f"media_player.{cfg.id}"
        super().__init__(
            entity_id,
            cfg.name,
            _FEATURES,
            {
                Attributes.STATE: States.STANDBY,
                Attributes.MEDIA_TYPE: MediaContentType.VIDEO,
                Attributes.VOLUME: 0,
                Attributes.MUTED: False,
                Attributes.SHUFFLE: False,
                Attributes.REPEAT: "off",
            },
            device_class=DeviceClasses.TV,
        )

    # ------------------------------------------------------------------
    # State updates from bridge
    # ------------------------------------------------------------------
    def apply_state(self, patch: dict[str, Any]) -> dict[str, Any]:
        """
        Merge *patch* into internal state and return ucapi attribute updates.
        """
        self._state.update(patch)
        attrs: dict[str, Any] = {}

        if "state" in patch or "active_player" in patch:
            bridge_state = self._state.get("state", "idle")
            active = self._state.get("active_player", "none")
            if active == "none":
                attrs[Attributes.STATE] = States.STANDBY
            else:
                attrs[Attributes.STATE] = _STATE_MAP.get(bridge_state, States.STANDBY)

        if "position" in patch:
            attrs[Attributes.MEDIA_POSITION] = int(patch["position"])
        if "duration" in patch:
            attrs[Attributes.MEDIA_DURATION] = int(patch["duration"])
        if "title" in patch:
            attrs[Attributes.MEDIA_TITLE] = patch["title"]
        if "artist" in patch:
            attrs[Attributes.MEDIA_ARTIST] = patch["artist"]
        if "album" in patch:
            attrs[Attributes.MEDIA_ALBUM] = patch["album"]
        if "artwork_url" in patch:
            attrs[Attributes.MEDIA_IMAGE_URL] = patch["artwork_url"]
        if "media_type" in patch:
            attrs[Attributes.MEDIA_TYPE] = _MEDIA_TYPE_MAP.get(patch["media_type"], MediaContentType.VIDEO)
        if "volume" in patch:
            attrs[Attributes.VOLUME] = patch["volume"]
        if "muted" in patch:
            attrs[Attributes.MUTED] = patch["muted"]
        if "shuffle" in patch:
            attrs[Attributes.SHUFFLE] = patch["shuffle"]
        if "repeat" in patch:
            attrs[Attributes.REPEAT] = patch["repeat"]

        return attrs

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def command(self, cmd_id: str, params: dict[str, Any] | None = None) -> StatusCodes:
        _LOG.debug("command %s %s", cmd_id, params)
        ok = await self._dispatch(cmd_id, params)
        return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

    async def _dispatch(self, cmd_id: str, params: dict | None) -> bool:
        c = self._client
        p = params or {}

        cmd_map: dict[str, tuple[str, Any]] = {
            Commands.ON: ("launch", None),
            Commands.OFF: ("quit", None),
            Commands.TOGGLE: ("toggle", None),
            Commands.PLAY_PAUSE: ("play_pause", None),
            Commands.STOP: ("stop", None),
            Commands.NEXT: ("next_chapter", None),
            Commands.PREVIOUS: ("prev_chapter", None),
            Commands.FAST_FORWARD: ("skip_forward", None),
            Commands.REWIND: ("skip_backward", None),
            Commands.VOLUME_UP: ("volume_up", None),
            Commands.VOLUME_DOWN: ("volume_down", None),
            Commands.MUTE_TOGGLE: ("mute", None),
            Commands.SHUFFLE: ("shuffle", None),
            Commands.CURSOR_UP: ("navigate_up", None),
            Commands.CURSOR_DOWN: ("navigate_down", None),
            Commands.CURSOR_LEFT: ("navigate_left", None),
            Commands.CURSOR_RIGHT: ("navigate_right", None),
            Commands.CURSOR_ENTER: ("navigate_select", None),
            Commands.BACK: ("navigate_back", None),
            Commands.HOME: ("navigate_home", None),
            Commands.CONTEXT_MENU: ("context_menu", None),
            Commands.INFO: ("show_info", None),
            Commands.SETTINGS: ("navigate_home", None),
        }

        if cmd_id in cmd_map:
            bridge_cmd, val = cmd_map[cmd_id]
            return await c.send_command(bridge_cmd, val)

        if cmd_id == Commands.SEEK:
            pos = p.get("media_position", 0)
            return await c.send_command("seek", pos)

        if cmd_id == Commands.VOLUME:
            vol = p.get("volume", 0)
            return await c.send_command("set_volume", vol)

        if cmd_id == Commands.REPEAT:
            mode = p.get("repeat", "off")
            return await c.send_command("repeat", mode)

        _LOG.warning("Unhandled command: %s", cmd_id)
        return False
