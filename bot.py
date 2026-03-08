import asyncio
import json
import logging
import os
import subprocess
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

logging.basicConfig(level=logging.INFO)

BOT_TOKEN    = os.getenv("BOT_TOKEN", "")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")  # https://xxxx.up.railway.app
PORT         = int(os.getenv("PORT", 8080))

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Node.js PATH ni to'g'irlash
os.environ["PATH"] = "/nix/var/nix/profiles/default/bin:/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", "")


def find_file(filename):
    paths = [
        os.path.join(BASE_DIR, filename),
        os.path.join("/app", filename),
        filename,
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


async def serve_app(request):
    tg_id = request.rel_url.query.get("tg_id", "")
    path = find_file("index.html")
    if not path:
        return web.Response(text="index.html topilmadi", status=500)
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__TG_ID__", str(tg_id))
    return web.Response(text=html, content_type="text/html")


async def submit(request):
    try:
        body  = await request.json()
        tg_id = int(body.get("tg_id", 0))
        data  = body.get("data", {})

        if not tg_id:
            return web.json_response({"ok": False, "error": "tg_id yo'q"})

        await bot.send_message(tg_id, "⏳ Hujjat tayyorlanmoqda...")

        os.makedirs("/tmp/obj", exist_ok=True)
        json_path = f"/tmp/obj/{tg_id}.json"
        docx_path = f"/tmp/obj/{tg_id}.docx"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        gen = find_file("generate_obektivka.js")
        if not gen:
            await bot.send_message(tg_id, "❌ Generator topilmadi.")
            return web.json_response({"ok": False})

        # node_modules ichidan docx topish
        node_mod = os.path.join(BASE_DIR, "node_modules", ".bin", "docx")
        # Node.js to'liq yo'lini topish
        node_bin = None
        for np in ["/usr/bin/node", "/usr/local/bin/node", "/nix/var/nix/profiles/default/bin/node"]:
            if os.path.exists(np):
                node_bin = np
                break
        if not node_bin:
            import shutil
            node_bin = shutil.which("node") or "node"
        logging.info(f"Node yo'li: {node_bin}")

        result = subprocess.run(
            [node_bin, gen, json_path, docx_path],
            capture_output=True, text=True, timeout=30,
            cwd=BASE_DIR,
            env={**os.environ, "NODE_PATH": os.path.join(BASE_DIR, "node_modules")}
        )

        if result.returncode != 0 or not os.path.exists(docx_path):
            logging.error(f"Generator xato:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
            await bot.send_message(tg_id, f"❌ Hujjat yaratishda xatolik.\n<code>{result.stderr[-200:]}</code>")
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
        logging.error(f"submit xato: {e}")
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
    # Diagnostika — qaysi fayllar bor
    import shutil
    logging.info(f"BASE_DIR: {BASE_DIR}")
    logging.info(f"FILES: {os.listdir(BASE_DIR)}")
    logging.info(f"node: {shutil.which('node')}")
    logging.info(f"NODE_PATH env: {os.environ.get('PATH', '')}")

    app = web.Application()
    app.router.add_get("/app", serve_app)
    app.router.add_post("/submit", submit)

    await bot.set_webhook(f"{WEBHOOK_HOST}/webhook")
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logging.info(f"Ishlamoqda: {WEBHOOK_HOST}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
