"""
Display + audio feedback for a 2.8" ILI9341 TFT (320×240, colour) + GPIO buzzer.

Idle mode
---------
start_idle() launches a daemon thread that redraws the screen every second:
  - NFC signal-wave logo (drawn with Pillow arcs)
  - Live HH:MM clock + date

Scan-result mode
----------------
show_scan_result(name, action) blocks for SCAN_DURATION seconds, rendering
a new frame ~20 fps:
  - Large ✓ (green) or ✗ (orange) symbol
  - Employee name + action label
  - Countdown bar that drains left→right

Generic messages (errors, registration capture) use show(line1, line2, duration).
"""

import threading
import time
import logging
from datetime import datetime
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

BuzzPattern = Literal["check_in", "check_out", "error"]

# ── Palette ────────────────────────────────────────────────────────────
_BG       = (20, 25, 60)
_NFC_BLUE = (0, 168, 224)
_WHITE    = (255, 255, 255)
_GRAY     = (120, 130, 160)
_GREEN    = (50, 210, 100)
_ORANGE   = (255, 150, 30)
_RED      = (210, 55, 55)
_TRACK    = (40, 48, 90)

# ── Layout ─────────────────────────────────────────────────────────────
_W, _H = 320, 240
SCAN_DURATION = 5.0

_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _load_fonts() -> dict:
    fonts = {}
    specs = [
        ("xl",  64, _FONT_BOLD),
        ("lg",  36, _FONT_BOLD),
        ("md",  22, _FONT_REG),
        ("sm",  16, _FONT_REG),
        ("xs",  13, _FONT_REG),
    ]
    for name, size, path in specs:
        try:
            fonts[name] = ImageFont.truetype(path, size)
        except OSError:
            fonts[name] = ImageFont.load_default()
    return fonts


def _draw_nfc_logo(draw: ImageDraw.ImageDraw, cx: int, cy: int,
                   color: tuple, scale: float = 1.0) -> None:
    """
    Three concentric arcs (∩-shaped, open at the bottom) + a central dot.
    Reads like the standard NFC / contactless signal icon.
    """
    dot_r = max(1, int(9 * scale))
    draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=color)

    # Arcs: start=135 → end=45 clockwise draws the upper 270° of each circle,
    # leaving the bottom open — classic contactless / WiFi-up symbol.
    for raw_r in [28, 52, 76]:
        r = int(raw_r * scale)
        w = max(1, int(5 * scale))
        bbox = [cx - r, cy - r, cx + r, cy + r]
        draw.arc(bbox, start=135, end=45, fill=color, width=w)


