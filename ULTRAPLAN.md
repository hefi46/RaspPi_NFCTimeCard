# ClockIn (RaspPi NFC TimeCard) — Ultraplan

## Vision

A self-contained NFC check-in/check-out terminal running on a Raspberry Pi. An employee taps an NFC card on a PN532 reader; an OLED display and buzzer confirm the action; a local SQLite database records the event. A web admin console served by the same Pi lets privileged users review logs, register cards, and manage users.

---

## Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | First-class RPi support, rich hardware libs |
| Web framework | Flask | Lightweight, synchronous, easy to embed in a thread |
| Database | SQLite (via `sqlite3`) | Zero-config, single file, plenty fast for this load |
| NFC reader | `adafruit-circuitpython-pn532` | Official Adafruit PN532 library |
| OLED | `adafruit-circuitpython-ssd1306` | Standard 128×64 SSD1306 over I2C |
| Buzzer | `RPi.GPIO` | Simple PWM tone via GPIO |
| Auth | Session cookie + `bcrypt` password hashing | Simple, no JWT overhead needed |
| Frontend | Vanilla HTML/CSS/JS (Jinja2 templates) | No build step, runs fine on Pi |
| Service | systemd unit | Auto-restart, boot launch |

---

## Repository Structure

```
RaspPi_NFCTimeCard/
├── requirements.txt
├── config.yaml                 # pin numbers, DB path, server port, etc.
├── src/
│   ├── main.py                 # entry point — starts NFC loop + Flask server
│   ├── config.py               # loads and validates config.yaml
│   ├── database.py             # SQLite connection + all SQL helpers
│   ├── nfc_reader.py           # PN532 polling loop; emits card-scan events
│   ├── display.py              # OLED text + buzzer tone helpers
│   ├── card_handler.py         # business logic: check-in/out toggle, log write
│   └── web/
│       ├── app.py              # Flask app factory
│       ├── auth.py             # login/logout routes + session guard decorator
│       ├── routes/
│       │   ├── api.py          # REST JSON endpoints
│       │   └── views.py        # HTML page routes
│       ├── templates/
│       │   ├── base.html
│       │   ├── login.html
│       │   ├── dashboard.html
│       │   ├── logs.html
│       │   ├── cards.html
│       │   └── users.html
│       └── static/
│           ├── css/
│           │   └── style.css
│           └── js/
│               └── app.js
├── tests/
│   ├── conftest.py             # shared fixtures (in-memory DB, mock hardware)
│   ├── test_database.py
│   ├── test_card_handler.py
│   └── test_api.py
├── scripts/
│   ├── install.sh              # apt deps, venv, enable systemd service
│   └── timecard.service        # systemd unit file
└── docs/
    └── wiring.md               # GPIO/I2C pin diagram
```

---

## Database Schema

```sql
CREATE TABLE users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    email      TEXT UNIQUE NOT NULL,
    password   TEXT NOT NULL,           -- bcrypt hash
    role       TEXT NOT NULL DEFAULT 'user',  -- 'admin' | 'user'
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE cards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT UNIQUE NOT NULL,   -- hex string, e.g. "04:AB:CD:12"
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    label       TEXT,                   -- optional friendly name
    assigned_at TEXT
);

CREATE TABLE time_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id    INTEGER REFERENCES cards(id),
    user_id    INTEGER REFERENCES users(id),
    action     TEXT NOT NULL,           -- 'check_in' | 'check_out'
    timestamp  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    expires_at TEXT NOT NULL
);
```

---

## REST API

All `/api/*` routes require a valid session cookie (role `admin`).

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Authenticate, set session cookie |
| `POST` | `/auth/logout` | Invalidate session |
| `GET` | `/api/logs` | List time logs; query params: `user_id`, `from`, `to`, `page` |
| `GET` | `/api/users` | List all users |
| `POST` | `/api/users` | Create user |
| `PATCH` | `/api/users/<id>` | Update name/email/role/password |
| `DELETE` | `/api/users/<id>` | Delete user |
| `GET` | `/api/cards` | List all cards |
| `POST` | `/api/cards` | Register a new card (uid required) |
| `PATCH` | `/api/cards/<id>` | Assign card to user or update label |
| `DELETE` | `/api/cards/<id>` | Remove card |

Internal (called by `card_handler.py`, not over HTTP):

- `database.record_scan(uid)` — resolves card → user, toggles check-in/out, writes `time_logs` row, returns action taken.

---

