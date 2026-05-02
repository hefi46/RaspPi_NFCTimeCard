# ClockIn (RaspPi NFC TimeCard)

Self-contained NFC check-in / check-out terminal for a Raspberry Pi. Tap a card on a PN532 reader — a 2.8" colour TFT and buzzer confirm the action, and a web admin console served by the same Pi lets privileged users review logs, register cards, and manage employees.

**Status: Phases 1–5 complete. Phase 6 (deployment) pending.**

---

## Features

- **NFC tap** — PN532 reads the card UID; unknown or unassigned cards get an error buzz
- **Check-in / check-out toggle** — last action per user determines the next one automatically
- **TFT display** — 2.8" ILI9341 (320×240 colour)
  - Idle: animated NFC logo + live clock
  - On tap: ✓ / ✗, employee name, action, and a 5-second countdown bar
- **Buzzer feedback** — two beeps for check-in, one for check-out, long buzz for errors
- **Web admin console** — Flask app served on the Pi's local network
  - Dashboard with live checked-in count and recent activity
  - Time log with user/date filtering and CSV export
  - Card management with tap-to-register (Pi reader captures UID directly)
  - User management with role-based access (admin / user)
- **Session auth** — bcrypt passwords, httponly session cookie, DB-backed sessions

---

## Hardware

| Part | Detail |
|---|---|
| Raspberry Pi | Zero 2W (recommended) or Pi 4 |
| NFC reader | PN532 module — SPI, I2C, or UART |
| Display | 2.8" ILI9341 TFT, 320×240, SPI |
| Buzzer | 3.3V passive piezo |
| SD card | 16 GB+ Class 10 / A1 |
| NFC cards | NTAG215 stickers or MIFARE Ultralight (avoid Classic for iOS compatibility) |

---

## Project Structure

```
src/
├── config.py          # YAML config loader (dataclasses)
├── database.py        # SQLite — all CRUD helpers, no ORM
├── nfc_reader.py      # PN532 polling loop + MockNFCReader for dev
├── display.py         # ILI9341 TFT (idle animation, scan result) + MockDisplay
├── card_handler.py    # Check-in/out logic + tap-to-register mode
└── web/
    ├── app.py         # Flask app factory
    ├── auth.py        # Login/logout routes + require_admin / login_required decorators
    ├── routes/
    │   ├── api.py     # REST API (/api/*)
    │   └── views.py   # HTML page routes
    ├── templates/     # Jinja2 templates (base, login, dashboard, logs, cards, users)
    └── static/        # style.css, app.js
config.yaml            # Runtime config (DB path, server, hardware pins)
```

---

## Development Setup

Requires Python 3.11+.

```bash
pip install -r requirements.txt
```

Set `mock: true` in `config.yaml` under `hardware` to run without any physical hardware — `MockNFCReader` and `MockDisplay` will be used automatically.

```bash
# Run tests
pytest

# Start the server (mock hardware mode)
python -m src.main        # Phase 6 — not yet implemented; see below
```

---

## API

All `/api/*` routes require an admin session cookie.

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Authenticate |
| `POST` | `/auth/logout` | Sign out |
| `GET` | `/api/users` | List users |
| `POST` | `/api/users` | Create user |
| `PATCH` | `/api/users/<id>` | Update user |
| `DELETE` | `/api/users/<id>` | Delete user |
| `GET` | `/api/cards` | List cards |
| `POST` | `/api/cards` | Register card (manual UID) |
| `PATCH` | `/api/cards/<id>` | Assign / relabel card |
| `DELETE` | `/api/cards/<id>` | Remove card |
| `POST` | `/api/cards/capture` | Tap-to-register — blocks up to 30 s for a card tap |
| `GET` | `/api/logs` | Time logs (filterable: user\_id, from, to, page) |
| `GET` | `/api/logs/export.csv` | Download filtered logs as CSV |

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| 1 | Foundation — config, DB schema, CRUD helpers | ✅ Done |
| 2 | Hardware abstraction — PN532 + TFT + buzzer (real + mock) | ✅ Done |
| 3 | Core logic — check-in/out toggle, tap-to-register | ✅ Done |
| 4 | Web backend — Flask, session auth, REST API | ✅ Done |
| 5 | Admin console UI — all pages, tap-to-register flow | ✅ Done |
| 6 | Deployment — `main.py`, systemd service, install script, wiring diagram | 🔲 Pending |

---

## Configuration

`config.yaml` (defaults shown):

```yaml
database:
  path: /var/lib/timecard/timecard.db

server:
  host: 0.0.0.0
  port: 5000
  secret_key: CHANGE_ME

hardware:
  mock: false
  nfc:
    interface: spi
    reset_pin: 20
    req_pin: 16
  tft:
    cs_pin: 8
    dc_pin: 25
    rst_pin: 24
    rotation: 90
    baudrate: 64000000
  buzzer:
    gpio_pin: 18
```

---

## Tests

71 tests across database, card handler, and API layers. Run with:

```bash
pytest
```

Hardware libraries are never imported during tests — `mock: true` is enforced via `MockDisplay` and `MockNFCReader`.
