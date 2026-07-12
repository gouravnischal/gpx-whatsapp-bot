"""Flask webhook for the GPX Express chatbot — WhatsApp + Instagram + Messenger.

One server, one /webhook URL, three platforms. Meta tells them apart by the
top-level "object" field:
  whatsapp_business_account -> WhatsApp Cloud API
  page                      -> Facebook Messenger
  instagram                 -> Instagram DMs

Endpoints:
  GET  /webhook  -> Meta verification handshake (same VERIFY_TOKEN for all)
  POST /webhook  -> incoming message events
  GET  /          -> health check
  GET  /leads     -> JSON of captured leads (protect before going public!)
  GET  /admin     -> Auto-learning admin dashboard
  GET  /api/unrecognized    -> JSON of unrecognized queries
  POST /api/smart-alias     -> Add a smart alias
  GET  /api/smart-aliases   -> List all smart aliases
  DELETE /api/smart-alias/<id> -> Delete a smart alias
  GET  /api/learning-stats  -> Learning statistics

Run locally:   python app.py
Run in prod:   gunicorn app:app
"""
import logging
import threading
import time

from flask import Flask, request, jsonify

import config
import store
import conversation
from channels import WhatsAppChannel, MessengerChannel

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gpx-bot")

app = Flask(__name__)
store.init_db()

WA = WhatsAppChannel()
MSGR = MessengerChannel("messenger")
IG = MessengerChannel("instagram")

# Channel lookup for follow-up worker
_CHANNELS = {"whatsapp": WA, "messenger": MSGR, "instagram": IG}

_seen = set()


def _once(mid):
    """True the first time we see a message id (de-dupe Meta retries)."""
    if not mid:
        return True
    if mid in _seen:
        return False
    _seen.add(mid)
    if len(_seen) > 5000:
        _seen.clear()
    return True


@app.route("/", methods=["GET"])
def health():
    return "GPX bot running ✅ (WhatsApp + Instagram + Messenger)", 200


@app.route("/leads", methods=["GET"])
def leads():
    return jsonify(store.recent_leads()), 200


@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == config.VERIFY_TOKEN:
        log.info("Webhook verified.")
        return challenge, 200
    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def incoming():
    payload = request.get_json(silent=True) or {}
    obj = payload.get("object", "")
    try:
        if obj == "whatsapp_business_account":
            _handle_whatsapp(payload)
        elif obj == "page":
            _handle_messaging(payload, MSGR)
        elif obj == "instagram":
            _handle_messaging(payload, IG)
        else:
            log.info("Ignoring webhook object: %s", obj)
    except Exception as e:
        log.exception("Error handling webhook: %s", e)
    return jsonify(status="ok"), 200


# ---- WhatsApp Cloud API shape ------------------------------------------
def _handle_whatsapp(payload):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for message in change.get("value", {}).get("messages", []):
                if not _once(message.get("id")):
                    continue
                user_id = message.get("from")
                mtype = message.get("type")
                text, reply_id = "", None
                if mtype == "text":
                    text = message.get("text", {}).get("body", "")
                elif mtype == "interactive":
                    inter = message.get("interactive", {})
                    if inter.get("type") == "button_reply":
                        reply_id = inter["button_reply"]["id"]
                        text = inter["button_reply"].get("title", "")
                    elif inter.get("type") == "list_reply":
                        reply_id = inter["list_reply"]["id"]
                        text = inter["list_reply"].get("title", "")
                elif mtype == "button":
                    text = message.get("button", {}).get("text", "")
                elif mtype in ("image", "document", "video", "audio", "sticker"):
                    # Media message — log it, acknowledge, and notify agent
                    media_data = message.get(mtype, {})
                    media_id = media_data.get("id", "")
                    caption = media_data.get("caption", "")
                    store.log_media(user_id, "whatsapp", mtype, media_id, caption)
                    conversation.handle_media(WA, user_id, mtype, caption)
                    continue
                log.info("[whatsapp] %s text=%r reply=%s", user_id, text, reply_id)
                conversation.handle_message(WA, user_id, text, reply_id)


