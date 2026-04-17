"""Integration configuration."""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from dataclasses import dataclass, field, fields
from typing import Callable, Iterator

_LOG = logging.getLogger(__name__)
_CFG_FILE = "config.json"


@dataclass
class DeviceConfig:
    id: str
    name: str
    bridge_host: str = field(default="localhost")
    bridge_port: int = field(default=13590)

    def __post_init__(self) -> None:
        for f in fields(self):
            if not isinstance(f.default, dataclasses.MISSING.__class__) and getattr(self, f.name) is None:
                setattr(self, f.name, f.default)


class _JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


class Devices:
    def __init__(
        self,
        data_path: str,
        add_handler: Callable[[DeviceConfig], None],
        remove_handler: Callable[[DeviceConfig | None], None],
        update_handler: Callable[[DeviceConfig], None],
    ) -> None:
        self._path = os.path.join(data_path, _CFG_FILE)
        self._config: list[DeviceConfig] = []
        self._add = add_handler
        self._remove = remove_handler
        self._update = update_handler
        self.load()

    def all(self) -> Iterator[DeviceConfig]:
        return iter(self._config)

    def contains(self, device_id: str) -> bool:
        return any(d.id == device_id for d in self._config)

    def get(self, device_id: str) -> DeviceConfig | None:
        for d in self._config:
            if d.id == device_id:
                return dataclasses.replace(d)
        return None

    def add_or_update(self, cfg: DeviceConfig) -> None:
        if self.contains(cfg.id):
            self.update(cfg)
            if self._update:
                self._update(cfg)
        else:
            self._config.append(cfg)
            self.store()
        if self._add:
            self._add(cfg)

    def update(self, cfg: DeviceConfig) -> bool:
        for d in self._config:
            if d.id == cfg.id:
                for f in fields(cfg):
                    setattr(d, f.name, getattr(cfg, f.name))
                return self.store()
        return False

    def remove(self, device_id: str) -> bool:
        cfg = self.get(device_id)
        if cfg is None:
            return False
        self._config = [d for d in self._config if d.id != device_id]
        if self._remove:
            self._remove(cfg)
        return self.store()

    def store(self) -> bool:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, cls=_JSONEncoder)
            return True
        except OSError:
            _LOG.error("Cannot write config")
            return False

    def load(self) -> bool:
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                try:
                    self._config.append(DeviceConfig(**item))
                except TypeError as exc:
                    _LOG.warning("Ignoring invalid config entry: %s", exc)
            return True
        except FileNotFoundError:
            return False
        except Exception as exc:
            _LOG.error("Config load error: %s", exc)
            return False


devices: Devices | None = None
