"""Everything the bot says, in English and Hindi, as pure functions (Telegram HTML).

Shared with the offline demo. Every function takes `lang` ("en" or "hi", default "en").
Short, plain wording: collectors should not need to read much. Digits stay 0-9 and
rupees keep Indian grouping in both languages.
"""
import re
from html import escape

from app.bot.client import UNREACHABLE
from app.classify.labels import LABEL_TEXT, LABEL_TO_CATEGORIES

MAX_WEIGHT_KG = 2000
LANGS = ("hi", "en")

# Keyboard button labels. Handlers accept either language (see telegram_bot.py).
BUTTONS = {
    "log": {"en": "📦 Log material", "hi": "📦 माल दर्ज करें"},
    "prices": {"en": "💰 Today's prices", "hi": "💰 आज के भाव"},
    "skip_photo": {"en": "Skip photo", "hi": "फोटो छोड़ें"},
    "skip_location": {"en": "Skip location", "hi": "लोकेशन छोड़ें"},
    "share_location": {"en": "📍 Share location", "hi": "📍 लोकेशन भेजें"},
    "forget_yes": {"en": "Yes, delete my data", "hi": "हाँ, मेरा डेटा हटाएँ"},
    "forget_no": {"en": "No, keep it", "hi": "नहीं, रहने दें"},
}
LANGUAGE_BUTTONS = {"hi": "हिंदी", "en": "English"}

MATERIAL_HI = {
    "PET plastic": "PET प्लास्टिक",
    "HDPE": "HDPE प्लास्टिक",
    "Cardboard/paper": "गत्ता / कागज़",
    "Glass": "कांच",
    "Metal (steel/aluminium blended)": "धातु (लोहा / एल्युमिनियम)",
    "Copper": "तांबा",
    "E-waste": "ई-कचरा (इलेक्ट्रॉनिक)",
}
LABEL_TEXT_HI = {
    "paper": "गत्ता / कागज़",
    "glass": "कांच",
    "metal": "धातु",
    "plastic": "प्लास्टिक (PET या HDPE)",
    "trash": "रीसायकल न होने वाला कचरा",
}

