"""Quote engine — FedEx zone-based, weight-slab, ALL-IN pricing (Package, Export).

Prices come from rates_data.py (generated from the GPX FedEx rate sheet) and
already include fuel surcharge + 18% GST. India -> destination.
"""
import math
import re

import config
import rates_data as rd

# Highest weight available in the rate ladder (kg). Above this -> bulk/agent.
MAX_KG = max(w for ladder in rd.PACKAGE_LADDER.values() for w, _ in ladder)


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def resolve_destination(text):
    """Return a canonical country key (matching rates_data) or None."""
    t = _norm(text)
    if not t:
        return None
    if t in rd.ALIASES:
        return rd.ALIASES[t]
    if t in rd.COUNTRY_ZONE:
        return t
    # word-boundary / substring match against country names & aliases
    for alias, canon in rd.ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", t):
            return canon
    for country in rd.COUNTRY_ZONE:
        if t == country or re.search(rf"\b{re.escape(country)}\b", t) or (len(t) >= 4 and t in country):
            return country
    # Auto-learning: check smart_aliases from DB
    try:
        import store
        smart = store.get_smart_alias(t)
        if smart and smart in rd.COUNTRY_ZONE:
            return smart
    except Exception:
        pass
    return None


def display_name(country):
    return rd.DISPLAY.get(country, country.title())


def parse_weight(text):
    t = (text or "").strip().lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kgs|kilo|kilos|kilogram|g|gram|grams)?", t)
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2) or "kg"
    if unit.startswith("g") and not unit.startswith("kg"):
        value = value / 1000.0
    return round(value, 3)


def billable_weight(weight_kg):
    """Round UP to the next 0.5 kg, 0.5 kg minimum."""
    return max(0.5, math.ceil(weight_kg * 2) / 2.0)


def is_bulk(weight_kg):
    return weight_kg > MAX_KG


def estimate(country, weight_kg):
    """Return (amount_inr, billed_kg, zone)."""
    zone = rd.COUNTRY_ZONE[country]
    ladder = rd.PACKAGE_LADDER[zone]
    bw = billable_weight(weight_kg)
    price = None
    chosen = bw
    for w, p in ladder:
        if w >= bw:
            price, chosen = p, w
            break
    if price is None:                      # heavier than ladder -> last slab
        chosen, price = ladder[-1]
    return int(price), chosen, zone


def _fmt_kg(kg):
    return f"{kg:g}"


def format_quote(country, weight_kg):
    amount, billed, zone = estimate(country, weight_kg)
    name = display_name(country)
    return (
        f"\U0001F4E6 *Estimated quote*\n"
        f"India → {name}\n"
        f"Weight: {_fmt_kg(weight_kg)} kg (billed {_fmt_kg(billed)} kg)\n"
        f"Approx. cost: *₹{amount:,}*  _(all-in: fuel + 18% GST included)_\n"
        f"Service: FedEx Express — usually 3-7 business days\n\n"
        f"_Indicative estimate. Final price is confirmed by our team after checking "
        f"parcel contents, exact address & any surcharges._"
    )


def format_bulk(country, weight_kg):
    name = display_name(country)
    return (
        f"\U0001F4E6 *Bulk shipment enquiry*\n"
        f"India → {name}\n"
        f"Weight: {_fmt_kg(weight_kg)} kg\n\n"
        f"\U0001F389 For shipments above {int(MAX_KG)} kg we offer *special rates*. "
        f"Our agent will share a custom quote for your shipment."
    )
