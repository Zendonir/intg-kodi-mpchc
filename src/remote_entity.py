"""
Pre-configured remote entity for the Kodi / MPC-HC bridge.

Appears under "Externe Fernbedienungen" in the UC Remote app and provides
a ready-made button layout with three pages:
  1. Wiedergabe  — playback & volume controls
  2. Navigation  — D-pad, back/home, info/menu
  3. System      — switch to Kodi/Windows, restart Kodi
"""

from __future__ import annotations

from ucapi import Remote, StatusCodes
from ucapi.remote import Attributes, Features, States, create_send_cmd
from ucapi.ui import Buttons, Size, UiPage, create_btn_mapping, create_ui_icon, create_ui_text

from bridge_client import BridgeClient
from config import DeviceConfig


def _build_button_mapping() -> list:
    """Map physical remote buttons to bridge commands."""
    return [
        create_btn_mapping(Buttons.PLAY, short=create_send_cmd("play_pause")),
        create_btn_mapping(Buttons.STOP, short=create_send_cmd("stop")),
        create_btn_mapping(Buttons.NEXT, short=create_send_cmd("next_chapter")),
        create_btn_mapping(Buttons.PREV, short=create_send_cmd("prev_chapter")),
        create_btn_mapping(Buttons.VOLUME_UP, short=create_send_cmd("volume_up")),
        create_btn_mapping(Buttons.VOLUME_DOWN, short=create_send_cmd("volume_down")),
        create_btn_mapping(Buttons.MUTE, short=create_send_cmd("mute")),
        create_btn_mapping(Buttons.DPAD_UP, short=create_send_cmd("navigate_up")),
        create_btn_mapping(Buttons.DPAD_DOWN, short=create_send_cmd("navigate_down")),
        create_btn_mapping(Buttons.DPAD_LEFT, short=create_send_cmd("navigate_left")),
        create_btn_mapping(Buttons.DPAD_RIGHT, short=create_send_cmd("navigate_right")),
        create_btn_mapping(Buttons.DPAD_MIDDLE, short=create_send_cmd("navigate_select")),
        create_btn_mapping(Buttons.BACK, short=create_send_cmd("navigate_back")),
        create_btn_mapping(Buttons.HOME, short=create_send_cmd("navigate_home")),
        create_btn_mapping(Buttons.CHANNEL_UP, short=create_send_cmd("skip_forward")),
        create_btn_mapping(Buttons.CHANNEL_DOWN, short=create_send_cmd("skip_backward")),
        create_btn_mapping(Buttons.MENU, short=create_send_cmd("context_menu")),
    ]


def _build_page_playback() -> UiPage:
    """Page 1 — Wiedergabe."""
    items = [
        # Row 0: stop | play | -10s | +30s
        create_ui_icon("uc:stop", 0, 0, cmd=create_send_cmd("stop")),
        create_ui_icon("uc:play", 1, 0, cmd=create_send_cmd("play_pause")),
        create_ui_icon("uc:skip-back", 2, 0, cmd=create_send_cmd("skip_backward")),
        create_ui_icon("uc:skip-fwd", 3, 0, cmd=create_send_cmd("skip_forward")),
        # Row 1: previous | next
        create_ui_icon("uc:prev", 0, 1, cmd=create_send_cmd("prev_chapter")),
        create_ui_icon("uc:next", 1, 1, cmd=create_send_cmd("next_chapter")),
        # Row 2: vol- | mute | vol+
        create_ui_icon("uc:vol-down", 0, 2, cmd=create_send_cmd("volume_down")),
        create_ui_icon("uc:mute", 1, 2, cmd=create_send_cmd("mute")),
        create_ui_icon("uc:vol-up", 2, 2, cmd=create_send_cmd("volume_up")),
    ]
    return UiPage("playback", "Wiedergabe", grid=Size(4, 3), items=items)


def _build_page_navigation() -> UiPage:
    """Page 2 — Navigation."""
    items = [
        # Row 0: [  ] up [  ] info
        create_ui_icon("uc:up", 1, 0, cmd=create_send_cmd("navigate_up")),
        create_ui_icon("uc:info", 3, 0, cmd=create_send_cmd("show_info")),
        # Row 1: left | ok | right | menu
        create_ui_icon("uc:left", 0, 1, cmd=create_send_cmd("navigate_left")),
        create_ui_icon("uc:ok", 1, 1, cmd=create_send_cmd("navigate_select")),
        create_ui_icon("uc:right", 2, 1, cmd=create_send_cmd("navigate_right")),
        create_ui_icon("uc:menu", 3, 1, cmd=create_send_cmd("context_menu")),
        # Row 2: [  ] down [  ] [  ]
        create_ui_icon("uc:down", 1, 2, cmd=create_send_cmd("navigate_down")),
        # Row 3: back | home
        create_ui_icon("uc:back", 0, 3, cmd=create_send_cmd("navigate_back")),
        create_ui_icon("uc:home", 1, 3, cmd=create_send_cmd("navigate_home")),
    ]
    return UiPage("navigation", "Navigation", grid=Size(4, 4), items=items)


def _build_page_system() -> UiPage:
    """Page 3 — System."""
    items = [
        create_ui_text("Zu Kodi wechseln", 0, 0, size=Size(4, 1), cmd=create_send_cmd("switch_to_kodi")),
        create_ui_text("Zu Windows wechseln", 0, 1, size=Size(4, 1), cmd=create_send_cmd("switch_to_desktop")),
        create_ui_text("Kodi neu starten", 0, 2, size=Size(4, 1), cmd=create_send_cmd("restart_kodi")),
    ]
    return UiPage("system", "System", grid=Size(4, 3), items=items)


_SIMPLE_COMMANDS = [
    "play_pause",
    "stop",
    "next_chapter",
    "prev_chapter",
    "skip_forward",
    "skip_backward",
    "volume_up",
    "volume_down",
    "mute",
    "navigate_up",
    "navigate_down",
    "navigate_left",
    "navigate_right",
    "navigate_select",
    "navigate_back",
    "navigate_home",
    "context_menu",
    "show_info",
    "switch_to_kodi",
    "switch_to_desktop",
    "restart_kodi",
]


# pylint: disable=too-few-public-methods
class BridgeRemote(Remote):
    """Pre-configured remote for the Kodi / MPC-HC bridge."""

    def __init__(self, cfg: DeviceConfig, client: BridgeClient) -> None:
        self._client = client
        super().__init__(
            f"remote.{cfg.id}",
            {"en": cfg.name, "de": cfg.name},
            features=[Features.SEND_CMD],
            attributes={Attributes.STATE: States.ON},
            simple_commands=_SIMPLE_COMMANDS,
            button_mapping=_build_button_mapping(),
            ui_pages=[
                _build_page_playback(),
                _build_page_navigation(),
                _build_page_system(),
            ],
            cmd_handler=self._handle_command,
        )

    async def _handle_command(
        self,
        _entity: Remote,
        cmd_id: str,
        params: dict | None,
    ) -> StatusCodes:
        bridge_cmd = (params or {}).get("command", "")
        if not bridge_cmd:
            return StatusCodes.BAD_REQUEST
        ok = await self._client.send_command(bridge_cmd, None)
        return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR
