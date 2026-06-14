"""
Entities for the optional HTPC WiFi power-control device.

Two entities are created per configured device (only when an HTPC IP is set):

* HtpcRemote  — a Remote entity with power on/off/toggle, reset and a
  force-off command. Its STATE reflects the PC power state (ON / OFF).
* HtpcSensor  — a binary sensor that surfaces the PC power state explicitly.
"""

from __future__ import annotations

from typing import Any

from ucapi import Remote, Sensor, StatusCodes
from ucapi.remote import Attributes, Commands, Features, States, create_send_cmd
from ucapi.sensor import Attributes as SensorAttributes
from ucapi.sensor import DeviceClasses as SensorDeviceClasses
from ucapi.sensor import States as SensorStates
from ucapi.ui import Buttons, Size, UiPage, create_btn_mapping, create_ui_text

from config import DeviceConfig
from htpc_client import HtpcClient

# Freely assignable simple commands exposed to the UC Remote profile editor.
HTPC_SIMPLE_COMMANDS = ["power_on", "power_off", "force_off", "reset", "toggle"]


def _power_to_state(power: str) -> States:
    if power == "on":
        return States.ON
    if power == "off":
        return States.OFF
    return States.UNKNOWN


def _build_page() -> UiPage:
    """Single UI page with the four power actions."""
    items = [
        create_ui_text("PC einschalten", 0, 0, size=Size(4, 1), cmd=create_send_cmd("power_on")),
        create_ui_text("PC ausschalten", 0, 1, size=Size(4, 1), cmd=create_send_cmd("power_off")),
        create_ui_text("PC zurücksetzen", 0, 2, size=Size(4, 1), cmd=create_send_cmd("reset")),
        create_ui_text("Hart ausschalten", 0, 3, size=Size(4, 1), cmd=create_send_cmd("force_off")),
    ]
    return UiPage("htpc", "PC", grid=Size(4, 4), items=items)


# pylint: disable=too-few-public-methods
class HtpcRemote(Remote):
    """Remote entity that controls the PC power via the HTPC device."""

    def __init__(self, cfg: DeviceConfig, client: HtpcClient) -> None:
        self._client = client
        super().__init__(
            f"remote.{cfg.id}.htpc",
            {"en": f"{cfg.name} PC", "de": f"{cfg.name} PC"},
            features=[Features.ON_OFF, Features.TOGGLE, Features.SEND_CMD],
            attributes={Attributes.STATE: States.UNKNOWN},
            simple_commands=HTPC_SIMPLE_COMMANDS,
            button_mapping=[create_btn_mapping(Buttons.POWER, short=create_send_cmd("toggle"))],
            ui_pages=[_build_page()],
            cmd_handler=self._handle_command,
        )

    def apply_power(self, power: str) -> dict[str, Any]:
        """Return attribute updates for a new power value."""
        return {Attributes.STATE: _power_to_state(power)}

    async def _handle_command(self, _entity: Remote, cmd_id: str, params: dict | None) -> StatusCodes:
        ok = await self._dispatch(cmd_id, params)
        return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

    async def _dispatch(self, cmd_id: str, params: dict | None) -> bool:
        if cmd_id == Commands.ON:
            return await self._client.power_on()
        if cmd_id == Commands.OFF:
            return await self._client.power_off()
        if cmd_id == Commands.TOGGLE:
            return await self._client.toggle()
        if cmd_id == Commands.SEND_CMD:
            return await self._run_simple((params or {}).get("command", ""))
        if cmd_id == Commands.SEND_CMD_SEQUENCE:
            ok = True
            for command in (params or {}).get("sequence", []):
                ok = await self._run_simple(command) and ok
            return ok
        return False

    async def _run_simple(self, command: str) -> bool:
        actions = {
            "power_on": self._client.power_on,
            "power_off": self._client.power_off,
            "force_off": self._client.force_off,
            "reset": self._client.reset,
            "toggle": self._client.toggle,
        }
        action = actions.get(command)
        if not action:
            return False
        return await action()


# pylint: disable=too-few-public-methods
class HtpcSensor(Sensor):
    """Binary sensor reflecting the PC power state."""

    def __init__(self, cfg: DeviceConfig) -> None:
        super().__init__(
            f"sensor.{cfg.id}.htpc_power",
            {"en": "PC Power", "de": "PC-Status"},
            [],
            {
                SensorAttributes.STATE: SensorStates.ON,
                SensorAttributes.VALUE: "",
            },
            device_class=SensorDeviceClasses.BINARY,
        )

    def apply_power(self, power: str) -> dict[str, Any]:
        value = "On" if power == "on" else "Off" if power == "off" else ""
        return {
            SensorAttributes.STATE: SensorStates.ON,
            SensorAttributes.VALUE: value,
        }
