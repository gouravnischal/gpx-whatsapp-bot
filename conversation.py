"""The conversation engine — a small state machine, channel-agnostic.

Entry point: handle_message(ch, user_id, text, reply_id)
  - ch       : a channel adapter (WhatsApp / Messenger / Instagram) used to reply
  - user_id  : the customer's id on that platform
  - text     : the text body they typed (may be empty for button/quick-reply taps)
  - reply_id : the id/payload of the option they tapped (or None)

The SAME logic serves all platforms; only `ch` differs.
"""
import re
import datetime
import logging
import store
import quotes
import tracking
import config
import ai_engine
import whatsapp_api as wa   # used only to alert the business of new leads

log = logging.getLogger("gpx-conv")

# ---- IST timezone --------------------------------------------------------
_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# ---- Menu option ids ----------------------------------------------------
OPT_QUOTE = "opt_quote"
OPT_TRACK = "opt_track"
OPT_PICKUP = "opt_pickup"
OPT_FAQ = "opt_faq"
OPT_AGENT = "opt_agent"

FAQ_AREAS = "faq_areas"
FAQ_DOCS = "faq_documents"
FAQ_TIME = "faq_timelines"
FAQ_PAY = "faq_payment"
FAQ_BACK = "faq_back"

RESET_WORDS = {"menu", "hi", "hello", "hey", "start", "restart", "back", "main menu", "/start"}

# Words that trigger agent handoff from any state
AGENT_WORDS = {"agent", "human", "support", "call"}

# Intent-detection keyword sets
_QUOTE_KEYWORDS = {"price", "cost", "rate", "quote", "shipping", "send", "courier",
                   "charges", "charge", "how much", "kitna", "rates", "fees"}
_TRACK_KEYWORDS = {"track", "tracking", "status", "where", "parcel", "shipment", "awb"}
_PICKUP_KEYWORDS = {"pickup", "pick up", "collect", "book", "booking", "schedule"}
_FAQ_KEYWORDS = {"help", "faq", "question", "questions", "info", "information"}


def _skey(ch, user_id):
    """Namespace sessions per platform so the same id on FB vs IG don't collide."""
    return f"{getattr(ch, 'name', 'wa')}:{user_id}"


# ---- Smart time-based greeting -------------------------------------------
def _get_greeting():
    """Pick a greeting based on the current IST hour."""
    hour = datetime.datetime.now(_IST).hour
    if 5 <= hour <= 11:
        return getattr(config, "GREETING_MORNING", config.GREETING)
    elif 12 <= hour <= 16:
        return getattr(config, "GREETING_AFTERNOON", config.GREETING)
    else:
        return getattr(config, "GREETING_EVENING", config.GREETING)


# ---- Helpers ------------------------------------------------------------
def _show_menu(ch, user_id, greet=True):
    body = _get_greeting() if greet else "What would you like to do next?"
    ch.send_list(
        user_id,
        body=body,
        button_text="Choose an option",
        header=config.BUSINESS_NAME,
        footer="Type 'menu' anytime to restart",
        rows=[
            (OPT_QUOTE,  "\U0001F4E6 Get a quote",     "Estimate shipping cost"),
            (OPT_TRACK,  "\U0001F50E Track a parcel",  "Check your shipment status"),
            (OPT_PICKUP, "\U0001F69A Book a pickup",   "Schedule a parcel pickup"),
            (OPT_FAQ,    "❓ FAQ",                 "Common questions"),
            (OPT_AGENT,  "\U0001F9D1 Talk to agent",   "Chat with our team"),
        ],
    )
    store.save_session(_skey(ch, user_id), "MENU", {})


def _show_faq_menu(ch, user_id):
    ch.send_list(
        user_id,
        body="Pick a topic and I'll share the details:",
        button_text="View topics",
        header="Frequently asked",
        rows=[
            (FAQ_AREAS, "\U0001F30D Countries we ship", "Where we deliver"),
            (FAQ_DOCS,  "\U0001F4C4 What you need",     "ID & documents"),
            (FAQ_TIME,  "⏱️ Delivery time",   "How long it takes"),
            (FAQ_PAY,   "\U0001F4B3 Payment options",   "How to pay"),
            (FAQ_BACK,  "⬅️ Back to menu",    "Main menu"),
        ],
    )
    store.save_session(_skey(ch, user_id), "FAQ", {})


