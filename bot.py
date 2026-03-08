import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "").strip().rstrip("/")
PORT = int(os.getenv("PORT", "8080"))
TMP_DIR = Path("/tmp/obektivka")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")
if not WEBHOOK_HOST.startswith("https://"):
    raise RuntimeError("WEBHOOK_HOST must start with https://")


BASE_DIR = Path(__file__).resolve().parent
INDEX_CANDIDATES = [
    BASE_DIR / "index.html",
    BASE_DIR / "app" / "index.html",
]
GENERATOR_CANDIDATES = [
    BASE_DIR / "generate_obektivka.js",
    BASE_DIR / "app" / "generate_obektivka.js",
]


def resolve_existing_file(candidates: list[Path], relative_name: str) -> Path:
    for path in candidates:
        if path.is_file():
            return path
    fallback = (BASE_DIR / relative_name).resolve()
    if fallback.is_file() and str(fallback).startswith(str(BASE_DIR)):
        return fallback
    raise FileNotFoundError(f"Required file not found: {relative_name}")


INDEX_PATH = resolve_existing_file(INDEX_CANDIDATES, "index.html")
GENERATOR_PATH = resolve_existing_file(GENERATOR_CANDIDATES, "generate_obektivka.js")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


@dp.message(CommandStart())
async def on_start(message: Message) -> None:
    tg_id = message.from_user.id
    app_url = f"{WEBHOOK_HOST}/app?tg_id={tg_id}"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Obektivkani to'ldirish",
                    web_app=WebAppInfo(url=app_url),
                )
            ]
        ]
    )
    await message.answer(
        "Assalomu alaykum. Rasmiy MA'LUMOTNOMA (obektivka) tayyorlash uchun formani to'ldiring.",
        reply_markup=keyboard,
    )


async def serve_app(request: web.Request) -> web.Response:
    tg_id = request.query.get("tg_id", "")
    if not tg_id.isdigit():
        return web.Response(status=400, text="Invalid tg_id")

    html = INDEX_PATH.read_text(encoding="utf-8")
    html = html.replace("const TG_ID = null", f"const TG_ID = {int(tg_id)}")
    return web.Response(text=html, content_type="text/html")


async def submit_handler(request: web.Request) -> web.Response:
    payload: dict[str, Any] = await request.json()
    tg_id_raw = payload.get("tg_id")
    form_data = payload.get("data")

    if not isinstance(tg_id_raw, int) or tg_id_raw <= 0:
        return web.json_response({"ok": False, "error": "tg_id must be positive integer"}, status=400)
    if not isinstance(form_data, dict):
        return web.json_response({"ok": False, "error": "data must be object"}, status=400)

    tg_id = tg_id_raw
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    json_path = None
    docx_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", prefix=f"{tg_id}_", dir=TMP_DIR, delete=False, encoding="utf-8") as in_file:
            json.dump(form_data, in_file, ensure_ascii=False)
            json_path = Path(in_file.name)

        docx_path = TMP_DIR / f"{json_path.stem}.docx"

        process = await asyncio.create_subprocess_exec(
            "node",
            str(GENERATOR_PATH),
            str(json_path),
            str(docx_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

        if process.returncode != 0 or not docx_path.exists():
            logger.error("Generator failed: stdout=%s stderr=%s", stdout.decode(), stderr.decode())
            await bot.send_message(tg_id, "❌ Hujjat yaratishda xatolik yuz berdi.")
            return web.json_response({"ok": False, "error": "generation failed"}, status=500)

        filename = f"obektivka_{tg_id}.docx"
        await bot.send_document(
            chat_id=tg_id,
            document=FSInputFile(path=docx_path, filename=filename),
            caption="✅ MA'LUMOTNOMA tayyorlandi.",
        )

        return web.json_response({"ok": True})
    except asyncio.TimeoutError:
        logger.exception("Generator timeout")
        await bot.send_message(tg_id, "❌ Hujjat yaratish vaqti tugadi.")
        return web.json_response({"ok": False, "error": "generation timeout"}, status=504)
    except Exception:
        logger.exception("Submit handler error")
        return web.json_response({"ok": False, "error": "internal error"}, status=500)
    finally:
        for file_path in (json_path, docx_path):
            if file_path and Path(file_path).exists():
                try:
                    Path(file_path).unlink()
                except OSError:
                    logger.warning("Failed to remove temporary file: %s", file_path)


async def on_startup(_: web.Application) -> None:
    webhook_url = f"{WEBHOOK_HOST}/webhook"
    await bot.set_webhook(webhook_url)
    logger.info("Webhook set: %s", webhook_url)


async def on_shutdown(_: web.Application) -> None:
    await bot.session.close()


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/app", serve_app)
    app.router.add_post("/submit", submit_handler)

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=PORT)
