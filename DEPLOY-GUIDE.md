# GPX Bot — Deployment Guide (Updated July 2026)

## What Changed

### 1. Europe Destination (27 EU Countries)
When a customer types any EU country name (France, Poland, Spain, Italy, etc.) or "Europe"/"EU", the bot now recognizes it as **Europe (EU)** with unified Zone F pricing.

### 2. Auto-Learning System
When the bot doesn't recognize a destination, it:
- Logs the unrecognized input to the database
- Notifies the agent via WhatsApp
- Shows popular destinations as suggestions

Admin panel at `/admin` lets you:
- See what customers are asking that the bot can't handle
- Add "smart aliases" so the bot learns new mappings instantly
- No code changes needed — just add the alias from the dashboard

### 3. AI Smart Replies (Gemini / OpenAI)
- Bot uses Google Gemini (free tier) or OpenAI as fallback for intelligent replies
- Handles general questions about courier services, pricing info, etc.
- Falls back to the standard menu if no AI key is configured

### 4. Multi-Language Hindi Support
- Detects Hindi (Devanagari), Hinglish, and English automatically
- AI replies respond in the same language the customer uses
- Translation support via AI engine

### 5. Photo / Document Handling
- Customers can send images, documents, videos, and audio
- Media is logged in the database for agent review
- Bot acknowledges receipt and notifies the agent
- Works across WhatsApp, Instagram, and Messenger

### 6. Auto Follow-up After Quotes
- After giving a quote, bot schedules a follow-up message (1 hour later)
- Background worker thread checks every 60 seconds for pending follow-ups
- Gently reminds customer to book if they haven't responded

### 7. Other Improvements
- **Smart greetings** — time-of-day greetings (Good morning/afternoon/evening) in IST
- **Intent detection** — natural sentences like "how much to send 2kg to UK" work without menus
- **Global agent handoff** — "agent", "human", "support" works from any state
- **Popular destination suggestions** when input isn't recognized

## Deploy to Render

### Step 1: Set Environment Variables
In the Render dashboard, add these env vars to `gpx-bot`:

| Variable | Required? | Notes |
|---|---|---|
| `GEMINI_API_KEY` | Optional | Get free key at https://aistudio.google.com/app/apikey |
| `OPENAI_API_KEY` | Optional | Fallback if Gemini is not set |

All existing env vars (WHATSAPP_TOKEN, PHONE_NUMBER_ID, etc.) stay the same.

### Step 2: Push Code

**Option A: Push via Git**
```bash
cd gpx-whatsapp-bot
git add -A
git commit -m "Add Europe, AI replies, Hindi, photos, follow-ups"
git push origin main
```
Render auto-deploys on push.

**Option B: Manual Deploy**
1. Go to https://dashboard.render.com
2. Select the `gpx-bot` service
3. Click "Manual Deploy" → "Deploy latest commit"

### Step 3: Verify
1. Visit `https://gpx-bot.onrender.com/` — should show "GPX bot running"
2. Visit `https://gpx-bot.onrender.com/admin` — admin dashboard
3. Test: send "France" or "Europe" to the WhatsApp bot — should show Europe quote
4. Test: send a photo — bot should acknowledge it
5. Test: type "namaste" or Hindi text — bot should respond appropriately (if Gemini key is set)

## Admin Panel

URL: `https://gpx-bot.onrender.com/admin`

**Important:** Add authentication before going public (currently open).

The admin panel shows:
- Stats: total unrecognized queries, unique inputs, resolved count
- Unrecognized queries table with "Add Alias" buttons
- Smart aliases list with delete buttons

When you add a smart alias (e.g., "timbuktu" → "mali"), the bot immediately starts recognizing that input — no restart needed.

## Files Overview

| File | Purpose |
|---|---|
| `config.py` | All settings, API keys, rate card, FAQ text |
| `app.py` | Flask webhook server + admin panel + follow-up worker |
| `conversation.py` | State machine conversation engine |
| `ai_engine.py` | **NEW** — Gemini/OpenAI smart replies + language detection |
| `store.py` | SQLite database (sessions, leads, learning, follow-ups, media) |
| `quotes.py` | Quote calculation + destination resolution |
| `rates_data.py` | Zone-based FedEx pricing data |
| `channels.py` | Channel adapters (WhatsApp, Messenger, Instagram) |
| `whatsapp_api.py` | WhatsApp Cloud API wrapper |
| `messenger_api.py` | Messenger/Instagram Send API wrapper |
| `tracking.py` | Parcel tracking |
