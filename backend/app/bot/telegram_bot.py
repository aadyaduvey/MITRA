"""MITRA Telegram bot: collector signup and lot logging by chat. No app install.

Run (from backend/):
    $env:TELEGRAM_TOKEN = "<token from @BotFather>"     # PowerShell
    uv run python -m app.bot.telegram_bot

The token can also go in backend/.env as TELEGRAM_TOKEN=... (git-ignored).
MITRA_API_URL points at the API (default http://127.0.0.1:8000).
"""
import asyncio
import logging
import os
import sys
import warnings
from pathlib import Path
from uuid import uuid4

from telegram import (
    BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup,
    ReplyKeyboardRemove, Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler,
    MessageHandler, PersistenceInput, PicklePersistence, filters,
)
from telegram.warnings import PTBUserWarning

from app.bot import messages as msg
from app.bot.client import ApiError, MitraClient, UnknownCollector

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PHOTO_DIR = DATA_DIR / "photos"
STATE_FILE = DATA_DIR / "bot_state.pickle"

NAME, AREA, MATERIAL, WEIGHT, PHOTO, LOCATION = range(6)
END = ConversationHandler.END

LOG_BUTTON = "📦 Log material"
PRICES_BUTTON = "💰 Today's prices"
SKIP_PHOTO = "Skip photo"
SKIP_LOCATION = "Skip location"
MENU = ReplyKeyboardMarkup([[LOG_BUTTON, PRICES_BUTTON]], resize_keyboard=True)

SEND_ATTEMPTS = 4
RETRY_DELAY_S = 1.5  # grows linearly per attempt

log = logging.getLogger("mitra.bot")


def _api(context: ContextTypes.DEFAULT_TYPE) -> MitraClient:
    return context.bot_data["api"]


async def _call(fn, *args, **kwargs):
    """Run a blocking API call off the event loop."""
    return await asyncio.to_thread(fn, *args, **kwargs)


async def _send(make_call, what: str) -> bool:
    """Call Telegram, retrying dropped connections (slow or flaky networks).

    Returns False if every attempt failed; the conversation still moves on, so the
    collector's next message lands in the right step. BadRequest is a bug, not the network.
    """
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            await make_call()
            return True
        except BadRequest:
            raise
        except NetworkError as e:
            if attempt == SEND_ATTEMPTS:
                log.warning("Gave up on %s after %d attempts: %s", what, attempt, e)
                return False
            log.info("Network error on %s (attempt %d), retrying: %s", what, attempt, e)
            await asyncio.sleep(RETRY_DELAY_S * attempt)
    return False


async def _say(update: Update, text: str, markup=None) -> bool:
    return await _send(lambda: update.effective_message.reply_text(
        text, parse_mode=ParseMode.HTML, reply_markup=markup), "reply")


# ---------- registration ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    ud.pop("lot", None)
    if ud.get("collector_id"):
        try:
            c = await _call(_api(context).collector, ud["collector_id"])
        except ApiError as e:
            await _say(update, str(e))
            return END
        if c and c["name"] == ud.get("name"):
            await _say(update, msg.welcome_back(c["name"], c["code"]), MENU)
            return END
        ud.clear()  # database was reset or record changed: register again
    await _say(update, msg.welcome_new(), ReplyKeyboardRemove())
    return NAME


async def got_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = " ".join(update.message.text.split())
    if not 2 <= len(name) <= 80:
        await _say(update, msg.bad_name())
        return NAME
    context.user_data["pending_name"] = name
    await _say(update, msg.ask_area(name))
    return AREA


