"""
Read-only sensor entities for bridge state values.

One BridgeSensor is created per bridge state key (title, artist, volume, …).
"""

from __future__ import annotations

from typing import Any

from ucapi import Sensor
from ucapi.sensor import Attributes, DeviceClasses, Options, States

# (state_key, English name, device_class, unit, decimals)
SENSOR_DEFS: list[tuple[str, str, DeviceClasses, str | None, int | None]] = [
    # Playback
    ("active_player",       "Active Player",   DeviceClasses.CUSTOM, None,    None),
    ("state",               "Playback State",  DeviceClasses.CUSTOM, None,    None),
    ("title",               "Title",           DeviceClasses.CUSTOM, None,    None),
    ("artist",              "Artist",          DeviceClasses.CUSTOM, None,    None),
    ("album",               "Album",           DeviceClasses.CUSTOM, None,    None),
    ("media_type",          "Media Type",      DeviceClasses.CUSTOM, None,    None),
    ("position",            "Position",        DeviceClasses.CUSTOM, "s",     0),
    ("duration",            "Duration",        DeviceClasses.CUSTOM, "s",     0),
    ("volume",              "Volume",          DeviceClasses.CUSTOM, "%",     0),
    ("muted",               "Muted",           DeviceClasses.BINARY, None,    None),
    ("shuffle",             "Shuffle",         DeviceClasses.BINARY, None,    None),
    ("repeat",              "Repeat",          DeviceClasses.CUSTOM, None,    None),
    # Video / stream info
    ("video_width",         "Width",           DeviceClasses.CUSTOM, "px",    0),
    ("video_height",        "Height",          DeviceClasses.CUSTOM, "px",    0),
    ("video_fps",           "Frame Rate",      DeviceClasses.CUSTOM, "fps",   3),
    ("hdr",                 "HDR",             DeviceClasses.CUSTOM, None,    None),
    ("video_codec",         "Video Codec",     DeviceClasses.CUSTOM, None,    None),
    ("video_bitrate_kbps",  "Bitrate",         DeviceClasses.CUSTOM, "kbps",  0),
]


_ZERO_IS_EMPTY = frozenset({
    "video_width", "video_height", "video_fps", "video_bitrate_kbps",
    "position", "duration",
})


def _format_value(state_key: str, raw: Any) -> str:
    """Convert a raw bridge value to a display-friendly string."""
    if state_key in ("muted", "shuffle"):
        return "On" if raw else "Off"
    if isinstance(raw, bool):
        return "On" if raw else "Off"
    # Show nothing for numeric "zero" fields when nothing is playing
    if state_key in _ZERO_IS_EMPTY and raw == 0:
        return ""
    # Show SDR instead of empty string for HDR field
    if state_key == "hdr":
        return raw if raw else "SDR"
    return str(raw) if raw is not None else ""


class BridgeSensor(Sensor):
    """UC Remote Sensor entity backed by a single bridge state field."""

    def __init__(
        self,
        device_id: str,
        state_key: str,
        name: str,
        device_class: DeviceClasses,
        unit: str | None = None,
        decimals: int | None = None,
    ) -> None:
        self._state_key = state_key

        opts: dict[str, Any] = {}
        if unit:
            opts[Options.CUSTOM_UNIT] = unit
        if decimals is not None:
            opts[Options.DECIMALS] = decimals

        super().__init__(
            f"sensor.{device_id}.{state_key}",
            {"en": name},
            [],
            {
                Attributes.STATE: States.ON,
                Attributes.VALUE: "",
            },
            device_class=device_class,
            options=opts or None,
        )

    @property
    def state_key(self) -> str:
        return self._state_key

    def apply_state(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Return attribute updates when the watched state key is present in *patch*."""
        if self._state_key not in patch:
            return {}
        return {
            Attributes.STATE: States.ON,
            Attributes.VALUE: _format_value(self._state_key, patch[self._state_key]),
        }