def _notify_agent(ch, kind, user_id, payload):
    """Alert the business WhatsApp number of a new lead (works for any channel)."""
    if not config.AGENT_NOTIFY_NUMBER:
        return
    src = getattr(ch, "name", "whatsapp")
    lines = [f"\U0001F514 New {kind} via {src} (user {user_id})"]
    for k, v in payload.items():
        lines.append(f"• {k}: {v}")
    wa.send_text(config.AGENT_NOTIFY_NUMBER, "\n".join(lines))


def _do_agent_handoff(ch, user_id, key, text):
    """Common agent handoff logic, usable from any state."""
    ch.send_text(user_id, config.AGENT_HANDOFF.format(phone=config.AGENT_PHONE))
    store.save_lead(key, "agent", {"note": text or "requested agent"})
    _notify_agent(ch, "agent request", user_id, {"message": text or "(requested agent)"})
    store.save_session(key, "AGENT", {})


# ---- Media handling (photos, documents, etc.) ----------------------------
def handle_media(ch, user_id, media_type, caption=""):
    """Handle incoming media messages (images, documents, videos, etc.)."""
    key = _skey(ch, user_id)
    type_labels = {
        "image": "photo", "document": "document", "video": "video",
        "audio": "voice message", "sticker": "sticker", "file": "file",
    }
    label = type_labels.get(media_type, "file")

    # Detect language for response
    lang = ai_engine.detect_language(caption) if caption else "en"

    if lang == "hi":
        reply = (
            f"📎 आपकी {label} मिल गयी है!\n\n"
            f"हमारी टीम को भेज दी गयी है और वो जल्द ही आपसे संपर्क करेंगे।\n"
            f"अगर कोई और जानकारी देनी हो तो यहाँ भेज दें।\n\n"
            f"मेनू पर वापस जाने के लिए *menu* टाइप करें।"
        )
    else:
        reply = (
            f"📎 Got your {label}!\n\n"
            f"I've forwarded it to our team — they'll review it and get back to you shortly.\n"
            f"Feel free to send any additional details here.\n\n"
            f"Type *menu* to use the assistant."
        )

    ch.send_text(user_id, reply)
    store.save_lead(key, "media", {"type": media_type, "caption": caption})
    _notify_agent(ch, f"customer {label}", user_id,
                  {"type": media_type, "caption": caption or "(no caption)"})


# ---- Intent detection from free text ------------------------------------
def _detect_intent(text, lower, ch, user_id, key):
    """Try to detect an intent from free text typed in MENU state.

    Returns True if an intent was handled, False if nothing was detected.
    """
    # Check for agent handoff words first
    if lower in AGENT_WORDS:
        _do_agent_handoff(ch, user_id, key, text)
        return True

    # Check for quote-related keywords
    has_quote_kw = any(kw in lower for kw in _QUOTE_KEYWORDS)
    if has_quote_kw:
        # Try to extract a destination from the full text
        dest = quotes.resolve_destination(text)
        if dest:
            # Destination found in the text -- skip asking and go straight to weight
            data = {"dest": dest}
            store.save_session(key, "QUOTE_WEIGHT", data)
            ch.send_text(user_id, f"\U0001F4E6 Got it — shipping to *{quotes.display_name(dest)}*.\n"
                                  f"What's the approx *weight*? (e.g. 2kg, 500g)")
            return True
        # Quote keywords but no destination -- ask for destination
        ch.send_text(user_id, "\U0001F4E6 Sure! Which *country* are you shipping to?\n"
                              "(e.g. Australia, USA, UK, UAE...)")
        store.save_session(key, "QUOTE_DEST", {})
        return True

    # Check for tracking keywords
    if any(kw in lower for kw in _TRACK_KEYWORDS):
        ch.send_text(user_id, "\U0001F50E Please send your *tracking / AWB number*.")
        store.save_session(key, "TRACK_AWB", {})
        return True

    # Check for pickup keywords
    if any(kw in lower for kw in _PICKUP_KEYWORDS):
        ch.send_text(user_id, "\U0001F69A Let's book a pickup. First, what's your *full name*?")
        store.save_session(key, "PICKUP_NAME", {})
        return True

    # Check for FAQ keywords
    if any(kw in lower for kw in _FAQ_KEYWORDS):
        _show_faq_menu(ch, user_id)
        return True

    return False


