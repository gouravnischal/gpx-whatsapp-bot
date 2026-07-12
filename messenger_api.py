"""Send API for Instagram DMs and Facebook Messenger.

Two supported setups:
  * Instagram "Instagram login"  -> POST graph.instagram.com/<ver>/me/messages, IG token
  * Messenger / Instagram via Page -> POST graph.facebook.com/<ver>/me/messages, Page token

The platform is passed in from the channel ("instagram" or "messenger"). If the
relevant token isn't set, messages print to the console (dev mode).
"""
import json
import requests

import config

FB_BASE = "https://graph.facebook.com/{ver}/me/messages"
IG_BASE = "https://graph.instagram.com/{ver}/me/messages"


def _target(platform):
    """Return (url, token) for the given platform."""
    if platform == "instagram" and config.IG_ACCESS_TOKEN:
        return IG_BASE.format(ver=config.IG_GRAPH_VERSION), config.IG_ACCESS_TOKEN
    return FB_BASE.format(ver=config.GRAPH_API_VERSION), config.PAGE_ACCESS_TOKEN


def _post(platform, payload):
    url, token = _target(platform)
    if not token:
        print(f"[{platform.upper()} DEV — not sent]\n" + json.dumps(payload, indent=2, ensure_ascii=False))
        return {"dev_mode": True}
    try:
        r = requests.post(url, params={"access_token": token}, json=payload, timeout=15)
        if r.status_code >= 400:
            print(f"[{platform} API error {r.status_code}] {r.text}")
        return r.json()
    except requests.RequestException as e:
        print(f"[{platform} API request failed] {e}")
        return {"error": str(e)}


def send_text(to, text, platform="messenger"):
    return _post(platform, {
        "messaging_type": "RESPONSE",
        "recipient": {"id": to},
        "message": {"text": text[:2000]},
    })


def send_quick_replies(to, text, replies, platform="messenger"):
    """replies: list of (payload_id, title). Up to 13; titles <= 20 chars."""
    qrs = [
        {"content_type": "text", "title": title[:20], "payload": pid}
        for pid, title in replies[:13]
    ]
    return _post(platform, {
        "messaging_type": "RESPONSE",
        "recipient": {"id": to},
        "message": {"text": text[:2000], "quick_replies": qrs},
    })
