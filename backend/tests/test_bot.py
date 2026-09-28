"""Bot tests without Telegram or network: pure message text, the API client over
TestClient, and the real conversation handlers driven by fake Telegram objects."""
import asyncio
import hashlib
import re
from types import SimpleNamespace

import httpx
import pytest

from app.bot import messages as msg
from app.bot import telegram_bot as bot
from app.bot.client import UNREACHABLE, ApiError, MitraClient, UnknownCollector
from app.bot.offline_demo import run as run_offline_demo
from app.engine import loaders

# ---------- messages ----------


@pytest.mark.parametrize("value,expected", [
    (0, "₹0"), (999, "₹999"), (1000, "₹1,000"), (123456.5, "₹1,23,456.50"),
    (12345678, "₹1,23,45,678"), (1200.0, "₹1,200"),
])
def test_inr_indian_grouping(value, expected):
    assert msg.inr(value) == expected


@pytest.mark.parametrize("text,expected", [
    ("12", 12.0), ("12.5", 12.5), ("12,5", 12.5), (" 3.5 kg ", 3.5), ("7 किलो", 7.0),
    ("0", None), ("-3", None), ("abc", None), ("", None), ("2001", None), ("1e3", None),
])
def test_parse_weight(text, expected):
    assert msg.parse_weight(text) == expected


def test_receipt_and_escaping():
    tx = {"passport_id": "MITRA-P-000401", "material": "Copper", "weight_kg": 3.0,
          "ref_price_per_kg": 400.0, "ref_amount": 1200.0, "gps_lat": 26.9}
    text = msg.receipt(tx)
    assert "MITRA-P-000401" in text and "₹400/kg" in text and "₹1,200" in text and "map" in text
    assert "not appear on the map" in msg.receipt({**tx, "gps_lat": None})
    assert "&lt;b&gt;" in msg.ask_area("<b>x</b>")  # user text cannot inject HTML


def test_short_material_names():
    assert msg.short_name("Metal (steel/aluminium blended)") == "Metal"
    assert msg.material_button({"name": "Copper", "ref_price_per_kg": 400.0}) == "Copper · ₹400/kg"


# ---------- API client ----------


def test_client_register_and_log(client):
    api = MitraClient(client=client)
    c = api.register("Asha Devi", "Sanganer")
    assert c["code"] == "MITRA-C-000041"
    copper = next(m for m in api.materials() if m["name"] == "Copper")
    tx = api.log_lot(c["id"], copper["id"], 2.0, 26.82, 75.79)
    assert tx["ref_amount"] == 800.0 and tx["collector_name"] == "Asha Devi"
    assert api.collector(c["id"])["lots"] == 1
    assert api.collector(99999) is None


def test_client_errors(client):
    api = MitraClient(client=client)
    with pytest.raises(UnknownCollector):
        api.log_lot(99999, 1, 1.0)
    with pytest.raises(ApiError, match="material_id"):
        api.log_lot(1, 999, 1.0)


def test_client_unreachable():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    api = MitraClient(client=httpx.Client(transport=httpx.MockTransport(refuse), base_url="http://x"))
    with pytest.raises(ApiError, match="not reachable"):
        api.materials()
    assert str(ApiError(UNREACHABLE)) == UNREACHABLE
    assert api.health() is False


# ---------- conversation handlers with fake Telegram objects ----------


class FakeMessage:
    def __init__(self, text=None, photo=None, location=None):
        self.text, self.photo, self.location = text, photo, location
        self.replies: list[str] = []

    async def reply_text(self, text, parse_mode=None, reply_markup=None):
        self.replies.append(text)


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.edits: list[str] = []

    async def answer(self):
        pass

    async def edit_message_text(self, text, parse_mode=None):
        self.edits.append(text)


class FakePhotoSize:
    def __init__(self, data: bytes):
        self.data = data

    async def get_file(self):
        return SimpleNamespace(download_as_bytearray=self._download)

    async def _download(self):
        return bytearray(self.data)


