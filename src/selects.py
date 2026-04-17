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

# Mapping: select_type → (bridge tracks key, bridge command name, bridge current-index key)
_TYPE_MAP: dict[str, tuple[str, str, str]] = {
    "audio": ("audio_tracks", "audio_track", "current_audio"),
    "subtitle": ("subtitle_tracks", "subtitle_track", "current_subtitle"),
    "chapter": ("chapters", "chapter", "current_chapter"),
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
        self._current_idx: int = -1 if select_type == "subtitle" else 0

        # All selects start empty — the UC Remote hides selects that have
        # exactly 1 option at registration time.  Real options arrive via
        # apply_state() once the bridge pushes state.
        super().__init__(
            f"select.{device_id}.{select_type}",
            {"en": name},
            {
                Attributes.STATE: States.ON,
                Attributes.CURRENT_OPTION: "",
                Attributes.OPTIONS: [],
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
        _, bridge_cmd, _ = _TYPE_MAP[self._select_type]

        if self._select_type == "subtitle" and option in (_SUBTITLE_OFF, "", "off"):
            return await self._client.send_command(bridge_cmd, -1)

        for i, track in enumerate(self._tracks):
            # Use the same fallback label as apply_state so label-less tracks (e.g. chapters) match.
            label = track.get("label", f"Track {i}")
            if label == option:
                return await self._client.send_command(bridge_cmd, track.get("pos", i))
        return False

    def _label_at(self, idx: int) -> str:
        """Return the display label for track at *idx*, using the same fallback as apply_state."""
        if 0 <= idx < len(self._tracks):
            return self._tracks[idx].get("label", f"Track {idx}")
        return ""

    async def _step(self, direction: int) -> bool:
        if not self._tracks:
            return False
        base = max(self._current_idx, 0)
        new_idx = (base + direction) % len(self._tracks)
        return await self._select_option(self._label_at(new_idx))

    async def _jump(self, idx: int) -> bool:
        if not self._tracks:
            return False
        target = idx if idx >= 0 else len(self._tracks) + idx
        return await self._select_option(self._label_at(target))

    # ------------------------------------------------------------------
    # State updates from bridge
    # ------------------------------------------------------------------
    def apply_state(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Return attribute updates when track lists or current index changes."""
        tracks_key, _, current_key = _TYPE_MAP[self._select_type]
        if tracks_key not in patch and current_key not in patch:
            return {}

        if tracks_key in patch:
            self._tracks = patch[tracks_key] or []

        if current_key in patch:
            self._current_idx = patch[current_key]

        labels = [t.get("label", f"Track {i}") for i, t in enumerate(self._tracks)]
        if self._select_type == "subtitle":
            options = [_SUBTITLE_OFF] + labels
        else:
            options = labels

        if self._select_type == "subtitle":
            if self._current_idx < 0 or self._current_idx >= len(self._tracks):
                current_label = _SUBTITLE_OFF
            else:
                # labels already includes the f"Track {i}" fallback for label-less tracks
                current_label = labels[self._current_idx]
        else:
            if 0 <= self._current_idx < len(self._tracks):
                current_label = labels[self._current_idx]
            else:
                current_label = labels[0] if labels else ""

        attrs: dict[str, Any] = {
            Attributes.OPTIONS: options,
            Attributes.CURRENT_OPTION: current_label,
        }
        return attrs
