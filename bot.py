import asyncio
import json
import logging
import os
import subprocess
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

logging.basicConfig(level=logging.INFO)

BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")
PORT         = int(os.getenv("PORT", 8080))
MINI_APP_URL = f"{WEBHOOK_HOST}/app"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher()


async def serve_miniapp(request):
    """Mini App HTML sahifasini beradi — URL da tg_id ni qo'shadi"""
    tg_id = request.rel_url.query.get("tg_id", "")
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()
    # tg_id ni JS ga uzatish
    content = content.replace(
        "const TG_ID = null;",
        f"const TG_ID = '{tg_id}';"
    )
    return web.Response(text=content, content_type="text/html")


async def receive_form(request):
    """Mini App dan JSON keladi — hujjat yaratib yuboradi"""
    try:
        body = await request.json()
        tg_id = int(body.get("tg_id", 0))
        data  = body.get("data", {})

        if not tg_id:
            return web.json_response({"ok": False, "error": "no tg_id"})

        await bot.send_message(tg_id, "⏳ Hujjat tayyorlanmoqda...")

        os.makedirs("/tmp/obektivka", exist_ok=True)
        json_path = f"/tmp/obektivka/{tg_id}.json"
        docx_path = f"/tmp/obektivka/{tg_id}.docx"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        result = subprocess.run(
            ["node", "generate_obektivka.js", json_path, docx_path],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0 or not os.path.exists(docx_path):
            logging.error(f"Generator xato: {result.stderr}")
            await bot.send_message(tg_id, "❌ Xatolik yuz berdi. Qayta urining.")
            return web.json_response({"ok": False})

        fullname = data.get("fullname", "obektivka")
        with open(docx_path, "rb") as f:
            await bot.send_document(
                tg_id,
                document=(f"{fullname}.docx", f.read()),
                caption="✅ <b>Obektivkangiz tayyor!</b>\n\n📎 Word (.docx) formatida.\n🖨 Chop etib ishlating."
            )

        os.remove(json_path)
        os.remove(docx_path)
        return web.json_response({"ok": True})

    except Exception as e:
        logging.error(f"receive_form xato: {e}")
        return web.json_response({"ok": False, "error": str(e)})


@dp.message(CommandStart())
async def cmd_start(message: Message):
    tg_id = message.from_user.id
    url   = f"{MINI_APP_URL}?tg_id={tg_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📋 Obektivkani to'ldirish",
            web_app=WebAppInfo(url=url)
        )
    ]])
    await message.answer(
        "👋 Assalomu alaykum!\n\n"
        "Bu bot sizga rasmiy <b>Ma'lumotnoma (Obektivka)</b> "
        "hujjatini avtomatik yaratib beradi.\n\n"
        "Quyidagi tugmani bosib formani to'ldiring 👇",
        reply_markup=kb
    )


async def main():
    app = web.Application()
    app.router.add_get("/app", serve_miniapp)
    app.router.add_post("/submit", receive_form)

    await bot.set_webhook(f"{WEBHOOK_HOST}/webhook")
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logging.info(f"Bot ishlamoqda. Mini App: {MINI_APP_URL}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