async def got_area(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    area = " ".join(update.message.text.split())
    if not 2 <= len(area) <= 60:
        await _say(update, "Please send your area name (2 to 60 letters).")
        return AREA
    ud = context.user_data
    try:
        c = await _call(_api(context).register, ud["pending_name"], area)
    except ApiError as e:
        await _say(update, f"{e}\nPlease send your area again.")
        return AREA
    ud.pop("pending_name", None)
    ud.update(collector_id=c["id"], name=c["name"], code=c["code"])
    await _say(update, msg.registered(c), MENU)
    return END


# ---------- logging a lot ----------

async def log_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    if not ud.get("collector_id"):
        await _say(update, msg.need_registration(), ReplyKeyboardRemove())
        return END
    try:
        materials = await _call(_api(context).materials)
    except ApiError as e:
        await _say(update, str(e), MENU)
        return END
    ud["materials"] = {m["id"]: m for m in materials}
    ud["lot"] = {}
    buttons = [InlineKeyboardButton(msg.material_button(m), callback_data=f"mat:{m['id']}") for m in materials]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    await _say(update, msg.material_prompt(), InlineKeyboardMarkup(rows))
    return MATERIAL


async def got_material(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await _send(q.answer, "button ack")
    m = context.user_data.get("materials", {}).get(int(q.data.split(":", 1)[1]))
    if m is None:
        await _send(lambda: q.edit_message_text("That list is out of date. Tap 📦 Log material again."), "edit")
        return END
    context.user_data.setdefault("lot", {})["material_id"] = m["id"]
    await _send(lambda: q.edit_message_text(msg.ask_weight(m), parse_mode=ParseMode.HTML), "edit")
    return WEIGHT


async def got_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    w = msg.parse_weight(update.message.text)
    if w is None:
        await _say(update, msg.bad_weight())
        return WEIGHT
    context.user_data["lot"]["weight_kg"] = w
    await _say(update, msg.ask_photo(), ReplyKeyboardMarkup([[SKIP_PHOTO]], resize_keyboard=True))
    return PHOTO


async def got_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    photo = update.message.photo[-1]  # largest size
    data = await (await photo.get_file()).download_as_bytearray()
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4().hex}.jpg"
    (PHOTO_DIR / name).write_bytes(bytes(data))
    context.user_data["lot"]["photo_url"] = f"photos/{name}"
    return await _ask_location(update)


async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _ask_location(update)


async def _ask_location(update: Update) -> int:
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Share location", request_location=True)], [SKIP_LOCATION]],
        resize_keyboard=True, one_time_keyboard=True)
    await _say(update, msg.ask_location(), keyboard)
    return LOCATION


async def got_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    loc = update.message.location
    context.user_data["lot"].update(gps_lat=loc.latitude, gps_lon=loc.longitude)
    return await _finish(update, context)


async def skip_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _finish(update, context)


async def _finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    lot = ud.pop("lot", {})
    try:
        tx = await _call(_api(context).log_lot, collector_id=ud["collector_id"], **lot)
    except UnknownCollector as e:
        ud.clear()
        await _say(update, str(e), ReplyKeyboardRemove())
        return END
    except ApiError as e:
        await _say(update, f"{e}\nYour lot was not saved. Tap 📦 Log material to try again.", MENU)
        return END
    await _say(update, msg.receipt(tx), MENU)
    return END


# ---------- always available ----------

async def prices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await _say(update, msg.prices(await _call(_api(context).materials)), MENU)
    except ApiError as e:
        await _say(update, str(e))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _say(update, msg.help_text())


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("lot", None)
    context.user_data.pop("pending_name", None)
    await _say(update, msg.cancelled(), MENU if context.user_data.get("collector_id") else None)
    return END


