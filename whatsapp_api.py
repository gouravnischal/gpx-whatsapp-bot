"""Thin wrapper around the WhatsApp Cloud API send endpoints.

All outgoing messages go through here. If WHATSAPP_TOKEN / PHONE_NUMBER_ID are
not configured, messages are printed to the console instead of sent — handy for
local testing without real credentials.
"""
import json
import requests

import config

BASE = "https://graph.facebook.com/{ver}/{pid}/messages"


def _endpoint():
    return BASE.format(ver=config.GRAPH_API_VERSION, pid=config.PHONE_NUMBER_ID)


def _headers():
    return {
        "Authorization": f"Bearer {config.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


def _post(payload):
    """Send a payload to the Cloud API. Falls back to console in dev mode."""
    if not config.WHATSAPP_TOKEN or not config.PHONE_NUMBER_ID:
        print("[DEV MODE — not sent]\n" + json.dumps(payload, indent=2, ensure_ascii=False))
        return {"dev_mode": True}
    try:
        r = requests.post(_endpoint(), headers=_headers(), json=payload, timeout=15)
        if r.status_code >= 400:
            print(f"[WhatsApp API error {r.status_code}] {r.text}")
        return r.json()
    except requests.RequestException as e:
        print(f"[WhatsApp API request failed] {e}")
        return {"error": str(e)}


def send_text(to, body, preview_url=False):
    return _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body[:4096], "preview_url": preview_url},
    })


def send_buttons(to, body, buttons, header=None):
    """buttons: list of (id, title). Max 3 buttons, titles <= 20 chars."""
    action_buttons = [
        {"type": "reply", "reply": {"id": bid, "title": title[:20]}}
        for bid, title in buttons[:3]
    ]
    interactive = {
        "type": "button",
        "body": {"text": body[:1024]},
        "action": {"buttons": action_buttons},
    }
    if header:
        interactive["header"] = {"type": "text", "text": header[:60]}
    return _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    })


def send_list(to, body, button_text, rows, header=None, footer=None):
    """rows: list of (id, title, description). Rendered as a tappable menu."""
    list_rows = [
        {"id": rid, "title": title[:24], "description": (desc or "")[:72]}
        for rid, title, desc in rows
    ]
    interactive = {
        "type": "list",
        "body": {"text": body[:1024]},
        "action": {
            "button": button_text[:20],
            "sections": [{"title": "Options", "rows": list_rows}],
        },
    }
    if header:
        interactive["header"] = {"type": "text", "text": header[:60]}
    if footer:
        interactive["footer"] = {"text": footer[:60]}
    return _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    })


def mark_read(message_id):
    if not config.WHATSAPP_TOKEN or not config.PHONE_NUMBER_ID:
        return {"dev_mode": True}
    return _post({
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    })
