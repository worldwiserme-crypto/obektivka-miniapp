"""
Yo'lchi Bot — P2P To'lov Tizimi (Premium UI)
"""

import logging
import os
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import DOC_PRICE
from database import get_or_create_user, get_user, topup_balance
from admin_panel import send_receipt_to_admin_group
from models import User

logger = logging.getLogger(__name__)

payment_router = Router(name="p2p_payment")

# ══════════════════════════════════════════════════════════════
#  KONFIGURATSIYA
# ══════════════════════════════════════════════════════════════

CARD_NUMBER = os.getenv("CARD_NUMBER", "8600 1234 5678 9012")
CARD_HOLDER = os.getenv("CARD_HOLDER", "Eshmatov T.")


def price_text(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"


# ══════════════════════════════════════════════════════════════
#  FSM STATE
# ══════════════════════════════════════════════════════════════

class PaymentState(StatesGroup):
    waiting_for_receipt = State()


# ══════════════════════════════════════════════════════════════
#  TO'LOVNI BOSHLASH
# ══════════════════════════════════════════════════════════════

@payment_router.callback_query(F.data == "p2p_pay")
async def start_p2p_payment(callback: CallbackQuery, state: FSMContext):
    tg_id = callback.from_user.id
    await callback.answer()

    await state.set_state(PaymentState.waiting_for_receipt)
    await state.update_data(
        amount=DOC_PRICE,
        user_fullname=callback.from_user.full_name or "—",
        started_at=datetime.now().isoformat(),
    )

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✕ Bekor qilish", callback_data="p2p_cancel")],
    ])

    await callback.message.answer(
        f"<b>Karta orqali to'lov</b>\n\n"
        f"Quyidagi kartaga <b>{price_text(DOC_PRICE)}</b> miqdorida "
        f"o'tkazma qiling va chekni shu chatga yuboring.\n\n"
        f"<code>{CARD_NUMBER}</code>\n"
        f"{CARD_HOLDER}\n\n"
        f"📷 Chek <b>rasmini</b> (screenshot) yoki <b>PDF faylini</b> yuboring. "
        f"Bank ilovangizda screenshot ishlamasa, PDF sifatida yuklab olib jo'nating.\n\n"
        f"Admin tekshirib tasdiqlagach, hujjat avtomatik yuboriladi. "
        f"Odatda bu 5–15 daqiqa vaqt oladi.",
        reply_markup=cancel_kb,
    )


# ══════════════════════════════════════════════════════════════
#  CHEKNI QABUL QILISH
# ══════════════════════════════════════════════════════════════

@payment_router.message(PaymentState.waiting_for_receipt, F.photo)
async def receive_receipt_photo(message: Message, state: FSMContext, bot: Bot):
    tg_id = message.from_user.id
    fsm_data = await state.get_data()
    amount = fsm_data.get("amount", DOC_PRICE)

    photo = message.photo[-1]

    msg_id = await send_receipt_to_admin_group(
        bot=bot,
        user_id=tg_id,
        user_full_name=message.from_user.full_name or "—",
        username=message.from_user.username,
        file_id=photo.file_id,
        file_type="photo",
        amount=amount,
    )

    await _finalize_receipt(message, state, msg_id)


@payment_router.message(PaymentState.waiting_for_receipt, F.document)
async def receive_receipt_document(message: Message, state: FSMContext, bot: Bot):
    tg_id = message.from_user.id
    fsm_data = await state.get_data()
    amount = fsm_data.get("amount", DOC_PRICE)

    doc = message.document
    
    # Fayl tipini tekshirish — PDF, JPG, PNG ruxsat etiladi
    allowed_mimes = {
        "application/pdf",
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
    }
    
    mime = (doc.mime_type or "").lower()
    if mime not in allowed_mimes:
        await message.answer(
            "<b>Noto'g'ri fayl turi</b>\n\n"
            "Faqat PDF yoki rasm (JPG, PNG) qabul qilinadi. "
            "Bank ilovangizdan chek faylini yuklab olib, shu yerga yuboring."
        )
        return
    
    # Fayl hajmini tekshirish — 10 MB dan oshmasin
    if doc.file_size and doc.file_size > 10 * 1024 * 1024:
        await message.answer(
            "<b>Fayl juda katta</b>\n\n"
            "Chek hajmi 10 MB dan oshmasligi kerak."
        )
        return

    msg_id = await send_receipt_to_admin_group(
        bot=bot,
        user_id=tg_id,
        user_full_name=message.from_user.full_name or "—",
        username=message.from_user.username,
        file_id=doc.file_id,
        file_type="document",
        amount=amount,
        file_name=doc.file_name,
    )

    await _finalize_receipt(message, state, msg_id)


async def _finalize_receipt(message: Message, state: FSMContext, msg_id: int | None):
    """Chek qabul qilingandan keyingi umumiy logika."""
    if not msg_id:
        await message.answer(
            "<b>Vaqtinchalik nosozlik</b>\n\n"
            "Chekni yetkazib bo'lmadi. Iltimos, bir oz vaqtdan "
            "so'ng qayta urinib ko'ring."
        )
        await state.clear()
        return

    await state.clear()
    await message.answer(
        "<b>Chek qabul qilindi!</b>\n\n"
        "To'lovingiz admin xodimlariga yuborildi. Tekshirish "
        "odatda 5–15 daqiqa davom etadi.\n\n"
        "Tasdiqlangach, sizga avtomatik xabar keladi va "
        "hujjat darhol yuboriladi."
    )


@payment_router.message(PaymentState.waiting_for_receipt)
async def receipt_wrong_format(message: Message):
    await message.answer(
        "<b>Chek qabul qilinmadi</b>\n\n"
        "Iltimos, to'lov chekining <b>rasmini</b> (screenshot) yoki "
        "<b>PDF faylini</b> yuboring. Bank ilovangizda screenshot olish "
        "imkoni bo'lmasa, chekni PDF sifatida yuklab olib jo'nating."
    )


@payment_router.callback_query(F.data == "p2p_cancel")
async def cancel_payment(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Bekor qilindi")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Bosh menyu", callback_data="main_menu")],
    ])

    await callback.message.answer(
        "<b>Bekor qilindi</b>\n\n"
        "Hech qanday summa yechilmadi. Istalgan vaqtda "
        "qaytadan urinib ko'rishingiz mumkin.",
        reply_markup=kb,
    )
