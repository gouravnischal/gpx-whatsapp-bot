"""Central configuration, branding, rate card and FAQ content for the GPX bot.

Everything a non-developer might want to tweak (prices, FAQ answers, wording)
lives in this one file so you don't have to dig through the logic.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---- Credentials / environment ----
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "gpx_verify_2026_change_me")
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v20.0")
TRACKING_API_URL = os.getenv("TRACKING_API_URL", "").strip()

BUSINESS_NAME = os.getenv("BUSINESS_NAME", "GPX Express Courier")
AGENT_PHONE = os.getenv("AGENT_PHONE", "918287193002")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "gpxsupports@outlook.com")
TRACKING_WEBSITE = os.getenv("TRACKING_WEBSITE", "https://www.gpxexpress.com")
AGENT_NOTIFY_NUMBER = os.getenv("AGENT_NOTIFY_NUMBER", "").strip()

# ---- AI Smart Replies (Gemini or OpenAI) ----
# Set one of these to enable AI-powered smart replies & Hindi support.
# Gemini free tier: https://aistudio.google.com/app/apikey
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ---- Instagram + Facebook Messenger (Meta Send API) ----
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
APP_SECRET = os.getenv("APP_SECRET", "")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
IG_GRAPH_VERSION = os.getenv("IG_GRAPH_VERSION", "v21.0")

# Shipments heavier than this (kg) get special bulk rates handled by an agent.
BULK_THRESHOLD_KG = int(os.getenv("BULK_THRESHOLD_KG", "71"))

# ---- Rate card ----------------------------------------------------------
RATE_CARD = {
    "australia":      {"rate": 550, "eta": "5-7 business days"},
    "usa":            {"rate": 950, "eta": "4-6 business days"},
    "canada":         {"rate": 950, "eta": "5-7 business days"},
    "uk":             {"rate": 500, "eta": "4-6 business days"},
    "uae":            {"rate": 410, "eta": "3-5 business days"},
    "new zealand":    {"rate": 950, "eta": "6-8 business days"},
    "singapore":      {"rate": 650, "eta": "3-5 business days"},
    "germany":        {"rate": 650, "eta": "4-6 business days"},
    "europe":         {"rate": 650, "eta": "4-7 business days"},
}

# Words customers might type, mapped to a rate-card key above.
DESTINATION_ALIASES = {
    "australia": "australia", "aus": "australia", "sydney": "australia",
    "melbourne": "australia", "perth": "australia", "brisbane": "australia",
    "usa": "usa", "us": "usa", "america": "usa", "united states": "usa",
    "new york": "usa", "california": "usa",
    "canada": "canada", "toronto": "canada", "vancouver": "canada",
    "uk": "uk", "england": "uk", "london": "uk", "united kingdom": "uk", "britain": "uk",
    "uae": "uae", "dubai": "uae", "abu dhabi": "uae", "sharjah": "uae",
    "new zealand": "new zealand", "nz": "new zealand", "auckland": "new zealand",
    "singapore": "singapore", "sg": "singapore",
    "germany": "germany", "berlin": "europe", "munich": "europe",
    # EU countries (all 27 member states)
    "austria": "europe", "belgium": "europe", "bulgaria": "europe",
    "croatia": "europe", "cyprus": "europe", "czech republic": "europe",
    "denmark": "europe", "estonia": "europe", "finland": "europe",
    "france": "europe", "greece": "europe", "hungary": "europe",
    "ireland": "europe", "italy": "europe", "latvia": "europe",
    "lithuania": "europe", "luxembourg": "europe", "malta": "europe",
    "netherlands": "europe", "poland": "europe", "portugal": "europe",
    "romania": "europe", "slovakia": "europe", "slovenia": "europe",
    "spain": "europe", "sweden": "europe",
    # EU / Europe aliases
    "eu": "europe", "european union": "europe", "europe": "europe",
    "european": "europe", "holland": "europe",
    # Major European cities
    "paris": "europe", "rome": "europe", "madrid": "europe",
    "barcelona": "europe", "amsterdam": "europe", "prague": "europe",
    "budapest": "europe", "warsaw": "europe", "vienna": "europe",
    "brussels": "europe", "lisbon": "europe", "athens": "europe",
    "copenhagen": "europe", "stockholm": "europe", "helsinki": "europe",
    "dublin": "europe", "milan": "europe", "florence": "europe",
    # Non-EU European countries kept for convenience
    "norway": "europe", "switzerland": "europe", "iceland": "europe",
}

# ---- Popular destinations (for suggestion buttons) -----------------------
POPULAR_DESTINATIONS = [
    "Australia", "USA", "Canada", "UK", "UAE",
    "Europe", "New Zealand", "Singapore",
]

# ---- FAQ content --------------------------------------------------------
FAQ = {
    "areas": (
        "\U0001F30D *Where we ship*\n"
        "We send parcels & documents from India to Australia, USA, Canada, UK, "
        "UAE, Europe (all 27 EU countries), New Zealand, Singapore, Germany "
        "and many more countries."
    ),
    "documents": (
        "\U0001F4C4 *What you need*\n"
        "For most parcels: a valid photo ID, the receiver's full address & phone, "
        "and an invoice/contents list. Food, medicines and branded goods may need "
        "extra paperwork — our team will guide you."
    ),
    "timelines": (
        "⏱️ *Delivery time*\n"
        "Typically 3-8 business days depending on the destination. You'll get a "
        "tracking number once your parcel is picked up."
    ),
    "payment": (
        "\U0001F4B3 *Payment*\n"
        "We accept UPI, bank transfer, cards and cash on pickup. You'll get a "
        "confirmed quote before anything is charged."
    ),
}

# ---- Wording ------------------------------------------------------------
GREETING = (
    "\U0001F44B Welcome to *{business}*!\n"
    "I'm your courier assistant. How can I help you today?"
).format(business=BUSINESS_NAME)

# ---- Smart greetings (time-based) ----
GREETING_MORNING = (
    "☀️ Good morning! Welcome to *{business}*!\n"
    "I'm your courier assistant. How can I help you today?"
).format(business=BUSINESS_NAME)

GREETING_AFTERNOON = (
    "\U0001F324️ Good afternoon! Welcome to *{business}*!\n"
    "I'm your courier assistant. How can I help you today?"
).format(business=BUSINESS_NAME)

GREETING_EVENING = (
    "\U0001F319 Good evening! Welcome to *{business}*!\n"
    "I'm your courier assistant. How can I help you today?"
).format(business=BUSINESS_NAME)

AGENT_HANDOFF = (
    "No problem — our team will take it from here.\n"
    "You can also reach us directly:\n"
    "\U0001F4DE Call/WhatsApp: *+91-8287193002*\n"
    "✉️ Email: *gpxsupports@outlook.com*\n"
    "Please send your question and an agent will reply during business hours "
    "(Mon-Sat, 10am-7pm IST)."
)
