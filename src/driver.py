"""
Integration driver — main module.

Manages device connections and routes bridge state updates to
UC Remote entities.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import ucapi
from ucapi import IntegrationAPI

import config
from bridge_client import BridgeClient
from config import DeviceConfig, Devices
from const import DRIVER_ID, DRIVER_NAME, INTEGRATION_VERSION
from media_player import BridgeMediaPlayer
from setup_flow import driver_setup_handler, reconfigure_handler

_LOG = logging.getLogger(__name__)

api = IntegrationAPI(os.environ.get("UC_CONFIG_HOME", "."))

# device_id → BridgeClient
_clients: dict[str, BridgeClient] = {}
# device_id → BridgeMediaPlayer
_players: dict[str, BridgeMediaPlayer] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _entity_id(device_id: str) -> str:
    return f"media_player.{device_id}"


def _add_device(cfg: DeviceConfig) -> None:
    """Create client + entities for a newly configured device."""
    if cfg.id in _clients:
        _LOG.debug("Device %s already registered", cfg.id)
        return

    client = BridgeClient(
        host=cfg.bridge_host,
        port=cfg.bridge_port,
        on_state=_make_state_handler(cfg.id),
    )
    _clients[cfg.id] = client

    player = BridgeMediaPlayer(cfg, client)
    _players[cfg.id] = player

    api.available_entities.add(player)
    _LOG.info("Device added: %s (%s:%d)", cfg.name, cfg.bridge_host, cfg.bridge_port)


def _remove_device(cfg: DeviceConfig | None) -> None:
    if cfg is None:
        return
    client = _clients.pop(cfg.id, None)
    if client:
        asyncio.create_task(client.stop())
    player = _players.pop(cfg.id, None)
    if player:
        api.available_entities.remove(player.id)
    _LOG.info("Device removed: %s", cfg.id)


def _update_device(cfg: DeviceConfig) -> None:
    _remove_device(cfg)
    _add_device(cfg)


def _make_state_handler(device_id: str):
    async def _on_state(state: dict[str, Any], is_full: bool) -> None:
        player = _players.get(device_id)
        if player is None:
            return
        attrs = player.apply_state(state)
        if attrs:
            api.configured_entities.update_attributes(player.id, attrs)
    return _on_state


# ---------------------------------------------------------------------------
# ucapi callbacks
# ---------------------------------------------------------------------------
@api.listens_to(ucapi.Events.CONNECT)
async def _on_connect() -> None:
    _LOG.info("UC Remote connected")
    await api.set_device_state(ucapi.DeviceStates.CONNECTED)
    # Start all clients
    for device_id, client in _clients.items():
        if not client.connected:
            client.start()


@api.listens_to(ucapi.Events.DISCONNECT)
async def _on_disconnect() -> None:
    _LOG.info("UC Remote disconnected")


@api.listens_to(ucapi.Events.ENTER_STANDBY)
async def _on_standby() -> None:
    for client in _clients.values():
        await client.stop()


@api.listens_to(ucapi.Events.EXIT_STANDBY)
async def _on_exit_standby() -> None:
    for device_id, client in _clients.items():
        cfg = config.devices.get(device_id) if config.devices else None
        if cfg:
            _clients[device_id] = BridgeClient(
                host=cfg.bridge_host,
                port=cfg.bridge_port,
                on_state=_make_state_handler(device_id),
            )
            _clients[device_id].start()


@api.listens_to(ucapi.Events.SUBSCRIBE_ENTITIES)
async def _on_subscribe(entity_ids: list[str]) -> None:
    for eid in entity_ids:
        device_id = eid.replace("media_player.", "")
        client = _clients.get(device_id)
        if client and not client.connected:
            client.start()


@api.listens_to(ucapi.Events.UNSUBSCRIBE_ENTITIES)
async def _on_unsubscribe(entity_ids: list[str]) -> None:
    pass  # keep connection alive; bridge is lightweight


# ---------------------------------------------------------------------------
# Entity command handler
# ---------------------------------------------------------------------------
@api.listens_to(ucapi.Events.ENTITY_COMMAND)
async def _on_entity_command(
    websocket, req_id: str, entity_id: str, cmd_id: str, params: dict | None
) -> None:
    player = _players.get(entity_id.replace("media_player.", ""))
    if player is None:
        await api.acknowledge(websocket, req_id, ucapi.StatusCodes.NOT_FOUND)
        return
    result = await player.command(cmd_id, params)
    await api.acknowledge(websocket, req_id, result)


# ---------------------------------------------------------------------------
# Driver setup
# ---------------------------------------------------------------------------
@api.listens_to(ucapi.Events.SETUP_DRIVER)
async def _on_setup(websocket, req_id: str, msg: ucapi.SetupDriver) -> None:
    action = await driver_setup_handler(msg, api)
    await api.driver_setup_response(websocket, req_id, action)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    config.devices = Devices(
        data_path=os.environ.get("UC_CONFIG_HOME", "."),
        add_handler=_add_device,
        remove_handler=_remove_device,
        update_handler=_update_device,
    )

    # Register configured devices
    for cfg in config.devices.all():
        _add_device(cfg)

    api.run()


if __name__ == "__main__":
    main()