def update(text=None, photo=None, location=None, query=None):
    m = FakeMessage(text, photo, location)
    return SimpleNamespace(message=m, effective_message=m, callback_query=query), m


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def ctx(client):
    return SimpleNamespace(user_data={}, bot_data={"api": MitraClient(client=client)})


def choose_language(ctx, lang):
    q = FakeQuery(f"lang:{lang}")
    u, m = update()
    u.callback_query = q
    assert run(bot.got_language(u, ctx)) == bot.NAME
    return q, m


def register(ctx, name="Ravi Kumar", area="Sanganer", lang="en"):
    assert run(bot.start(update("/start")[0], ctx)) == bot.LANG  # new user picks a language first
    choose_language(ctx, lang)
    assert run(bot.got_name(update(name)[0], ctx)) == bot.AREA
    u, m = update(area)
    assert run(bot.got_area(u, ctx)) == bot.END
    return m.replies[-1]


def test_registration_flow(ctx):
    reply = register(ctx)
    assert "MITRA-C-000041" in reply
    assert ctx.user_data["collector_id"] == 41
    u, m = update("/start")
    assert run(bot.start(u, ctx)) == bot.END and "Welcome back" in m.replies[-1]


@pytest.fixture
def fake_cv(monkeypatch):
    """Stand-in classifier: no torch, no weights download, no network."""
    from app.classify import model as cv
    from app.classify.labels import suggestion

    state = {"probs": {"metal": 0.91, "glass": 0.04, "paper": 0.03, "plastic": 0.01, "trash": 0.01},
             "available": True}

    def classify(data: bytes) -> dict:
        if not state["available"]:
            raise cv.Unavailable("Photo classifier in development.")
        return suggestion(state["probs"])

    monkeypatch.setattr(cv, "classify", classify)
    return state


def test_log_flow_photo_suggestion_then_confirm(ctx, client, tmp_path, monkeypatch, fake_cv):
    monkeypatch.setattr(bot, "PHOTO_DIR", tmp_path / "photos")
    monkeypatch.setattr(loaders, "DATA_DIR", tmp_path)
    register(ctx)

    u, m = update("📦 Log material")
    assert run(bot.log_start(u, ctx)) == bot.PHOTO and "photo" in m.replies[-1]

    image = b"\xff\xd8fake-jpeg-bytes"
    u, m = update(photo=[FakePhotoSize(b"small"), FakePhotoSize(image)])
    assert run(bot.got_photo(u, ctx)) == bot.MATERIAL
    assert "metal" in m.replies[-1] and "91% sure" in m.replies[-1]
    assert ctx.user_data["lot"]["cv_suggested"] == "metal"

    # the suggestion only reorders the list; the collector picks Copper (a metal) to confirm
    copper_id = next(i for i, mat in ctx.user_data["materials"].items() if mat["name"] == "Copper")
    q = FakeQuery(f"mat:{copper_id}")
    assert run(bot.got_material(SimpleNamespace(callback_query=q), ctx)) == bot.WEIGHT
    assert "₹400/kg" in q.edits[-1]

    u, m = update("lots")  # not a number
    assert run(bot.got_weight(u, ctx)) == bot.WEIGHT and "number" in m.replies[-1]
    assert run(bot.got_weight(update("3,5 kg")[0], ctx)) == bot.LOCATION

    u, m = update(location=SimpleNamespace(latitude=26.9, longitude=75.83))
    assert run(bot.got_location(u, ctx)) == bot.END
    receipt = m.replies[-1]
    assert "MITRA-P-000401" in receipt and "₹1,400" in receipt and "on the MITRA map" in receipt
    assert "Camera suggested metal; you confirmed Copper" in receipt

    tx = client.get("/api/transactions", params={"collector_id": 41}).json()[0]
    assert (tx["material"], tx["weight_kg"], tx["gps_lat"]) == ("Copper", 3.5, 26.9)
    assert (tx["cv_suggested"], tx["cv_confidence"]) == ("metal", 0.91)
    passport = client.get(f"/api/passport/{tx['id']}").json()
    assert passport["photo_sha256"] == hashlib.sha256(image).hexdigest()
    assert passport["classification"] == {"confirmed_by": "collector", "cv_suggested": "metal", "cv_confidence": 0.91}


