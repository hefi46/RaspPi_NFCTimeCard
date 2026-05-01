"""
NFC reader abstraction.

Real hardware:  PN532 over SPI (default), I2C, or UART via Adafruit library.
Mock:           emits configurable UIDs on a timer — no hardware required.

Usage:
    reader = make_reader(config)
    reader.start(on_card=lambda uid: print(uid))   # blocks; run in a thread
    # later:
    reader.stop()
"""

import time
import logging
from typing import Callable

logger = logging.getLogger(__name__)

# Seconds between poll attempts on the real reader
_POLL_INTERVAL = 0.2
# Seconds a card must be absent before re-firing for the same UID
_DEBOUNCE_SECONDS = 2.0


class NFCReader:
    """Real PN532 implementation.  Imports hardware libs lazily."""

    def __init__(self, config) -> None:
        self._cfg = config.hardware
        self._running = False

    def _build_pn532(self):
        """Initialise PN532 according to configured interface."""
        import board  # type: ignore
        import busio  # type: ignore
        import digitalio  # type: ignore

        iface = self._cfg.nfc.interface.lower()

        if iface == "spi":
            from adafruit_pn532.spi import PN532_SPI  # type: ignore
            spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
            cs = digitalio.DigitalInOut(
                getattr(board, f"D{self._cfg.nfc.req_pin}")
            )
            reset = digitalio.DigitalInOut(
                getattr(board, f"D{self._cfg.nfc.reset_pin}")
            )
            pn532 = PN532_SPI(spi, cs, reset=reset, debug=False)
        elif iface == "i2c":
            from adafruit_pn532.i2c import PN532_I2C  # type: ignore
            i2c = busio.I2C(board.SCL, board.SDA)
            reset = digitalio.DigitalInOut(
                getattr(board, f"D{self._cfg.nfc.reset_pin}")
            )
            pn532 = PN532_I2C(i2c, reset=reset, debug=False)
        elif iface == "uart":
            from adafruit_pn532.uart import PN532_UART  # type: ignore
            uart = busio.UART(board.TX, board.RX, baudrate=115200)
            pn532 = PN532_UART(uart, debug=False)
        else:
            raise ValueError(f"Unknown NFC interface: {iface!r}")

        pn532.SAM_configuration()
        return pn532

    def start(self, on_card: Callable[[str], None]) -> None:
        """Poll for cards.  Blocks — run this in a daemon thread."""
        pn532 = self._build_pn532()
        self._running = True
        last_uid: str | None = None
        last_seen: float = 0.0

        logger.info("NFC reader started (interface=%s)", self._cfg.nfc.interface)

        while self._running:
            uid_bytes = pn532.read_passive_target(timeout=_POLL_INTERVAL)
            if uid_bytes is None:
                last_uid = None
                continue

            uid = ":".join(f"{b:02X}" for b in uid_bytes)
            now = time.monotonic()

            # Debounce: ignore the same card within the hold-down window
            if uid == last_uid and (now - last_seen) < _DEBOUNCE_SECONDS:
                continue

            last_uid = uid
            last_seen = now
            logger.debug("Card scanned: %s", uid)
            try:
                on_card(uid)
            except Exception:
                logger.exception("Error in on_card callback for %s", uid)

    def stop(self) -> None:
        self._running = False


class MockNFCReader:
    """
    Development stub — no hardware needed.
    Emits UIDs from `uids` cyclically every `emit_interval` seconds.
    Pass emit_interval=0 or call emit() directly in tests for synchronous use.
    """

    def __init__(self, config=None, emit_interval: float = 5.0,
                 uids: list[str] | None = None) -> None:
        self._interval = emit_interval
        self._uids = uids or ["04:AB:CD:12"]
        self._running = False
        self._idx = 0
        self._callback: Callable[[str], None] | None = None

    def start(self, on_card: Callable[[str], None]) -> None:
        """Emit UIDs on a timer.  Blocks — run in a daemon thread."""
        self._callback = on_card
        self._running = True
        logger.info("MockNFCReader started (interval=%.1fs, uids=%s)",
                    self._interval, self._uids)
        while self._running:
            time.sleep(self._interval)
            if self._running:
                self.emit()

    def emit(self, uid: str | None = None) -> None:
        """Fire a card-scan event synchronously.  Useful in tests."""
        if self._callback is None:
            raise RuntimeError("Call start() or register a callback first")
        target = uid or self._uids[self._idx % len(self._uids)]
        self._idx += 1
        self._callback(target)

    def stop(self) -> None:
        self._running = False


def make_reader(config) -> NFCReader | MockNFCReader:
    if config.hardware.mock:
        return MockNFCReader(config)
    return NFCReader(config)