_T = {
    "choose_language": {
        "en": "Choose your language / अपनी भाषा चुनें",
        "hi": "Choose your language / अपनी भाषा चुनें",
    },
    "language_set": {"en": "✅ Language set to English.", "hi": "✅ भाषा हिंदी कर दी गई है।"},
    "welcome_new": {
        "en": ("Namaste! 🙏 I am <b>MITRA</b>. I record the material you collect and tell you "
               "the fair price. No app needed, just this chat.\n\nWhat is your name?"),
        "hi": ("नमस्ते! 🙏 मैं <b>MITRA</b> हूँ। आप जो माल इकट्ठा करते हैं, मैं उसे दर्ज करता हूँ "
               "और आपको उसका सही भाव बताता हूँ। कोई ऐप नहीं चाहिए, बस यह चैट।\n\nआपका नाम क्या है?"),
    },
    "bad_name": {"en": "Please send your name (2 to 80 letters).",
                 "hi": "कृपया अपना नाम भेजें (2 से 80 अक्षर)।"},
    "bad_area": {"en": "Please send your area name (2 to 60 letters).",
                 "hi": "कृपया अपने इलाके का नाम भेजें (2 से 60 अक्षर)।"},
    "area_again": {"en": "Please send your area again.", "hi": "कृपया अपना इलाका फिर से भेजें।"},
    "need_registration": {"en": "Please register first: send /start",
                          "hi": "पहले पंजीकरण करें: /start भेजें"},
    "material_prompt": {"en": "What material is it? Tap one:", "hi": "यह कौन सा माल है? एक चुनें:"},
    "tap_material": {"en": "Please tap one of the material buttons:",
                     "hi": "कृपया नीचे दिए माल के बटन में से एक दबाएँ:"},
    "cv_unsure": {"en": "📷 I am not sure what this is. Please tap the material:",
                  "hi": "📷 मुझे पक्का नहीं पता कि यह क्या है। कृपया माल चुनें:"},
    "cv_trash": {"en": "📷 This looks like non-recyclable waste. If it can be recycled, tap the material:",
                 "hi": "📷 यह ऐसा कचरा लगता है जो रीसायकल नहीं होता। अगर यह रीसायकल हो सकता है, तो माल चुनें:"},
    "ask_photo": {"en": "📷 Send a photo of the material, or tap <b>Skip photo</b>.",
                  "hi": "📷 माल की फोटो भेजें, या <b>फोटो छोड़ें</b> दबाएँ।"},
    "photo_received": {"en": "📷 Photo received.", "hi": "📷 फोटो मिल गई।"},
    "no_photo": {"en": "OK, no photo.", "hi": "ठीक है, बिना फोटो।"},
    "ask_location": {
        "en": ("📍 Tap <b>Share location</b> so this lot is recorded where it was collected, "
               "or tap <b>Skip location</b>."),
        "hi": ("📍 <b>लोकेशन भेजें</b> दबाएँ ताकि यह माल उसी जगह दर्ज हो जहाँ इकट्ठा हुआ, "
               "या <b>लोकेशन छोड़ें</b> दबाएँ।"),
    },
    "list_outdated": {"en": "That list is out of date. Tap 📦 Log material again.",
                      "hi": "यह सूची पुरानी है। 📦 माल दर्ज करें फिर से दबाएँ।"},
    "lot_not_saved": {"en": "Your lot was not saved. Tap 📦 Log material to try again.",
                      "hi": "आपका माल दर्ज नहीं हुआ। फिर से कोशिश करने के लिए 📦 माल दर्ज करें दबाएँ।"},
    "register_again": {"en": "Send /start any time to register again.",
                       "hi": "दोबारा पंजीकरण के लिए कभी भी /start भेजें।"},
    "forget_kept": {"en": "OK, nothing was deleted.", "hi": "ठीक है, कुछ भी नहीं हटाया गया।"},
    "nothing_to_forget": {"en": "You are not registered, so there is nothing to delete.",
                          "hi": "आपका पंजीकरण नहीं है, इसलिए हटाने के लिए कुछ नहीं है।"},
    "nothing_deleted_retry": {"en": "Nothing was deleted. Please try /forget again.",
                              "hi": "कुछ भी नहीं हटाया गया। कृपया /forget फिर से भेजें।"},
    "cancelled": {"en": "Cancelled. Tap 📦 Log material to start again.",
                  "hi": "रद्द कर दिया। फिर से शुरू करने के लिए 📦 माल दर्ज करें दबाएँ।"},
    "something_wrong": {"en": "Sorry, something went wrong. Please try again.",
                        "hi": "माफ़ कीजिए, कुछ गड़बड़ हो गई। कृपया फिर से कोशिश करें।"},
    "help": {
        "en": ("/start: register or see your Collector ID\n"
               "/log: record material you collected\n"
               "/prices: today's reference prices\n"
               "/language: change language (हिंदी / English)\n"
               "/cancel: stop the current step\n"
               "/forget: delete your name and details"),
        "hi": ("/start: पंजीकरण करें या अपनी कलेक्टर आईडी देखें\n"
               "/log: इकट्ठा किया माल दर्ज करें\n"
               "/prices: आज के संदर्भ भाव\n"
               "/language: भाषा बदलें (हिंदी / English)\n"
               "/cancel: अभी का काम रोकें\n"
               "/forget: अपना नाम और जानकारी हटाएँ"),
    },
}

# Server/API errors the collector may see, in Hindi. Unknown errors are shown with a prefix.
_API_ERRORS_HI = {
    UNREACHABLE: "MITRA सर्वर से अभी संपर्क नहीं हो पा रहा है। एक मिनट बाद फिर कोशिश करें।",
    "The MITRA server had a problem. Please try again.": "MITRA सर्वर में दिक्कत आई। कृपया फिर से कोशिश करें।",
    "Your registration was not found. Please send /start to register again.":
        "आपका पंजीकरण नहीं मिला। कृपया /start भेजकर फिर से पंजीकरण करें।",
}


def _lang(lang: str) -> str:
    return lang if lang in LANGS else "en"


def t(key: str, lang: str = "en") -> str:
    """A fixed message in the given language."""
    return _T[key][_lang(lang)]


def button(key: str, lang: str = "en") -> str:
    return BUTTONS[key][_lang(lang)]


def all_labels(key: str) -> list[str]:
    """Every language's label for a button, for handlers that must accept both."""
    return list(BUTTONS[key].values())


def api_error(error: Exception | str, lang: str = "en") -> str:
    text = str(error)
    if _lang(lang) == "en":
        return text
    return _API_ERRORS_HI.get(text, f"गड़बड़ी: {text}")


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


def material_name(name: str, lang: str = "en") -> str:
    """Full material name in the collector's language (unknown names stay as stored)."""
    return MATERIAL_HI.get(name, name) if _lang(lang) == "hi" else name


def short_name(material: str, lang: str = "en") -> str:
    """'Metal (steel/aluminium blended)' -> 'Metal' / 'धातु'."""
    return material_name(material, lang).split(" (")[0]


def per_kg(price: float, lang: str = "en") -> str:
    return f"₹{price:g}/{'किलो' if _lang(lang) == 'hi' else 'kg'}"


def label_text(label: str, lang: str = "en") -> str:
    table = LABEL_TEXT_HI if _lang(lang) == "hi" else LABEL_TEXT
    return table.get(label, label)


