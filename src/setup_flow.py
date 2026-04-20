"""
UC Remote setup and reconfiguration flow.

Setup menu (first page)
-----------------------
Option 1  Erstinstallation         — always available
Option 2  Aus Backup wiederherstellen — always available
Option 3  Backup erstellen         — only when a device is already configured
Option 4  Einstellungen ändern     — only when a device is already configured

Backup format
-------------
A JSON object that can be saved to disk and later pasted back:
  {"version": 1, "name": "...", "bridge_host": "...", "bridge_port": 13590}

Because device UUIDs are derived deterministically from host:port, the same
backup always re-creates the exact same entity IDs so all UC Remote activity
and profile assignments survive reinstalls unchanged.
"""

from __future__ import annotations

import json
import logging
import uuid

import ucapi
from ucapi import IntegrationAPI

import config
from config import DeviceConfig
from const import DEFAULT_BRIDGE_HOST, DEFAULT_BRIDGE_PORT

_LOG = logging.getLogger(__name__)

_UUID_NS = uuid.NAMESPACE_URL

# ---------------------------------------------------------------------------
# Backup helpers
# ---------------------------------------------------------------------------


def _encode_backup(cfg: DeviceConfig) -> str:
    """Encode a DeviceConfig as a compact JSON backup string."""
    return json.dumps(
        {"version": 1, "name": cfg.name, "bridge_host": cfg.bridge_host, "bridge_port": cfg.bridge_port},
        indent=2,
    )


def _decode_backup(text: str) -> dict | None:
    """Parse a backup JSON string.  Returns a normalised dict or *None* on error."""
    try:
        data = json.loads(text.strip())
        return {
            "name": str(data.get("name", "")).strip() or "Kodi / MPC-HC",
            "bridge_host": str(data.get("bridge_host", "")).strip(),
            "bridge_port": int(data.get("bridge_port", DEFAULT_BRIDGE_PORT)),
        }
    except Exception:
        return None


def _first_device() -> DeviceConfig | None:
    """Return the first configured device or *None*."""
    if not config.devices:
        return None
    all_devs = list(config.devices.all())
    return all_devs[0] if all_devs else None


# ---------------------------------------------------------------------------
# Re-usable form fragments
# ---------------------------------------------------------------------------

_CONN_FIELDS = [
    {
        "id": "name",
        "label": {"en": "Device name", "de": "Gerätename"},
        "field": {"text": {"value": "Kodi / MPC-HC"}},
    },
    {
        "id": "bridge_host",
        "label": {"en": "Bridge host", "de": "Bridge-Host"},
        "field": {"text": {"value": DEFAULT_BRIDGE_HOST}},
    },
    {
        "id": "bridge_port",
        "label": {"en": "Bridge port", "de": "Bridge-Port"},
        "field": {"text": {"value": str(DEFAULT_BRIDGE_PORT)}},
    },
]


def _conn_fields_prefilled(cfg: DeviceConfig) -> list[dict]:
    return [
        {
            "id": "name",
            "label": {"en": "Device name", "de": "Gerätename"},
            "field": {"text": {"value": cfg.name}},
        },
        {
            "id": "bridge_host",
            "label": {"en": "Bridge host", "de": "Bridge-Host"},
            "field": {"text": {"value": cfg.bridge_host}},
        },
        {
            "id": "bridge_port",
            "label": {"en": "Bridge port", "de": "Bridge-Port"},
            "field": {"text": {"value": str(cfg.bridge_port)}},
        },
    ]


# ---------------------------------------------------------------------------
# Setup handler (initial install / reconfigure via setup menu)
# ---------------------------------------------------------------------------


async def driver_setup_handler(msg: ucapi.SetupDriver, api: IntegrationAPI) -> ucapi.SetupAction:
    """Handle all setup flow steps."""
    if isinstance(msg, ucapi.DriverSetupRequest):
        return _step_action_menu()

    if isinstance(msg, ucapi.UserDataResponse):
        return await _handle_user_data(msg, api)

    if isinstance(msg, ucapi.AbortDriverSetup):
        _LOG.info("Setup aborted")
        return ucapi.SetupComplete()

    return ucapi.SetupError()


def _step_action_menu() -> ucapi.RequestUserInput:
    """Step 1 — show the four-option action menu."""
    has_device = _first_device() is not None

    items = [
        {"id": "install", "label": {"en": "Fresh installation", "de": "Erstinstallation"}},
        {"id": "restore", "label": {"en": "Restore from backup", "de": "Aus Backup wiederherstellen"}},
    ]
    if has_device:
        items += [
            {"id": "backup", "label": {"en": "Create backup", "de": "Backup erstellen"}},
            {"id": "settings", "label": {"en": "Change settings", "de": "Einstellungen ändern"}},
        ]

    return ucapi.RequestUserInput(
        {"en": "Kodi / MPC-HC Bridge", "de": "Kodi / MPC-HC Bridge"},
        [
            {
                "id": "action",
                "label": {"en": "What would you like to do?", "de": "Was möchten Sie tun?"},
                "field": {"dropdown": {"value": "install", "items": items}},
            }
        ],
    )


