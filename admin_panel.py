"""
Obektivka Bot — Admin Panel (Guruh asosida)

Xususiyatlar:
  1. Guruh ichida to'lovni tasdiqlash (race-condition himoyasi)
  2. Inline admin dashboard (/admin)
  3. Broadcast tizimi (flood-safe)
"""

import asyncio
import logging
from datetime import datetime
from typing import Set

from aiogram import Router, F, Bot
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
)
from sqlalchemy import select, func

from config import ADMIN_GROUP_ID, ADMIN_LIST, DOC_PRICE
from database import get_session, get_user, topup_balance
from models import User, Transaction, Document

logger = logging.getLogger(__name__)

admin_router = Router(name="admin_panel")

# Qayta ishlanayotgan to'lovlar — ikki marta bosishdan himoya
_processing_payments: Set[int] = set()


def price_text(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"


# ══════════════════════════════════════════════════════════════
#  ADMIN FILTER
# ══════════════════════════════════════════════════════════════

class IsAdmin(BaseFilter):
    """Foydalanuvchi admin ekanligini tekshiradi."""
    async def __call__(self, event: Message | CallbackQuery, bot: Bot) -> bool:
        user_id = event.from_user.id

        if user_id in ADMIN_LIST:
            return True

        if not ADMIN_GROUP_ID:
            return False

        try:
            member = await bot.get_chat_member(ADMIN_GROUP_ID, user_id)
            return member.status in ("creator", "administrator", "member")
        except (TelegramBadRequest, TelegramForbiddenError):
            return False
        except Exception as e:
            logger.warning(f"IsAdmin check xatosi: {e}")
            return False


# ══════════════════════════════════════════════════════════════
#  FSM STATES
# ══════════════════════════════════════════════════════════════

class AdminStates(StatesGroup):
    broadcast_waiting_message = State()
    broadcast_confirm = State()
    find_user_waiting_id = State()


# ══════════════════════════════════════════════════════════════
#  1. GURUH TO'LOV TASDIQLASH
# ══════════════════════════════════════════════════════════════

async def send_receipt_to_admin_group(
    bot: Bot,
    user_id: int,
    user_full_name: str,
    username: str | None,
    photo_file_id: str,
    amount: int,
) -> int | None:
    """Chekni admin guruhiga yuborish."""
    if not ADMIN_GROUP_ID:
        logger.critical("ADMIN_GROUP_ID sozlanmagan!")
        return None

    caption = (
        f"<b>Yangi to'lov cheki</b>\n"
        f"<i>tasdiqlash kutilmoqda</i>\n\n"
        f"<i>foydalanuvchi</i>\n"
        f"<b>{user_full_name}</b>\n\n"
        f"<i>id</i>\n"
        f"<code>{user_id}</code>\n\n"
        f"<i>username</i>\n"
        f"@{username or '—'}\n\n"
        f"<i>summa</i>\n"
        f"<b>{price_text(amount)}</b>\n\n"
        f"<i>vaqt</i>\n"
        f"<b>{datetime.now().strftime('%d.%m.%Y  %H:%M')}</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_approve:{user_id}:{amount}"),
            InlineKeyboardButton(text="❌ Rad qilish", callback_data=f"adm_reject:{user_id}:{amount}"),
        ],
    ])

    try:
        msg = await bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=photo_file_id,
            caption=caption,
            reply_markup=kb,
        )
        return msg.message_id
    except Exception as e:
        logger.error(f"Guruhga chek yuborib bo'lmadi: {e}", exc_info=True)
        return None


def _parse_payment_cb(data: str) -> tuple[str, int, int] | None:
    """adm_approve:USER_ID:AMOUNT → ('approve', user_id, amount)"""
    try:
        parts = data.split(":")
        action = parts[0].replace("adm_", "")
        return action, int(parts[1]), int(parts[2])
    except (IndexError, ValueError):
        return None


