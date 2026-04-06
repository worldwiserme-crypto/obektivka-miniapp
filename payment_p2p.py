"""
Obektivka Bot — P2P To'lov Tizimi (FSM)

Oqim:
  1. "To'lov qilish" → karta raqami ko'rsatiladi → FSM: waiting_for_receipt
  2. Foydalanuvchi chek (rasm) yuboradi → Admin'ga forward (✅/❌ tugmalar)
  3. Admin tasdiqlaydi → fayl yuboriladi | Admin rad etadi → xabar beriladi

Ulash:
  from payment_fsm import payment_router
  dp.include_router(payment_router)
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
    BufferedInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import DOC_PRICE
from database_async import get_or_create_user, get_session
from models import User

logger = logging.getLogger(__name__)

payment_router = Router(name="p2p_payment")

# ══════════════════════════════════════════════════════════════
#  KONFIGURATSIYA
# ══════════════════════════════════════════════════════════════

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CARD_NUMBER = os.getenv("CARD_NUMBER", "8600 1234 5678 9012")
CARD_HOLDER = os.getenv("CARD_HOLDER", "Eshmatov T.")


def price_text(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"


# ══════════════════════════════════════════════════════════════
#  1. FSM STATE
# ══════════════════════════════════════════════════════════════

class PaymentState(StatesGroup):
    waiting_for_receipt = State()


# ══════════════════════════════════════════════════════════════
#  KUTAYOTGAN HUJJATLAR XOTIRASI
#  (webapp_handler.py dagi _pending_docs bilan umumiy bo'lishi kerak.
#   Production'da Redis yoki alohida modul orqali ulash tavsiya qilinadi.)
# ══════════════════════════════════════════════════════════════

_pending_docs: dict[int, dict] = {}


# ══════════════════════════════════════════════════════════════
#  2. TO'LOVNI BOSHLASH — callback_data="pay_p2p"
# ══════════════════════════════════════════════════════════════

@payment_router.callback_query(F.data == "pay_p2p")
async def start_p2p_payment(callback: CallbackQuery, state: FSMContext):
    """
    Foydalanuvchi "To'lov qilish" tugmasini bosdi.
    → Karta raqamini ko'rsatish
    → FSM: waiting_for_receipt ga o'tkazish
    """
    tg_id = callback.from_user.id
    await callback.answer()

    # FSM ga to'lov ma'lumotlarini saqlash
    await state.set_state(PaymentState.waiting_for_receipt)
    await state.update_data(
        amount=DOC_PRICE,
        user_fullname=callback.from_user.full_name or "—",
        started_at=datetime.now().isoformat(),
    )

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="❌ Bekor qilish",
            callback_data="p2p_cancel",
        )],
    ])

    await callback.message.answer(
        f"💳 <b>To'lov ma'lumotlari</b>\n"
        f"{'━' * 28}\n\n"
        f"Quyidagi kartaga <b>{price_text(DOC_PRICE)}</b> o'tkazing:\n\n"
        f"┌───────────────────────────┐\n"
        f"│  <code>{CARD_NUMBER}</code>\n"
        f"│  {CARD_HOLDER}\n"
        f"└───────────────────────────┘\n\n"
        f"📸 To'lovdan so'ng <b>chek skrinshotini</b>\n"
        f"shu chatga yuboring.\n\n"
        f"⏱ <i>Chek uchun 30 daqiqa vaqtingiz bor.</i>",
        reply_markup=cancel_kb,
    )


# ══════════════════════════════════════════════════════════════
#  3. CHEKNI QABUL QILISH — rasm kelganda (FSM state ichida)
# ══════════════════════════════════════════════════════════════

@payment_router.message(PaymentState.waiting_for_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext, bot: Bot):
    """
    Foydalanuvchi chek rasmini yubordi.
    → Rasmni ADMIN ga forward qilish (✅/❌ tugmalar bilan)
    → FSM ni tozalash
    → Mijozga "kutayotgan" xabar berish
    """
    tg_id = message.from_user.id
    fsm_data = await state.get_data()
    amount = fsm_data.get("amount", DOC_PRICE)

    # Admin ID tekshirish
    if not ADMIN_ID:
        logger.critical("ADMIN_ID sozlanmagan! .env faylda ADMIN_ID ni belgilang.")
        await message.answer(
            "⚠️ <b>Tizimda vaqtinchalik nosozlik.</b>\n"
            "<i>Iltimos, keyinroq qayta urinib ko'ring.</i>"
        )
        await state.clear()
        return

    # Eng katta o'lchamdagi rasm
    photo = message.photo[-1]

    # ─── Admin uchun xabar ───
    admin_text = (
        f"🧾 <b>Yangi to'lov cheki</b>\n"
        f"{'━' * 30}\n\n"
        f"👤 <b>{message.from_user.full_name or '—'}</b>\n"
        f"🆔 ID: <code>{tg_id}</code>\n"
        f"📱 @{message.from_user.username or '—'}\n\n"
        f"💰 Summa: <b>{price_text(amount)}</b>\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y  %H:%M')}"
    )

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Tasdiqlash",
                callback_data=f"approve_pay:{tg_id}",
            ),
            InlineKeyboardButton(
                text="❌ Rad qilish",
                callback_data=f"reject_pay:{tg_id}",
            ),
        ],
    ])

    # ─── Adminga yuborish ───
    try:
        await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo.file_id,
            caption=admin_text,
            reply_markup=admin_kb,
        )
    except Exception as e:
        logger.error(f"Adminga chek yuborib bo'lmadi: {e}", exc_info=True)
        await message.answer(
            "⚠️ <b>Texnik nosozlik yuz berdi.</b>\n"
            "<i>Iltimos, keyinroq qayta urinib ko'ring.</i>"
        )
        await state.clear()
        return

    # ─── FSM tozalash + Mijozga xabar ───
    await state.clear()
    await message.answer(
        "✅ <b>Chekingiz qabul qilindi!</b>\n\n"
        "⏳ <i>Admin tekshirib, tasdiqlagach sizga\n"
        "hujjatning asl nusxasi yuboriladi.</i>\n\n"
        "💡 Odatda bu <b>5–15 daqiqa</b> ichida amalga oshadi."
    )


# ─── Rasm emas, boshqa narsa yuborsa ───

@payment_router.message(PaymentState.waiting_for_receipt)
async def receipt_wrong_format(message: Message):
    """Foydalanuvchi rasm o'rniga matn/sticker/boshqa yubordi."""
    await message.answer(
        "⚠️ <b>Faqat rasmni yuboring!</b>\n\n"
        "📸 <i>To'lov chekining skrinshotini rasmga olib,\n"
        "shu chatga yuboring.</i>"
    )


