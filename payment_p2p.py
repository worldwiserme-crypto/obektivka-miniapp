"""
Obektivka Bot — P2P (Card-to-Card) To'lov Moduli

Yarim-avtomat to'lov tizimi:
  1. Foydalanuvchi "To'lov qilish" → karta raqami ko'rsatiladi
  2. Chek (screenshot) yuboriladi → FSM: PaymentStates.wait_receipt
  3. Chek ADMIN ga forward qilinadi (✅ / ❌ tugmalar bilan)
  4. Admin tasdiqlaydi → balans to'ldiriladi → hujjat beriladi
  5. Admin rad etadi → foydalanuvchiga xabar

Integratsiya:
  - bot_v2.py dagi _pending_docs va _deliver_document bilan bog'lanadi
  - database.py dagi topup_balance, deduct_balance ishlatiladi
  - models.py dagi Transaction jadvaliga yoziladi

Ishlatish:
  from payment_p2p import p2p_router
  dp.include_router(p2p_router)
"""

import logging
from datetime import datetime

from aiogram import Bot, Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import DOC_PRICE, TEMP_DIR
from database import (
    get_or_create_user, get_user,
    topup_balance, deduct_balance,
    save_document,
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  KONFIGURATSIYA
# ══════════════════════════════════════════════════════════════

# Admin Telegram ID — cheklar shu odam(lar)ga yuboriladi
# Bir nechta admin bo'lishi mumkin (tuple/list)
ADMIN_IDS: list[int] = [
    123456789,   # <-- O'z Telegram ID raqamingizni qo'ying
    # 987654321,  # Ikkinchi admin (ixtiyoriy)
]

# Karta ma'lumotlari
CARD_NUMBER = "8600 1234 5678 9012"
CARD_HOLDER = "Eshmatov T."

# Chek kutish vaqti (soniyada) — 30 daqiqa
RECEIPT_TIMEOUT = 30 * 60


# ══════════════════════════════════════════════════════════════
#  FSM STATES — To'lov holatlari
# ══════════════════════════════════════════════════════════════

class PaymentStates(StatesGroup):
    """
    Foydalanuvchining to'lov jarayonidagi holatlari.

    wait_receipt:
        Foydalanuvchi karta-ga pul o'tkazib, chek (screenshot) yuborishini
        kutayotgan holat. FSM data ichida quyidagilar saqlanadi:
          - amount: to'lov summasi
          - purpose: "topup" yoki "doc_purchase"
          - doc_fullname: (ixtiyoriy) hujjat egasining ismi
    """
    wait_receipt = State()


# ══════════════════════════════════════════════════════════════
#  ROUTER
# ══════════════════════════════════════════════════════════════

p2p_router = Router(name="p2p_payment")


# ──────────────────────────────────────────────────────────────
#  YORDAMCHI
# ──────────────────────────────────────────────────────────────

def price_text(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"


def is_admin(tg_id: int) -> bool:
    return tg_id in ADMIN_IDS


# ══════════════════════════════════════════════════════════════
#  1-QADAM: TO'LOV BOSHLASH
#     Foydalanuvchi "To'lov qilish" tugmasini bosadi
# ══════════════════════════════════════════════════════════════

@p2p_router.callback_query(F.data == "p2p_pay")
async def start_p2p_payment(callback: CallbackQuery, state: FSMContext):
    """
    Preview ko'rgandan keyin "P2P to'lov" tugmasini bosganida ishga tushadi.
    Karta raqamini ko'rsatadi va chek kutish holatiga o'tkazadi.
    """
    tg_id = callback.from_user.id
    await callback.answer()

    # FSM ga to'lov ma'lumotlarini saqlash
    await state.set_state(PaymentStates.wait_receipt)
    await state.update_data(
        amount=DOC_PRICE,
        purpose="doc_purchase",
        started_at=datetime.now().isoformat(),
    )

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="p2p_cancel")]
    ])

    await callback.message.answer(
        f"💳 <b>To'lov qilish</b>\n"
        f"{'━' * 28}\n\n"
        f"Hujjatning asl nusxasini olish uchun quyidagi\n"
        f"karta raqamiga <b>{price_text(DOC_PRICE)}</b> o'tkazing:\n\n"
        f"┌─────────────────────────┐\n"
        f"│  <code>{CARD_NUMBER}</code>  │\n"
        f"│  {CARD_HOLDER}                          │\n"
        f"└─────────────────────────┘\n\n"
        f"📸 To'lovni amalga oshirgach, <b>chekning skrinshotini</b>\n"
        f"shu yerga yuboring.\n\n"
        f"⏱ Chek uchun <b>30 daqiqa</b> vaqtingiz bor.",
        reply_markup=cancel_kb,
    )