@admin_router.callback_query(F.data.startswith("adm_approve:"), IsAdmin())
async def admin_approve_payment(callback: CallbackQuery, bot: Bot):
    """Guruhda admin tasdiqlashni bosganda."""
    parsed = _parse_payment_cb(callback.data)
    if not parsed:
        await callback.answer("Noto'g'ri format", show_alert=True)
        return

    _, user_id, amount = parsed

    if user_id in _processing_payments:
        await callback.answer("Boshqa admin allaqachon ishlayapti...", show_alert=True)
        return

    _processing_payments.add(user_id)

    try:
        await callback.answer("Tasdiqlanmoqda...")

        admin_mention = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name
        new_caption = (
            f"{callback.message.caption}\n\n"
            f"━━━━━━━━━━━━━\n"
            f"✅ <b>TASDIQLANDI</b>\n"
            f"<i>admin</i>  ·  <b>{admin_mention}</b>\n"
            f"<i>vaqt</i>  ·  <b>{datetime.now().strftime('%H:%M')}</b>"
        )

        try:
            await callback.message.edit_caption(caption=new_caption, reply_markup=None)
        except TelegramBadRequest as e:
            logger.warning(f"Edit caption xatosi: {e}")
            await callback.answer("Xabar allaqachon tahrirlangan", show_alert=True)
            return

        tx = await topup_balance(
            tg_id=user_id,
            amount=amount,
            provider="p2p_card",
            provider_tx_id=f"grp_{callback.from_user.id}_{int(datetime.now().timestamp())}",
        )

        if not tx:
            logger.error(f"topup_balance None qaytardi: user={user_id}")
            await bot.send_message(
                ADMIN_GROUP_ID,
                f"⚠️ Xatolik: user <code>{user_id}</code> balansini yangilab bo'lmadi.",
                reply_to_message_id=callback.message.message_id,
            )
            return

        user = await get_user(user_id)
        balance_str = price_text(user.balance) if user else price_text(amount)

        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"<b>To'lov tasdiqlandi</b>\n"
                    f"<i>hisobingiz to'ldirildi</i>\n\n"
                    f"<i>qo'shildi</i>\n"
                    f"<b>+ {price_text(amount)}</b>\n\n"
                    f"<i>yangi balans</i>\n"
                    f"<b>{balance_str}</b>\n\n"
                    f"<i>Obektivka yaratish uchun  ·  /start</i>"
                ),
            )
        except TelegramForbiddenError:
            logger.warning(f"User {user_id} botni bloklagan.")
        except Exception as e:
            logger.error(f"Userga xabar yuborishda xato: {e}")

    finally:
        _processing_payments.discard(user_id)


@admin_router.callback_query(F.data.startswith("adm_reject:"), IsAdmin())
async def admin_reject_payment(callback: CallbackQuery, bot: Bot):
    """Guruhda admin rad qilishni bosganda."""
    parsed = _parse_payment_cb(callback.data)
    if not parsed:
        await callback.answer("Noto'g'ri format", show_alert=True)
        return

    _, user_id, amount = parsed

    if user_id in _processing_payments:
        await callback.answer("Boshqa admin ishlayapti...", show_alert=True)
        return

    _processing_payments.add(user_id)

    try:
        await callback.answer("Rad qilindi")

        admin_mention = f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name
        new_caption = (
            f"{callback.message.caption}\n\n"
            f"━━━━━━━━━━━━━\n"
            f"❌ <b>RAD QILINDI</b>\n"
            f"<i>admin</i>  ·  <b>{admin_mention}</b>\n"
            f"<i>vaqt</i>  ·  <b>{datetime.now().strftime('%H:%M')}</b>"
        )

        try:
            await callback.message.edit_caption(caption=new_caption, reply_markup=None)
        except TelegramBadRequest:
            await callback.answer("Xabar allaqachon tahrirlangan", show_alert=True)
            return

        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"<b>To'lov tasdiqlanmadi</b>\n"
                    f"<i>chek qabul qilinmadi</i>\n\n"
                    f"<i>mumkin bo'lgan sabablar</i>\n"
                    f"\u00a0\u00a0\u00a0Summa <b>{price_text(amount)}</b> emas\n"
                    f"\u00a0\u00a0\u00a0Karta raqami boshqa\n"
                    f"\u00a0\u00a0\u00a0Rasm aniq emas\n\n"
                    f"<i>Qayta urinish  ·  /start</i>"
                ),
            )
        except TelegramForbiddenError:
            logger.warning(f"User {user_id} botni bloklagan.")
        except Exception as e:
            logger.error(f"Reject xabari: {e}")

    finally:
        _processing_payments.discard(user_id)


# ══════════════════════════════════════════════════════════════
#  2. INLINE ADMIN DASHBOARD (/admin)
# ══════════════════════════════════════════════════════════════

