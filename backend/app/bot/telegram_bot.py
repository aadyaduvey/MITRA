"""MITRA Telegram bot: collector signup and lot logging by chat, in Hindi or English. No app install.

Run (from backend/):
    $env:TELEGRAM_TOKEN = "<token from @BotFather>"     # PowerShell
    uv run python -m app.bot.telegram_bot

The token can also go in backend/.env as TELEGRAM_TOKEN=... (git-ignored).
MITRA_API_URL points at the API (default http://127.0.0.1:8000).
"""
import asyncio
import logging
import re
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
import httpx
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler,
    MessageHandler, PersistenceInput, PicklePersistence, filters,
)
from telegram.request import HTTPXRequest
from telegram.warnings import PTBUserWarning

from app.bot import messages as msg
from app.bot.client import ApiError, MitraClient, UnknownCollector
from app.classify.labels import CONFIDENT, LABEL_TO_CATEGORIES
from app.config import env_value

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PHOTO_DIR = DATA_DIR / "photos"
STATE_FILE = DATA_DIR / "bot_state.pickle"

NAME, AREA, MATERIAL, WEIGHT, PHOTO, LOCATION, LANG = range(7)
END = ConversationHandler.END

# English labels kept as names for tests and the offline demo; handlers accept both languages.
LOG_BUTTON = msg.button("log")
PRICES_BUTTON = msg.button("prices")
SKIP_PHOTO = msg.button("skip_photo")
SKIP_LOCATION = msg.button("skip_location")

SEND_ATTEMPTS = 6
RETRY_DELAY_S = 1.5  # grows linearly per attempt: about 22 s of retrying in total

log = logging.getLogger("mitra.bot")


class IPv4Request(HTTPXRequest):
    """Telegram requests over IPv4 only.

    api.telegram.org also has an IPv6 address; on networks where the IPv6 route is broken
    (common on Indian ISPs and venue Wi-Fi) most requests fail with ConnectError while
    IPv4 works. Binding to 0.0.0.0 makes every connection IPv4. Set TELEGRAM_IPV6=1 in
    backend/.env to allow IPv6 again.
    """

    def _build_client(self) -> httpx.AsyncClient:
        if env_value("TELEGRAM_IPV6") != "1":
            self._client_kwargs["transport"] = httpx.AsyncHTTPTransport(
                local_address="0.0.0.0", limits=self._client_kwargs["limits"])
        return super()._build_client()


def button_pattern(key: str) -> str:
    """Regex matching a keyboard button in any language."""
    return "^(" + "|".join(re.escape(label) for label in msg.all_labels(key)) + ")$"


def _lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang", "en")


def menu(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[msg.button("log", lang), msg.button("prices", lang)]], resize_keyboard=True)


def language_picker(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, callback_data=f"{prefix}:{code}")
        for code, label in msg.LANGUAGE_BUTTONS.items()
    ]])


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


async def _edit(update: Update, text: str) -> bool:
    q = update.callback_query
    return await _send(lambda: q.edit_message_text(text, parse_mode=ParseMode.HTML), "edit")


def _reset_keeping_language(ud: dict) -> None:
    lang = ud.get("lang")
    ud.clear()
    if lang:
        ud["lang"] = lang


# ---------- registration ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    ud.pop("lot", None)
    lang = _lang(context)
    if ud.get("collector_id"):
        try:
            c = await _call(_api(context).collector, ud["collector_id"])
        except ApiError as e:
            await _say(update, msg.api_error(e, lang))
            return END
        if c and c["name"] == ud.get("name"):
            await _say(update, msg.welcome_back(c["name"], c["code"], lang), menu(lang))
            return END
        _reset_keeping_language(ud)  # database was reset or record changed: register again
    if "lang" not in ud:
        await _say(update, msg.choose_language(), language_picker("lang"))
        return LANG
    await _say(update, msg.welcome_new(lang), ReplyKeyboardRemove())
    return NAME


async def got_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await _send(q.answer, "button ack")
    lang = q.data.split(":", 1)[1]
    context.user_data["lang"] = lang
    await _edit(update, msg.t("language_set", lang))
    await _say(update, msg.welcome_new(lang), ReplyKeyboardRemove())
    return NAME


async def got_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    name = " ".join(update.message.text.split())
    if not 2 <= len(name) <= 80:
        await _say(update, msg.bad_name(lang))
        return NAME
    context.user_data["pending_name"] = name
    await _say(update, msg.ask_area(name, lang))
    return AREA