# ─── Hisobni to'ldirish uchun ham alohida callback ───

@p2p_router.callback_query(F.data.startswith("p2p_topup_"))
async def start_p2p_topup(callback: CallbackQuery, state: FSMContext):
    """
    "Hisobni to'ldirish" menyusidan keladi.
    callback_data formati: p2p_topup_15000
    """
    tg_id = callback.from_user.id
    await callback.answer()

    try:
        amount = int(callback.data.replace("p2p_topup_", ""))
    except ValueError:
        amount = DOC_PRICE

    await state.set_state(PaymentStates.wait_receipt)
    await state.update_data(
        amount=amount,
        purpose="topup",
        started_at=datetime.now().isoformat(),
    )

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="p2p_cancel")]
    ])

    await callback.message.answer(
        f"💳 <b>Hisobni to'ldirish</b>\n"
        f"{'━' * 28}\n\n"
        f"Quyidagi karta raqamiga <b>{price_text(amount)}</b> o'tkazing:\n\n"
        f"┌─────────────────────────┐\n"
        f"│  <code>{CARD_NUMBER}</code>  │\n"
        f"│  {CARD_HOLDER}                          │\n"
        f"└─────────────────────────┘\n\n"
        f"📸 To'lovni amalga oshirgach, <b>chekning skrinshotini</b>\n"
        f"shu yerga yuboring.\n\n"
        f"⏱ Chek uchun <b>30 daqiqa</b> vaqtingiz bor.",
        reply_markup=cancel_kb,
    )


# ══════════════════════════════════════════════════════════════
#  2-QADAM: CHEK QABUL QILISH (RASM)
#     Foydalanuvchi screenshot yuboradi → Adminga forward
# ══════════════════════════════════════════════════════════════

@p2p_router.message(PaymentStates.wait_receipt, F.photo)
async def receive_receipt_photo(message: Message, state: FSMContext, bot: Bot):
    """
    Foydalanuvchi chek rasmini yuboradi.
    Rasm admin(lar)ga yuboriladi — tasdiqlash/rad qilish tugmalari bilan.
    """
    tg_id = message.from_user.id
    fsm_data = await state.get_data()
    amount = fsm_data.get("amount", DOC_PRICE)
    purpose = fsm_data.get("purpose", "doc_purchase")

    user = await get_or_create_user(tg_id, username=message.from_user.username)

    # Eng katta o'lchamdagi rasmni olish
    photo = message.photo[-1]

    # ─── Admin uchun ma'lumot matni ───
    purpose_label = "📄 Hujjat sotib olish" if purpose == "doc_purchase" else "💰 Hisobni to'ldirish"

    admin_text = (
        f"🧾 <b>Yangi to'lov cheki</b>\n"
        f"{'━' * 30}\n\n"
        f"👤 Foydalanuvchi: <b>{message.from_user.full_name or '—'}</b>\n"
        f"🆔 ID: <code>{tg_id}</code>\n"
        f"📱 Username: @{message.from_user.username or '—'}\n\n"
        f"💰 Summa: <b>{price_text(amount)}</b>\n"
        f"🎯 Maqsad: {purpose_label}\n"
        f"🕐 Vaqt: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
    )

    # ─── Callback data formati: p2p_{action}_{user_id}_{amount}_{purpose} ───
    # Callback data Telegram limiti: max 64 bayt
    # Shu sababli qisqartirilgan format ishlatamiz
    approve_data = f"p2pOK_{tg_id}_{amount}_{purpose}"
    reject_data = f"p2pNO_{tg_id}_{amount}_{purpose}"

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=approve_data),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=reject_data),
        ]
    ])

    # Har bir adminga yuborish
    sent_to_any = False
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                chat_id=admin_id,
                photo=photo.file_id,
                caption=admin_text,
                reply_markup=admin_kb,
            )
            sent_to_any = True
        except Exception as e:
            logger.error(f"Adminga ({admin_id}) yuborib bo'lmadi: {e}")

    if not sent_to_any:
        logger.critical("HECH BIR ADMINGA yuborib bo'lmadi!")
        await message.answer(
            "⚠️ Texnik nosozlik yuz berdi. Iltimos, keyinroq urinib ko'ring\n"
            "yoki admin bilan bog'laning."
        )
        await state.clear()
        return

    # Foydalanuvchiga tasdiq xabari
    await message.answer(
        "✅ <b>Chekingiz qabul qilindi!</b>\n\n"
        "⏳ Admin tekshirib, <b>5-15 daqiqa</b> ichida tasdiqlaydi.\n"
        "Tasdiqlanishi bilan sizga xabar yuboriladi.\n\n"
        "💡 Agar uzoq kutib qolsangiz, /help orqali admin bilan bog'laning."
    )

    # FSM ni tozalash — endi admin callback orqali davom etadi
    # Lekin FSM data ni saqlash shart emas, chunki admin callback_data
    # ichida barcha kerakli ma'lumot bor
    await state.clear()


