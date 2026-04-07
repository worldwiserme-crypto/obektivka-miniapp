"""
Obektivka Bot — WebApp Data Handler
F.web_app_data orqali kelgan ma'lumotlarni qayta ishlash.

Oqim:
  WebApp → F.web_app_data → JSON parse → User tekshirish →
  → Loading xabar → DOCX+Preview (to_thread) → Natija yuborish
"""

import asyncio
import json
import os
import logging
from datetime import datetime
from functools import partial

from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    BufferedInputFile,
    InputMediaPhoto,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ParseMode

from config import DOC_PRICE, TEMP_DIR, STARS_PER_DOC
from database import get_or_create_user, get_session
from generator import generate
from preview import _generate_preview_sync  # sinxron funksiya — to_thread uchun

logger = logging.getLogger(__name__)

webapp_router = Router(name="webapp_handler")


# ══════════════════════════════════════════════════════════════
#  BLOCKING TASK WRAPPER
# ══════════════════════════════════════════════════════════════

async def generate_doc_and_preview(data: dict, docx_path: str, script: str) -> list[bytes]:
    """
    DOCX yaratish + Preview rasmlar — og'ir jarayon.

    generator.generate() va preview sinxron (blocking) funksiyalar.
    asyncio.to_thread orqali alohida thread'da ishga tushadi,
    bot event loop QOTIB QOLMAYDI.

    Returns:
        Watermark qo'shilgan JPEG rasmlar ro'yxati (bytes[])

    Raises:
        Exception — fayl yaratish yoki convert qilishda xatolik
    """
    # 1) DOCX yaratish (blocking → thread)
    await asyncio.to_thread(generate, data, docx_path, script)

    # 2) DOCX → PDF → PNG + Watermark (blocking → thread)
    preview_images = await asyncio.to_thread(_generate_preview_sync, docx_path)

    return preview_images


# ══════════════════════════════════════════════════════════════
#  YORDAMCHI
# ══════════════════════════════════════════════════════════════

