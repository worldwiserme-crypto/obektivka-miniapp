import asyncio
import logging
import os
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.types.input_file import FSInputFile
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from generator import generate

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "").strip().rstrip("/")
PORT = int(os.getenv("PORT", "8080"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env yo'q. Masalan: export BOT_TOKEN=123:ABC")
if not WEBHOOK_HOST:
    raise RuntimeError("WEBHOOK_HOST env yo'q. Masalan: https://your-domain.com")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


async def serve_app(request: web.Request):
    tg_id = request.rel_url.query.get("tg_id", "")
    html_path = os.path.join(BASE_DIR, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__TG_ID__", str(tg_id))
    return web.Response(text=html, content_type="text/html")


async def submit(request: web.Request):
    body = {}
    try:
        body = await request.json()
        tg_id = int(body.get("tg_id", 0))
        data = body.get("data", {})

        if not tg_id:
            return web.json_response({"ok": False, "error": "tg_id yo'q"})

        await bot.send_message(tg_id, "⏳ Hujjat tayyorlanmoqda...")

        os.makedirs("/tmp/obj", exist_ok=True)
        docx_path = f"/tmp/obj/{tg_id}.docx"

        generate(data, docx_path)

        fullname = (data.get("fullname") or "obektivka").strip()
        safe_name = "".join(ch for ch in fullname if ch.isalnum() or ch in (" ", "_", "-")).strip() or "obektivka"
        out_name = f"{safe_name}.docx"

        await bot.send_document(
            tg_id,
            document=FSInputFile(docx_path, filename=out_name),
            caption="✅ <b>Obektivkangiz tayyor!</b>\n\n📎 Word (.docx) formatida.\n🖨 Chop etib ishlating."
        )

        try:
            os.remove(docx_path)
        except:
            pass

        return web.json_response({"ok": True})

    except Exception as e:
        logging.error(f"submit xato: {e}", exc_info=True)
        try:
            bad_id = int(body.get("tg_id", 0) or 0)
            if bad_id:
                await bot.send_message(bad_id, f"❌ Xatolik: {str(e)[:300]}")
        except:
            pass
        return web.json_response({"ok": False, "error": str(e)})


@dp.message(CommandStart())
async def start(message: Message):
    tg_id = message.from_user.id
    url = f"{WEBHOOK_HOST}/app?tg_id={tg_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📋 Obektivkani to'ldirish", web_app=WebAppInfo(url=url))
    ]])
    await message.answer(
        "👋 Assalomu alaykum!\n\n"
        "Bu bot rasmiy <b>Ma'lumotnoma (Obektivka)</b> hujjatini yaratib beradi.\n\n"
        "Quyidagi tugmani bosing 👇",
        reply_markup=kb
    )


async def main():
    app = web.Application()

    # WebApp routes
    app.router.add_get("/app", serve_app)
    app.router.add_post("/submit", submit)

    # Webhook routes
    await bot.set_webhook(f"{WEBHOOK_HOST}/webhook")
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logging.info(f"Ishlamoqda: {WEBHOOK_HOST} (port={PORT})")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
