import os
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class DatabaseConfig:
    path: str = "/var/lib/timecard/timecard.db"


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 5000
    secret_key: str = "CHANGE_ME"


@dataclass
class NFCConfig:
    interface: str = "spi"
    reset_pin: int = 20
    req_pin: int = 16


@dataclass
class TFTConfig:
    cs_pin: int = 8          # SPI CE0 / GPIO8
    dc_pin: int = 25         # data/command GPIO25
    rst_pin: int = 24        # reset GPIO24
    rotation: int = 90       # landscape
    baudrate: int = 64_000_000


@dataclass
class BuzzerConfig:
    gpio_pin: int = 18


@dataclass
class HardwareConfig:
    mock: bool = False
    nfc: NFCConfig = field(default_factory=NFCConfig)
    tft: TFTConfig = field(default_factory=TFTConfig)
    buzzer: BuzzerConfig = field(default_factory=BuzzerConfig)


@dataclass
class Config:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    hardware: HardwareConfig = field(default_factory=HardwareConfig)


def _pick(data: dict, cls: type) -> dict:
    """Return only the keys that exist as fields on the dataclass."""
    valid = {f for f in cls.__dataclass_fields__}
    return {k: v for k, v in data.items() if k in valid}


def load_config(path: str = "config.yaml") -> Config:
    if not os.path.exists(path):
        return Config()

    with open(path) as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    db = data.get("database", {})
    srv = data.get("server", {})
    hw = data.get("hardware", {})

    return Config(
        database=DatabaseConfig(**_pick(db, DatabaseConfig)),
        server=ServerConfig(**_pick(srv, ServerConfig)),
        hardware=HardwareConfig(
            mock=hw.get("mock", False),
            nfc=NFCConfig(**_pick(hw.get("nfc", {}), NFCConfig)),
            tft=TFTConfig(**_pick(hw.get("tft", {}), TFTConfig)),
            buzzer=BuzzerConfig(**_pick(hw.get("buzzer", {}), BuzzerConfig)),
        ),
    )
