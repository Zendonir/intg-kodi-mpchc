"""
UC Remote setup and reconfiguration flow.

Backup / Restore
----------------
The reconfigure dialog shows a short backup code that encodes the device's
host, port and name as a compact base64 JSON string.  During initial setup
the user can paste that code into the optional "Restore backup" field to
re-apply all settings without typing them again — useful after a full
delete-and-reinstall of the integration.

Because device UUIDs are derived deterministically from host:port, the same
backup code always re-creates the exact same entity IDs, which means all
UC Remote activity and profile assignments survive reinstalls unchanged.
"""

from __future__ import annotations

import base64
import json
import logging
import uuid

import ucapi
from ucapi import IntegrationAPI

import config
from config import DeviceConfig
from const import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT

_LOG = logging.getLogger(__name__)

# Namespace for deterministic device UUIDs derived from host:port.
# Using the standard URL namespace (uuid.NAMESPACE_URL) so the same
# bridge endpoint always hashes to the same UUID, keeping entity IDs
# stable across integration reinstalls.
_UUID_NS = uuid.NAMESPACE_URL


# ---------------------------------------------------------------------------
# Backup / Restore helpers
# ---------------------------------------------------------------------------

def _encode_backup(host: str, port: int, name: str) -> str:
    """Encode connection settings as a compact base64 string."""
    data = {"h": host, "p": port, "n": name}
    return base64.b64encode(json.dumps(data, separators=(",", ":")).encode()).decode()


def _decode_backup(code: str) -> dict | None:
    """Decode a backup code.  Returns a dict with bridge_host/bridge_port/name
    or *None* if the code is invalid / cannot be decoded."""
    try:
        raw = base64.b64decode(code.strip().encode()).decode()
        data = json.loads(raw)
        return {
            "name": str(data.get("n", "")).strip() or "Kodi / MPC-HC",
            "bridge_host": str(data.get("h", "")).strip(),
            "bridge_port": int(data.get("p", DEFAULT_BRIDGE_PORT)),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Initial setup
# ---------------------------------------------------------------------------

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
                    "id": "restore_code",
                    "label": {"en": "Restore backup code (optional)"},
                    "field": {"text": {"value": ""}},
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


async def _handle_user_data(msg: ucapi.UserDataResponse, _api: IntegrationAPI) -> ucapi.SetupAction:
    inp = msg.input_values or {}

    # --- Restore path ---
    restore_code = inp.get("restore_code", "").strip()
    if restore_code:
        restored = _decode_backup(restore_code)
        if restored:
            name = restored["name"]
            host = restored["bridge_host"]
            port = restored["bridge_port"]
            _LOG.info("Restore: using backup code for %s @ %s:%d", name, host, port)
        else:
            _LOG.warning("Restore: invalid backup code, falling back to manual input")
            restored = None

    # --- Manual input path (or fallback when restore code is invalid) ---
    if not restore_code or restored is None:
        name = inp.get("name", "Kodi / MPC-HC").strip() or "Kodi / MPC-HC"
        host = inp.get("bridge_host", DEFAULT_BRIDGE_HOST).strip() or DEFAULT_BRIDGE_HOST
        try:
            port = int(inp.get("bridge_port", str(DEFAULT_BRIDGE_PORT)).strip())
        except ValueError:
            port = DEFAULT_BRIDGE_PORT

    # Derive a deterministic device ID from host:port so entity IDs remain
    # identical across integration reinstalls.  The UC Remote stores activity /
    # profile assignments by entity ID, so a stable UUID means users never have
    # to re-map entities after upgrading or reinstalling the integration.
    device_id = str(uuid.uuid5(_UUID_NS, f"{host}:{port}"))
    cfg = DeviceConfig(id=device_id, name=name, bridge_host=host, bridge_port=port)

    if config.devices:
        config.devices.add_or_update(cfg)

    _LOG.info("Device configured: %s @ %s:%d", name, host, port)
    return ucapi.SetupComplete()


# ---------------------------------------------------------------------------
# Reconfigure
# ---------------------------------------------------------------------------

async def reconfigure_handler(msg: ucapi.SetupDriver, _api: IntegrationAPI, device_id: str) -> ucapi.SetupAction:
    """Handle device reconfiguration."""
    cfg = config.devices.get(device_id) if config.devices else None

    if isinstance(msg, ucapi.DriverSetupRequest):
        current_host = cfg.bridge_host if cfg else DEFAULT_BRIDGE_HOST
        current_port = str(cfg.bridge_port) if cfg else str(DEFAULT_BRIDGE_PORT)
        current_name = cfg.name if cfg else "Kodi / MPC-HC"
        backup_code = _encode_backup(current_host, int(current_port), current_name)

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
                {
                    "id": "backup_info",
                    "label": {"en": "Backup code (copy and save this)"},
                    "field": {"label": {"value": {"en": backup_code}}},
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
        if config.devices:
            config.devices.add_or_update(updated)
        return ucapi.SetupComplete()

    if isinstance(msg, ucapi.AbortDriverSetup):
        return ucapi.SetupComplete()

    return ucapi.SetupError()