def price_text(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"


# Kutayotgan hujjatlar xotirasi (to'lov kutish uchun)
# Production: Redis ishlatish tavsiya qilinadi
_pending_docs: dict[int, dict] = {}


# ══════════════════════════════════════════════════════════════
#  WEBAPP DATA HANDLER
# ══════════════════════════════════════════════════════════════

@webapp_router.message(F.web_app_data)
async def handle_webapp_data(message: Message, bot: Bot):
    """
    WebApp'dan JSON ma'lumot kelganda ishga tushadi.

    UX oqimi:
      1. JSON parse + validatsiya
      2. Foydalanuvchini bazada tekshirish/yaratish
      3. "Tayyorlanmoqda..." loading xabari
      4. DOCX + Preview yaratish (alohida thread — bot qotmaydi)
      5. Loading xabarini o'chirish
      6. Preview rasm + to'lov tugmasi yuborish

    Xatolik bo'lsa → foydalanuvchiga chiroyli xabar, log'ga batafsil.
    """
    tg_id = message.from_user.id
    loading_msg = None

    try:
        # ─── 1-QADAM: JSON PARSE ───
        raw = message.web_app_data.data
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse xatosi: tg_id={tg_id}, error={e}")
            await message.answer(
                "❌ <b>Ma'lumotlar noto'g'ri formatda keldi.</b>\n"
                "Iltimos, formani qaytadan to'ldiring."
            )
            return

        data = payload.get("data", {})
        script = payload.get("script", "lat")

        if not data or not data.get("fullname"):
            await message.answer(
                "⚠️ <b>Ma'lumotlar to'liq emas.</b>\n"
                "Iltimos, kamida F.I.Sh. maydonini to'ldiring."
            )
            return

        logger.info(f"WebApp data: tg_id={tg_id}, fullname={data.get('fullname')}")

        # ─── 2-QADAM: FOYDALANUVCHINI TEKSHIRISH ───
        user = await get_or_create_user(
            tg_id=tg_id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        if not user:
            await message.answer(
                "❌ <b>Tizimda vaqtinchalik nosozlik.</b>\n"
                "Iltimos, bir necha daqiqadan so'ng qayta urinib ko'ring."
            )
            return

        # ─── 3-QADAM: LOADING XABAR ───
        loading_msg = await message.answer(
            "⏳ <b>Ma'lumotlar qabul qilindi!</b>\n"
            "<i>Hujjat namunasi tayyorlanmoqda, iltimos kuting...</i>"
        )

        # ─── 4-QADAM: DOCX + PREVIEW (alohida thread) ───
        os.makedirs(TEMP_DIR, exist_ok=True)
        timestamp = int(datetime.now().timestamp())
        docx_path = os.path.join(TEMP_DIR, f"{tg_id}_{timestamp}.docx")

        preview_images = await generate_doc_and_preview(data, docx_path, script)

        # ─── 5-QADAM: LOADING XABARINI O'CHIRISH ───
        try:
            await bot.delete_message(chat_id=tg_id, message_id=loading_msg.message_id)
        except Exception:
            pass  # Xabar allaqachon o'chirilgan bo'lishi mumkin
        loading_msg = None

        # ─── 6-QADAM: XOTIRADA SAQLASH (to'lov kutish uchun) ───
        _pending_docs[tg_id] = {
            "docx_path": docx_path,
            "data": data,
            "script": script,
            "created_at": datetime.now(),
        }

        # ─── 7-QADAM: TO'LOV TUGMALARINI TAYYORLASH ───
        fullname = data.get("fullname", "—")
        script_label = "Кирилл" if script == "cyr" else "Lotin"

        if user.has_enough_balance(DOC_PRICE):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"✅ Balansdan yechish ({price_text(DOC_PRICE)})",
                    callback_data="pay_from_balance",
                )],
                [InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data="cancel_doc",
                )],
            ])
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"💳 Karta orqali to'lash ({price_text(DOC_PRICE)})",
                    callback_data="p2p_pay",
                )],
                [InlineKeyboardButton(
                    text=f"⭐ Telegram Stars ({STARS_PER_DOC} ⭐)",
                    callback_data="topup_stars",
                )],
                [InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data="cancel_doc",
                )],
            ])

        # ─── 8-QADAM: NATIJANI YUBORISH ───
        caption_text = (
            f"📋 <b>Obektivka namunasi tayyor!</b>\n\n"
            f"👤 <b>{fullname}</b>  •  {script_label}\n"
            f"{'━' * 26}\n"
            f"💰 Narxi: <b>{price_text(DOC_PRICE)}</b>\n"
            f"💳 Balansingiz: <b>{price_text(user.balance)}</b>\n\n"
            f"<i>Asl nusxani olish uchun to'lov qiling 👇</i>"
        )

        if preview_images:
            # Preview rasmlarni media group sifatida yuborish (max 2 sahifa)
            media_group = []
            for i, img_bytes in enumerate(preview_images[:2]):
                media_group.append(InputMediaPhoto(
                    media=BufferedInputFile(img_bytes, filename=f"preview_{i + 1}.jpg"),
                    caption=caption_text if i == 0 else None,
                    parse_mode=ParseMode.HTML if i == 0 else None,
                ))

            await bot.send_media_group(chat_id=tg_id, media=media_group)
            await bot.send_message(
                chat_id=tg_id,
                text="👆 <b>Yuqoridagi namunani ko'ring.</b>\n"
                     "Asl nusxani olish uchun tanlang:",
                reply_markup=kb,
            )
        else:
            # Preview yaratilmasa — faqat matn bilan
            await message.answer(caption_text, reply_markup=kb)

    except Exception as e:
        logger.error(f"WebApp handler xatosi: tg_id={tg_id}, error={e}", exc_info=True)

        # Loading xabari hali turgan bo'lsa — o'chirish
        if loading_msg:
            try:
                await bot.delete_message(chat_id=tg_id, message_id=loading_msg.message_id)
            except Exception:
                pass

        await message.answer(
            "❌ <b>Kechirasiz, xatolik yuz berdi.</b>\n\n"
            "Iltimos, ma'lumotlarni tekshirib qayta urinib ko'ring.\n"
            "Muammo davom etsa, /help orqali bog'laning."
        )