async def got_area(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    area = " ".join(update.message.text.split())
    if not 2 <= len(area) <= 60:
        await _say(update, msg.t("bad_area", lang))
        return AREA
    ud = context.user_data
    try:
        c = await _call(_api(context).register, ud["pending_name"], area)
    except ApiError as e:
        await _say(update, f"{msg.api_error(e, lang)}\n{msg.t('area_again', lang)}")
        return AREA
    ud.pop("pending_name", None)
    ud.update(collector_id=c["id"], name=c["name"], code=c["code"])
    await _say(update, msg.registered(c, lang), menu(lang))
    return END


# ---------- logging a lot ----------

async def log_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    lang = _lang(context)
    if not ud.get("collector_id"):
        await _say(update, msg.need_registration(lang), ReplyKeyboardRemove())
        return END
    try:
        materials = await _call(_api(context).materials)
    except ApiError as e:
        await _say(update, msg.api_error(e, lang), menu(lang))
        return END
    ud["materials"] = {m["id"]: m for m in materials}
    ud["lot"] = {}
    skip = ReplyKeyboardMarkup([[msg.button("skip_photo", lang)]], resize_keyboard=True)
    await _say(update, msg.ask_photo(lang), skip)
    return PHOTO


async def got_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    photo = update.message.photo[-1]  # largest size
    data = bytes(await (await photo.get_file()).download_as_bytearray())
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid4().hex}.jpg"
    (PHOTO_DIR / name).write_bytes(data)
    lot = context.user_data["lot"]
    lot["photo_url"] = f"photos/{name}"
    try:
        suggestion = await _call(_api(context).classify, data)
    except ApiError as e:  # classifier trouble never blocks logging
        log.warning("Classifier failed, showing plain list: %s", e)
        suggestion = None
    if suggestion:
        lot.update(cv_suggested=suggestion["label"], cv_confidence=suggestion["confidence"])
    return await _ask_material(update, context, suggestion, msg.t("photo_received", _lang(context)))


async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _ask_material(update, context, None, msg.t("no_photo", _lang(context)))


async def _ask_material(update: Update, context: ContextTypes.DEFAULT_TYPE, suggestion: dict | None,
                        ack: str) -> int:
    """Material buttons; a camera suggestion only reorders and marks them, the collector decides."""
    lang = _lang(context)
    await _say(update, ack, ReplyKeyboardRemove())  # also hides the Skip photo button
    await _say(update, msg.cv_prompt(suggestion, lang), _material_keyboard(context, suggestion))
    return MATERIAL


def _material_keyboard(context: ContextTypes.DEFAULT_TYPE, suggestion: dict | None) -> InlineKeyboardMarkup:
    lang = _lang(context)
    materials = list(context.user_data["materials"].values())
    buttons = [InlineKeyboardButton(msg.material_button(m, suggested, lang), callback_data=f"mat:{m['id']}")
               for m, suggested in msg.ordered_materials(materials, suggestion)]
    return InlineKeyboardMarkup([buttons[i:i + 2] for i in range(0, len(buttons), 2)])


# ---------- unexpected messages: ask again instead of staying silent ----------
# If a reply was lost on a bad network, or the collector sends something the current
# step does not expect, they get the question and its buttons again.

async def again_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _say(update, msg.choose_language(), language_picker("lang"))
    return LANG


async def again_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _say(update, msg.bad_name(_lang(context)))
    return NAME


async def again_area(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _say(update, msg.t("bad_area", _lang(context)))
    return AREA


async def again_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    skip = ReplyKeyboardMarkup([[msg.button("skip_photo", lang)]], resize_keyboard=True)
    await _say(update, msg.ask_photo(lang), skip)
    return PHOTO


async def again_material(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lot = context.user_data.get("lot", {})
    suggestion = None
    if lot.get("cv_suggested"):
        conf = lot.get("cv_confidence") or 0.0
        suggestion = {"label": lot["cv_suggested"], "confidence": conf, "confident": conf >= CONFIDENT,
                      "categories": LABEL_TO_CATEGORIES.get(lot["cv_suggested"], [])}
    await _say(update, msg.t("tap_material", _lang(context)), _material_keyboard(context, suggestion))
    return MATERIAL


async def again_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _say(update, msg.bad_weight(_lang(context)))
    return WEIGHT


async def again_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _ask_location(update, _lang(context))


async def got_material(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    q = update.callback_query
    await _send(q.answer, "button ack")
    m = context.user_data.get("materials", {}).get(int(q.data.split(":", 1)[1]))
    if m is None:
        await _edit(update, msg.t("list_outdated", lang))
        return END
    context.user_data.setdefault("lot", {})["material_id"] = m["id"]
    await _edit(update, msg.ask_weight(m, lang))
    return WEIGHT


async def got_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    w = msg.parse_weight(update.message.text)
    if w is None:
        await _say(update, msg.bad_weight(lang))
        return WEIGHT
    context.user_data["lot"]["weight_kg"] = w
    return await _ask_location(update, lang)


async def _ask_location(update: Update, lang: str) -> int:
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(msg.button("share_location", lang), request_location=True)],
         [msg.button("skip_location", lang)]],
        resize_keyboard=True, one_time_keyboard=True)
    await _say(update, msg.ask_location(lang), keyboard)
    return LOCATION


