"""
Display + audio feedback abstraction.

Real hardware:  SSD1306 128×64 OLED over I2C, passive buzzer on a GPIO pin.
Mock:           prints to stdout — no hardware required.

Buzz patterns
-------------
  check_in   → two short beeps (happy tone)
  check_out  → one short beep
  error      → one long low buzz
"""

import time
import logging
from typing import Literal

logger = logging.getLogger(__name__)

BuzzPattern = Literal["check_in", "check_out", "error"]


class Display:
    """Real SSD1306 + RPi.GPIO buzzer.  Imports hardware libs lazily."""

    def __init__(self, config) -> None:
        self._cfg = config.hardware
        self._oled = None
        self._draw = None
        self._font = None
        self._image = None
        self._gpio_ready = False
        self._buzzer_pin = config.hardware.buzzer.gpio_pin
        self._setup()

    def _setup(self) -> None:
        import board  # type: ignore
        import busio  # type: ignore
        import adafruit_ssd1306  # type: ignore
        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        i2c = busio.I2C(board.SCL, board.SDA)
        cfg = self._cfg.oled
        self._oled = adafruit_ssd1306.SSD1306_I2C(
            cfg.width, cfg.height, i2c, addr=cfg.i2c_address
        )
        self._image = Image.new("1", (cfg.width, cfg.height))
        self._draw = ImageDraw.Draw(self._image)
        try:
            self._font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except OSError:
            self._font = ImageFont.load_default()

        import RPi.GPIO as GPIO  # type: ignore
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._buzzer_pin, GPIO.OUT)
        self._pwm = GPIO.PWM(self._buzzer_pin, 1000)
        self._gpio_ready = True

    def show(self, line1: str, line2: str = "", duration: float = 3.0) -> None:
        cfg = self._cfg.oled
        self._draw.rectangle((0, 0, cfg.width, cfg.height), outline=0, fill=0)
        self._draw.text((2, 4), line1, font=self._font, fill=255)
        if line2:
            self._draw.text((2, 26), line2, font=self._font, fill=255)
        self._oled.image(self._image)
        self._oled.show()
        if duration > 0:
            time.sleep(duration)
            self.clear()

    def clear(self) -> None:
        self._oled.fill(0)
        self._oled.show()

    def buzz(self, pattern: BuzzPattern) -> None:
        if not self._gpio_ready:
            return
        if pattern == "check_in":
            self._beep(880, 0.12)
            time.sleep(0.08)
            self._beep(880, 0.12)
        elif pattern == "check_out":
            self._beep(660, 0.15)
        elif pattern == "error":
            self._beep(220, 0.4)

    def _beep(self, freq: int, duration: float) -> None:
        self._pwm.ChangeFrequency(freq)
        self._pwm.start(50)
        time.sleep(duration)
        self._pwm.stop()

    def cleanup(self) -> None:
        import RPi.GPIO as GPIO  # type: ignore
        if self._gpio_ready:
            GPIO.cleanup(self._buzzer_pin)


class MockDisplay:
    """Stub that prints to stdout.  No hardware needed."""

    def show(self, line1: str, line2: str = "", duration: float = 3.0) -> None:
        msg = f"[DISPLAY] {line1}"
        if line2:
            msg += f" | {line2}"
        logger.info(msg)
        print(msg)

    def clear(self) -> None:
        logger.debug("[DISPLAY] clear")

    def buzz(self, pattern: BuzzPattern) -> None:
        msg = f"[BUZZER] {pattern}"
        logger.info(msg)
        print(msg)

    def cleanup(self) -> None:
        pass


def make_display(config) -> Display | MockDisplay:
    if config.hardware.mock:
        return MockDisplay()
    return Display(config)