class Display:
    """ILI9341 320×240 colour TFT with idle animation and scan confirmation."""

    def __init__(self, config) -> None:
        self._cfg = config.hardware
        self._fonts = _load_fonts()
        self._tft = self._setup_tft()
        self._show_event = threading.Event()
        self._running = False
        self._idle_thread: threading.Thread | None = None
        # GPIO PWM handle, initialised lazily on first buzz()
        self._pwm = None

    def _setup_tft(self):
        import board          # type: ignore
        import busio          # type: ignore
        import digitalio      # type: ignore
        from adafruit_rgb_display import ili9341  # type: ignore

        cfg = self._cfg.tft
        spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
        cs  = digitalio.DigitalInOut(getattr(board, f"D{cfg.cs_pin}"))
        dc  = digitalio.DigitalInOut(getattr(board, f"D{cfg.dc_pin}"))
        rst = digitalio.DigitalInOut(getattr(board, f"D{cfg.rst_pin}"))
        return ili9341.ILI9341(
            spi, cs=cs, dc=dc, rst=rst,
            width=_W, height=_H,
            rotation=cfg.rotation,
            baudrate=cfg.baudrate,
        )

    # ── Idle loop ──────────────────────────────────────────────────────

    def start_idle(self) -> None:
        """Spawn the daemon thread that keeps the idle screen alive."""
        self._running = True
        self._idle_thread = threading.Thread(target=self._idle_loop, daemon=True)
        self._idle_thread.start()
        logger.info("Display idle loop started")

    def _idle_loop(self) -> None:
        while self._running:
            if not self._show_event.is_set():
                try:
                    self._blit(self._render_idle())
                except Exception:
                    logger.exception("Idle render error")
            time.sleep(1.0)

    def _render_idle(self) -> Image.Image:
        img = self._blank()
        draw = ImageDraw.Draw(img)
        now = datetime.now()

        # NFC logo — centered horizontally, upper portion of screen
        _draw_nfc_logo(draw, cx=160, cy=95, color=_NFC_BLUE, scale=1.0)

        # Prompt label
        draw.text((160, 158), "TAP CARD", font=self._fonts["sm"],
                  fill=_GRAY, anchor="mm")

        # Large clock
        draw.text((160, 193), now.strftime("%H:%M"),
                  font=self._fonts["lg"], fill=_WHITE, anchor="mm")

        # Date
        draw.text((160, 224), now.strftime("%a  %d %b %Y"),
                  font=self._fonts["xs"], fill=_GRAY, anchor="mm")

        return img

    # ── Scan result ────────────────────────────────────────────────────

    def show_scan_result(self, name: str, action: str) -> None:
        """
        Display check-in/out confirmation with a draining countdown bar.
        Blocks for SCAN_DURATION seconds; idle loop resumes automatically.
        """
        self._show_event.set()
        start = time.monotonic()
        try:
            while True:
                remaining = SCAN_DURATION - (time.monotonic() - start)
                if remaining <= 0:
                    break
                self._blit(self._render_scan_result(name, action, remaining))
                time.sleep(0.05)   # ~20 fps
        finally:
            self._show_event.clear()

    def _render_scan_result(self, name: str, action: str,
                            remaining: float) -> Image.Image:
        img = self._blank()
        draw = ImageDraw.Draw(img)

        is_in = action == "check_in"
        color  = _GREEN if is_in else _ORANGE
        symbol = "✓" if is_in else "✗"
        label  = "CHECK IN" if is_in else "CHECK OUT"

        # Large symbol
        draw.text((160, 58), symbol,
                  font=self._fonts["xl"], fill=color, anchor="mm")

        # Name — truncate gracefully
        display_name = name if len(name) <= 18 else name[:17] + "…"
        draw.text((160, 122), display_name,
                  font=self._fonts["lg"], fill=_WHITE, anchor="mm")

        # Action label
        draw.text((160, 158), label,
                  font=self._fonts["md"], fill=color, anchor="mm")

        # Time
        draw.text((160, 185), datetime.now().strftime("%H:%M  •  %d %b"),
                  font=self._fonts["xs"], fill=_GRAY, anchor="mm")

        # Countdown bar — drains left to right
        bar_x, bar_y, bar_h = 10, 218, 12
        bar_max = _W - 20
        bar_now = max(0, int((remaining / SCAN_DURATION) * bar_max))
        draw.rectangle([bar_x, bar_y, bar_x + bar_max, bar_y + bar_h], fill=_TRACK)
        if bar_now > 0:
            draw.rectangle([bar_x, bar_y, bar_x + bar_now, bar_y + bar_h], fill=color)

        return img

    # ── Generic message ────────────────────────────────────────────────

    def show(self, line1: str, line2: str = "", duration: float = 3.0) -> None:
        """Generic message screen — used for errors and registration capture."""
        self._show_event.set()
        start = time.monotonic()
        try:
            while (time.monotonic() - start) < duration:
                remaining = duration - (time.monotonic() - start)
                self._blit(self._render_message(line1, line2, remaining, duration))
                time.sleep(0.1)
        finally:
            self._show_event.clear()

    def _render_message(self, line1: str, line2: str,
                        remaining: float, total: float) -> Image.Image:
        img = self._blank()
        draw = ImageDraw.Draw(img)

        draw.text((160, 90), line1,
                  font=self._fonts["lg"], fill=_WHITE, anchor="mm")
        if line2:
            draw.text((160, 135), line2,
                      font=self._fonts["md"], fill=_GRAY, anchor="mm")

        bar_x, bar_y, bar_h = 10, 218, 12
        bar_max = _W - 20
        bar_now = max(0, int((remaining / total) * bar_max))
        draw.rectangle([bar_x, bar_y, bar_x + bar_max, bar_y + bar_h], fill=_TRACK)
        if bar_now > 0:
            draw.rectangle([bar_x, bar_y, bar_x + bar_now, bar_y + bar_h],
                           fill=_NFC_BLUE)

        return img

    # ── Audio ──────────────────────────────────────────────────────────

    def buzz(self, pattern: BuzzPattern) -> None:
        import RPi.GPIO as GPIO  # type: ignore

        pin = self._cfg.buzzer.gpio_pin
        if self._pwm is None:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.OUT)
            self._pwm = GPIO.PWM(pin, 1000)

        if pattern == "check_in":
            self._beep(880, 0.12)
            time.sleep(0.08)
            self._beep(880, 0.12)
        elif pattern == "check_out":
            self._beep(660, 0.15)
        elif pattern == "error":
            self._beep(220, 0.40)

    def _beep(self, freq: int, duration: float) -> None:
        self._pwm.ChangeFrequency(freq)
        self._pwm.start(50)
        time.sleep(duration)
        self._pwm.stop()

    # ── Helpers ────────────────────────────────────────────────────────

    def _blank(self) -> Image.Image:
        return Image.new("RGB", (_W, _H), _BG)

    def _blit(self, img: Image.Image) -> None:
        self._tft.image(img)

    def cleanup(self) -> None:
        self._running = False
        if self._pwm is not None:
            try:
                import RPi.GPIO as GPIO  # type: ignore
                GPIO.cleanup(self._cfg.buzzer.gpio_pin)
            except Exception:
                pass


# ── Mock ───────────────────────────────────────────────────────────────

class MockDisplay:
    """Dev/test stub — prints to stdout, no blocking, no hardware needed."""

    def start_idle(self) -> None:
        logger.info("[DISPLAY] idle screen active")

    def show(self, line1: str, line2: str = "", duration: float = 3.0) -> None:
        msg = f"[DISPLAY] {line1}" + (f"  |  {line2}" if line2 else "")
        logger.info(msg)
        print(msg)

    def show_scan_result(self, name: str, action: str) -> None:
        symbol = "✓" if action == "check_in" else "✗"
        label  = "Check In" if action == "check_in" else "Check Out"
        msg = f"[DISPLAY] {symbol}  {name}  —  {label}  ({SCAN_DURATION:.0f}s countdown)"
        logger.info(msg)
        print(msg)

    def buzz(self, pattern: BuzzPattern) -> None:
        msg = f"[BUZZER]  {pattern}"
        logger.info(msg)
        print(msg)

    def cleanup(self) -> None:
        pass


def make_display(config) -> "Display | MockDisplay":
    if config.hardware.mock:
        return MockDisplay()
    return Display(config)
