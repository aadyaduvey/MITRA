"""Scripted chat walkthrough for demos with no internet (Telegram unreachable).

Plays the same conversation as the Telegram bot, with the same wording, and makes
the same API calls, so the new collector and lot really appear on the dashboard.

    uv run python -m app.bot.offline_demo            # press Enter to advance each message
    uv run python -m app.bot.offline_demo --auto     # no pauses
"""
import argparse
import sys
from uuid import uuid4

from app.bot import messages as msg
from app.bot.client import ApiError, MitraClient
from app.bot.telegram_bot import DATA_DIR, PHOTO_DIR

SAMPLE_PHOTO = DATA_DIR / "samples" / "metal_sample.jpg"  # held-out TrashNet photo (MIT)

SCRIPT = {
    "name": "Sunita Devi",
    "area": "Raja Park",
    "material": "Copper",
    "weight": "3.5",
    "gps": (26.9012, 75.8297),  # Raja Park, Jaipur
}

BOT, USER = "🤖 MITRA", "👤 Collector"


def show(who: str, text: str, pause: bool) -> None:
    body = msg.html_to_text(text).replace("\n", "\n    ")
    print(f"\n{who}:\n    {body}")
    if pause:
        input("    [Enter]")


def run(api: MitraClient, pause: bool = True) -> dict:
    s = SCRIPT
    show(USER, "/start", pause)
    show(BOT, msg.welcome_new(), pause)
    show(USER, s["name"], pause)
    show(BOT, msg.ask_area(s["name"]), pause)
    show(USER, s["area"], pause)
    collector = api.register(s["name"], s["area"])
    show(BOT, msg.registered(collector), pause)

    show(USER, "📦 Log material", pause)
    materials = api.materials()
    show(BOT, msg.ask_photo(), pause)

    lot: dict = {}
    suggestion = None
    if SAMPLE_PHOTO.exists():
        show(USER, f"(sends photo) {SAMPLE_PHOTO.name}", pause)
        data = SAMPLE_PHOTO.read_bytes()
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{uuid4().hex}.jpg"  # stored like a bot upload, so /forget can delete it
        (PHOTO_DIR / name).write_bytes(data)
        lot["photo_url"] = f"photos/{name}"
        try:
            suggestion = api.classify(data)  # None when the classifier is in development
        except ApiError:
            suggestion = None
        if suggestion:
            lot.update(cv_suggested=suggestion["label"], cv_confidence=suggestion["confidence"])
        show(BOT, "📷 Photo received.", False)
    else:
        show(USER, "(taps) Skip photo", pause)

    buttons = "   ".join(f"[{msg.material_button(m, sug)}]" for m, sug in msg.ordered_materials(materials, suggestion))
    show(BOT, f"{msg.cv_prompt(suggestion)}\n{buttons}", pause)
    material = next(m for m in materials if m["name"] == s["material"])
    show(USER, f"(taps) {msg.material_button(material)}", pause)
    show(BOT, msg.ask_weight(material), pause)
    show(USER, s["weight"], pause)
    show(BOT, msg.ask_location(), pause)
    lat, lon = s["gps"]
    show(USER, f"(shares location) {lat}, {lon}", pause)
    tx = api.log_lot(collector["id"], material["id"], msg.parse_weight(s["weight"]), lat, lon, **lot)
    show(BOT, msg.receipt(tx), False)
    print("\n→ Open the dashboard Collector Map: the lot is outlined orange in Raja Park, "
          f"and listed first under Latest lots ({collector['name']}).")
    return tx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--auto", action="store_true", help="run without pausing")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # emoji and Hindi on Windows consoles
    try:
        run(MitraClient(), pause=not args.auto)
    except ApiError as e:
        sys.exit(f"\n{e}\nStart the API first:  uv run uvicorn app.main:app --port 8000")


if __name__ == "__main__":
    main()