def test_collector_overrides_wrong_suggestion(ctx, client, tmp_path, monkeypatch, fake_cv):
    monkeypatch.setattr(bot, "PHOTO_DIR", tmp_path / "photos")
    register(ctx)
    run(bot.log_start(update("log")[0], ctx))
    run(bot.got_photo(update(photo=[FakePhotoSize(b"img")])[0], ctx))  # camera says metal
    glass_id = next(i for i, mat in ctx.user_data["materials"].items() if mat["category"] == "glass")
    run(bot.got_material(SimpleNamespace(callback_query=FakeQuery(f"mat:{glass_id}")), ctx))
    run(bot.got_weight(update("20")[0], ctx))
    u, m = update(bot.SKIP_LOCATION)
    run(bot.skip_location(u, ctx))
    assert "Camera suggested metal; you chose Glass" in m.replies[-1]
    assert client.get("/api/transactions", params={"collector_id": 41}).json()[0]["material"] == "Glass"


def test_photo_when_classifier_in_development(ctx, tmp_path, monkeypatch, fake_cv):
    monkeypatch.setattr(bot, "PHOTO_DIR", tmp_path / "photos")
    fake_cv["available"] = False
    register(ctx)
    run(bot.log_start(update("log")[0], ctx))
    u, m = update(photo=[FakePhotoSize(b"img")])
    assert run(bot.got_photo(u, ctx)) == bot.MATERIAL  # plain list, logging continues
    assert m.replies[-1] == msg.material_prompt()
    assert "cv_suggested" not in ctx.user_data["lot"]


def test_log_without_photo_or_location(ctx, client):
    register(ctx)
    assert run(bot.log_start(update("log")[0], ctx)) == bot.PHOTO
    u, m = update(bot.SKIP_PHOTO)
    assert run(bot.skip_photo(u, ctx)) == bot.MATERIAL and m.replies[-1] == msg.material_prompt()
    run(bot.got_material(SimpleNamespace(callback_query=FakeQuery("mat:1")), ctx))
    assert run(bot.got_weight(update("10")[0], ctx)) == bot.LOCATION
    u, m = update(bot.SKIP_LOCATION)
    assert run(bot.skip_location(u, ctx)) == bot.END
    assert "not appear on the map" in m.replies[-1]
    assert client.get("/api/transactions", params={"collector_id": 41}).json()[0]["gps_lat"] is None


def test_log_requires_registration(ctx):
    u, m = update("/log")
    assert run(bot.log_start(u, ctx)) == bot.END and "/start" in m.replies[-1]


def test_stale_registration_after_db_reset(ctx):
    ctx.user_data.update(collector_id=99999, name="Ghost", code="MITRA-C-099999", lang="hi")
    u, m = update("/start")
    assert run(bot.start(u, ctx)) == bot.NAME  # asks to register again, language remembered
    assert "collector_id" not in ctx.user_data and ctx.user_data["lang"] == "hi"
    assert "आपका नाम क्या है?" in m.replies[-1]


def test_api_down_is_reported_not_crashed():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    api = MitraClient(client=httpx.Client(transport=httpx.MockTransport(refuse), base_url="http://x"))
    ctx = SimpleNamespace(user_data={"collector_id": 1, "name": "A"}, bot_data={"api": api})
    u, m = update("/log")
    assert run(bot.log_start(u, ctx)) == bot.END
    assert "not reachable" in m.replies[-1]