## NFC Scan Flow

```
PN532 polling loop detects card UID
        │
        ▼
card_handler.handle_scan(uid)
        │
        ├─ uid known? ──No──► display "Unknown card", short error buzz
        │
        └─ Yes
            │
            ▼
        lookup last log for this user
            │
            ├─ last == check_in  ──► action = check_out
            └─ otherwise         ──► action = check_in
                │
                ▼
        INSERT into time_logs
                │
                ▼
        display.show(name, action, time)
        display.buzz(action)   ← two beeps for in, one for out
```

---

## Admin Console Pages

### `/` → Dashboard
- Today's active check-ins count
- Last 10 log entries (card, user, action, time)
- Quick link to full logs

### `/logs` → Time Log
- Filterable/pageable table: user, date range, action type
- CSV export button

### `/cards` → Card Management
- Table: UID, label, assigned user, assigned date
- "Register card" button (enter UID manually or tap-to-register mode)
- Assign/reassign card to user inline

### `/users` → User Management
- Table: name, email, role, created date
- Add / edit / delete user
- Role toggle (user ↔ admin)

### `/login` → Login
- Email + password form
- Redirects to dashboard on success

---

## Implementation Phases

### Phase 1 — Foundation
1. `requirements.txt` with pinned deps
2. `config.yaml` with defaults + schema comment
3. `src/config.py` loader (pydantic or plain dataclass)
4. `src/database.py`: connect, `init_db()` (CREATE TABLE IF NOT EXISTS), all CRUD helpers
5. `tests/test_database.py` with an in-memory DB fixture

### Phase 2 — Hardware Abstraction
1. `src/nfc_reader.py`: real PN532 impl + `MockNFCReader` for tests
2. `src/display.py`: real SSD1306 + buzzer impl + `MockDisplay` stub
3. Hardware classes selected by `config.yaml` `mock_hardware: true/false`

### Phase 3 — Core Logic
1. `src/card_handler.py`: `handle_scan(uid)` with check-in/out toggle
2. `tests/test_card_handler.py` using mock hardware + in-memory DB

### Phase 4 — Web Backend
1. `src/web/app.py`: Flask factory, registers blueprints
2. `src/web/auth.py`: login/logout routes, `@require_admin` decorator
3. `src/web/routes/api.py`: all REST endpoints
4. `src/web/routes/views.py`: HTML page routes (render Jinja2 templates)
5. `tests/test_api.py`: endpoint tests with Flask test client

### Phase 5 — Admin Console UI
1. `base.html`: nav, session user display
2. `login.html`
3. `dashboard.html`
4. `logs.html`: filterable table + CSV export
5. `cards.html`: card list, register, assign
6. `users.html`: user list, add/edit/delete
7. `static/css/style.css`: clean responsive layout (no framework needed)
8. `static/js/app.js`: inline form submissions, fetch-based updates

### Phase 6 — Entry Point & Deployment
1. `src/main.py`: init DB, start NFC loop in background thread, start Flask
2. `scripts/timecard.service`: systemd unit (WorkingDirectory, ExecStart, Restart=always)
3. `scripts/install.sh`: `apt install` system deps, create venv, `pip install`, `systemctl enable`
4. `docs/wiring.md`: I2C pins for OLED, SPI pins for PN532, GPIO pin for buzzer

---

## config.yaml Shape

```yaml
database:
  path: /var/lib/timecard/timecard.db

server:
  host: 0.0.0.0
  port: 5000
  secret_key: CHANGE_ME

hardware:
  mock: false                # set true on dev machine without hardware
  nfc:
    interface: spi           # spi | i2c | uart
    reset_pin: 20
    req_pin: 16
  oled:
    i2c_address: 0x3C
    width: 128
    height: 64
  buzzer:
    gpio_pin: 18
```

---

## Key Constraints & Decisions

- **Single process**: NFC loop runs in a daemon thread; Flask runs in the main thread. No inter-process complexity.
- **No ORM**: Raw `sqlite3` keeps deps minimal and avoids migration tooling overhead on a Pi.
- **Mock hardware flag**: Lets all development and CI happen on a laptop without any hardware.
- **Session store in DB**: `sessions` table — no Redis, no in-memory dict that resets on restart.
- **No HTTPS initially**: Pi is on a local LAN. Document that users should put nginx + self-signed cert in front if exposed externally.
- **CSV export**: Done server-side with Python's `csv` module, streamed as a response; no JS needed.