async def got_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    loc = update.message.location
    context.user_data["lot"].update(gps_lat=loc.latitude, gps_lon=loc.longitude)
    return await _finish(update, context)


async def skip_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _finish(update, context)


async def _finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ud = context.user_data
    lang = _lang(context)
    lot = ud.pop("lot", {})
    try:
        tx = await _call(_api(context).log_lot, collector_id=ud["collector_id"], **lot)
    except UnknownCollector as e:
        _reset_keeping_language(ud)
        await _say(update, msg.api_error(e, lang), ReplyKeyboardRemove())
        return END
    except ApiError as e:
        await _say(update, f"{msg.api_error(e, lang)}\n{msg.t('lot_not_saved', lang)}", menu(lang))
        return END
    await _say(update, msg.receipt(tx, lang), menu(lang))
    return END


# ---------- always available ----------

async def prices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _lang(context)
    try:
        await _say(update, msg.prices(await _call(_api(context).materials), lang), menu(lang))
    except ApiError as e:
        await _say(update, msg.api_error(e, lang))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _say(update, msg.help_text(_lang(context)))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = _lang(context)
    context.user_data.pop("lot", None)
    context.user_data.pop("pending_name", None)
    await _say(update, msg.cancelled(lang), menu(lang) if context.user_data.get("collector_id") else None)
    return END


async def language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/language: switch between Hindi and English. Also ends any half-finished step."""
    context.user_data.pop("lot", None)
    await _say(update, msg.choose_language(), language_picker("setlang"))
    return END


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await _send(q.answer, "button ack")
    lang = q.data.split(":", 1)[1]
    context.user_data["lang"] = lang
    await _edit(update, msg.t("language_set", lang))
    if context.user_data.get("collector_id"):
        await _say(update, msg.welcome_back(context.user_data["name"], context.user_data["code"], lang), menu(lang))
    else:
        await _say(update, msg.need_registration(lang))


async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask before erasing. Also ends any half-finished step."""
    ud = context.user_data
    lang = _lang(context)
    ud.pop("lot", None)
    ud.pop("pending_name", None)
    if not ud.get("collector_id"):
        await _say(update, msg.nothing_to_forget(lang), ReplyKeyboardRemove())
        return END
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton(msg.button("forget_yes", lang), callback_data="forget:yes"),
        InlineKeyboardButton(msg.button("forget_no", lang), callback_data="forget:no"),
    ]])
    await _say(update, msg.forget_confirm(ud["name"], ud["code"], lang), buttons)
    return END


async def forget_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await _send(q.answer, "button ack")
    ud = context.user_data
    lang = _lang(context)
    if q.data != "forget:yes":
        await _edit(update, msg.forget_kept(lang))
        return
    if not ud.get("collector_id"):
        await _edit(update, msg.nothing_to_forget(lang))
        return
    try:
        result = await _call(_api(context).forget, ud["collector_id"])
    except ApiError as e:
        await _edit(update, f"{msg.api_error(e, lang)}\n{msg.t('nothing_deleted_retry', lang)}")
        return
    _reset_keeping_language(ud)
    await _edit(update, msg.forgotten(result["lots_kept"] if result else 0, lang))
    await _say(update, msg.register_again(lang), ReplyKeyboardRemove())


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled error", exc_info=context.error)
    if isinstance(context.error, NetworkError) and not isinstance(context.error, BadRequest):
        return  # replying would hit the same network problem
    if isinstance(update, Update) and update.effective_message:
        await _say(update, msg.t("something_wrong", _lang(context)))


# ---------- wiring ----------