async def _handle_user_data(msg: ucapi.UserDataResponse, _api: IntegrationAPI) -> ucapi.SetupAction:
    inp = msg.input_values or {}

    action = inp.get("action")

    # ── Step 1 → Step 2 routing ─────────────────────────────────────────────
    if action == "install":
        return ucapi.RequestUserInput(
            {"en": "Installation", "de": "Installation"},
            _CONN_FIELDS,
        )

    if action == "restore":
        return ucapi.RequestUserInput(
            {"en": "Restore from backup", "de": "Backup wiederherstellen"},
            [
                {
                    "id": "info",
                    "label": {"en": "Paste backup JSON content below.", "de": "Inhalt der Backup-JSON-Datei einfügen."},
                    "field": {"label": {"value": {"en": ""}}},
                },
                {
                    "id": "backup_json",
                    "label": {"en": "Backup JSON", "de": "Backup-JSON"},
                    "field": {"text": {"value": ""}},
                },
            ],
        )

    if action == "backup":
        cfg = _first_device()
        if not cfg:
            return ucapi.SetupError(ucapi.IntegrationSetupError.NOT_FOUND)
        backup_text = _encode_backup(cfg)
        return ucapi.RequestUserInput(
            {"en": "Backup", "de": "Backup"},
            [
                {
                    "id": "info",
                    "label": {"en": "Copy the JSON and save as a file.", "de": "JSON kopieren und als Datei sichern."},
                    "field": {"label": {"value": {"en": ""}}},
                },
                {
                    "id": "backup_content",
                    "label": {"en": "Backup JSON", "de": "Backup-JSON"},
                    "field": {"label": {"value": {"en": backup_text}}},
                },
                {
                    "id": "_backup_done",
                    "label": {"en": "Backup saved", "de": "Backup gespeichert"},
                    "field": {"checkbox": {"value": True}},
                },
            ],
        )

    if action == "settings":
        cfg = _first_device()
        if not cfg:
            return ucapi.SetupError(ucapi.IntegrationSetupError.NOT_FOUND)
        return ucapi.RequestUserInput(
            {"en": "Change settings", "de": "Einstellungen ändern"},
            _conn_fields_prefilled(cfg),
        )

    # ── Step 2 → processing ─────────────────────────────────────────────────

    # Backup display was acknowledged → nothing to save
    if "_backup_done" in inp:
        return ucapi.SetupComplete()

    # Restore from JSON
    if "backup_json" in inp:
        restored = _decode_backup(inp.get("backup_json", ""))
        if not restored:
            _LOG.warning("Restore: invalid backup JSON")
            return ucapi.SetupError(ucapi.IntegrationSetupError.OTHER)
        return _save_device(restored["name"], restored["bridge_host"], restored["bridge_port"])

    # Install / change settings: name + bridge_host + bridge_port present
    if "bridge_host" in inp or "name" in inp:
        name = inp.get("name", "Kodi / MPC-HC").strip() or "Kodi / MPC-HC"
        host = inp.get("bridge_host", DEFAULT_BRIDGE_HOST).strip() or DEFAULT_BRIDGE_HOST
        try:
            port = int(inp.get("bridge_port", str(DEFAULT_BRIDGE_PORT)).strip())
        except ValueError:
            port = DEFAULT_BRIDGE_PORT
        return _save_device(name, host, port)

    _LOG.warning("Setup: unexpected input %s", list(inp.keys()))
    return ucapi.SetupError()


def _save_device(name: str, host: str, port: int) -> ucapi.SetupAction:
    device_id = str(uuid.uuid5(_UUID_NS, f"{host}:{port}"))
    cfg = DeviceConfig(id=device_id, name=name, bridge_host=host, bridge_port=port)
    if config.devices:
        config.devices.add_or_update(cfg)
    _LOG.info("Device configured: %s @ %s:%d", name, host, port)
    return ucapi.SetupComplete()


# ---------------------------------------------------------------------------
# Reconfigure handler (called from device settings on the remote)
# ---------------------------------------------------------------------------


async def reconfigure_handler(msg: ucapi.SetupDriver, _api: IntegrationAPI, device_id: str) -> ucapi.SetupAction:
    """Handle device reconfiguration."""
    cfg = config.devices.get(device_id) if config.devices else None

    if isinstance(msg, ucapi.DriverSetupRequest):
        current_host = cfg.bridge_host if cfg else DEFAULT_BRIDGE_HOST
        current_port = str(cfg.bridge_port) if cfg else str(DEFAULT_BRIDGE_PORT)
        current_name = cfg.name if cfg else "Kodi / MPC-HC"
        backup_text = _encode_backup(cfg) if cfg else ""

        return ucapi.RequestUserInput(
            {"en": "Reconfigure kodi-mpchc-bridge", "de": "Kodi / MPC-HC Bridge neu konfigurieren"},
            [
                {
                    "id": "name",
                    "label": {"en": "Device name", "de": "Gerätename"},
                    "field": {"text": {"value": current_name}},
                },
                {
                    "id": "bridge_host",
                    "label": {"en": "Bridge host", "de": "Bridge-Host"},
                    "field": {"text": {"value": current_host}},
                },
                {
                    "id": "bridge_port",
                    "label": {"en": "Bridge port", "de": "Bridge-Port"},
                    "field": {"text": {"value": current_port}},
                },
                {
                    "id": "backup_info",
                    "label": {"en": "Backup JSON (copy and save)", "de": "Backup-JSON (kopieren und speichern)"},
                    "field": {"label": {"value": {"en": backup_text}}},
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