# ---- Messenger / Instagram shape (shared) ------------------------------
def _handle_messaging(payload, channel):
    for entry in payload.get("entry", []):
        for event in entry.get("messaging", []):
            msg = event.get("message")
            if not msg or msg.get("is_echo"):
                continue  # skip echoes, delivery & read receipts
            if not _once(msg.get("mid")):
                continue
            user_id = event.get("sender", {}).get("id")
            text, reply_id = msg.get("text", ""), None
            if msg.get("quick_reply"):
                reply_id = msg["quick_reply"].get("payload")
            # Handle attachments (images, docs, etc.)
            attachments = msg.get("attachments", [])
            if attachments and not text:
                att = attachments[0]
                att_type = att.get("type", "file")
                store.log_media(user_id, channel.name, att_type,
                                att.get("payload", {}).get("url", ""), "")
                conversation.handle_media(channel, user_id, att_type, "")
                continue
            log.info("[%s] %s text=%r reply=%s", channel.name, user_id, text, reply_id)
            conversation.handle_message(channel, user_id, text, reply_id)


# ---- Auto-Learning Admin Panel -----------------------------------------
# TODO: add auth before production

ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GPX Express - Admin Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f0f2f5;
    color: #1a1a2e;
    min-height: 100vh;
  }
  .header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: #fff;
    padding: 20px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  }
  .header h1 { font-size: 22px; font-weight: 700; }
  .header .subtitle { font-size: 13px; opacity: 0.7; margin-top: 2px; }
  .header .badge {
    background: #25d366;
    color: #fff;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
  }
  .container { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }

  /* Stats Cards */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }
  .stat-card {
    background: #fff;
    border-radius: 10px;
    padding: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }
  .stat-card .label { font-size: 13px; color: #666; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-card .value { font-size: 32px; font-weight: 700; margin-top: 6px; color: #1a1a2e; }
  .stat-card.green .value { color: #25d366; }
  .stat-card.orange .value { color: #e67e22; }
  .stat-card.blue .value { color: #3498db; }

  /* Sections */
  .section {
    background: #fff;
    border-radius: 10px;
    padding: 24px;
    margin-bottom: 24px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  }
  .section h2 {
    font-size: 17px;
    font-weight: 600;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 2px solid #f0f2f5;
  }

  /* Tables */
  table { width: 100%; border-collapse: collapse; }
  th {
    text-align: left;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #888;
    padding: 10px 12px;
    border-bottom: 2px solid #f0f2f5;
  }
  td {
    padding: 10px 12px;
    border-bottom: 1px solid #f0f2f5;
    font-size: 14px;
  }
  tr:hover td { background: #f8f9fa; }

  /* Buttons */
  .btn {
    padding: 6px 14px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    transition: opacity 0.2s;
  }
  .btn:hover { opacity: 0.85; }
  .btn-primary { background: #25d366; color: #fff; }
  .btn-danger { background: #e74c3c; color: #fff; }
  .btn-sm { padding: 4px 10px; font-size: 12px; }

  /* Add Alias Form */
  .alias-form {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
    margin-top: 16px;
    padding: 16px;
    background: #f8f9fa;
    border-radius: 8px;
  }
  .alias-form input {
    padding: 8px 12px;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 14px;
    flex: 1;
    min-width: 180px;
  }
  .alias-form input:focus { outline: none; border-color: #25d366; }
  .alias-form label { font-size: 13px; color: #666; font-weight: 500; }

  /* Modal overlay */
  .modal-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.4);
    z-index: 1000;
    align-items: center;
    justify-content: center;
  }
  .modal-overlay.active { display: flex; }
  .modal {
    background: #fff;
    border-radius: 12px;
    padding: 28px;
    width: 420px;
    max-width: 90vw;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
  }
  .modal h3 { margin-bottom: 16px; font-size: 17px; }
  .modal input {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 14px;
    margin-bottom: 12px;
  }
  .modal input:focus { outline: none; border-color: #25d366; }
  .modal .modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 8px; }
  .modal .btn-cancel { background: #eee; color: #333; }

  .empty-msg { text-align: center; padding: 32px; color: #999; font-size: 14px; }
  .count-badge {
    background: #e74c3c;
    color: #fff;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 600;
  }
  .category-tag {
    background: #eef2ff;
    color: #3b5bdb;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
  }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>GPX Express</h1>
    <div class="subtitle">Auto-Learning Admin Dashboard</div>
  </div>
  <span class="badge">Bot Active</span>
</div>

<div class="container">
  <!-- Stats -->
  <div class="stats-row">
    <div class="stat-card orange">
      <div class="label">Total Unrecognized</div>
      <div class="value" id="stat-total">--</div>
    </div>
    <div class="stat-card blue">
      <div class="label">Unique Queries</div>
      <div class="value" id="stat-unique">--</div>
    </div>
    <div class="stat-card green">
      <div class="label">Resolved</div>
      <div class="value" id="stat-resolved">--</div>
    </div>
  </div>

  <!-- Unrecognized Queries -->
  <div class="section">
    <h2>Unrecognized Queries</h2>
    <table>
      <thead>
        <tr>
          <th>Count</th>
          <th>Input Text</th>
          <th>Category</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody id="unrecognized-body">
        <tr><td colspan="4" class="empty-msg">Loading...</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Add Smart Alias (manual) -->
  <div class="section">
    <h2>Add Smart Alias</h2>
    <div class="alias-form">
      <div>
        <label>Input text (what the user types)</label>
        <input type="text" id="alias-input" placeholder='e.g. "send to mumbai"'>
      </div>
      <div>
        <label>Maps to (destination / action)</label>
        <input type="text" id="alias-maps-to" placeholder='e.g. "mumbai"'>
      </div>
      <button class="btn btn-primary" onclick="addAlias()">Add Alias</button>
    </div>
  </div>

  <!-- Current Smart Aliases -->
  <div class="section">
    <h2>Smart Aliases</h2>
    <table>
      <thead>
        <tr>
          <th>Input Text</th>
          <th>Maps To</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody id="aliases-body">
        <tr><td colspan="3" class="empty-msg">Loading...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<!-- Modal for quick alias from unrecognized row -->
<div class="modal-overlay" id="alias-modal">
  <div class="modal">
    <h3>Create Smart Alias</h3>
    <label style="font-size:13px;color:#666;">Input text</label>
    <input type="text" id="modal-input" readonly style="background:#f8f9fa;">
    <label style="font-size:13px;color:#666;">Maps to</label>
    <input type="text" id="modal-maps-to" placeholder="Enter destination / action">
    <div class="modal-actions">
      <button class="btn btn-cancel" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" onclick="submitModal()">Save Alias</button>
    </div>
  </div>
</div>

<script>
  // TODO: add auth before production

  async function loadStats() {
    try {
      const r = await fetch('/api/learning-stats');
      const data = await r.json();
      document.getElementById('stat-total').textContent = data.total_unrecognized || 0;
      document.getElementById('stat-unique').textContent = data.unique_queries || 0;
      document.getElementById('stat-resolved').textContent = data.resolved_count || 0;
    } catch(e) { console.error('Failed to load stats', e); }
  }

  async function loadUnrecognized() {
    try {
      const r = await fetch('/api/unrecognized');
      const rows = await r.json();
      const tbody = document.getElementById('unrecognized-body');
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">No unrecognized queries yet</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(row => `
        <tr>
          <td><span class="count-badge">${row.cnt || 1}</span></td>
          <td>${escapeHtml(row.user_input)}</td>
          <td><span class="category-tag">${escapeHtml(row.category || 'unknown')}</span></td>
          <td><button class="btn btn-primary btn-sm" onclick="openModal('${escapeJs(row.user_input)}')">Add Alias</button></td>
        </tr>
      `).join('');
    } catch(e) { console.error('Failed to load unrecognized', e); }
  }

  async function loadAliases() {
    try {
      const r = await fetch('/api/smart-aliases');
      const rows = await r.json();
      const tbody = document.getElementById('aliases-body');
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">No smart aliases defined</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(row => `
        <tr>
          <td>${escapeHtml(row.input)}</td>
          <td><strong>${escapeHtml(row.maps_to)}</strong></td>
          <td><button class="btn btn-danger btn-sm" onclick="deleteAlias('${row.id || escapeJs(row.input)}')">Delete</button></td>
        </tr>
      `).join('');
    } catch(e) { console.error('Failed to load aliases', e); }
  }

  async function addAlias() {
    const input = document.getElementById('alias-input').value.trim();
    const maps_to = document.getElementById('alias-maps-to').value.trim();
    if (!input || !maps_to) { alert('Both fields are required.'); return; }
    try {
      const r = await fetch('/api/smart-alias', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({input, maps_to})
      });
      if (r.ok) {
        document.getElementById('alias-input').value = '';
        document.getElementById('alias-maps-to').value = '';
        refreshAll();
      } else {
        const err = await r.json();
        alert('Error: ' + (err.error || 'Unknown error'));
      }
    } catch(e) { alert('Failed to add alias'); }
  }

  async function deleteAlias(aliasId) {
    if (!confirm('Delete this alias?')) return;
    try {
      const r = await fetch('/api/smart-alias/' + encodeURIComponent(aliasId), {method: 'DELETE'});
      if (r.ok) refreshAll();
      else alert('Failed to delete alias');
    } catch(e) { alert('Failed to delete alias'); }
  }

  function openModal(inputText) {
    document.getElementById('modal-input').value = inputText;
    document.getElementById('modal-maps-to').value = '';
    document.getElementById('alias-modal').classList.add('active');
    document.getElementById('modal-maps-to').focus();
  }

  function closeModal() {
    document.getElementById('alias-modal').classList.remove('active');
  }

  async function submitModal() {
    const input = document.getElementById('modal-input').value.trim();
    const maps_to = document.getElementById('modal-maps-to').value.trim();
    if (!maps_to) { alert('Please enter a destination.'); return; }
    try {
      const r = await fetch('/api/smart-alias', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({input, maps_to})
      });
      if (r.ok) {
        closeModal();
        refreshAll();
      } else {
        const err = await r.json();
        alert('Error: ' + (err.error || 'Unknown error'));
      }
    } catch(e) { alert('Failed to add alias'); }
  }

  function refreshAll() {
    loadStats();
    loadUnrecognized();
    loadAliases();
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function escapeJs(str) {
    if (!str) return '';
    return str.replace(/\\\\/g,'\\\\\\\\').replace(/'/g,"\\\\'").replace(/"/g,'\\\\"');
  }

  // Initial load and auto-refresh every 30s
  refreshAll();
  setInterval(refreshAll, 30000);
</script>
</body>
</html>"""


# TODO: add auth before production
@app.route("/admin", methods=["GET"])
def admin_dashboard():
    return ADMIN_HTML, 200


@app.route("/api/unrecognized", methods=["GET"])
def api_unrecognized():
    return jsonify(store.get_unrecognized()), 200


@app.route("/api/smart-alias", methods=["POST"])
def api_add_smart_alias():
    data = request.get_json(silent=True) or {}
    input_text = data.get("input", "").strip()
    maps_to = data.get("maps_to", "").strip()
    if not input_text or not maps_to:
        return jsonify(error="Both 'input' and 'maps_to' are required."), 400
    store.add_smart_alias(input_text, maps_to)
    store.mark_resolved_by_input(input_text)
    log.info("Smart alias added: %r -> %r", input_text, maps_to)
    return jsonify(status="ok", input=input_text, maps_to=maps_to), 201


@app.route("/api/smart-aliases", methods=["GET"])
def api_list_smart_aliases():
    return jsonify(store.get_smart_aliases()), 200


@app.route("/api/learning-stats", methods=["GET"])
def api_learning_stats():
    return jsonify(store.get_learning_stats()), 200


@app.route("/api/smart-alias/<alias_id>", methods=["DELETE"])
def api_delete_smart_alias(alias_id):
    store.delete_smart_alias(alias_id)
    log.info("Smart alias deleted: %s", alias_id)
    return jsonify(status="ok"), 200


# ---- Follow-up background worker ----------------------------------------
def _followup_worker():
    """Background thread that sends scheduled follow-up messages."""
    while True:
        try:
            pending = store.get_pending_followups()
            for fu in pending:
                ch = _CHANNELS.get(fu.get("channel"), WA)
                user_id = fu.get("user_id")
                message = fu.get("message", "")
                if user_id and message:
                    try:
                        ch.send_text(user_id, message)
                        log.info("Follow-up sent to %s via %s", user_id, fu.get("channel"))
                    except Exception as e:
                        log.warning("Follow-up send failed: %s", e)
                store.mark_followup_sent(fu["id"])
        except Exception as e:
            log.warning("Follow-up worker error: %s", e)
        time.sleep(60)  # check every minute


# Start follow-up worker thread
_followup_thread = threading.Thread(target=_followup_worker, daemon=True)
_followup_thread.start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