def parse_weight(text: str) -> float | None:
    """Accepts '12', '12.5', '12,5', '12.5 kg', '12 किलो'. None if not a sensible weight."""
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(?:kg|kgs|किलो|किग्रा)?\s*", text.lower())
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    return round(value, 2) if 0 < value <= MAX_WEIGHT_KG else None


# ---------- registration ----------

def choose_language() -> str:
    return t("choose_language")


def welcome_new(lang: str = "en") -> str:
    return t("welcome_new", lang)


def ask_area(name: str, lang: str = "en") -> str:
    if _lang(lang) == "hi":
        return f"धन्यवाद, {escape(name)}। आप किस इलाके में काम करते हैं? (जैसे: सांगानेर)"
    return f"Thank you, {escape(name)}. Which area do you work in? (for example: Sanganer)"


def bad_name(lang: str = "en") -> str:
    return t("bad_name", lang)


def registered(collector: dict, lang: str = "en") -> str:
    name, code = escape(collector["name"]), collector["code"]
    if _lang(lang) == "hi":
        return (f"✅ आपका पंजीकरण हो गया, {name}।\nआपकी MITRA कलेक्टर आईडी: <b>{code}</b>\n\n"
                "जब भी माल इकट्ठा करें, <b>📦 माल दर्ज करें</b> दबाएँ।")
    return (f"✅ You are registered, {name}.\nYour MITRA Collector ID: <b>{code}</b>\n\n"
            "Tap <b>📦 Log material</b> each time you collect material.")


def welcome_back(name: str, code: str, lang: str = "en") -> str:
    if _lang(lang) == "hi":
        return (f"फिर से स्वागत है, {escape(name)} ({code})।\n"
                "माल दर्ज करने के लिए <b>📦 माल दर्ज करें</b> दबाएँ, या <b>💰 आज के भाव</b> देखें।")
    return (f"Welcome back, {escape(name)} ({code}).\n"
            "Tap <b>📦 Log material</b> to record a lot, or <b>💰 Today's prices</b>.")


def need_registration(lang: str = "en") -> str:
    return t("need_registration", lang)


# ---------- logging a lot ----------

def material_prompt(lang: str = "en") -> str:
    return t("material_prompt", lang)


def material_button(m: dict, suggested: bool = False, lang: str = "en") -> str:
    return f"{'📷 ' if suggested else ''}{short_name(m['name'], lang)} · {per_kg(m['ref_price_per_kg'], lang)}"


def ordered_materials(materials: list[dict], suggestion: dict | None) -> list[tuple[dict, bool]]:
    """Suggested materials first (marked), then the rest. Every material is always offered."""
    cats = set(suggestion["categories"]) if suggestion and suggestion["confident"] else set()
    first = [(m, True) for m in materials if m["category"] in cats]
    return first + [(m, False) for m in materials if m["category"] not in cats]


def cv_prompt(suggestion: dict | None, lang: str = "en") -> str:
    """What to say above the material buttons after a photo."""
    if suggestion is None:
        return material_prompt(lang)
    if not suggestion["confident"]:
        return t("cv_unsure", lang)
    if suggestion["label"] == "trash":
        return t("cv_trash", lang)
    pct = min(99, round(100 * suggestion["confidence"]))  # a model is never 100% sure
    label = label_text(suggestion["label"], lang)
    if _lang(lang) == "hi":
        return f"📷 यह <b>{label}</b> लगता है ({pct}% भरोसा)। सही हो तो दबाएँ, नहीं तो दूसरा चुनें:"
    return f"📷 This looks like <b>{label}</b> ({pct}% sure). Tap to confirm, or pick another:"


def ask_weight(m: dict, lang: str = "en") -> str:
    name, price = escape(material_name(m["name"], lang)), per_kg(m["ref_price_per_kg"], lang)
    if _lang(lang) == "hi":
        return f"<b>{name}</b>, संदर्भ भाव {price}।\nकितने किलो है? सिर्फ़ संख्या भेजें, जैसे 12.5"
    return f"<b>{name}</b>, reference price {price}.\nHow many kg? Send a number, e.g. 12.5"


def bad_weight(lang: str = "en") -> str:
    if _lang(lang) == "hi":
        return f"कृपया वज़न किलो में संख्या के रूप में भेजें (0 से {MAX_WEIGHT_KG} के बीच), जैसे 12.5"
    return f"Please send the weight in kg as a number between 0 and {MAX_WEIGHT_KG}, e.g. 12.5"


def ask_photo(lang: str = "en") -> str:
    return t("ask_photo", lang)


def ask_location(lang: str = "en") -> str:
    return t("ask_location", lang)


