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
        f"o'tkazma qiling va chek skrinshotini shu chatga yuboring.\n\n"
        f"<code>{CARD_NUMBER}</code>\n"
        f"{CARD_HOLDER}\n\n"
        f"Admin tekshirib tasdiqlagach, hujjat avtomatik yuboriladi. "
        f"Odatda bu 5–15 daqiqa vaqt oladi.",
        reply_markup=cancel_kb,
    )


# ══════════════════════════════════════════════════════════════
#  CHEKNI QABUL QILISH
# ══════════════════════════════════════════════════════════════

@payment_router.message(PaymentState.waiting_for_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext, bot: Bot):
    tg_id = message.from_user.id
    fsm_data = await state.get_data()
    amount = fsm_data.get("amount", DOC_PRICE)

    photo = message.photo[-1]

    msg_id = await send_receipt_to_admin_group(
        bot=bot,
        user_id=tg_id,
        user_full_name=message.from_user.full_name or "—",
        username=message.from_user.username,
        photo_file_id=photo.file_id,
        amount=amount,
    )

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
        "<b>Faqat rasm yuboring</b>\n\n"
        "To'lov chekining skrinshotini rasm sifatida "
        "shu chatga yuboring. Matn yoki fayl qabul qilinmaydi."
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
