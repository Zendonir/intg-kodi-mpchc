"""
Integration driver — main module.

Manages device connections and routes bridge state updates to
UC Remote entities.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from functools import partial
from typing import Any

import ucapi
from ucapi import IntegrationAPI

import config
from bridge_client import BridgeClient
from config import DeviceConfig, Devices
from media_player import BridgeMediaPlayer
from selects import BridgeEpisodeSelect, BridgeSelect
from sensors import SENSOR_DEFS, BridgeSensor
from setup_flow import driver_setup_handler

_LOG = logging.getLogger(__name__)

if sys.platform == "win32":
    _LOOP = asyncio.SelectorEventLoop()
else:
    _LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)

api = IntegrationAPI(_LOOP)

# device_id → BridgeClient
_clients: dict[str, BridgeClient] = {}
# device_id → BridgeMediaPlayer
_players: dict[str, BridgeMediaPlayer] = {}
# device_id → list of BridgeSensor
_sensors: dict[str, list[BridgeSensor]] = {}
# device_id → list of BridgeSelect (audio / subtitle / chapter)
_selects: dict[str, list[BridgeSelect]] = {}
# device_id → BridgeEpisodeSelect
_episode_selects: dict[str, BridgeEpisodeSelect] = {}

# Select entity definitions: (select_type, {en, de} name)
_SELECT_DEFS = [
    ("audio", {"en": "Audio Track", "de": "Audiospur"}),
    ("subtitle", {"en": "Subtitle", "de": "Untertitel"}),
    ("chapter", {"en": "Chapter", "de": "Kapitel"}),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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

    # Media player
    player = BridgeMediaPlayer(cfg, client)
    player.device_id = cfg.id
    _players[cfg.id] = player
    api.available_entities.add(player)

    # Sensor entities (one per bridge state field)
    sensors: list[BridgeSensor] = []
    for state_key, name, device_class, unit, decimals in SENSOR_DEFS:
        sensor = BridgeSensor(cfg.id, state_key, name, device_class, unit, decimals)
        sensor.device_id = cfg.id
        api.available_entities.add(sensor)
        sensors.append(sensor)
    _sensors[cfg.id] = sensors

    # Select entities (audio track, subtitle, chapter)
    selects: list[BridgeSelect] = []
    for sel_type, sel_name in _SELECT_DEFS:
        sel = BridgeSelect(cfg.id, sel_type, sel_name, client)
        sel.device_id = cfg.id
        api.available_entities.add(sel)
        selects.append(sel)
    _selects[cfg.id] = selects

    # Episode select (Kodi TV season navigation)
    ep_sel = BridgeEpisodeSelect(cfg.id, client)
    ep_sel.device_id = cfg.id
    api.available_entities.add(ep_sel)
    _episode_selects[cfg.id] = ep_sel

    _LOG.info(
        "Device added: %s (%s:%d) — %d entities registered",
        cfg.name,
        cfg.bridge_host,
        cfg.bridge_port,
        1 + len(sensors) + len(selects) + 1,  # +1 for episode select
    )


def _remove_device(cfg: DeviceConfig | None) -> None:
    if cfg is None:
        return
    client = _clients.pop(cfg.id, None)
    if client:
        asyncio.create_task(client.stop())
    player = _players.pop(cfg.id, None)
    if player:
        api.available_entities.remove(player.id)
    for sensor in _sensors.pop(cfg.id, []):
        api.available_entities.remove(sensor.id)
    for sel in _selects.pop(cfg.id, []):
        api.available_entities.remove(sel.id)
    ep_sel = _episode_selects.pop(cfg.id, None)
    if ep_sel:
        api.available_entities.remove(ep_sel.id)
    _LOG.info("Device removed: %s", cfg.id)


def _update_device(cfg: DeviceConfig) -> None:
    _remove_device(cfg)
    _add_device(cfg)


def _make_state_handler(device_id: str):
    async def _on_state(state: dict[str, Any], is_full: bool) -> None:
        # Media player
        player = _players.get(device_id)
        if player:
            attrs = player.apply_state(state)
            if attrs:
                api.configured_entities.update_attributes(player.id, attrs)

        # Sensors
        for sensor in _sensors.get(device_id, []):
            attrs = sensor.apply_state(state)
            if attrs:
                api.configured_entities.update_attributes(sensor.id, attrs)

        # Selects (audio / subtitle / chapter)
        for sel in _selects.get(device_id, []):
            attrs = sel.apply_state(state)
            if attrs:
                api.configured_entities.update_attributes(sel.id, attrs)

        # Episode select (Kodi season navigation)
        ep_sel = _episode_selects.get(device_id)
        if ep_sel:
            attrs = ep_sel.apply_state(state)
            if attrs:
                api.configured_entities.update_attributes(ep_sel.id, attrs)

    return _on_state


# ---------------------------------------------------------------------------
# ucapi callbacks
# ---------------------------------------------------------------------------
@api.listens_to(ucapi.Events.CONNECT)
async def _on_connect() -> None:
    _LOG.info("UC Remote connected")
    await api.set_device_state(ucapi.DeviceStates.CONNECTED)
    for device_id, client in _clients.items():
        if not client.connected:
            _LOG.info("Starting bridge client for device %s", device_id)
            client.start()
        else:
            # Already connected — push fresh state so remote is up to date
            current = await client.fetch_state()
            if current:
                handler = _make_state_handler(device_id)
                await handler(current, True)


@api.listens_to(ucapi.Events.DISCONNECT)
async def _on_disconnect() -> None:
    _LOG.info("UC Remote disconnected")


@api.listens_to(ucapi.Events.ENTER_STANDBY)
async def _on_standby() -> None:
    for client in _clients.values():
        await client.stop()


@api.listens_to(ucapi.Events.EXIT_STANDBY)
async def _on_exit_standby() -> None:
    for device_id, _ in _clients.items():
        cfg = config.devices.get(device_id) if config.devices else None
        if not cfg:
            continue
        old = _clients.get(device_id)
        if old:
            await old.stop()
        new_client = BridgeClient(
            host=cfg.bridge_host,
            port=cfg.bridge_port,
            on_state=_make_state_handler(device_id),
        )
        _clients[device_id] = new_client
        new_client.start()


@api.listens_to(ucapi.Events.SUBSCRIBE_ENTITIES)
async def _on_subscribe(entity_ids: list[str]) -> None:
    """
    Called when the UC Remote subscribes to entities (e.g. adds them to a profile,
    or reconnects after a restart).  Start the bridge connection for each device
    and immediately push the current state so the remote doesn't stay at 'unknown'.
    """
    started: set[str] = set()

    for eid in entity_ids:
        # entity IDs: media_player.<dev_id>  |  sensor.<dev_id>.<key>  |  select.<dev_id>.<type>
        parts = eid.split(".", 2)
        device_id = parts[1] if len(parts) >= 2 else eid
        if device_id in started:
            continue

        client = _clients.get(device_id)
        if not client:
            continue

        started.add(device_id)
        _LOG.info("Subscribe: device %s (connected=%s)", device_id, client.connected)

        if not client.connected:
            client.start()
            # The bridge sends state_full on WS connect — wait briefly so the
            # first message arrives and populates the entities before the remote
            # finishes its subscription handshake.
            await asyncio.sleep(0.5)

        # If the client was already connected (e.g. integration restart), fetch
        # the current state explicitly and push it to all entities for this device.
        if client.connected:
            current = await client.fetch_state()
            if current:
                _LOG.info("Subscribe: pushing current state to device %s", device_id)
                handler = _make_state_handler(device_id)
                await handler(current, True)


@api.listens_to(ucapi.Events.UNSUBSCRIBE_ENTITIES)
async def _on_unsubscribe(entity_ids: list[str]) -> None:
    pass  # keep connection alive; bridge is lightweight


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
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

    # Wire the setup handler: driver_setup_handler(msg, api) — bind api via partial
    await api.init("driver.json", partial(driver_setup_handler, api=api))


if __name__ == "__main__":
    _LOOP.run_until_complete(main())
    _LOOP.run_forever()