def test_conversation_and_application_build():
    conv = bot.build_conversation()
    assert set(conv.states) == {bot.LANG, bot.NAME, bot.AREA, bot.MATERIAL, bot.WEIGHT, bot.PHOTO, bot.LOCATION}
    assert conv.persistent and conv.name == "mitra"


def test_offline_demo_runs_end_to_end(client, capsys, tmp_path, monkeypatch, fake_cv):
    from app.bot import offline_demo
    monkeypatch.setattr(offline_demo, "PHOTO_DIR", tmp_path / "photos")
    tx = run_offline_demo(MitraClient(client=client), pause=False)
    out = capsys.readouterr().out
    assert tx["material"] == "Copper" and tx["gps_lat"] is not None
    assert "Sunita Devi" in out and tx["passport_id"] in out and "₹1,400" in out
    assert "This looks like metal" in out and tx["cv_suggested"] == "metal"


# ---------- suggestion text and ordering (pure) ----------


def test_suggested_materials_come_first_and_all_stay_available():
    mats = [{"id": 1, "name": "PET plastic", "category": "pet", "ref_price_per_kg": 12},
            {"id": 2, "name": "HDPE", "category": "hdpe", "ref_price_per_kg": 14},
            {"id": 3, "name": "Glass", "category": "glass", "ref_price_per_kg": 2}]
    plastic = {"label": "plastic", "confidence": 0.8, "categories": ["pet", "hdpe"], "confident": True}
    ordered = msg.ordered_materials(mats, plastic)
    assert [(m["id"], s) for m, s in ordered] == [(1, True), (2, True), (3, False)]
    unsure = {**plastic, "confident": False}
    assert all(not s for _, s in msg.ordered_materials(mats, unsure))
    assert msg.material_button(mats[0], True).startswith("📷 ")


def test_cv_prompt_wording():
    base = {"alternatives": []}
    assert "not sure" in msg.cv_prompt({**base, "label": "metal", "confidence": 0.3, "categories": ["metal"], "confident": False})
    assert "non-recyclable" in msg.cv_prompt({**base, "label": "trash", "confidence": 0.9, "categories": [], "confident": True})
    assert "99% sure" in msg.cv_prompt({**base, "label": "metal", "confidence": 1.0, "categories": ["metal"], "confident": True})
    assert msg.cv_prompt(None) == msg.material_prompt()


def test_persistence_keeps_api_client_on_restart(tmp_path):
    """Regression: persisted bot_data used to overwrite bot_data["api"] at startup (KeyError: 'api')."""
    async def scenario():
        p = bot.build_persistence(tmp_path / "state.pickle")
        assert p.store_data.user_data and p.store_data.bot_data is False
        await p.update_user_data(7, {"collector_id": 41, "name": "Ravi", "code": "MITRA-C-000041"})
        await p.flush()
        # a fresh process: new persistence object reading the same file
        p2 = bot.build_persistence(tmp_path / "state.pickle")
        return await p2.get_user_data()

    assert run(scenario())[7]["collector_id"] == 41
    app = bot.build_application("123:ABC", MitraClient(base_url="http://x"), tmp_path / "s.pickle")
    assert isinstance(app.bot_data["api"], MitraClient)
    assert app.persistence.store_data.bot_data is False


class FlakyMessage(FakeMessage):
    """Drops the first `failures` sends, like a flaky mobile/ISP connection."""

    def __init__(self, text, failures):
        super().__init__(text)
        self.failures = failures

    async def reply_text(self, text, parse_mode=None, reply_markup=None):
        if self.failures > 0:
            self.failures -= 1
            from telegram.error import NetworkError
            raise NetworkError("httpx.ConnectError: ")
        await super().reply_text(text, parse_mode, reply_markup)


def flaky_update(text, failures):
    m = FlakyMessage(text, failures)
    return SimpleNamespace(message=m, effective_message=m, callback_query=None), m


