"""
Select entities for audio track, subtitle track and chapter selection.

Each BridgeSelect exposes the list of available options that arrive in
bridge state pushes and dispatches SELECT_OPTION commands back as bridge
control commands.

Chapter note: the bridge exposes no direct "jump to chapter N" command.
Selecting a chapter is implemented by seeking to its timestamp (time_ms).
"""

from __future__ import annotations

from typing import Any

from ucapi import Select, StatusCodes
from ucapi.select import Attributes, Commands, States

from bridge_client import BridgeClient

# Mapping: select_type → (bridge tracks key, bridge command name, bridge current-index key)
# The chapter "command" column is unused — chapter selection uses seek instead.
_TYPE_MAP: dict[str, tuple[str, str, str]] = {
    "audio": ("audio_tracks", "audio_track", "current_audio"),
    "subtitle": ("subtitle_tracks", "subtitle_track", "current_subtitle"),
    "chapter": ("chapters", "chapter", "current_chapter"),
}

_SUBTITLE_OFF = "Off"


def _track_label(track: dict[str, Any], idx: int) -> str:
    """Return a display label for a track.

    Audio/subtitle tracks carry a pre-formatted ``label`` key.
    Chapter objects use ``name`` instead.  Fall back to ``"Track N"`` when
    neither is present (should not happen in practice).
    """
    return track.get("label") or track.get("name") or f"Track {idx}"


class BridgeEpisodeSelect(Select):
    """Select entity for navigating episodes within the current TV season.

    Options are populated from the bridge's ``season_episodes`` state field
    (available only when Kodi is playing a TV episode).  Selecting an episode
    calls ``POST /api/external_play`` with the episode's file path, which
    triggers the bridge's resume dialog and launches MPC-HC.
    """

    def __init__(self, device_id: str, client: BridgeClient) -> None:
        self._client = client
        self._episodes: list[dict[str, Any]] = []
        self._playlist_index: int = -1
        self._season: int = 0

        super().__init__(
            f"select.{device_id}.episode",
            {"en": "Episode", "de": "Episode"},
            {
                Attributes.STATE: States.ON,
                Attributes.CURRENT_OPTION: "",
                Attributes.OPTIONS: [],
            },
            cmd_handler=self._handle_command,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _episode_label(self, ep: dict[str, Any]) -> str:
        """Format ``S01E01 – Title`` (or ``E01 – Title`` when season unknown)."""
        num = ep.get("episode", 0)
        title = ep.get("title", "").strip()
        if title:
            if self._season > 0:
                return f"S{self._season:02d}E{num:02d} \u2013 {title}"
            return f"E{num:02d} \u2013 {title}"
        return f"Episode {num}"

    def _label_at(self, idx: int) -> str:
        if 0 <= idx < len(self._episodes):
            return self._episode_label(self._episodes[idx])
        return ""

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
            ok = await self._play_by_label(option)
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

    async def _play_by_label(self, label: str) -> bool:
        for ep in self._episodes:
            if self._episode_label(ep) == label:
                filepath = ep.get("file", "")
                if not filepath:
                    return False
                return await self._client.play_episode(filepath)
        return False

    async def _step(self, direction: int) -> bool:
        if not self._episodes:
            return False
        base = max(self._playlist_index, 0)
        new_idx = (base + direction) % len(self._episodes)
        return await self._play_by_label(self._label_at(new_idx))

    async def _jump(self, idx: int) -> bool:
        if not self._episodes:
            return False
        target = idx if idx >= 0 else len(self._episodes) + idx
        return await self._play_by_label(self._label_at(target))

    # ------------------------------------------------------------------
    # State updates from bridge
    # ------------------------------------------------------------------
    def apply_state(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Return attribute updates when the episode list or current index changes."""
        if "season_episodes" not in patch and "playlist_index" not in patch and "season" not in patch:
            return {}

        if "season" in patch:
            self._season = patch["season"] or 0
        if "season_episodes" in patch:
            self._episodes = patch["season_episodes"] or []
        if "playlist_index" in patch:
            self._playlist_index = patch["playlist_index"]

        labels = [self._episode_label(ep) for ep in self._episodes]

        if 0 <= self._playlist_index < len(self._episodes):
            current = labels[self._playlist_index]
        else:
            current = labels[0] if labels else ""

        return {
            Attributes.OPTIONS: labels,
            Attributes.CURRENT_OPTION: current,
        }


class BridgeSelect(Select):
    """UC Remote Select entity for audio / subtitle / chapter selection."""

    def __init__(
        self,
        device_id: str,
        select_type: str,
        name: str | dict[str, str],
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
            {"en": name} if isinstance(name, str) else name,
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
            if _track_label(track, i) == option:
                if self._select_type == "chapter":
                    # The bridge has no direct "jump to chapter N" command.
                    # Seek to the chapter's start timestamp instead.
                    time_s = track.get("time_ms", 0) / 1000.0
                    return await self._client.send_command("seek", time_s)
                return await self._client.send_command(bridge_cmd, track.get("pos", i))
        return False

    def _label_at(self, idx: int) -> str:
        """Return the display label for track at *idx*."""
        if 0 <= idx < len(self._tracks):
            return _track_label(self._tracks[idx], idx)
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

        labels = [_track_label(t, i) for i, t in enumerate(self._tracks)]
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
