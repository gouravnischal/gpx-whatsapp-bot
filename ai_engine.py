"""AI-powered smart replies for the GPX Express chatbot.

Uses Google Gemini (free tier) or OpenAI as fallback. Provides intelligent
responses when the rule-based engine can't handle a query, and handles
language detection + translation for multi-language support.

Set GEMINI_API_KEY or OPENAI_API_KEY in your .env file.
"""
import json
import logging
import os
import re
import requests

log = logging.getLogger("gpx-ai")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ---- System prompt with GPX business context ----------------------------
SYSTEM_PROMPT = """You are the GPX Express Courier assistant chatbot. You help customers with:
- Shipping parcels from India to international destinations
- Getting shipping quotes (price estimates)
- Tracking parcels
- Booking pickups
- Answering FAQs about shipping

Key business info:
- Company: GPX Express Service India Pvt Ltd
- Service: International courier & logistics from India
- Main destinations: Australia, USA, Canada, UK, UAE, Europe (27 EU countries), New Zealand, Singapore, Germany
- Carrier: FedEx Express (3-7 business days)
- Contact: +91-8287193002, gpxsupports@outlook.com
- Website: gpxexpress.com
- Payment: UPI, bank transfer, cards, cash on pickup
- Documents needed: Photo ID, receiver's full address & phone, invoice/contents list
- Business hours: Mon-Sat, 10am-7pm IST
- Bulk shipments (70+ kg) get special rates from an agent

Rules:
- Be helpful, concise, and professional
- If asked for a specific price, suggest they use the quote feature (type "quote" or "menu")
- If you can't answer something, suggest they speak to an agent (type "agent")
- Reply in the SAME LANGUAGE the customer uses (Hindi, English, or mixed)
- Keep replies under 200 words
- Use WhatsApp-style formatting: *bold*, _italic_
- Never make up tracking numbers or specific prices
- Never share internal business details
"""


def _detect_language(text):
    """Detect if text is Hindi (Devanagari), English, or mixed."""
    devanagari = len(re.findall(r'[ऀ-ॿ]', text))
    latin = len(re.findall(r'[a-zA-Z]', text))
    total = devanagari + latin
    if total == 0:
        return "en"
    if devanagari > latin:
        return "hi"
    if devanagari > 0 and latin > 0:
        return "hinglish"
    return "en"


def detect_language(text):
    """Public API for language detection."""
    return _detect_language(text)


def _call_gemini(user_message, conversation_context=""):
    """Call Google Gemini API."""
    if not GEMINI_API_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = SYSTEM_PROMPT
    if conversation_context:
        prompt += f"\n\nConversation context: {conversation_context}"

    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt + "\n\nCustomer message: " + user_message}]}
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 300,
        }
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            data = r.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
        else:
            log.warning("Gemini API error %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("Gemini API call failed: %s", e)
    return None


def _call_openai(user_message, conversation_context=""):
    """Call OpenAI API."""
    if not OPENAI_API_KEY:
        return None
    url = "https://api.openai.com/v1/chat/completions"
    system = SYSTEM_PROMPT
    if conversation_context:
        system += f"\n\nConversation context: {conversation_context}"

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.7,
        "max_tokens": 300,
    }
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
        else:
            log.warning("OpenAI API error %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("OpenAI API call failed: %s", e)
    return None


def smart_reply(user_message, conversation_context=""):
    """Get an AI-powered reply. Tries Gemini first, then OpenAI.
    Returns the reply text or None if both fail."""
    reply = _call_gemini(user_message, conversation_context)
    if reply:
        return reply
    reply = _call_openai(user_message, conversation_context)
    if reply:
        return reply
    return None


def translate_message(text, target_lang="hi"):
    """Translate a message to the target language using AI.
    target_lang: 'hi' for Hindi, 'en' for English."""
    if not GEMINI_API_KEY and not OPENAI_API_KEY:
        return None
    prompt = f"Translate this to {'Hindi' if target_lang == 'hi' else 'English'}. Keep WhatsApp formatting (*bold*, _italic_). Only return the translation, nothing else:\n\n{text}"
    return _call_gemini(prompt) or _call_openai(prompt)


def is_ai_available():
    """Check if any AI backend is configured."""
    return bool(GEMINI_API_KEY or OPENAI_API_KEY)