def test_reply_retried_after_dropped_connection(ctx, monkeypatch):
    """Regression: a single dropped connection lost the 'which area?' reply and stalled signup."""
    monkeypatch.setattr(bot, "RETRY_DELAY_S", 0)
    run(bot.start(update("/start")[0], ctx))
    u, m = flaky_update("Ravi Kumar", failures=2)
    assert run(bot.got_name(u, ctx)) == bot.AREA
    assert "Which area" in m.replies[-1]


def test_conversation_advances_even_if_reply_never_arrives(ctx, monkeypatch):
    monkeypatch.setattr(bot, "RETRY_DELAY_S", 0)
    run(bot.start(update("/start")[0], ctx))
    u, m = flaky_update("Ravi Kumar", failures=99)
    assert run(bot.got_name(u, ctx)) == bot.AREA  # name kept; next message is taken as the area
    u, m = update("Sanganer")
    assert run(bot.got_area(u, ctx)) == bot.END and "MITRA-C-000041" in m.replies[-1]


def test_forget_flow_yes(ctx, client):
    register(ctx)
    u, m = update("/forget")
    assert run(bot.forget(u, ctx)) == bot.END and "Delete your data?" in m.replies[-1]
    q = FakeQuery("forget:yes")
    u2, m2 = update()
    u2.callback_query = q
    run(bot.forget_answer(u2, ctx))
    assert "deleted" in q.edits[-1] and "/start" in m2.replies[-1]
    assert ctx.user_data == {"lang": "en"}  # registration gone; language choice kept
    assert client.get("/api/collectors/41").json()["name"] == "Erased collector"


def test_forget_flow_no_and_unregistered(ctx, client):
    u, m = update("/forget")
    run(bot.forget(u, ctx))
    assert "not registered" in m.replies[-1]
    register(ctx)
    q = FakeQuery("forget:no")
    u2, _ = update()
    u2.callback_query = q
    run(bot.forget_answer(u2, ctx))
    assert "nothing was deleted" in q.edits[-1]
    assert ctx.user_data["collector_id"] == 41
    assert client.get("/api/collectors/41").json()["name"] == "Ravi Kumar"


def test_forget_mid_log_ends_the_step(ctx):
    register(ctx)
    run(bot.log_start(update("log")[0], ctx))
    assert "lot" in ctx.user_data
    run(bot.forget(update("/forget")[0], ctx))
    assert "lot" not in ctx.user_data


# ---------- Hindi ----------

DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def test_every_message_and_button_exists_in_both_languages():
    from app.classify.labels import LABELS
    for key, texts in msg._T.items():
        assert set(texts) == {"en", "hi"} and all(texts.values()), key
        assert DEVANAGARI.search(texts["hi"]), f"{key} has no Hindi"
    for key, labels in msg.BUTTONS.items():
        assert DEVANAGARI.search(labels["hi"]) and not DEVANAGARI.search(labels["en"]), key
    assert set(msg.LABEL_TEXT_HI) == set(LABELS)
    seeded = {"PET plastic", "HDPE", "Cardboard/paper", "Glass", "Metal (steel/aluminium blended)", "Copper", "E-waste"}
    assert seeded <= set(msg.MATERIAL_HI)


def test_hindi_formatting():
    copper = {"name": "Copper", "ref_price_per_kg": 400.0, "category": "metal"}
    assert msg.material_button(copper, lang="hi") == "तांबा · ₹400/किलो"
    assert msg.material_button(copper, True, lang="hi") == "📷 तांबा · ₹400/किलो"
    assert msg.parse_weight("3.5 किलो") == 3.5
    assert msg.material_name("Unknown thing", "hi") == "Unknown thing"  # falls back, never crashes
    assert msg.t("bad_name", "fr") == msg.t("bad_name", "en")  # unknown language -> English


def test_buttons_accept_both_languages():
    for key in ("log", "prices", "skip_photo", "skip_location"):
        for label in msg.all_labels(key):
            assert re.match(bot.button_pattern(key), label), (key, label)
    assert not re.match(bot.button_pattern("log"), "📦 Log material please")


