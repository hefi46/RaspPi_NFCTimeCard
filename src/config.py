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
class OLEDConfig:
    i2c_address: int = 0x3C
    width: int = 128
    height: int = 64


@dataclass
class BuzzerConfig:
    gpio_pin: int = 18


@dataclass
class HardwareConfig:
    mock: bool = False
    nfc: NFCConfig = field(default_factory=NFCConfig)
    oled: OLEDConfig = field(default_factory=OLEDConfig)
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
            oled=OLEDConfig(**_pick(hw.get("oled", {}), OLEDConfig)),
            buzzer=BuzzerConfig(**_pick(hw.get("buzzer", {}), BuzzerConfig)),
        ),
    )