def build_conversation() -> ConversationHandler:
    text = filters.TEXT & ~filters.COMMAND
    # anything that is not a command and not the log/prices menu buttons (those restart or show prices)
    other = (~filters.COMMAND & ~filters.Regex(button_pattern("log"))
             & ~filters.Regex(button_pattern("prices")) & ~filters.Regex(r"(?i)^\s*log\s*$"))
    log_entry = [CommandHandler("log", log_start),
                 MessageHandler(filters.Regex(button_pattern("log")) | filters.Regex(r"(?i)^\s*log\s*$"),
                                log_start)]
    with warnings.catch_warnings():  # per_message=False with a CallbackQueryHandler is intended here
        warnings.simplefilter("ignore", PTBUserWarning)
        return ConversationHandler(
            entry_points=[CommandHandler("start", start), *log_entry],
            # In every step, anything unexpected (last handler) gets the question again.
            states={
                LANG: [CallbackQueryHandler(got_language, pattern=r"^lang:(hi|en)$"),
                       MessageHandler(other, again_language)],
                NAME: [MessageHandler(text, got_name), MessageHandler(other, again_name)],
                AREA: [MessageHandler(text, got_area), MessageHandler(other, again_area)],
                MATERIAL: [CallbackQueryHandler(got_material, pattern=r"^mat:\d+$"),
                           MessageHandler(other, again_material)],
                WEIGHT: [MessageHandler(text, got_weight), MessageHandler(other, again_weight)],
                PHOTO: [MessageHandler(filters.PHOTO, got_photo),
                        MessageHandler(filters.Regex(button_pattern("skip_photo")), skip_photo),
                        MessageHandler(other, again_photo)],
                LOCATION: [MessageHandler(filters.LOCATION, got_location),
                           MessageHandler(filters.Regex(button_pattern("skip_location")), skip_location),
                           MessageHandler(other, again_location)],
            },
            fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start),
                       CommandHandler("forget", forget), CommandHandler("language", language), *log_entry],
            name="mitra",
            persistent=True,
            allow_reentry=True,
        )


COMMANDS = {
    "en": [
        BotCommand("start", "Register, or see your Collector ID"),
        BotCommand("log", "Record material you collected"),
        BotCommand("prices", "Today's reference prices"),
        BotCommand("language", "हिंदी / English"),
        BotCommand("cancel", "Stop the current step"),
        BotCommand("forget", "Delete your name and details"),
        BotCommand("help", "What I can do"),
    ],
    "hi": [
        BotCommand("start", "पंजीकरण करें या अपनी आईडी देखें"),
        BotCommand("log", "इकट्ठा किया माल दर्ज करें"),
        BotCommand("prices", "आज के संदर्भ भाव"),
        BotCommand("language", "भाषा बदलें / English"),
        BotCommand("cancel", "अभी का काम रोकें"),
        BotCommand("forget", "अपना नाम और जानकारी हटाएँ"),
        BotCommand("help", "मदद"),
    ],
}


async def _post_init(app: Application) -> None:
    """Command menu shown when a collector types '/': Hindi for phones set to Hindi."""
    await _send(lambda: app.bot.set_my_commands(COMMANDS["en"]), "set commands")
    await _send(lambda: app.bot.set_my_commands(COMMANDS["hi"], language_code="hi"), "set hindi commands")


def build_persistence(state_file: Path = STATE_FILE) -> PicklePersistence:
    # Persist only per-user registration and conversation state. bot_data holds the live
    # API client: loading it from disk would replace it, and it cannot be pickled anyway.
    return PicklePersistence(filepath=state_file,
                             store_data=PersistenceInput(bot_data=False, chat_data=False, callback_data=False))


def build_application(token: str, api: MitraClient, state_file: Path = STATE_FILE) -> Application:
    # IPv4-only connections, generous timeouts: Telegram can take 1-2 s per request on some networks
    app = (Application.builder().token(token).persistence(build_persistence(state_file))
           .request(IPv4Request(connect_timeout=15, read_timeout=20, write_timeout=20, pool_timeout=10))
           .get_updates_request(IPv4Request(connect_timeout=15, read_timeout=30, write_timeout=20,
                                            pool_timeout=10))
           .post_init(_post_init)
           .build())
    app.bot_data["api"] = api
    app.add_handler(build_conversation())
    app.add_handler(CommandHandler("prices", prices))
    app.add_handler(MessageHandler(filters.Regex(button_pattern("prices")), prices))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("forget", forget))
    app.add_handler(CommandHandler("language", language))
    app.add_handler(CallbackQueryHandler(forget_answer, pattern=r"^forget:(yes|no)$"))
    app.add_handler(CallbackQueryHandler(set_language, pattern=r"^setlang:(hi|en)$"))
    app.add_error_handler(on_error)
    return app


def _token() -> str | None:
    return env_value("TELEGRAM_TOKEN")


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
    # bootstrap_retries=-1: keep retrying the first contact with Telegram instead of exiting
    # on one network blip at startup (the default gives up after a single failure)
    build_application(token, api).run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=-1)


if __name__ == "__main__":
    main()