def test_full_flow_in_hindi(ctx, client, tmp_path, monkeypatch, fake_cv):
    monkeypatch.setattr(bot, "PHOTO_DIR", tmp_path / "photos")
    run(bot.start(update("/start")[0], ctx))
    q, m = choose_language(ctx, "hi")
    assert "हिंदी" in q.edits[-1] and "आपका नाम क्या है?" in m.replies[-1]
    u, m = update("सुनीता देवी")
    run(bot.got_name(u, ctx))
    assert "आप किस इलाके में काम करते हैं?" in m.replies[-1]
    u, m = update("राजा पार्क")
    run(bot.got_area(u, ctx))
    assert "आपका पंजीकरण हो गया" in m.replies[-1] and "MITRA-C-000041" in m.replies[-1]

    u, m = update("📦 माल दर्ज करें")
    assert run(bot.log_start(u, ctx)) == bot.PHOTO and "माल की फोटो भेजें" in m.replies[-1]
    u, m = update(photo=[FakePhotoSize(b"img")])
    run(bot.got_photo(u, ctx))
    assert "यह <b>धातु</b> लगता है (91% भरोसा)" in m.replies[-1]
    copper_id = next(i for i, mat in ctx.user_data["materials"].items() if mat["name"] == "Copper")
    q = FakeQuery(f"mat:{copper_id}")
    run(bot.got_material(SimpleNamespace(callback_query=q), ctx))
    assert "तांबा" in q.edits[-1] and "₹400/किलो" in q.edits[-1] and "कितने किलो" in q.edits[-1]
    u, m = update("abc")
    run(bot.got_weight(u, ctx))
    assert "कृपया वज़न" in m.replies[-1]
    assert run(bot.got_weight(update("3.5 किलो")[0], ctx)) == bot.LOCATION
    u, m = update(location=SimpleNamespace(latitude=26.9, longitude=75.83))
    run(bot.got_location(u, ctx))
    receipt = m.replies[-1]
    for part in ("माल दर्ज हो गया", "पासपोर्ट MITRA-P-000401", "तांबा · 3.5 किलो", "₹400/किलो",
                 "सही कीमत: <b>₹1,400</b>", "कैमरे का सुझाव: धातु; आपने पुष्टि की: तांबा", "नक्शे पर"):
        assert part in receipt, part
    # the database keeps canonical English material names; only the chat is translated
    assert client.get("/api/transactions", params={"collector_id": 41}).json()[0]["material"] == "Copper"


def test_switch_language_any_time(ctx):
    register(ctx, lang="en")
    u, m = update("/language")
    assert run(bot.language(u, ctx)) == bot.END and "अपनी भाषा चुनें" in m.replies[-1]
    q = FakeQuery("setlang:hi")
    u, m = update()
    u.callback_query = q
    run(bot.set_language(u, ctx))
    assert ctx.user_data["lang"] == "hi"
    assert "फिर से स्वागत है" in m.replies[-1]
    u, m = update("/prices")
    run(bot.prices(u, ctx))
    assert "आज के संदर्भ भाव" in m.replies[-1] and "तांबा: <b>₹400/किलो</b>" in m.replies[-1]
    u, m = update("/help")
    run(bot.help_cmd(u, ctx))
    assert "/language" in m.replies[-1] and "भाषा बदलें" in m.replies[-1]


def test_errors_and_forget_in_hindi(ctx, client):
    register(ctx, lang="hi")
    u, m = update("/forget")
    run(bot.forget(u, ctx))
    assert "क्या आप अपना डेटा हटाना चाहते हैं?" in m.replies[-1]
    q = FakeQuery("forget:yes")
    u2, m2 = update()
    u2.callback_query = q
    run(bot.forget_answer(u2, ctx))
    assert "आपका नाम और जानकारी हटा दी गई है" in q.edits[-1] and "/start" in m2.replies[-1]
    assert ctx.user_data == {"lang": "hi"}


