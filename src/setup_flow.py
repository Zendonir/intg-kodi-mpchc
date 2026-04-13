"""
UC Remote setup and reconfiguration flow.
"""

from __future__ import annotations

import logging
import uuid

import ucapi
from ucapi import IntegrationAPI, SetupError

from config import DeviceConfig, devices
from const import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT

_LOG = logging.getLogger(__name__)


async def driver_setup_handler(msg: ucapi.SetupDriver, api: IntegrationAPI) -> ucapi.SetupAction:
    """Handle setup flow steps."""
    if isinstance(msg, ucapi.DriverSetupRequest):
        return ucapi.RequestUserInput(
            {"en": "kodi-mpchc-bridge Setup"},
            [
                {
                    "id": "info",
                    "label": {"en": "Enter your bridge connection details."},
                    "field": {"label": {"value": {"en": ""}}},
                },
                {
                    "id": "name",
                    "label": {"en": "Device name"},
                    "field": {"text": {"value": "Kodi / MPC-HC"}},
                },
                {
                    "id": "bridge_host",
                    "label": {"en": "Bridge host"},
                    "field": {"text": {"value": DEFAULT_BRIDGE_HOST}},
                },
                {
                    "id": "bridge_port",
                    "label": {"en": "Bridge port"},
                    "field": {"text": {"value": str(DEFAULT_BRIDGE_PORT)}},
                },
            ],
        )

    if isinstance(msg, ucapi.UserDataResponse):
        return await _handle_user_data(msg, api)

    if isinstance(msg, ucapi.AbortDriverSetup):
        _LOG.info("Setup aborted")
        return ucapi.SetupComplete()

    return ucapi.SetupError()


async def _handle_user_data(
    msg: ucapi.UserDataResponse, api: IntegrationAPI
) -> ucapi.SetupAction:
    inp = msg.input_values or {}
    name = inp.get("name", "Kodi / MPC-HC").strip() or "Kodi / MPC-HC"
    host = inp.get("bridge_host", DEFAULT_BRIDGE_HOST).strip() or DEFAULT_BRIDGE_HOST
    try:
        port = int(inp.get("bridge_port", str(DEFAULT_BRIDGE_PORT)).strip())
    except ValueError:
        port = DEFAULT_BRIDGE_PORT

    device_id = str(uuid.uuid4())
    cfg = DeviceConfig(id=device_id, name=name, bridge_host=host, bridge_port=port)

    if devices:
        devices.add_or_update(cfg)

    _LOG.info("Device configured: %s @ %s:%d", name, host, port)
    return ucapi.SetupComplete()


async def reconfigure_handler(
    msg: ucapi.SetupDriver, api: IntegrationAPI, device_id: str
) -> ucapi.SetupAction:
    """Handle device reconfiguration."""
    cfg = devices.get(device_id) if devices else None

    if isinstance(msg, ucapi.DriverSetupRequest):
        current_host = cfg.bridge_host if cfg else DEFAULT_BRIDGE_HOST
        current_port = str(cfg.bridge_port) if cfg else str(DEFAULT_BRIDGE_PORT)
        current_name = cfg.name if cfg else "Kodi / MPC-HC"

        return ucapi.RequestUserInput(
            {"en": "Reconfigure kodi-mpchc-bridge"},
            [
                {
                    "id": "name",
                    "label": {"en": "Device name"},
                    "field": {"text": {"value": current_name}},
                },
                {
                    "id": "bridge_host",
                    "label": {"en": "Bridge host"},
                    "field": {"text": {"value": current_host}},
                },
                {
                    "id": "bridge_port",
                    "label": {"en": "Bridge port"},
                    "field": {"text": {"value": current_port}},
                },
            ],
        )

    if isinstance(msg, ucapi.UserDataResponse):
        inp = msg.input_values or {}
        name = inp.get("name", "Kodi / MPC-HC").strip() or "Kodi / MPC-HC"
        host = inp.get("bridge_host", DEFAULT_BRIDGE_HOST).strip() or DEFAULT_BRIDGE_HOST
        try:
            port = int(inp.get("bridge_port", str(DEFAULT_BRIDGE_PORT)).strip())
        except ValueError:
            port = DEFAULT_BRIDGE_PORT

        updated = DeviceConfig(id=device_id, name=name, bridge_host=host, bridge_port=port)
        if devices:
            devices.add_or_update(updated)
        return ucapi.SetupComplete()

    if isinstance(msg, ucapi.AbortDriverSetup):
        return ucapi.SetupComplete()

    return ucapi.SetupError()
