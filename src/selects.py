"""
Select entities for audio track, subtitle track and chapter selection.

Each BridgeSelect exposes the list of available options that arrive in
bridge state pushes and dispatches SELECT_OPTION commands back as bridge
control commands.
"""

from __future__ import annotations

from typing import Any

from ucapi import Select, StatusCodes
from ucapi.select import Attributes, Commands, States

from bridge_client import BridgeClient

# Mapping: select_type → (bridge tracks state key, bridge command name)
_TYPE_MAP: dict[str, tuple[str, str]] = {
    "audio":    ("audio_tracks",    "audio_track"),
    "subtitle": ("subtitle_tracks", "subtitle_track"),
    "chapter":  ("chapters",        "chapter"),
}

_SUBTITLE_OFF = "Off"


class BridgeSelect(Select):
    """UC Remote Select entity for audio / subtitle / chapter selection."""

    def __init__(
        self,
        device_id: str,
        select_type: str,
        name: str,
        client: BridgeClient,
    ) -> None:
        assert select_type in _TYPE_MAP, f"Unknown select type: {select_type}"
        self._select_type = select_type
        self._client = client
        self._tracks: list[dict[str, Any]] = []

        super().__init__(
            f"select.{device_id}.{select_type}",
            {"en": name},
            {
                Attributes.STATE: States.ON,
                Attributes.CURRENT_OPTION: _SUBTITLE_OFF if select_type == "subtitle" else "",
                Attributes.OPTIONS: [_SUBTITLE_OFF] if select_type == "subtitle" else [],
            },
            cmd_handler=self._handle_command,
        )

    @property
    def select_type(self) -> str:
        return self._select_type

    # ------------------------------------------------------------------
    # Command handler
    # ------------------------------------------------------------------
    async def _handle_command(
        self,
        _entity: Select,
        cmd_id: str,
        params: dict[str, Any] | None,
    ) -> StatusCodes:
        option = (params or {}).get("option", "")

        if cmd_id == Commands.SELECT_OPTION:
            ok = await self._select_option(option)
        elif cmd_id == Commands.SELECT_NEXT:
            ok = await self._step(+1)
        elif cmd_id == Commands.SELECT_PREVIOUS:
            ok = await self._step(-1)
        elif cmd_id == Commands.SELECT_FIRST:
            ok = await self._jump(0)
        elif cmd_id == Commands.SELECT_LAST:
            ok = await self._jump(-1)
        else:
            return StatusCodes.NOT_IMPLEMENTED

        return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

    async def _select_option(self, option: str) -> bool:
        _, bridge_cmd = _TYPE_MAP[self._select_type]

        if self._select_type == "subtitle" and option in (_SUBTITLE_OFF, "", "off"):
            return await self._client.send_command(bridge_cmd, -1)

        for track in self._tracks:
            if track.get("label") == option:
                return await self._client.send_command(bridge_cmd, track.get("pos", 0))
        return False

    async def _step(self, direction: int) -> bool:
        if not self._tracks:
            return False
        current = next((t.get("label") for t in self._tracks if t.get("active")), None)
        labels = [t.get("label") for t in self._tracks]
        idx = labels.index(current) if current in labels else -1
        new_idx = (idx + direction) % len(self._tracks)
        return await self._select_option(labels[new_idx])

    async def _jump(self, idx: int) -> bool:
        if not self._tracks:
            return False
        return await self._select_option(self._tracks[idx].get("label", ""))

    # ------------------------------------------------------------------
    # State updates from bridge
    # ------------------------------------------------------------------
    def apply_state(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Return attribute updates when track lists or active track changes."""
        tracks_key, _ = _TYPE_MAP[self._select_type]
        if tracks_key not in patch:
            return {}

        self._tracks = patch[tracks_key] or []
        labels = [t.get("label", f"Track {i}") for i, t in enumerate(self._tracks)]

        options = ([_SUBTITLE_OFF] + labels) if self._select_type == "subtitle" else labels

        active = next((t.get("label") for t in self._tracks if t.get("active")), None)
        if active is None and self._select_type == "subtitle":
            active = _SUBTITLE_OFF

        attrs: dict[str, Any] = {Attributes.OPTIONS: options}
        if active is not None:
            attrs[Attributes.CURRENT_OPTION] = active

        return attrs