def receipt(tx: dict, lang: str = "en") -> str:
    hi = _lang(lang) == "hi"
    material = escape(material_name(tx["material"], lang))
    lines = [
        f"✅ <b>{'माल दर्ज हो गया' if hi else 'Lot recorded'}</b> · "
        f"{'पासपोर्ट' if hi else 'Passport'} {tx['passport_id']}",
        f"{material} · {tx['weight_kg']:g} {'किलो' if hi else 'kg'}",
        f"{'संदर्भ भाव' if hi else 'Reference price'}: <b>{per_kg(tx['ref_price_per_kg'], lang)}</b>",
        f"{'सही कीमत' if hi else 'Fair value'}: <b>{inr(tx['ref_amount'])}</b>",
    ]
    if tx.get("cv_suggested"):
        agreed = tx["category"] in LABEL_TO_CATEGORIES.get(tx["cv_suggested"], [])
        label = label_text(tx["cv_suggested"], lang)
        if hi:
            lines.append(f"📷 कैमरे का सुझाव: {label}; आपने {'पुष्टि की' if agreed else 'चुना'}: {material}।")
        else:
            lines.append(f"📷 Camera suggested {label}; {'you confirmed' if agreed else 'you chose'} {material}.")
    if tx.get("gps_lat") is not None:
        lines.append("📍 लोकेशन सेव हो गई। यह माल अब MITRA नक्शे पर है।" if hi
                     else "📍 Location saved. This lot is now on the MITRA map.")
    else:
        lines.append("लोकेशन नहीं भेजी गई, इसलिए यह माल नक्शे पर नहीं दिखेगा।" if hi
                     else "No location shared, so this lot will not appear on the map.")
    return "\n".join(lines)


def prices(materials: list[dict], lang: str = "en") -> str:
    rows = [f"• {escape(material_name(m['name'], lang))}: <b>{per_kg(m['ref_price_per_kg'], lang)}</b>"
            for m in sorted(materials, key=lambda m: -m["ref_price_per_kg"])]
    if _lang(lang) == "hi":
        head = ("💰 <b>आज के संदर्भ भाव</b>\n"
                "थोक भाव में से व्यापारी का उचित मुनाफ़ा घटाकर। इससे बहुत कम में न बेचें।")
    else:
        head = ("💰 <b>Today's reference prices</b>\n"
                "Wholesale price minus fair trader margin. Do not sell for much less.")
    dates = [m["price_updated_at"][:10] for m in materials if m.get("price_updated_at")]
    if dates:
        day = "/".join(reversed(max(dates).split("-")))  # 2026-09-28 -> 28/09/2026
        rows.append(f"\n{'भाव अपडेट' if _lang(lang) == 'hi' else 'Prices updated'}: {day}")
    return head + "\n\n" + "\n".join(rows)


# ---------- right to erasure ----------

def forget_confirm(name: str, code: str, lang: str = "en") -> str:
    if _lang(lang) == "hi":
        return (f"इससे आपका नाम और जानकारी ({escape(name)}, {code}) और आपकी भेजी सभी फोटो हट जाएँगी।\n"
                "आपके पुराने माल के रिकॉर्ड MITRA में <b>बिना आपके नाम के</b> रहेंगे, "
                "क्योंकि रीसाइक्लिंग रिपोर्ट के लिए वे ज़रूरी हैं।\n\n"
                "क्या आप अपना डेटा हटाना चाहते हैं?")
    return (f"This deletes your name and details ({escape(name)}, {code}) and any photos you sent.\n"
            "Your past lots stay in MITRA <b>without your name</b>, because recycling reports need them.\n\n"
            "Delete your data?")


def forgotten(lots_kept: int, lang: str = "en") -> str:
    if _lang(lang) == "hi":
        kept = f"आपके {lots_kept} पुराने माल रिकॉर्ड बिना नाम के MITRA में रहेंगे।" if lots_kept else ""
        return f"✅ हो गया। आपका नाम और जानकारी हटा दी गई है। {kept}".rstrip()
    kept = f"{lots_kept} past lot{'s' if lots_kept != 1 else ''} stay in MITRA without your name. " if lots_kept else ""
    return f"✅ Done. Your name and details are deleted. {kept}".rstrip()


def register_again(lang: str = "en") -> str:
    return t("register_again", lang)


def forget_kept(lang: str = "en") -> str:
    return t("forget_kept", lang)


def nothing_to_forget(lang: str = "en") -> str:
    return t("nothing_to_forget", lang)


def cancelled(lang: str = "en") -> str:
    return t("cancelled", lang)


def help_text(lang: str = "en") -> str:
    return t("help", lang)


def html_to_text(s: str) -> str:
    """For the terminal demo: drop Telegram HTML tags."""
    return re.sub(r"</?b>", "", s)