# ─── Bekor qilish ───

@payment_router.callback_query(F.data == "p2p_cancel")
async def cancel_payment(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Bekor qilindi", show_alert=False)
    await callback.message.answer(
        "🗑 <b>To'lov bekor qilindi.</b>\n\n"
        "<i>Qayta urinish uchun /start bosing.</i>"
    )


# ══════════════════════════════════════════════════════════════
#  4. ADMIN CALLBACK HANDLERS — Tasdiqlash / Rad qilish
# ══════════════════════════════════════════════════════════════

@payment_router.callback_query(F.data.startswith("approve_pay:"))
async def admin_approve(callback: CallbackQuery, bot: Bot):
    """
    Admin chekni tasdiqladi.
    → Foydalanuvchiga tayyor faylni yuborish
    → Admin xabarini yangilash
    """
    # ─── Ruxsat tekshirish ───
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Sizda ruxsat yo'q!", show_alert=True)
        return

    # ─── User ID ni olish ───
    try:
        user_tg_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Noto'g'ri ma'lumot!", show_alert=True)
        return

    await callback.answer("✅ Tasdiqlanmoqda...")

    # ─── Admin xabarini yangilash ───
    try:
        updated_caption = (
            f"{callback.message.caption}\n\n"
            f"✅ <b>TASDIQLANDI</b>\n"
            f"👮 {callback.from_user.full_name}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        await callback.message.edit_caption(
            caption=updated_caption,
            reply_markup=None,
        )
    except Exception:
        pass

    # ─── Faylni yuborish ───
    pending = _pending_docs.get(user_tg_id)

    if pending and os.path.exists(pending.get("docx_path", "")):
        try:
            docx_path = pending["docx_path"]
            fullname = pending.get("data", {}).get("fullname", "obektivka")
            script = pending.get("script", "lat")
            script_label = "Кирилл" if script == "cyr" else "Lotin"

            with open(docx_path, "rb") as f:
                file_data = f.read()

            await bot.send_document(
                chat_id=user_tg_id,
                document=BufferedInputFile(file_data, filename=f"{fullname}.docx"),
                caption=(
                    f"✅ <b>To'lov tasdiqlandi!</b>\n\n"
                    f"📎 <b>{fullname}</b>  •  {script_label}\n"
                    f"<i>Word (.docx) formatida tayyor.</i>\n\n"
                    f"💡 Bu hujjat «Mening hujjatlarim» bo'limida saqlanadi."
                ),
            )

            # Tozalash
            _pending_docs.pop(user_tg_id, None)
            try:
                os.remove(docx_path)
            except OSError:
                pass

        except Exception as e:
            logger.error(f"Fayl yuborishda xato: user={user_tg_id}, err={e}", exc_info=True)
            await bot.send_message(
                chat_id=user_tg_id,
                text=(
                    "✅ <b>To'lov tasdiqlandi!</b>\n\n"
                    "⚠️ <i>Faylni yuborishda xatolik yuz berdi.\n"
                    "Iltimos, /start bosib qayta urinib ko'ring.</i>"
                ),
            )
    else:
        # Kutayotgan hujjat topilmasa — faqat balans to'ldirish
        await bot.send_message(
            chat_id=user_tg_id,
            text=(
                "✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
                f"💰 <b>+{price_text(DOC_PRICE)}</b> balansingizga qo'shildi.\n\n"
                "<i>Hujjat olish uchun /start bosib,\n"
                "obektivkani to'ldiring.</i>"
            ),
        )


@payment_router.callback_query(F.data.startswith("reject_pay:"))
async def admin_reject(callback: CallbackQuery, bot: Bot):
    """
    Admin chekni rad qildi.
    → Foydalanuvchiga sabablar bilan xabar
    → Admin xabarini yangilash
    """
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Sizda ruxsat yo'q!", show_alert=True)
        return

    try:
        user_tg_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Noto'g'ri ma'lumot!", show_alert=True)
        return

    await callback.answer("❌ Rad qilindi")

    # ─── Admin xabarini yangilash ───
    try:
        updated_caption = (
            f"{callback.message.caption}\n\n"
            f"❌ <b>RAD QILINDI</b>\n"
            f"👮 {callback.from_user.full_name}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        await callback.message.edit_caption(
            caption=updated_caption,
            reply_markup=None,
        )
    except Exception:
        pass

    # ─── Foydalanuvchiga xabar ───
    try:
        await bot.send_message(
            chat_id=user_tg_id,
            text=(
                "❌ <b>To'lov tasdiqlanmadi.</b>\n\n"
                "<i>Mumkin bo'lgan sabablar:</i>\n"
                f"• Chekda summa noto'g'ri (<b>{price_text(DOC_PRICE)}</b> emas)\n"
                "• Karta raqami boshqa\n"
                "• Rasm aniq ko'rinmayapti\n\n"
                "<i>Qayta urinish uchun /start bosing.</i>"
            ),
        )
    except Exception as e:
        logger.error(f"Rad xabarini yuborib bo'lmadi: user={user_tg_id}, err={e}")