async def _fetch_dashboard_stats() -> dict:
    """Dashboard uchun statistikalarni olish."""
    async with get_session() as session:
        total_users = await session.scalar(select(func.count(User.tg_id)))

        paid_users = await session.scalar(
            select(func.count(func.distinct(Transaction.user_tg_id)))
            .where(Transaction.tx_type == "topup", Transaction.status == "success")
        )

        total_revenue = await session.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(Transaction.tx_type == "topup", Transaction.status == "success")
        )

        total_docs = await session.scalar(select(func.count(Document.id)))

    return {
        "total_users": total_users or 0,
        "paid_users": paid_users or 0,
        "total_revenue": int(total_revenue or 0),
        "total_docs": total_docs or 0,
    }


def _dashboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🔍 Foydalanuvchi qidirish", callback_data="adm_find_user")],
        [InlineKeyboardButton(text="🔄 Yangilash", callback_data="adm_refresh")],
        [InlineKeyboardButton(text="🔙 Yopish", callback_data="adm_close")],
    ])


def _dashboard_text(stats: dict) -> str:
    conversion = (stats["paid_users"] / stats["total_users"] * 100) if stats["total_users"] else 0
    total_users_str = f"{stats['total_users']:,}".replace(",", " ")
    paid_users_str = f"{stats['paid_users']:,}".replace(",", " ")
    total_docs_str = f"{stats['total_docs']:,}".replace(",", " ")

    return (
        f"<b>⚙️ Admin Dashboard</b>\n"
        f"<i>umumiy statistika</i>\n\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"<i>jami foydalanuvchilar</i>\n"
        f"<b>👥 {total_users_str}</b>\n\n"
        f"<i>to'lov qilganlar</i>\n"
        f"<b>💳 {paid_users_str}</b>  ·  <i>{conversion:.1f}%</i>\n\n"
        f"<i>umumiy tushum</i>\n"
        f"<b>💰 {price_text(stats['total_revenue'])}</b>\n\n"
        f"<i>yaratilgan hujjatlar</i>\n"
        f"<b>📄 {total_docs_str}</b>\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<i>yangilangan  ·  {datetime.now().strftime('%H:%M:%S')}</i>"
    )


@admin_router.message(Command("admin"), IsAdmin())
async def cmd_admin(message: Message):
    try:
        stats = await _fetch_dashboard_stats()
        await message.answer(_dashboard_text(stats), reply_markup=_dashboard_keyboard())
    except Exception as e:
        logger.error(f"Dashboard xatosi: {e}", exc_info=True)
        await message.answer("❌ Statistikani olishda xato yuz berdi.")


@admin_router.callback_query(F.data == "adm_refresh", IsAdmin())
async def dashboard_refresh(callback: CallbackQuery):
    await callback.answer("Yangilanmoqda...")
    try:
        stats = await _fetch_dashboard_stats()
        await callback.message.edit_text(_dashboard_text(stats), reply_markup=_dashboard_keyboard())
    except TelegramBadRequest:
        pass
    except Exception as e:
        logger.error(f"Refresh xatosi: {e}")


@admin_router.callback_query(F.data == "adm_close", IsAdmin())
async def dashboard_close(callback: CallbackQuery):
    await callback.answer("Yopildi")
    try:
        await callback.message.delete()
    except Exception:
        pass


@admin_router.callback_query(F.data == "adm_find_user", IsAdmin())
async def find_user_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.find_user_waiting_id)
    await callback.message.answer(
        "<b>🔍 Foydalanuvchi qidirish</b>\n\n"
        "Telegram ID ni yuboring (faqat raqam):"
    )


@admin_router.message(AdminStates.find_user_waiting_id, IsAdmin())
async def find_user_process(message: Message, state: FSMContext):
    await state.clear()

    if not message.text or not message.text.strip().isdigit():
        await message.answer("❌ Noto'g'ri ID. Faqat raqam kiriting.")
        return

    user_id = int(message.text.strip())
    user = await get_user(user_id)

    if not user:
        await message.answer(f"❌ Foydalanuvchi <code>{user_id}</code> topilmadi.")
        return

    await message.answer(
        f"<b>👤 Foydalanuvchi topildi</b>\n\n"
        f"<i>id</i>\n<code>{user.tg_id}</code>\n\n"
        f"<i>ism</i>\n<b>{user.full_name or '—'}</b>\n\n"
        f"<i>username</i>\n@{user.username or '—'}\n\n"
        f"<i>balans</i>\n<b>{price_text(user.balance)}</b>\n\n"
        f"<i>hujjatlar</i>\n<b>{user.docs_count} ta</b>\n\n"
        f"<i>ro'yxatdan o'tgan</i>\n<b>{user.created_at.strftime('%d.%m.%Y')}</b>"
    )


