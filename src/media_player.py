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
    Options,
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
    # Channel up/down → relative seek (Springe)
    Features.CHANNEL_SWITCHER,
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
            options={
                Options.SIMPLE_COMMANDS: [
                    # System
                    "Zu Windows wechseln",
                    "Zu Kodi wechseln",
                    "Kodi neu starten",
                    # Tonspur
                    "Nächste Tonspur",
                    "Vorherige Tonspur",
                    # Untertitel
                    "Nächster Untertitel",
                    "Vorheriger Untertitel",
                    "Untertitel aus",
                    # Kapitel
                    "Nächstes Kapitel",
                    "Vorheriges Kapitel",
                    # Folge
                    "Nächste Folge",
                    "Vorherige Folge",
                ]
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _format_media_title(self) -> str:
        """Return episode title as ``S{s}E{e} – Title``; raw title for all other types."""
        raw = self._state.get("title", "")
        season = self._state.get("season", 0)
        ep_num = self._state.get("episode", 0)
        if self._state.get("media_type") == "episode" and raw and season > 0 and ep_num > 0:
            return f"S{season:02d}E{ep_num:02d} \u2013 {raw}"
        return raw

    def _mark_watched_if_advanced(self, old_idx: int, new_idx: int) -> None:
        """Optimistically set playcount=1 for the episode that just finished."""
        if new_idx <= old_idx or old_idx < 0:
            return
        episodes: list[dict[str, Any]] = self._state.get("season_episodes", [])
        if 0 <= old_idx < len(episodes):
            ep = episodes[old_idx]
            ep["playcount"] = max(ep.get("playcount", 0), 1)
            _LOG.debug("optimistic watched mark: episode index %d", old_idx)

    async def _seek_relative(self, client: Any, cmd_id: str, params: dict) -> bool:
        """CHANNEL_UP/DOWN → relative seek ("Springe").

        Optional param ``seconds`` (or ``value``) sets the jump amount.
        Defaults: +30 s forward, +10 s backward.
        """
        default = 30 if cmd_id == Commands.CHANNEL_UP else 10
        delta = abs(float(params.get("seconds", params.get("value", default))))
        direction = 1 if cmd_id == Commands.CHANNEL_UP else -1
        new_pos = max(0.0, float(self._state.get("position", 0)) + direction * delta)
        return await client.send_command("seek", new_pos)

    def _ep_display_title(self, ep: dict[str, Any], season: int, idx: int) -> str:
        """Format browse/select label: ``S{s}E{e} – Title`` or fallbacks."""
        ep_num = ep.get("episode", idx + 1)
        ep_title = ep.get("title", "")
        if season > 0 and ep_num > 0 and ep_title:
            return f"S{season:02d}E{ep_num:02d} \u2013 {ep_title}"
        if ep_title:
            return f"E{ep_num:02d} \u2013 {ep_title}"
        return f"Episode {ep_num}"

    def _ep_subtitle(self, ep: dict[str, Any], is_current: bool) -> str | None:
        """Return the status subtitle for a browser episode item."""
        if is_current:
            return "\u25b6 Now Playing"
        resume = ep.get("resume_pos", 0.0)
        watched = ep.get("playcount", 0) > 0
        if resume and resume > 60:
            return f"{'✓ ' if watched else ''}Resume: {int(resume // 60)}m {int(resume % 60):02d}s"
        return "✓ Watched" if watched else None

    async def _step_track(self, tracks_key: str, cur_key: str, bridge_cmd: str, direction: int) -> bool:
        tracks = self._state.get(tracks_key, [])
        if not tracks:
            return False
        cur = self._state.get(cur_key, 0)
        nxt = (max(cur, 0) + direction) % len(tracks)
        return await self._client.send_command(bridge_cmd, tracks[nxt].get("pos", nxt))

    async def _step_chapter(self, direction: int) -> bool:
        chapters = self._state.get("chapters", [])
        if not chapters:
            return False
        cur = self._state.get("current_chapter", 0)
        nxt = max(0, min(len(chapters) - 1, cur + direction))
        return await self._client.send_command("seek", chapters[nxt].get("time_ms", 0) / 1000.0)

    async def _step_episode(self, direction: int) -> bool:
        episodes = self._state.get("season_episodes", [])
        if not episodes:
            return False
        nxt = (self._state.get("playlist_index", 0) + direction) % len(episodes)
        filepath = episodes[nxt].get("file", "")
        return await self._client.play_episode(filepath) if filepath else False

    # ------------------------------------------------------------------
    # State updates from bridge
    # ------------------------------------------------------------------
    def apply_state(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge *patch* into internal state and return ucapi attribute updates."""
        old_idx = self._state.get("playlist_index", -1)
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
        if "title" in patch or "season" in patch or "episode" in patch or "media_type" in patch:
            attrs[Attributes.MEDIA_TITLE] = self._format_media_title()
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

        if "playlist_index" in patch:
            self._mark_watched_if_advanced(old_idx, patch["playlist_index"])

        return attrs

    # ------------------------------------------------------------------
    # Media browser
    # ------------------------------------------------------------------
    async def browse(self, options: BrowseOptions) -> BrowseResults | StatusCodes:
        """Return the current season's episode list for the media browser widget."""
        episodes: list[dict[str, Any]] = self._state.get("season_episodes", [])
        if not episodes:
            return BrowseResults(media=None, pagination=Pagination(page=1, limit=0, count=0))

        tv_show = self._state.get("tv_show", "")
        season = self._state.get("season", 0)
        playlist_index = self._state.get("playlist_index", -1)
        # Use current artwork as fallback thumbnail for every episode without its own image.
        current_artwork = self._state.get("artwork_url", "") or None

        ep_items: list[BrowseMediaItem] = []
        for i, ep in enumerate(episodes):
            is_current = i == playlist_index
            # Per-episode image from bridge; fall back to season/current artwork for all episodes.
            thumbnail = ep.get("thumbnail") or ep.get("art", {}).get("thumb") or current_artwork
            ep_items.append(
                BrowseMediaItem(
                    media_id=str(ep.get("episodeid", i)),
                    title=self._ep_display_title(ep, season, i),
                    subtitle=self._ep_subtitle(ep, is_current),
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
            # Custom simple commands (assigned freely to buttons on the remote)
            "Zu Windows wechseln": ("switch_to_desktop", None),
            "Zu Kodi wechseln": ("switch_to_kodi", None),
            "Kodi neu starten": ("restart_kodi", None),
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

        if cmd_id in (Commands.CHANNEL_UP, Commands.CHANNEL_DOWN):
            return await self._seek_relative(c, cmd_id, p)

        if cmd_id == Commands.PLAY_MEDIA:
            media_id = str(p.get("media_id", ""))
            for ep in self._state.get("season_episodes", []):
                if str(ep.get("episodeid")) == media_id:
                    filepath = ep.get("file", "")
                    if filepath:
                        return await c.play_episode(filepath)
            _LOG.warning("PLAY_MEDIA: episode not found: %s", media_id)
            return False

        if cmd_id == "Nächste Tonspur":
            return await self._step_track("audio_tracks", "current_audio", "audio_track", +1)
        if cmd_id == "Vorherige Tonspur":
            return await self._step_track("audio_tracks", "current_audio", "audio_track", -1)
        if cmd_id == "Nächster Untertitel":
            return await self._step_track("subtitle_tracks", "current_subtitle", "subtitle_track", +1)
        if cmd_id == "Vorheriger Untertitel":
            return await self._step_track("subtitle_tracks", "current_subtitle", "subtitle_track", -1)
        if cmd_id == "Untertitel aus":
            return await c.send_command("subtitle_track", -1)
        if cmd_id == "Nächstes Kapitel":
            return await self._step_chapter(+1)
        if cmd_id == "Vorheriges Kapitel":
            return await self._step_chapter(-1)
        if cmd_id == "Nächste Folge":
            return await self._step_episode(+1)
        if cmd_id == "Vorherige Folge":
            return await self._step_episode(-1)

        _LOG.warning("Unhandled command: %s", cmd_id)
        return False