@p2p_router.message(PaymentStates.wait_receipt, F.document)
async def receive_receipt_document(message: Message, state: FSMContext, bot: Bot):
    """
    Foydalanuvchi chekni fayl (PDF/JPEG) sifatida yuborishi mumkin.
    Buni ham qabul qilamiz.
    """
    tg_id = message.from_user.id
    fsm_data = await state.get_data()
    amount = fsm_data.get("amount", DOC_PRICE)
    purpose = fsm_data.get("purpose", "doc_purchase")

    user = await get_or_create_user(tg_id, username=message.from_user.username)

    purpose_label = "📄 Hujjat sotib olish" if purpose == "doc_purchase" else "💰 Hisobni to'ldirish"

    admin_text = (
        f"🧾 <b>Yangi to'lov cheki (fayl)</b>\n"
        f"{'━' * 30}\n\n"
        f"👤 Foydalanuvchi: <b>{message.from_user.full_name or '—'}</b>\n"
        f"🆔 ID: <code>{tg_id}</code>\n"
        f"📱 Username: @{message.from_user.username or '—'}\n\n"
        f"💰 Summa: <b>{price_text(amount)}</b>\n"
        f"🎯 Maqsad: {purpose_label}\n"
        f"🕐 Vaqt: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
    )

    approve_data = f"p2pOK_{tg_id}_{amount}_{purpose}"
    reject_data = f"p2pNO_{tg_id}_{amount}_{purpose}"

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=approve_data),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=reject_data),
        ]
    ])

    sent_to_any = False
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_document(
                chat_id=admin_id,
                document=message.document.file_id,
                caption=admin_text,
                reply_markup=admin_kb,
            )
            sent_to_any = True
        except Exception as e:
            logger.error(f"Adminga ({admin_id}) yuborib bo'lmadi: {e}")

    if sent_to_any:
        await message.answer(
            "✅ <b>Chekingiz qabul qilindi!</b>\n\n"
            "⏳ Admin tekshirib, <b>5-15 daqiqa</b> ichida tasdiqlaydi.\n"
            "Tasdiqlanishi bilan sizga xabar yuboriladi."
        )
    else:
        await message.answer("⚠️ Texnik nosozlik. Iltimos, keyinroq urinib ko'ring.")

    await state.clear()


@p2p_router.message(PaymentStates.wait_receipt)
async def receipt_wrong_format(message: Message):
    """
    Foydalanuvchi rasm yoki fayl emas, boshqa narsa yuborsa.
    """
    await message.answer(
        "⚠️ Iltimos, to'lov <b>chekining skrinshotini (rasm)</b> yuboring.\n\n"
        "📸 Telefondan rasmga oling yoki bank ilovasi chekini yuboring.\n"
        "Matn yoki boshqa formatdagi xabar qabul qilinmaydi."
    )


# ══════════════════════════════════════════════════════════════
#  BEKOR QILISH (foydalanuvchi tomonidan)
# ══════════════════════════════════════════════════════════════

@p2p_router.callback_query(F.data == "p2p_cancel", PaymentStates.wait_receipt)
async def cancel_payment(callback: CallbackQuery, state: FSMContext):
    """Foydalanuvchi to'lovni bekor qiladi."""
    await state.clear()
    await callback.answer("Bekor qilindi", show_alert=False)
    await callback.message.answer(
        "🗑 To'lov bekor qilindi.\n\n"
        "Qayta urinish uchun /start bosing."
    )


@p2p_router.callback_query(F.data == "p2p_cancel")
async def cancel_payment_no_state(callback: CallbackQuery):
    """State bo'lmasa ham cancel tugmasini qo'llab-quvvatlash."""
    await callback.answer("Bekor qilindi", show_alert=False)
    await callback.message.answer("🗑 To'lov bekor qilindi.")