# ---- Main entry point ---------------------------------------------------
def handle_message(ch, user_id, text, reply_id=None):
    text = (text or "").strip()
    lower = text.lower()
    key = _skey(ch, user_id)
    session = store.get_session(key)
    state = session["state"]
    data = session["data"]

    if lower in RESET_WORDS and not reply_id:
        _show_menu(ch, user_id, greet=True)
        return

    # ---- Global agent handoff: works from ANY state ----
    if lower in AGENT_WORDS and not reply_id:
        _do_agent_handoff(ch, user_id, key, text)
        return

    intent = reply_id or ""

    if intent == "opt_menu":
        _show_menu(ch, user_id, greet=False)
        return

    # ---- Top-level menu choices ----
    if intent == OPT_QUOTE:
        ch.send_text(user_id, "\U0001F4E6 Sure! Which *country* are you shipping to?\n"
                              "(e.g. Australia, USA, UK, UAE...)")
        store.save_session(key, "QUOTE_DEST", {})
        return
    if intent == OPT_TRACK:
        ch.send_text(user_id, "\U0001F50E Please send your *tracking / AWB number*.")
        store.save_session(key, "TRACK_AWB", {})
        return
    if intent == OPT_PICKUP:
        ch.send_text(user_id, "\U0001F69A Let's book a pickup. First, what's your *full name*?")
        store.save_session(key, "PICKUP_NAME", {})
        return
    if intent == OPT_FAQ:
        _show_faq_menu(ch, user_id)
        return
    if intent == OPT_AGENT:
        _do_agent_handoff(ch, user_id, key, text)
        return

    # ---- FAQ topic taps ----
    if intent in (FAQ_AREAS, FAQ_DOCS, FAQ_TIME, FAQ_PAY):
        fkey = {FAQ_AREAS: "areas", FAQ_DOCS: "documents",
                FAQ_TIME: "timelines", FAQ_PAY: "payment"}[intent]
        ch.send_text(user_id, config.FAQ[fkey])
        _show_faq_menu(ch, user_id)
        return
    if intent == FAQ_BACK:
        _show_menu(ch, user_id, greet=False)
        return

    # ---- State-driven free text ----
    if state == "QUOTE_DEST":
        # Try normal destination resolution first
        dest = quotes.resolve_destination(text)
        # If not found, try smart alias lookup
        if not dest:
            alias = store.get_smart_alias(text)
            if alias:
                dest = alias
        if not dest:
            # Log unrecognized destination for learning
            store.log_unrecognized(key, getattr(ch, 'name', 'whatsapp'), 'QUOTE_DEST', text, 'destination')
            _notify_agent(ch, "unrecognized destination", user_id, {"typed": text})
            # Build a helpful error message with popular destinations
            popular = getattr(config, "POPULAR_DESTINATIONS",
                              ["Australia", "USA", "Canada", "UK", "UAE"])
            dest_list = ", ".join(popular)
            ch.send_text(
                user_id,
                f"I didn't recognise that destination. We currently ship to:\n"
                f"{dest_list}\n\n"
                f"Please type a destination from the list, or type *agent* to speak with our team."
            )
            return
        data["dest"] = dest
        store.save_session(key, "QUOTE_WEIGHT", data)
        ch.send_text(user_id, f"Great — shipping to *{quotes.display_name(dest)}*.\n"
                              f"What's the approx *weight*? (e.g. 2kg, 500g)")
        return

    if state == "QUOTE_WEIGHT":
        weight = quotes.parse_weight(text)
        if not weight or weight <= 0:
            ch.send_text(user_id, "Please send a weight like *2kg* or *500g*.")
            return
        dest = data.get("dest")
        if quotes.is_bulk(weight):
            ch.send_text(user_id, quotes.format_bulk(dest, weight))
            store.save_lead(key, "bulk_quote", {"dest": dest, "weight_kg": weight})
            _notify_agent(ch, "BULK quote (special rates)", user_id,
                          {"destination": quotes.display_name(dest), "weight_kg": weight})
            ch.send_buttons(user_id, "Shall I connect you with an agent for special rates?",
                            [(OPT_AGENT, "Yes, contact agent"), ("opt_menu", "Main menu")])
            store.save_session(key, "MENU", {})
            return
        ch.send_text(user_id, quotes.format_quote(dest, weight))
        # Follow-up tip after showing a quote
        ch.send_text(user_id, "\U0001F4A1 _Tip: You can also ask me about other destinations "
                              "like Europe, Australia, or UAE!_")
        store.save_lead(key, "quote", {"dest": dest, "weight_kg": weight})
        _notify_agent(ch, "quote enquiry", user_id,
                      {"destination": quotes.display_name(dest), "weight_kg": weight})
        # Schedule auto follow-up after 1 hour
        followup_msg = (
            f"Hi! \U0001F44B Just checking in — did you want to go ahead with your "
            f"shipment to *{quotes.display_name(dest)}* ({quotes._fmt_kg(weight)} kg)?\n\n"
            f"I can help you *book a pickup* right away, or connect you with our team "
            f"for any questions.\n\n"
            f"Type *menu* to get started!"
        )
        try:
            store.schedule_followup(getattr(ch, 'name', 'whatsapp'), user_id,
                                    followup_msg, delay_seconds=3600)
        except Exception as e:
            log.warning("Failed to schedule follow-up: %s", e)
        ch.send_buttons(user_id, "Would you like to book a pickup for this?",
                        [(OPT_PICKUP, "Book pickup"), (OPT_AGENT, "Talk to agent"),
                         ("opt_menu", "Main menu")])
        store.save_session(key, "MENU", {})
        return

    if state == "TRACK_AWB":
        if not tracking.valid_awb(text):
            ch.send_text(user_id, "That doesn't look like a valid tracking number. "
                                  "Please re-check and send it again (6-20 characters).")
            return
        ch.send_text(user_id, tracking.lookup(text))
        store.save_lead(key, "track", {"awb": text})
        _show_menu(ch, user_id, greet=False)
        return

    # ---- Pickup booking ----
    if state == "PICKUP_NAME":
        if len(text) < 2:
            ch.send_text(user_id, "Please send your full name.")
            return
        data["name"] = text
        store.save_session(key, "PICKUP_ADDRESS", data)
        ch.send_text(user_id, f"Thanks {text.split()[0]}! What's the *pickup address*? "
                              f"(house/flat, area, city, pincode)")
        return

    if state == "PICKUP_ADDRESS":
        if len(text) < 8:
            ch.send_text(user_id, "Please send a complete pickup address including pincode.")
            return
        data["address"] = text
        store.save_session(key, "PICKUP_DEST", data)
        ch.send_text(user_id, "Which *destination country* is the parcel going to?")
        return

    if state == "PICKUP_DEST":
        dest = quotes.resolve_destination(text)
        data["destination"] = dest.title() if dest else text
        store.save_session(key, "PICKUP_DATE", data)
        ch.send_text(user_id, "On which *date* should we pick up? (e.g. 15 Jun, tomorrow)")
        return

    if state == "PICKUP_DATE":
        data["pickup_date"] = text
        lead_id = store.save_lead(key, "pickup", data)
        _notify_agent(ch, "pickup booking", user_id, data)
        ch.send_text(
            user_id,
            "✅ *Pickup request received!*\n"
            f"Ref #{lead_id}\n"
            f"Name: {data.get('name')}\n"
            f"Address: {data.get('address')}\n"
            f"To: {data.get('destination')}\n"
            f"Date: {data.get('pickup_date')}\n\n"
            f"Our team will contact you to confirm. Thank you for choosing "
            f"{config.BUSINESS_NAME}! \U0001F69A"
        )
        store.reset_session(key)
        return

    if state == "AGENT":
        store.save_lead(key, "agent", {"message": text})
        _notify_agent(ch, "agent message", user_id, {"message": text})
        ch.send_text(user_id, "\U0001F44D Thanks for your message! Our team has been notified "
                              "and will reply shortly.\n\n"
                              "If it's urgent, you can call us at *+91-8287193002* "
                              "(Mon-Sat, 10am-7pm IST).\n\n"
                              "Type *menu* to use the assistant again.")
        return

    # ---- Smart intent detection (MENU state, no reply_id) ----
    if state == "MENU" and not reply_id:
        if _detect_intent(text, lower, ch, user_id, key):
            return

    # ---- AI Smart Reply fallback (if configured) ----
    if text and ai_engine.is_ai_available():
        try:
            context = f"User is in state: {state}. Channel: {getattr(ch, 'name', 'whatsapp')}."
            ai_reply = ai_engine.smart_reply(text, context)
            if ai_reply:
                ch.send_text(user_id, ai_reply)
                ch.send_text(user_id, "Type *menu* for more options.")
                store.save_session(key, "MENU", {})
                return
        except Exception as e:
            log.warning("AI reply failed: %s", e)

    # ---- Fallback ----
    _show_menu(ch, user_id, greet=True)
