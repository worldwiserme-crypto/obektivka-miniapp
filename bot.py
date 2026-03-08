import asyncio
import json
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, BufferedInputFile
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from generator import generate

logging.basicConfig(level=logging.INFO)

BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")
PORT         = int(os.getenv("PORT", 8080))

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher()

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")


async def serve_app(request):
    tg_id = request.rel_url.query.get("tg_id", "")
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__TG_ID__", str(tg_id))
    return web.Response(text=html, content_type="text/html")


async def submit(request):
    tg_id = 0
    try:
        body  = await request.json()
        tg_id = int(body.get("tg_id", 0))
        data  = body.get("data", {})

        logging.info(f"Submit keldi: tg_id={tg_id}, fullname={data.get('fullname')}")

        if not tg_id:
            return web.json_response({"ok": False, "error": "tg_id yo'q"})

        await bot.send_message(tg_id, "⏳ Hujjat tayyorlanmoqda...")

        os.makedirs("/tmp/obj", exist_ok=True)
        docx_path = f"/tmp/obj/{tg_id}.docx"

        generate(data, docx_path)
        logging.info(f"Hujjat yaratildi: {docx_path}")

        fullname = data.get("fullname", "obektivka")
        with open(docx_path, "rb") as f:
            file_data = f.read()
        await bot.send_document(
            tg_id,
            document=BufferedInputFile(file_data, filename=f"{fullname}.docx"),
            caption="✅ <b>Obektivkangiz tayyor!</b>\n📎 Word (.docx) formatida."
        )

        os.remove(docx_path)
        return web.json_response({"ok": True})

    except Exception as e:
        logging.error(f"Xato: {e}", exc_info=True)
        if tg_id:
            try:
                await bot.send_message(tg_id, f"❌ Xatolik yuz berdi:\n{str(e)[:300]}")
            except Exception:
                pass
        return web.json_response({"ok": False, "error": str(e)})


@dp.message(CommandStart())
async def start(message: Message):
    tg_id = message.from_user.id
    url = f"{WEBHOOK_HOST}/app?tg_id={tg_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📋 Obektivkani to'ldirish",
            web_app=WebAppInfo(url=url)
        )
    ]])
    await message.answer(
        "👋 Assalomu alaykum!\n\n"
        "Bu bot rasmiy <b>Ma'lumotnoma (Obektivka)</b> hujjatini yaratib beradi.\n\n"
        "Quyidagi tugmani bosing 👇",
        reply_markup=kb
    )


async def main():
    app = web.Application()
    app.router.add_get("/app", serve_app)
    app.router.add_post("/submit", submit)

    await bot.set_webhook(f"{WEBHOOK_HOST}/webhook")
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logging.info(f"Bot ishlamoqda: {WEBHOOK_HOST}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
