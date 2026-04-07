"""
Obektivka Bot — P2P To'lov Tizimi (FSM)

Yangilandi: Chek endi admin guruhiga yuboriladi (bitta admin emas).
Tasdiqlash/rad qilish logikasi admin_panel.py ga ko'chirildi.
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
        [InlineKeyboardButton(text="✕  Bekor qilish", callback_data="p2p_cancel")],
    ])

    await callback.message.answer(
        f"<b>Karta orqali to'lov</b>\n"
        f"<i>quyidagi rekvizitlarga o'tkazma qiling</i>\n\n"
        f"<i>summa</i>\n"
        f"<b>{price_text(DOC_PRICE)}</b>\n\n"
        f"<i>karta raqami</i>\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        f"<i>qabul qiluvchi</i>\n"
        f"<b>{CARD_HOLDER}</b>\n\n"
        f"\u00a0\u00a0\u00a0To'lovdan so'ng chek skrinshotini\n"
        f"\u00a0\u00a0\u00a0shu chatga yuboring.\n\n"
        f"<i>Tasdiqlash vaqti  ·  5–15 daqiqa</i>",
        reply_markup=cancel_kb,
    )
# ══════════════════════════════════════════════════════════════
#  BALANS TO'LDIRISH (5k / 10k / 25k / 50k)
# ══════════════════════════════════════════════════════════════

@payment_router.callback_query(F.data.startswith("p2p_topup_"))
async def start_p2p_topup(callback: CallbackQuery, state: FSMContext):
    """
    Balansni to'ldirish tugmalari: p2p_topup_5000, p2p_topup_10000, va h.k.
    Istalgan summa bilan karta orqali to'lov oqimini boshlaydi.
    """
    tg_id = callback.from_user.id
    await callback.answer()

    # Callback'dan summani ajratib olish
    try:
        amount = int(callback.data.replace("p2p_topup_", ""))
    except ValueError:
        await callback.message.answer("❌ Noto'g'ri summa")
        return

    # FSM state'ga tanlangan summani saqlash
    await state.set_state(PaymentState.waiting_for_receipt)
    await state.update_data(
        amount=amount,
        user_fullname=callback.from_user.full_name or "—",
        started_at=datetime.now().isoformat(),
    )

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✕  Bekor qilish", callback_data="p2p_cancel")],
    ])

    await callback.message.answer(
        f"<b>Karta orqali to'lov</b>\n"
        f"<i>balansni to'ldirish</i>\n\n"
        f"<i>summa</i>\n"
        f"<b>{price_text(amount)}</b>\n\n"
        f"<i>karta raqami</i>\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        f"<i>qabul qiluvchi</i>\n"
        f"<b>{CARD_HOLDER}</b>\n\n"
        f"\u00a0\u00a0\u00a0Aynan <b>{price_text(amount)}</b> miqdorida\n"
        f"\u00a0\u00a0\u00a0o'tkazma qiling va chek\n"
        f"\u00a0\u00a0\u00a0skrinshotini shu chatga yuboring.\n\n"
        f"<i>Tasdiqlash vaqti  ·  5–15 daqiqa</i>",
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

    # Chekni admin guruhiga yuborish
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
            "<b>Vaqtinchalik nosozlik</b>\n"
            "<i>chekni yetkazib bo'lmadi</i>\n\n"
            "\u00a0\u00a0\u00a0Iltimos, bir oz vaqtdan so'ng\n"
            "\u00a0\u00a0\u00a0qayta urinib ko'ring."
        )
        await state.clear()
        return

    await state.clear()
    await message.answer(
        "<b>Chek qabul qilindi</b>\n"
        "<i>tasdiqlash kutilmoqda</i>\n\n"
        "\u00a0\u00a0\u00a0Admin to'lovingizni tekshirib,\n"
        "\u00a0\u00a0\u00a0tasdiqlagach hisobingiz avtomatik\n"
        "\u00a0\u00a0\u00a0to'ldiriladi.\n\n"
        "<i>Odatda  ·  5–15 daqiqa</i>"
    )


@payment_router.message(PaymentState.waiting_for_receipt)
async def receipt_wrong_format(message: Message):
    await message.answer(
        "<b>Faqat rasm yuboring</b>\n"
        "<i>matn yoki fayl qabul qilinmaydi</i>\n\n"
        "\u00a0\u00a0\u00a0To'lov chekining skrinshotini\n"
        "\u00a0\u00a0\u00a0rasm sifatida shu chatga yuboring."
    )


@payment_router.callback_query(F.data == "p2p_cancel")
async def cancel_payment(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Bekor qilindi", show_alert=False)
    await callback.message.answer(
        "<b>To'lov bekor qilindi</b>\n"
        "<i>hech qanday summa yechilmadi</i>\n\n"
        "<i>Qayta boshlash uchun /start bosing.</i>"
    )
