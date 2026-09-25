"""Everything the bot says, as pure functions (Telegram HTML). Shared with the offline demo.

Short, plain English with a Hindi line on the key prompts: collectors should not
need to read much.
"""
import re
from html import escape

from app.classify.labels import LABEL_TEXT, LABEL_TO_CATEGORIES

MAX_WEIGHT_KG = 2000
PICK_HINDI = "सही माल चुनें।"  # "choose the correct material"


def inr(v: float) -> str:
    """Rupees with Indian digit grouping: 123456.5 -> ₹1,23,456.50; whole numbers drop paise."""
    whole, paise = f"{abs(v):.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    grouped = ",".join(groups + [tail]) if groups else tail
    sign = "-" if v < 0 else ""
    return f"{sign}₹{grouped}" + ("" if paise == "00" else f".{paise}")


def short_name(material_name: str) -> str:
    """'Metal (steel/aluminium blended)' -> 'Metal'."""
    return material_name.split(" (")[0]


def parse_weight(text: str) -> float | None:
    """Accepts '12', '12.5', '12,5', '12.5 kg'. Returns None if not a sensible weight."""
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(?:kg|kgs|किलो)?\s*", text.lower())
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    return round(value, 2) if 0 < value <= MAX_WEIGHT_KG else None


def welcome_new() -> str:
    return ("Namaste! 🙏 I am <b>MITRA</b>. I record the material you collect and tell you "
            "the fair price. No app needed, just this chat.\n\n"
            "What is your name?\nआपका नाम क्या है?")


def ask_area(name: str) -> str:
    return (f"Thank you, {escape(name)}. Which area do you work in? (for example: Sanganer)\n"
            "आप किस इलाके में काम करते हैं?")


def bad_name() -> str:
    return "Please send your name (2 to 80 letters)."


def registered(collector: dict) -> str:
    return (f"✅ You are registered, {escape(collector['name'])}.\n"
            f"Your MITRA Collector ID: <b>{collector['code']}</b>\n\n"
            "Tap <b>📦 Log material</b> each time you collect material.")


def welcome_back(name: str, code: str) -> str:
    return (f"Welcome back, {escape(name)} ({code}).\n"
            "Tap <b>📦 Log material</b> to record a lot, or <b>💰 Today's prices</b>.")


def need_registration() -> str:
    return "Please register first: send /start"


def material_prompt() -> str:
    return "What material is it? Tap one:\nकौन सा माल है?"


def material_button(m: dict, suggested: bool = False) -> str:
    return f"{'📷 ' if suggested else ''}{short_name(m['name'])} · ₹{m['ref_price_per_kg']:g}/kg"


def ordered_materials(materials: list[dict], suggestion: dict | None) -> list[tuple[dict, bool]]:
    """Suggested materials first (marked), then the rest. Every material is always offered."""
    cats = set(suggestion["categories"]) if suggestion and suggestion["confident"] else set()
    first = [(m, True) for m in materials if m["category"] in cats]
    return first + [(m, False) for m in materials if m["category"] not in cats]


def cv_prompt(suggestion: dict | None) -> str:
    """What to say above the material buttons after a photo."""
    if suggestion is None:
        return material_prompt()
    if not suggestion["confident"]:
        return f"📷 I am not sure what this is. Please tap the material:\n{PICK_HINDI}"
    if suggestion["label"] == "trash":
        return f"📷 This looks like non-recyclable waste. If it can be recycled, tap the material:\n{PICK_HINDI}"
    pct = min(99, round(100 * suggestion["confidence"]))  # a model is never 100% sure
    return (f"📷 This looks like <b>{LABEL_TEXT[suggestion['label']]}</b> ({pct}% sure). "
            f"Tap to confirm, or pick another:\n{PICK_HINDI}")


def ask_weight(m: dict) -> str:
    return (f"<b>{escape(m['name'])}</b>, reference price ₹{m['ref_price_per_kg']:g}/kg.\n"
            "How many kg? Send a number, e.g. 12.5\nकितने किलो?")


def bad_weight() -> str:
    return f"Please send the weight in kg as a number between 0 and {MAX_WEIGHT_KG}, e.g. 12.5"


def ask_photo() -> str:
    return "📷 Send a photo of the material, or tap <b>Skip photo</b>.\nफोटो भेजें या Skip दबाएं।"


def ask_location() -> str:
    return ("📍 Tap <b>Share location</b> so this lot is recorded where it was collected, "
            "or tap <b>Skip location</b>.")


def receipt(tx: dict) -> str:
    lines = [
        f"✅ <b>Lot recorded</b> · Passport {tx['passport_id']}",
        f"{escape(tx['material'])} · {tx['weight_kg']:g} kg",
        f"Reference price: <b>₹{tx['ref_price_per_kg']:g}/kg</b>",
        f"Fair value: <b>{inr(tx['ref_amount'])}</b>",
    ]
    if tx.get("cv_suggested"):
        agreed = tx["category"] in LABEL_TO_CATEGORIES.get(tx["cv_suggested"], [])
        lines.append(f"📷 Camera suggested {LABEL_TEXT.get(tx['cv_suggested'], tx['cv_suggested'])}; "
                     f"{'you confirmed' if agreed else 'you chose'} {escape(tx['material'])}.")
    if tx.get("gps_lat") is not None:
        lines.append("📍 Location saved. This lot is now on the MITRA map.")
    else:
        lines.append("No location shared, so this lot will not appear on the map.")
    return "\n".join(lines)


def prices(materials: list[dict]) -> str:
    rows = [f"• {escape(m['name'])}: <b>₹{m['ref_price_per_kg']:g}/kg</b>"
            for m in sorted(materials, key=lambda m: -m["ref_price_per_kg"])]
    return ("💰 <b>Today's reference prices</b>\n"
            "Wholesale price minus fair trader margin. Do not sell for much less.\n\n" + "\n".join(rows))


def forget_confirm(name: str, code: str) -> str:
    return (f"This deletes your name and details ({escape(name)}, {code}) and any photos you sent.\n"
            "Your past lots stay in MITRA <b>without your name</b>, because recycling reports need them.\n\n"
            "Delete your data?\nक्या आप अपना नाम और जानकारी हटाना चाहते हैं?")


def forgotten(lots_kept: int) -> str:
    kept = f"{lots_kept} past lot{'s' if lots_kept != 1 else ''} stay in MITRA without your name. " if lots_kept else ""
    return f"✅ Done. Your name and details are deleted. {kept}".rstrip()


def register_again() -> str:
    return "Send /start any time to register again."


def forget_kept() -> str:
    return "OK, nothing was deleted."


def nothing_to_forget() -> str:
    return "You are not registered, so there is nothing to delete."


def cancelled() -> str:
    return "Cancelled. Tap 📦 Log material to start again."


def help_text() -> str:
    return ("/start: register or see your Collector ID\n"
            "/log: record material you collected\n"
            "/prices: today's reference prices\n"
            "/cancel: stop the current step\n"
            "/forget: delete your name and details")


def html_to_text(s: str) -> str:
    """For the terminal demo: drop Telegram HTML tags."""
    return re.sub(r"</?b>", "", s)
