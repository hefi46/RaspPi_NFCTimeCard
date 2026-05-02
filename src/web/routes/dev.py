"""
Dev-only tap simulator — only mounted when config.hardware.mock = true.

Routes:
  GET  /dev        Browser UI to simulate card taps
  POST /dev/tap    JSON API: {"uid": "04:AA:BB:CC"} → fires handle_scan()
"""

from flask import Blueprint, current_app, jsonify, render_template_string, request

from src.web.auth import require_admin

dev_bp = Blueprint("dev", __name__, url_prefix="/dev")

_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Tap Simulator — NFC TimeCard Dev</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, sans-serif;
      background: #0f1117;
      color: #e0e0e0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 3rem 1rem;
    }
    h1 { font-size: 1.4rem; margin-bottom: .25rem; color: #00a8e0; }
    .sub { color: #666; font-size: .85rem; margin-bottom: 2rem; }
    .card {
      background: #1a1f2e;
      border: 1px solid #2a2f3e;
      border-radius: 10px;
      padding: 1.5rem;
      width: 100%;
      max-width: 480px;
    }
    label { display: block; font-size: .8rem; color: #888; margin-bottom: 4px; }
    .row { display: flex; gap: .5rem; margin-bottom: 1rem; }
    input[type=text] {
      flex: 1;
      padding: 9px 12px;
      background: #0f1117;
      border: 1px solid #333;
      border-radius: 6px;
      color: #e0e0e0;
      font-size: .95rem;
      font-family: monospace;
    }
    input[type=text]:focus { outline: 2px solid #00a8e0; border-color: transparent; }
    button {
      padding: 9px 18px;
      background: #00a8e0;
      color: #fff;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: .9rem;
      font-weight: 600;
      white-space: nowrap;
    }
    button:hover { background: #0088bb; }
    button:disabled { opacity: .5; cursor: not-allowed; }
    .presets { display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: 1.25rem; }
    .presets span { font-size: .75rem; color: #666; align-self: center; }
    .preset {
      background: #22273a;
      border: 1px solid #333;
      color: #aaa;
      font-size: .78rem;
      font-family: monospace;
      padding: 4px 10px;
      border-radius: 5px;
    }
    .preset:hover { background: #2c3348; color: #e0e0e0; }
    .result {
      background: #0f1117;
      border: 1px solid #2a2f3e;
      border-radius: 6px;
      padding: 1rem;
      font-family: monospace;
      font-size: .85rem;
      white-space: pre;
      min-height: 80px;
      color: #666;
    }
    .result.ok  { color: #50d280; border-color: #1a4a2a; }
    .result.err { color: #ff6b6b; border-color: #4a1a1a; }
    .result.warn { color: #f9ab00; border-color: #4a3a00; }
    .section-label {
      font-size: .75rem;
      color: #555;
      margin-bottom: .5rem;
      text-transform: uppercase;
      letter-spacing: .05em;
    }
    hr { border: none; border-top: 1px solid #2a2f3e; margin: 1.25rem 0; }
    a { color: #00a8e0; font-size: .85rem; }
  </style>
</head>
<body>
  <h1>⚡ NFC Tap Simulator</h1>
  <p class="sub">Mock hardware mode — no physical reader needed</p>

  <div class="card">
    <p class="section-label">Simulate a card tap</p>
    <label for="uid">Card UID</label>
    <div class="row">
      <input id="uid" type="text" value="04:AA:BB:CC" spellcheck="false">
      <button id="tap-btn" onclick="tap()">Tap</button>
    </div>

    <div class="presets">
      <span>Quick:</span>
      <button class="preset" onclick="set('04:AA:BB:CC')">04:AA:BB:CC</button>
      <button class="preset" onclick="set('04:11:22:33')">04:11:22:33</button>
      <button class="preset" onclick="set('04:DE:AD:BE')">04:DE:AD:BE</button>
      <button class="preset" onclick="set('FF:FF:FF:FF')">FF:FF:FF:FF (unknown)</button>
    </div>

    <hr>
    <p class="section-label">Result</p>
    <div id="result" class="result">— tap a card to see the result —</div>

    <hr>
    <a href="/">← Back to admin console</a>
  </div>

  <script>
    function set(v) { document.getElementById('uid').value = v; }

    async function tap() {
      const btn = document.getElementById('tap-btn');
      const uid = document.getElementById('uid').value.trim().toUpperCase();
      const el  = document.getElementById('result');

      btn.disabled = true;
      el.className = 'result';
      el.textContent = 'sending…';

      try {
        const res  = await fetch('/dev/tap', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ uid }),
        });
        const data = await res.json();

        if (!res.ok) {
          el.className = 'result err';
          el.textContent = JSON.stringify(data, null, 2);
        } else if (data.result === 'no_match') {
          el.className = 'result warn';
          el.textContent = `⚠  UID not recognised or card unassigned\\n\\n${JSON.stringify(data, null, 2)}`;
        } else {
          const icon = data.result === 'check_in' ? '✓' : '✗';
          el.className = 'result ok';
          el.textContent = `${icon}  ${data.user}  →  ${data.result.replace('_', ' ')}\\n\\n${JSON.stringify(data, null, 2)}`;
        }
      } catch (e) {
        el.className = 'result err';
        el.textContent = 'Network error: ' + e.message;
      } finally {
        btn.disabled = false;
      }
    }

    document.getElementById('uid').addEventListener('keydown', e => {
      if (e.key === 'Enter') tap();
    });
  </script>
</body>
</html>
"""


@dev_bp.route("/", methods=["GET"])
@require_admin
def dev_page():
    return render_template_string(_PAGE)


@dev_bp.route("/tap", methods=["POST"])
@require_admin
def simulate_tap():
    handler = current_app.config.get("CARD_HANDLER")
    if handler is None:
        return jsonify({"error": "Card handler not available"}), 503

    data = request.get_json(force=True) or {}
    uid = (data.get("uid") or "").strip().upper()
    if not uid:
        return jsonify({"error": "uid is required"}), 400

    result = handler.handle_scan(uid)

    if result is None:
        return jsonify({"ok": True, "result": "no_match", "uid": uid})

    return jsonify({
        "ok": True,
        "result": result["action"],
        "user": result["user"]["name"],
        "uid": uid,
        "log_id": result["log_id"],
    })
