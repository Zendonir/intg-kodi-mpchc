"""
UC Remote media player entity backed by the bridge hub.
"""

from __future__ import annotations

import logging
from typing import Any

from ucapi import MediaPlayer, StatusCodes
from ucapi.media_player import (
    Attributes,
    BrowseMediaItem,
    BrowseOptions,
    BrowseResults,
    Commands,
    DeviceClasses,
    Features,
    MediaClass,
    MediaContentType,
    Pagination,
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
    # Media browser (UC Remote >= 2.9.1)
    Features.BROWSE_MEDIA,
    Features.PLAY_MEDIA,
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
        # Snapshot old playlist index before merging so we can detect advances.
        old_playlist_index = self._state.get("playlist_index", -1)

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

        # Build display title: episodes use "S{s}E{e} – Title"; everything else raw.
        if "title" in patch or "season" in patch or "episode" in patch or "media_type" in patch:
            raw_title = self._state.get("title", "")
            media_type = self._state.get("media_type", "")
            season = self._state.get("season", 0)
            ep_num = self._state.get("episode", 0)
            if media_type == "episode" and raw_title and season > 0 and ep_num > 0:
                attrs[Attributes.MEDIA_TITLE] = f"S{season:02d}E{ep_num:02d} \u2013 {raw_title}"
            else:
                attrs[Attributes.MEDIA_TITLE] = raw_title

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

        if "audio_tracks" in patch or "current_audio" in patch:
            tracks = self._state.get("audio_tracks", [])
            cur_idx = self._state.get("current_audio", 0)
            attrs[Attributes.SOURCE_LIST] = [t.get("label", f"Track {i}") for i, t in enumerate(tracks)]
            if 0 <= cur_idx < len(tracks):
                attrs[Attributes.SOURCE] = tracks[cur_idx].get("label", "")

        # When the playlist advances forward, optimistically mark the completed
        # episode as watched so the browser reflects it immediately (before the
        # next Kodi state push arrives with the confirmed playcount).
        if "playlist_index" in patch:
            new_idx = patch["playlist_index"]
            if new_idx > old_playlist_index >= 0:
                episodes: list[dict[str, Any]] = self._state.get("season_episodes", [])
                if 0 <= old_playlist_index < len(episodes):
                    ep = episodes[old_playlist_index]
                    ep["playcount"] = max(ep.get("playcount", 0), 1)
                    _LOG.debug("optimistic watched mark: episode index %d", old_playlist_index)

        return attrs

    # ------------------------------------------------------------------
    # Media browser
    # ------------------------------------------------------------------
    async def browse(self, options: BrowseOptions) -> BrowseResults | StatusCodes:
        """Return the current season's episode list for the media browser widget."""
        episodes: list[dict[str, Any]] = self._state.get("season_episodes", [])

        if not episodes:
            # Nothing to browse right now (movie, music, or idle)
            return BrowseResults(
                media=None,
                pagination=Pagination(page=1, limit=0, count=0),
            )

        tv_show = self._state.get("tv_show", "")
        season = self._state.get("season", 0)
        playlist_index = self._state.get("playlist_index", -1)
        # Use current artwork as fallback thumbnail for the playing episode.
        current_artwork = self._state.get("artwork_url", "") or None

        ep_items: list[BrowseMediaItem] = []
        for i, ep in enumerate(episodes):
            watched = ep.get("playcount", 0) > 0
            resume = ep.get("resume_pos", 0.0)
            is_current = i == playlist_index

            if is_current:
                subtitle = "\u25b6 Now Playing"
            elif resume and resume > 60:
                subtitle = f"{'✓ ' if watched else ''}Resume: {int(resume // 60)}m {int(resume % 60):02d}s"
            elif watched:
                subtitle = "✓ Watched"
            else:
                subtitle = None

            # Prefer S{s}E{e} – Title; fall back to E{e} – Title.
            ep_num = ep.get("episode", i + 1)
            ep_title = ep.get("title", "")
            if season > 0 and ep_num > 0 and ep_title:
                display_title = f"S{season:02d}E{ep_num:02d} \u2013 {ep_title}"
            elif ep_title:
                display_title = f"E{ep_num:02d} \u2013 {ep_title}"
            else:
                display_title = f"Episode {ep_num}"

            # Per-episode thumbnail from bridge, fallback to current artwork when playing.
            thumbnail = (
                ep.get("thumbnail")
                or ep.get("art", {}).get("thumb")
                or (current_artwork if is_current else None)
            )

            ep_items.append(
                BrowseMediaItem(
                    media_id=str(ep.get("episodeid", i)),
                    title=display_title,
                    subtitle=subtitle,
                    media_class=MediaClass.EPISODE,
                    media_type=MediaContentType.TV_SHOW,
                    can_browse=False,
                    can_play=True,
                    thumbnail=thumbnail,
                    duration=ep.get("runtime"),
                )
            )

        season_label = f"S{season:02d} \u2013 {tv_show}" if tv_show else f"Season {season}"
        container = BrowseMediaItem(
            media_id="season",
            title=season_label,
            media_class=MediaClass.SEASON,
            media_type=MediaContentType.TV_SHOW,
            can_browse=True,
            can_play=False,
            thumbnail=current_artwork,
            items=ep_items,
        )

        return BrowseResults(
            media=container,
            pagination=Pagination(page=1, limit=len(ep_items), count=len(ep_items)),
        )

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

        if cmd_id == Commands.PLAY_MEDIA:
            media_id = str(p.get("media_id", ""))
            for ep in self._state.get("season_episodes", []):
                if str(ep.get("episodeid")) == media_id:
                    filepath = ep.get("file", "")
                    if filepath:
                        return await c.play_episode(filepath)
            _LOG.warning("PLAY_MEDIA: episode not found: %s", media_id)
            return False

        _LOG.warning("Unhandled command: %s", cmd_id)
        return False
