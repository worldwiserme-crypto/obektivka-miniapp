import asyncio
import json
import logging
import os
import subprocess

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

logging.basicConfig(level=logging.INFO)

BOT_TOKEN   = os.getenv("BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "")   # Mini App URL si

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📋 Obektivkani to'ldirish",
            web_app=WebAppInfo(url=MINI_APP_URL)
        )
    ]])
    await message.answer(
        "👋 Assalomu alaykum!\n\n"
        "Bu bot sizga rasmiy <b>Ma'lumotnoma (Obektivka)</b> "
        "hujjatini avtomatik yaratib beradi.\n\n"
        "Quyidagi tugmani bosib formani to'ldiring 👇",
        reply_markup=kb
    )


@dp.message(F.web_app_data)
async def handle_form(message: Message):
    await message.answer("⏳ Hujjat tayyorlanmoqda...")

    try:
        data = json.loads(message.web_app_data.data)
    except Exception:
        await message.answer("❌ Xatolik: ma'lumot noto'g'ri keldi.")
        return

    # JSON faylga yozish
    os.makedirs("/tmp/obektivka", exist_ok=True)
    uid       = message.from_user.id
    json_path = f"/tmp/obektivka/{uid}.json"
    docx_path = f"/tmp/obektivka/{uid}.docx"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    # Node.js generator chaqirish
    result = subprocess.run(
        ["node", "generate_obektivka.js", json_path, docx_path],
        capture_output=True, text=True, timeout=30
    )

    if result.returncode != 0 or not os.path.exists(docx_path):
        logging.error(f"Generator xato: {result.stderr}")
        await message.answer("❌ Hujjat yaratishda xatolik yuz berdi. Qayta urining.")
        return

    # Faylni yuborish
    fullname = data.get("fullname", "obektivka")
    with open(docx_path, "rb") as f:
        await message.answer_document(
            document=(f"{fullname}.docx", f.read()),
            caption="✅ <b>Obektivkangiz tayyor!</b>\n\n📎 Word (.docx) formatida.\n🖨 Chop etib ishlating."
        )

    # Temp fayllarni tozalash
    os.remove(json_path)
    os.remove(docx_path)


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