# ══════════════════════════════════════════════════════════════
#  3-QADAM: ADMIN TASDIQLASH / RAD QILISH
# ══════════════════════════════════════════════════════════════

@p2p_router.callback_query(F.data.startswith("p2pOK_"))
async def admin_approve_payment(callback: CallbackQuery, bot: Bot):
    """
    Admin chekni tasdiqlaydi.
    callback_data formati: p2pOK_{user_tg_id}_{amount}_{purpose}

    Natija:
      - topup: balansga pul qo'shiladi
      - doc_purchase: balansga pul qo'shiladi + kutayotgan hujjat beriladi
    """
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Sizda ruxsat yo'q!", show_alert=True)
        return

    # Callback data ni parse qilish
    parts = callback.data.split("_")
    # p2pOK_123456789_15000_doc_purchase → ["p2pOK", "123456789", "15000", "doc", "purchase"]
    # p2pOK_123456789_15000_topup        → ["p2pOK", "123456789", "15000", "topup"]
    try:
        user_tg_id = int(parts[1])
        amount = int(parts[2])
        purpose = "_".join(parts[3:])  # "topup" yoki "doc_purchase"
    except (IndexError, ValueError) as e:
        logger.error(f"Admin callback parse xatosi: {callback.data} → {e}")
        await callback.answer("❌ Xatolik!", show_alert=True)
        return

    await callback.answer("✅ Tasdiqlanmoqda...")

    # ─── Balansga pul qo'shish ───
    try:
        tx = await topup_balance(
            tg_id=user_tg_id,
            amount=amount,
            provider="p2p_card",
            provider_tx_id=f"admin_{admin_id}_{int(datetime.now().timestamp())}",
        )
    except ValueError:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ <b>XATO:</b> Foydalanuvchi topilmadi!",
        )
        return

    user = await get_user(user_tg_id)

    # ─── Admin xabarini yangilash ───
    new_caption = (
        callback.message.caption
        + f"\n\n✅ <b>TASDIQLANDI</b>"
        f"\n👮 Admin: {callback.from_user.full_name}"
        f"\n🕐 {datetime.now().strftime('%H:%M:%S')}"
        f"\n💰 Yangi balans: {price_text(user.balance) if user else '—'}"
    )
    try:
        await callback.message.edit_caption(caption=new_caption, reply_markup=None)
    except Exception:
        pass  # Agar xabar eski bo'lsa

    # ─── Foydalanuvchiga xabar ───
    if purpose == "doc_purchase":
        # Hujjat uchun to'lov — balansdan yechib, hujjatni berish
        await bot.send_message(
            user_tg_id,
            f"✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
            f"💰 +{price_text(amount)} balansingizga qo'shildi.\n"
            f"⏳ Hujjatingiz tayyorlanmoqda..."
        )

        # _pending_docs dan hujjatni olish va berish
        # Bu funksiyani bot_v2.py dan import qilamiz
        from bot_v2 import _pending_docs, _deliver_document

        pending = _pending_docs.get(user_tg_id)
        if pending:
            deduct_tx = await deduct_balance(
                user_tg_id, DOC_PRICE,
                description="Obektivka — P2P to'lov"
            )
            if deduct_tx:
                await _deliver_document(user_tg_id, pending)
            else:
                await bot.send_message(
                    user_tg_id,
                    f"💰 Balansingiz to'ldirildi: <b>{price_text(user.balance)}</b>\n"
                    f"📋 Hujjat olish uchun /start bosing."
                )
        else:
            await bot.send_message(
                user_tg_id,
                f"💰 Balansingiz to'ldirildi: <b>{price_text(user.balance)}</b>\n"
                f"📋 Hujjat olish uchun /start bosib, obektivkani to'ldiring."
            )

    else:
        # Oddiy topup — faqat balans to'ldiriladi
        await bot.send_message(
            user_tg_id,
            f"✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
            f"💰 +{price_text(amount)} balansingizga qo'shildi.\n"
            f"💳 Joriy balans: <b>{price_text(user.balance)}</b>"
        )

    logger.info(
        f"P2P tasdiqlandi: user={user_tg_id}, amount={amount}, "
        f"purpose={purpose}, admin={admin_id}"
    )