# ══════════════════════════════════════════════════════════════
#  3. BROADCAST TIZIMI
# ══════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "adm_broadcast", IsAdmin())
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.broadcast_waiting_message)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✕ Bekor qilish", callback_data="adm_broadcast_cancel")],
    ])

    await callback.message.answer(
        "<b>📢 Broadcast yuborish</b>\n"
        "<i>barcha foydalanuvchilarga xabar</i>\n\n"
        "Yubormoqchi bo'lgan xabarni shu yerga yozing.\n"
        "<i>Matn, rasm, video yoki fayl bo'lishi mumkin.</i>\n\n"
        "<b>Eslatma:</b> Xabar aynan shu ko'rinishda yuboriladi.",
        reply_markup=kb,
    )


@admin_router.callback_query(F.data == "adm_broadcast_cancel", IsAdmin())
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Bekor qilindi")
    await callback.message.answer("❌ Broadcast bekor qilindi.")


@admin_router.message(AdminStates.broadcast_waiting_message, IsAdmin())
async def broadcast_preview(message: Message, state: FSMContext):
    """Adminga xabar preview-ni ko'rsatish."""
    await state.update_data(
        from_chat_id=message.chat.id,
        message_id=message.message_id,
    )
    await state.set_state(AdminStates.broadcast_confirm)

    async with get_session() as session:
        total = await session.scalar(select(func.count(User.tg_id))) or 0

    total_str = f"{total:,}".replace(",", " ")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Yuborish ({total_str} ga)", callback_data="adm_broadcast_confirm")],
        [InlineKeyboardButton(text="✕ Bekor qilish", callback_data="adm_broadcast_cancel")],
    ])

    await message.answer(
        f"<b>Yuqoridagi xabar yuboriladi</b>\n\n"
        f"<i>qabul qiluvchilar</i>\n"
        f"<b>{total_str} foydalanuvchi</b>\n\n"
        f"<i>Tasdiqlash uchun tugmani bosing.</i>",
        reply_markup=kb,
    )


@admin_router.callback_query(F.data == "adm_broadcast_confirm", IsAdmin())
async def broadcast_execute(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    from_chat_id = data.get("from_chat_id")
    source_msg_id = data.get("message_id")

    if not from_chat_id or not source_msg_id:
        await callback.answer("Ma'lumot yo'qolgan", show_alert=True)
        return

    await callback.answer("Yuborish boshlandi...")
    status_msg = await callback.message.answer("⏳ <b>Broadcast boshlandi...</b>")

    async with get_session() as session:
        result = await session.execute(select(User.tg_id))
        user_ids = [row[0] for row in result.all()]

    total = len(user_ids)
    sent = 0
    failed = 0
    blocked = 0

    for i, uid in enumerate(user_ids, 1):
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=from_chat_id,
                message_id=source_msg_id,
            )
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
        except TelegramRetryAfter as e:
            logger.warning(f"Flood limit: {e.retry_after}s kutilmoqda")
            await asyncio.sleep(e.retry_after)
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=source_msg_id)
                sent += 1
            except Exception:
                failed += 1
        except Exception as e:
            failed += 1
            logger.debug(f"Broadcast xatosi uid={uid}: {e}")

        await asyncio.sleep(0.05)

        if i % 25 == 0:
            try:
                await status_msg.edit_text(
                    f"⏳ <b>Broadcast davom etmoqda</b>\n\n"
                    f"<i>jarayon</i>\n<b>{i} / {total}</b>\n\n"
                    f"<i>yuborildi</i>  ·  <b>{sent}</b>\n"
                    f"<i>bloklangan</i>  ·  <b>{blocked}</b>\n"
                    f"<i>xato</i>  ·  <b>{failed}</b>"
                )
            except TelegramBadRequest:
                pass

    try:
        await status_msg.edit_text(
            f"<b>✅ Broadcast yakunlandi</b>\n\n"
            f"<i>jami</i>\n<b>{total}</b>\n\n"
            f"<i>yuborildi</i>\n<b>✓ {sent}</b>\n\n"
            f"<i>bloklangan</i>\n<b>🚫 {blocked}</b>\n\n"
            f"<i>xato</i>\n<b>⚠️ {failed}</b>"
        )
    except Exception:
        pass
