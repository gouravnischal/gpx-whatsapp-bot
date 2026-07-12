"""Parcel tracking.

Customers are pointed to the GPX tracking website to see live status. If you
later expose a tracking API, set TRACKING_API_URL in .env and this will read
JSON {status, location, eta} from it instead.
"""
import re
import requests

import config


def valid_awb(text):
    """Basic sanity check for an AWB / tracking number (6-20 chars)."""
    t = (text or "").strip().replace(" ", "")
    return bool(re.fullmatch(r"[A-Za-z0-9\-]{6,20}", t))


def lookup(awb):
    awb = (awb or "").strip()
    if config.TRACKING_API_URL:
        try:
            r = requests.get(config.TRACKING_API_URL, params={"awb": awb}, timeout=12)
            if r.status_code == 200:
                d = r.json()
                return (
                    f"\U0001F50E *Tracking {awb}*\n"
                    f"Status: {d.get('status', 'Unknown')}\n"
                    f"Location: {d.get('location', '—')}\n"
                    f"Est. delivery: {d.get('eta', '—')}"
                )
        except requests.RequestException:
            pass

    # Default: send the customer to the tracking website.
    return (
        f"\U0001F50E *Track parcel {awb}*\n"
        f"You can see live status here:\n{config.TRACKING_WEBSITE}\n\n"
        f"Just enter your tracking number on the website. "
        f"Need help? Call *+91-8287193002* or email *{config.CONTACT_EMAIL}*."
    )