@p2p_router.callback_query(F.data.startswith("p2pNO_"))
async def admin_reject_payment(callback: CallbackQuery, bot: Bot):
    """
    Admin chekni rad qiladi.
    callback_data formati: p2pNO_{user_tg_id}_{amount}_{purpose}
    """
    admin_id = callback.from_user.id
    if not is_admin(admin_id):
        await callback.answer("⛔ Sizda ruxsat yo'q!", show_alert=True)
        return

    parts = callback.data.split("_")
    try:
        user_tg_id = int(parts[1])
        amount = int(parts[2])
    except (IndexError, ValueError) as e:
        logger.error(f"Admin reject parse xatosi: {callback.data} → {e}")
        await callback.answer("❌ Xatolik!", show_alert=True)
        return

    await callback.answer("❌ Rad qilindi")

    # Admin xabarini yangilash
    new_caption = (
        callback.message.caption
        + f"\n\n❌ <b>RAD QILINDI</b>"
        f"\n👮 Admin: {callback.from_user.full_name}"
        f"\n🕐 {datetime.now().strftime('%H:%M:%S')}"
    )
    try:
        await callback.message.edit_caption(caption=new_caption, reply_markup=None)
    except Exception:
        pass

    # Foydalanuvchiga xabar
    try:
        await bot.send_message(
            user_tg_id,
            f"❌ <b>To'lov tasdiqlanmadi</b>\n\n"
            f"Yuborgan chekingiz yaroqsiz deb topildi.\n\n"
            f"Mumkin bo'lgan sabablar:\n"
            f"• Chekda summa noto'g'ri ({price_text(amount)} emas)\n"
            f"• Chek boshqa karta uchun\n"
            f"• Rasm aniq ko'rinmaydi\n\n"
            f"Qayta urinish uchun /start bosing.\n"
            f"Muammo bo'lsa admin bilan bog'laning."
        )
    except Exception as e:
        logger.error(f"Foydalanuvchiga ({user_tg_id}) xabar yuborib bo'lmadi: {e}")

    logger.info(f"P2P rad qilindi: user={user_tg_id}, amount={amount}, admin={admin_id}")


# ══════════════════════════════════════════════════════════════
#  ADMIN BUYRUQLARI (ixtiyoriy — qo'shimcha boshqaruv)
# ══════════════════════════════════════════════════════════════

@p2p_router.message(F.text.startswith("/admin_topup"))
async def admin_manual_topup(message: Message, bot: Bot):
    """
    Admin qo'lda balans to'ldirish:
      /admin_topup 123456789 15000
    """
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(
            "📝 Format: <code>/admin_topup {tg_id} {summa}</code>\n"
            "Masalan: <code>/admin_topup 123456789 15000</code>"
        )
        return

    try:
        target_tg_id = int(parts[1])
        amount = int(parts[2])
    except ValueError:
        await message.answer("❌ ID va summa raqam bo'lishi kerak.")
        return

    try:
        await topup_balance(
            tg_id=target_tg_id,
            amount=amount,
            provider="admin_manual",
            provider_tx_id=f"manual_{message.from_user.id}_{int(datetime.now().timestamp())}",
        )
        user = await get_user(target_tg_id)
        await message.answer(
            f"✅ Bajar ildi!\n"
            f"👤 User: <code>{target_tg_id}</code>\n"
            f"💰 +{price_text(amount)}\n"
            f"💳 Yangi balans: <b>{price_text(user.balance)}</b>"
        )

        # Foydalanuvchiga xabar
        try:
            await bot.send_message(
                target_tg_id,
                f"💰 Admin tomonidan balansingiz to'ldirildi: +{price_text(amount)}"
            )
        except Exception:
            pass

    except ValueError:
        await message.answer(f"❌ Foydalanuvchi topilmadi: {target_tg_id}")


@p2p_router.message(F.text == "/admin_stats")
async def admin_stats(message: Message):
    """Admin: oddiy statistika."""
    if not is_admin(message.from_user.id):
        return

    from database import get_session
    from sqlalchemy import select, func as sa_func
    from models import User, Transaction

    async with get_session() as session:
        total_users = (await session.execute(
            select(sa_func.count()).select_from(User)
        )).scalar() or 0

        total_topups = (await session.execute(
            select(sa_func.sum(Transaction.amount))
            .where(Transaction.tx_type == "topup", Transaction.status == "success")
        )).scalar() or 0

        total_purchases = (await session.execute(
            select(sa_func.count())
            .where(Transaction.tx_type == "purchase", Transaction.status == "success")
        )).scalar() or 0

    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users}</b>\n"
        f"💰 Jami to'lovlar: <b>{price_text(total_topups)}</b>\n"
        f"📄 Sotilgan hujjatlar: <b>{total_purchases}</b>"
    )