def test_api_down_message_in_hindi():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    api = MitraClient(client=httpx.Client(transport=httpx.MockTransport(refuse), base_url="http://x"))
    ctx = SimpleNamespace(user_data={"collector_id": 1, "name": "A", "lang": "hi"}, bot_data={"api": api})
    u, m = update("/log")
    run(bot.log_start(u, ctx))
    assert "MITRA सर्वर से अभी संपर्क नहीं हो पा रहा है" in m.replies[-1]


def test_offline_demo_in_hindi(client, capsys, tmp_path, monkeypatch, fake_cv):
    from app.bot import offline_demo
    monkeypatch.setattr(offline_demo, "PHOTO_DIR", tmp_path / "photos")
    tx = run_offline_demo(MitraClient(client=client), pause=False, lang="hi")
    out = capsys.readouterr().out
    assert "नमस्ते" in out and "माल दर्ज हो गया" in out and "₹1,400" in out and tx["material"] == "Copper"


# ---------- bad networks: IPv4 only, and never silent ----------


def test_telegram_requests_use_ipv4_only(monkeypatch):
    req = bot.IPv4Request()
    assert req._client._transport._pool._local_address == "0.0.0.0"  # binds IPv4: no broken IPv6 route
    monkeypatch.setenv("TELEGRAM_IPV6", "1")
    assert bot.IPv4Request()._client._transport is not req._client._transport
    assert getattr(bot.IPv4Request()._client._transport._pool, "_local_address", None) is None


def test_every_step_asks_again_instead_of_staying_silent():
    conv = bot.build_conversation()
    expected = {bot.LANG: bot.again_language, bot.NAME: bot.again_name, bot.AREA: bot.again_area,
                bot.MATERIAL: bot.again_material, bot.WEIGHT: bot.again_weight,
                bot.PHOTO: bot.again_photo, bot.LOCATION: bot.again_location}
    for state, handler in expected.items():
        assert conv.states[state][-1].callback is handler, state


def test_lost_location_question_is_asked_again(ctx):
    """Regression: the location question was lost on a bad network; the next message got no reply."""
    register(ctx, lang="hi")
    run(bot.log_start(update("log")[0], ctx))
    run(bot.skip_photo(update(bot.SKIP_PHOTO)[0], ctx))
    run(bot.got_material(SimpleNamespace(callback_query=FakeQuery("mat:1")), ctx))
    assert run(bot.got_weight(update("5")[0], ctx)) == bot.LOCATION
    u, m = update("hello?")  # collector never saw the question
    assert run(bot.again_location(u, ctx)) == bot.LOCATION
    assert "लोकेशन भेजें" in m.replies[-1]


def test_material_buttons_resent_with_camera_suggestion(ctx, tmp_path, monkeypatch, fake_cv):
    monkeypatch.setattr(bot, "PHOTO_DIR", tmp_path / "photos")
    register(ctx)
    run(bot.log_start(update("log")[0], ctx))
    run(bot.got_photo(update(photo=[FakePhotoSize(b"img")])[0], ctx))
    u, m = update("copper")  # typed instead of tapping
    assert run(bot.again_material(u, ctx)) == bot.MATERIAL
    assert "tap one of the material buttons" in m.replies[-1]
    assert ctx.user_data["lot"]["cv_suggested"] == "metal"  # suggestion kept for the re-sent buttons


def test_prices_button_still_works_mid_conversation():
    from datetime import datetime

    from telegram import Chat, Message, Update

    def tg(text):
        return Update(1, message=Message(1, datetime.now(), Chat(1, "private"), text=text))

    catch_all = bot.build_conversation().states[bot.LOCATION][-1]
    for label in msg.all_labels("prices") + msg.all_labels("log"):
        assert not catch_all.filters.check_update(tg(label)), label  # left to the prices / log handlers
    assert catch_all.filters.check_update(tg("hello?"))  # anything else gets the question again