async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask before erasing. Also ends any half-finished step."""
    ud = context.user_data
    ud.pop("lot", None)
    ud.pop("pending_name", None)
    if not ud.get("collector_id"):
        await _say(update, msg.nothing_to_forget(), ReplyKeyboardRemove())
        return END
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("Yes, delete my data", callback_data="forget:yes"),
        InlineKeyboardButton("No, keep it", callback_data="forget:no"),
    ]])
    await _say(update, msg.forget_confirm(ud["name"], ud["code"]), buttons)
    return END


async def forget_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await _send(q.answer, "button ack")
    ud = context.user_data
    if q.data != "forget:yes":
        await _send(lambda: q.edit_message_text(msg.forget_kept()), "edit")
        return
    if not ud.get("collector_id"):
        await _send(lambda: q.edit_message_text(msg.nothing_to_forget()), "edit")
        return
    try:
        result = await _call(_api(context).forget, ud["collector_id"])
    except ApiError as e:
        await _send(lambda: q.edit_message_text(f"{e}\nNothing was deleted. Please try /forget again."), "edit")
        return
    ud.clear()
    await _send(lambda: q.edit_message_text(msg.forgotten(result["lots_kept"] if result else 0)), "edit")
    await _say(update, msg.register_again(), ReplyKeyboardRemove())


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled error", exc_info=context.error)
    if isinstance(context.error, NetworkError) and not isinstance(context.error, BadRequest):
        return  # replying would hit the same network problem
    if isinstance(update, Update) and update.effective_message:
        await _say(update, "Sorry, something went wrong. Please try again.")


# ---------- wiring ----------

def build_conversation() -> ConversationHandler:
    text = filters.TEXT & ~filters.COMMAND
    log_entry = [CommandHandler("log", log_start),
                 MessageHandler(filters.Regex(f"^{LOG_BUTTON}$") | filters.Regex(r"(?i)^\s*log\s*$"), log_start)]
    with warnings.catch_warnings():  # per_message=False with a CallbackQueryHandler is intended here
        warnings.simplefilter("ignore", PTBUserWarning)
        return ConversationHandler(
            entry_points=[CommandHandler("start", start), *log_entry],
            states={
                NAME: [MessageHandler(text, got_name)],
                AREA: [MessageHandler(text, got_area)],
                MATERIAL: [CallbackQueryHandler(got_material, pattern=r"^mat:\d+$")],
                WEIGHT: [MessageHandler(text, got_weight)],
                PHOTO: [MessageHandler(filters.PHOTO, got_photo),
                        MessageHandler(filters.Regex(f"^{SKIP_PHOTO}$"), skip_photo)],
                LOCATION: [MessageHandler(filters.LOCATION, got_location),
                           MessageHandler(filters.Regex(f"^{SKIP_LOCATION}$"), skip_location)],
            },
            fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start),
                       CommandHandler("forget", forget), *log_entry],
            name="mitra",
            persistent=True,
            allow_reentry=True,
        )


COMMANDS = [
    BotCommand("start", "Register, or see your Collector ID"),
    BotCommand("log", "Record material you collected"),
    BotCommand("prices", "Today's reference prices"),
    BotCommand("cancel", "Stop the current step"),
    BotCommand("forget", "Delete your name and details"),
    BotCommand("help", "What I can do"),
]


async def _post_init(app: Application) -> None:
    """Show the command menu when a collector types '/'."""
    await _send(lambda: app.bot.set_my_commands(COMMANDS), "set commands")


def build_persistence(state_file: Path = STATE_FILE) -> PicklePersistence:
    # Persist only per-user registration and conversation state. bot_data holds the live
    # API client: loading it from disk would replace it, and it cannot be pickled anyway.
    return PicklePersistence(filepath=state_file,
                             store_data=PersistenceInput(bot_data=False, chat_data=False, callback_data=False))


def build_application(token: str, api: MitraClient, state_file: Path = STATE_FILE) -> Application:
    app = (Application.builder().token(token).persistence(build_persistence(state_file))
           # generous timeouts: Telegram can take 1-2 s per request on some Indian networks
           .connect_timeout(15).read_timeout(20).write_timeout(20).pool_timeout(10)
           .get_updates_connect_timeout(15).get_updates_read_timeout(30)
           .post_init(_post_init)
           .build())
    app.bot_data["api"] = api
    app.add_handler(build_conversation())
    app.add_handler(CommandHandler("prices", prices))
    app.add_handler(MessageHandler(filters.Regex(f"^{PRICES_BUTTON}$"), prices))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("forget", forget))
    app.add_handler(CallbackQueryHandler(forget_answer, pattern=r"^forget:(yes|no)$"))
    app.add_error_handler(on_error)
    return app


def _token() -> str | None:
    token = os.environ.get("TELEGRAM_TOKEN")
    env_file = DATA_DIR.parent / ".env"
    if not token and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "TELEGRAM_TOKEN":
                token = value.strip().strip('"').strip("'")
    return token or None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    token = _token()
    if not token:
        sys.exit("TELEGRAM_TOKEN is not set. Get a token from @BotFather, then:\n"
                 '  PowerShell:  $env:TELEGRAM_TOKEN = "123456:ABC..."\n'
                 "  or put TELEGRAM_TOKEN=123456:ABC... in backend/.env")
    api = MitraClient()
    if not api.health():
        log.warning("MITRA API not reachable at %s; start it first (uvicorn app.main:app --port 8000)",
                    api.http.base_url)
    log.info("MITRA bot running. Press Ctrl+C to stop.")
    build_application(token, api).run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
