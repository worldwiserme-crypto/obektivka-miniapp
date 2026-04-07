"""
Obektivka Bot — Asosiy Bot Fayli (Kengaytirilgan)

Modullar:
  1. To'lov va Balans tizimi (Telegram Stars + Click/Payme)
  2. Preview (namuna rasm) + watermark
  3. Arxiv va Shablonlar (user retention)

Arxitektura:
  WebApp → /submit (JSON) → DOCX yaratish → Preview rasm →
  → Foydalanuvchiga namuna ko'rsatish → To'lov → Asl fayl berish
"""

import asyncio
import json
import logging
import os
from datetime import datetime

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
    BufferedInputFile, InputMediaPhoto
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from config import BOT_TOKEN, WEBHOOK_HOST, PORT, DOC_PRICE, STARS_PER_DOC, TEMP_DIR
from database import (
    init_db, get_or_create_user, get_user,
    topup_balance, deduct_balance,
    save_template, get_default_template,
    save_document, get_user_documents,
)
from generator import generate
from preview import generate_preview
from payment_fsm import payment_router
from admin_panel import admin_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(admin_router)
dp.include_router(payment_router)# P2P to'lov — birinchi (FSM handler'lar ustuvorlik oladi)
dp.include_router(router)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")


# ══════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ══════════════════════════════════════════════════════════════

# O'zbek tilidagi qisqa oy nomlari (premium sana formati uchun)
_MONTHS_UZ = {
    1: "yan", 2: "fev", 3: "mar", 4: "apr", 5: "may", 6: "iyn",
    7: "iyl", 8: "avg", 9: "sen", 10: "okt", 11: "noy", 12: "dek",
}


def price_text(amount: int) -> str:
    """Narxni chiroyli formatda ko'rsatish."""
    return f"{amount:,}".replace(",", " ") + " so'm"


def balance_text(user) -> str:
    return f"<b>{price_text(user.balance)}</b>"


def fmt_date(dt: datetime) -> str:
    """Premium sana formati: 21 apr 2026"""
    return f"{dt.day} {_MONTHS_UZ[dt.month]} {dt.year}"


# ──────────────────────────────────────────────
#  Vaqtinchalik fayl ma'lumotlarini xotirada saqlash
# ──────────────────────────────────────────────
_pending_docs: dict[int, dict] = {}


# ══════════════════════════════════════════════════════════════
#  1. /start — BOSHLASH
# ══════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(message: Message):
    tg_id = message.from_user.id
    user = await get_or_create_user(
        tg_id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    url = f"{WEBHOOK_HOST}/app?tg_id={tg_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="◆  Yangi obektivka yaratish",
            web_app=WebAppInfo(url=url)
        )],
        [
            InlineKeyboardButton(text="◷  Hisobim", callback_data="my_balance"),
            InlineKeyboardButton(text="◳  Hujjatlarim", callback_data="my_docs"),
        ],
        [InlineKeyboardButton(text="✦  Hisobni to'ldirish", callback_data="topup_menu")],
    ])

    await message.answer(
        f"<b>Obektivka</b>\n"
        f"<i>Rasmiy ma'lumotnoma generatori</i>\n\n"
        f"\u00a0\u00a0\u00a0Bir necha daqiqada to'liq\n"
        f"\u00a0\u00a0\u00a0rasmiy hujjat — Word formatda,\n"
        f"\u00a0\u00a0\u00a0ikkala alifboda.\n\n"
        f"<i>narx</i>\u00a0\u00a0\u00a0\u00a0\u00a0<b>{price_text(DOC_PRICE)}</b> / hujjat\n"
        f"<i>balans</i>\u00a0\u00a0\u00a0{balance_text(user)}\n\n"
        f"<i>Boshlash uchun pastdagi tugmani bosing.</i>",
        reply_markup=kb,
    )


# ══════════════════════════════════════════════════════════════
#  2. BALANS VA TO'LOV
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_balance")
async def show_balance(callback: CallbackQuery):
    user = await get_or_create_user(callback.from_user.id)
    await callback.answer()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✦  Hisobni to'ldirish", callback_data="topup_menu")],
        [InlineKeyboardButton(text="←  Bosh menyu", callback_data="back_main")],
    ])

    await callback.message.answer(
        f"<b>Hisobim</b>\n"
        f"<i>shaxsiy hisob holati</i>\n\n"
        f"<i>joriy balans</i>\n"
        f"{balance_text(user)}\n\n"
        f"<i>yaratilgan hujjatlar</i>\n"
        f"<b>{user.docs_count} ta</b>",
        reply_markup=kb,
    )

@router.callback_query(F.data == "topup_menu")
async def topup_menu(callback: CallbackQuery):
    """Hisobni to'ldirish — faqat Telegram Stars."""
    await callback.answer()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✦  Telegram Stars bilan to'lash", callback_data="topup_stars")],
        [InlineKeyboardButton(text="←  Bosh menyu", callback_data="back_main")],
    ])

    await callback.message.answer(
        "<b>Hisobni to'ldirish</b>\n"
        "<i>xavfsiz to'lov usuli</i>\n\n"
        "\u00a0\u00a0\u00a0Telegram Stars orqali bir bosishda\n"
        "\u00a0\u00a0\u00a0to'lang. Tasdiqlash darhol amalga\n"
        "\u00a0\u00a0\u00a0oshadi.\n\n"
        f"<i>narx</i>  ·  <b>{price_text(DOC_PRICE)}</b> / hujjat",
        reply_markup=kb,
    )

# ─── Telegram Stars bilan to'lov ───

@router.callback_query(F.data == "topup_stars")
async def topup_with_stars(callback: CallbackQuery):
    """Telegram Stars invoice yaratish."""
    await callback.answer()
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Obektivka yaratish",
        description="Bitta rasmiy obektivka hujjati uchun to'lov",
        payload=f"obektivka_{callback.from_user.id}_{int(datetime.now().timestamp())}",
        currency="XTR",
        prices=[LabeledPrice(label="Obektivka", amount=STARS_PER_DOC)],
    )


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery):
    """Stars to'lovini tasdiqlash."""
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """Stars to'lovi muvaffaqiyatli bo'lganda."""
    tg_id = message.from_user.id
    payment = message.successful_payment

    await topup_balance(
        tg_id=tg_id,
        amount=DOC_PRICE,
        provider="telegram_stars",
        provider_tx_id=payment.telegram_payment_charge_id,
    )

    user = await get_user(tg_id)
    await message.answer(
        f"<b>To'lov qabul qilindi</b>\n"
        f"<i>tranzaksiya muvaffaqiyatli yakunlandi</i>\n\n"
        f"<i>qabul qilindi</i>\n"
        f"<b>{STARS_PER_DOC} ⭐</b>\n\n"
        f"<i>yangi balans</i>\n"
        f"{balance_text(user)}\n\n"
        f"<i>Endi obektivkangizni yaratishingiz mumkin.</i>"
    )

    await _try_deliver_pending(tg_id)


# ─── Click/Payme to'lov (webhook callback) ───

async def payment_webhook(request):
    try:
        body = await request.json()
        action = body.get("action")
        tg_id = int(body.get("merchant_trans_id", 0))
        amount = int(body.get("amount", 0))
        tx_id = body.get("click_trans_id") or body.get("id")

        if action == "prepare":
            user = await get_user(tg_id)
            if not user:
                return web.json_response({"error": -5, "error_note": "User not found"})
            return web.json_response({"error": 0, "error_note": "Success"})

        elif action == "complete":
            await topup_balance(tg_id, amount, provider="click", provider_tx_id=str(tx_id))

            user = await get_user(tg_id)
            try:
                await bot.send_message(
                    tg_id,
                    f"<b>Hisob to'ldirildi</b>\n"
                    f"<i>tranzaksiya muvaffaqiyatli</i>\n\n"
                    f"<i>qo'shildi</i>\n"
                    f"<b>+ {price_text(amount)}</b>\n\n"
                    f"<i>yangi balans</i>\n"
                    f"{balance_text(user)}"
                )
                await _try_deliver_pending(tg_id)
            except Exception:
                pass

            return web.json_response({"error": 0, "error_note": "Success"})

    except Exception as e:
        logger.error(f"Payment webhook xatosi: {e}", exc_info=True)
        return web.json_response({"error": -1, "error_note": str(e)})


# ══════════════════════════════════════════════════════════════
#  3. WEBAPP /submit — PREVIEW VA TO'LOV OQIMI
# ══════════════════════════════════════════════════════════════

async def serve_app(request):
    tg_id = request.rel_url.query.get("tg_id", "")
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__TG_ID__", str(tg_id))
    return web.Response(text=html, content_type="text/html")


async def serve_template(request):
    tg_id = int(request.rel_url.query.get("tg_id", 0))
    if not tg_id:
        return web.json_response({"ok": False, "data": None})

    data = await get_default_template(tg_id)
    return web.json_response({"ok": True, "data": data})


async def submit(request):
    tg_id = 0
    try:
        body = await request.json()
        tg_id = int(body.get("tg_id", 0))
        data = body.get("data", {})
        script = body.get("script", "lat")

        if not tg_id:
            return web.json_response({"ok": False, "error": "tg_id yo'q"})

        logger.info(f"Submit: tg_id={tg_id}, fullname={data.get('fullname')}")

        template_data = {k: v for k, v in data.items() if k != "photo_base64"}
        await save_template(tg_id, template_data, name=data.get("fullname"))

        loading_msg = await bot.send_message(
            tg_id,
            "<b>Hujjat tayyorlanmoqda</b>\n"
            "<i>bir necha soniya kuting</i>\n\n"
            "\u00a0\u00a0\u00a0Ma'lumotlaringiz qabul qilindi.\n"
            "\u00a0\u00a0\u00a0Word faylni shakllantiramiz va\n"
            "\u00a0\u00a0\u00a0namuna ko'rinishini tayyorlaymiz."
        )

        os.makedirs(TEMP_DIR, exist_ok=True)
        docx_path = f"{TEMP_DIR}/{tg_id}_{int(datetime.now().timestamp())}.docx"
        generate(data, docx_path, script=script)

        try:
            preview_images = await generate_preview(docx_path)
        except Exception as e:
            logger.warning(f"Preview yaratib bo'lmadi: {e}")
            preview_images = []

        await bot.delete_message(tg_id, loading_msg.message_id)

        _pending_docs[tg_id] = {
            "docx_path": docx_path,
            "data": data,
            "script": script,
            "created_at": datetime.now(),
        }

        user = await get_or_create_user(tg_id)

        if user.has_enough_balance(DOC_PRICE):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"◆  Hisobdan to'lash  ·  {price_text(DOC_PRICE)}",
                    callback_data="pay_from_balance"
                )],
                [InlineKeyboardButton(text="✕  Bekor qilish", callback_data="cancel_doc")],
            ])
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"◆  Karta orqali to'lash  ·  {price_text(DOC_PRICE)}",
                    callback_data="p2p_pay"
                )],
                [InlineKeyboardButton(
                    text=f"✦  Telegram Stars  ·  {STARS_PER_DOC} ⭐",
                    callback_data="topup_stars"
                )],
                [InlineKeyboardButton(text="✕  Bekor qilish", callback_data="cancel_doc")],
            ])

        if preview_images:
            media_group = []
            for i, img_bytes in enumerate(preview_images[:2]):
                caption = None
                if i == 0:
                    script_label = "Кирилл" if script == "cyr" else "Lotin"
                    caption = (
                        f"<b>Namuna tayyor</b>\n"
                        f"<i>quyida hujjatingizning ko'rinishi</i>\n\n"
                        f"<i>kim uchun</i>\n"
                        f"<b>{data.get('fullname', '—')}</b>\n\n"
                        f"<i>alifbo</i>\n"
                        f"<b>{script_label}</b>\n\n"
                        f"<i>narx</i>\n"
                        f"<b>{price_text(DOC_PRICE)}</b>\n\n"
                        f"<i>balans</i>\n"
                        f"<b>{price_text(user.balance)}</b>"
                    )
                media_group.append(InputMediaPhoto(
                    media=BufferedInputFile(img_bytes, filename=f"preview_{i+1}.jpg"),
                    caption=caption, parse_mode=ParseMode.HTML if caption else None,
                ))

            await bot.send_media_group(tg_id, media=media_group)
            await bot.send_message(
                tg_id,
                "<b>Asl nusxani olish</b>\n"
                "<i>to'lov usulini tanlang</i>\n\n"
                "\u00a0\u00a0\u00a0Yuqoridagi rasmlar — namuna.\n"
                "\u00a0\u00a0\u00a0To'lovdan so'ng sizga\n"
                "\u00a0\u00a0\u00a0watermark<b>siz</b> Word fayl\n"
                "\u00a0\u00a0\u00a0yuboriladi.",
                reply_markup=kb,
            )
        else:
            await bot.send_message(
                tg_id,
                f"<b>Hujjat tayyor</b>\n"
                f"<i>to'lovdan so'ng yuboriladi</i>\n\n"
                f"<i>kim uchun</i>\n"
                f"<b>{data.get('fullname', '—')}</b>\n\n"
                f"<i>narx</i>\n"
                f"<b>{price_text(DOC_PRICE)}</b>\n\n"
                f"<i>balans</i>\n"
                f"<b>{price_text(user.balance)}</b>",
                reply_markup=kb,
            )

        return web.json_response({"ok": True})

    except Exception as e:
        logger.error(f"Submit xatosi: {e}", exc_info=True)
        if tg_id:
            try:
                await bot.send_message(
                    tg_id,
                    f"<b>Xatolik yuz berdi</b>\n"
                    f"<i>hujjatni tayyorlab bo'lmadi</i>\n\n"
                    f"<i>sabab</i>\n"
                    f"<code>{str(e)[:200]}</code>\n\n"
                    f"<i>Iltimos, /start orqali qayta boshlang.</i>"
                )
            except Exception:
                pass
        return web.json_response({"ok": False, "error": str(e)})


# ══════════════════════════════════════════════════════════════
#  4. TO'LOV TASDIQLASH VA FAYL BERISH
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "pay_from_balance")
async def pay_from_balance(callback: CallbackQuery):
    tg_id = callback.from_user.id
    await callback.answer()

    pending = _pending_docs.get(tg_id)
    if not pending:
        await callback.message.answer(
            "<b>Hujjat topilmadi</b>\n"
            "<i>kutayotgan namuna mavjud emas</i>\n\n"
            "\u00a0\u00a0\u00a0Hujjat eskirgan yoki tizimdan\n"
            "\u00a0\u00a0\u00a0o'chirilgan bo'lishi mumkin.\n\n"
            "<i>Yangi obektivka yaratish uchun /start bosing.</i>"
        )
        return

    tx = await deduct_balance(tg_id, DOC_PRICE, description="Obektivka yaratish")
    if not tx:
        user = await get_user(tg_id)
        await callback.message.answer(
            f"<b>Mablag' yetarli emas</b>\n"
            f"<i>balansingizni to'ldirishingiz kerak</i>\n\n"
            f"<i>joriy balans</i>\n"
            f"{balance_text(user)}\n\n"
            f"<i>kerak</i>\n"
            f"<b>{price_text(DOC_PRICE)}</b>\n\n"
            f"<i>yetishmaydi</i>\n"
            f"<b>{price_text(DOC_PRICE - user.balance)}</b>"
        )
        return

    await _deliver_document(tg_id, pending)


async def _try_deliver_pending(tg_id: int):
    pending = _pending_docs.get(tg_id)
    if not pending:
        return

    user = await get_user(tg_id)
    if not user or not user.has_enough_balance(DOC_PRICE):
        return

    tx = await deduct_balance(tg_id, DOC_PRICE, description="Obektivka yaratish (auto)")
    if tx:
        await _deliver_document(tg_id, pending)


async def _deliver_document(tg_id: int, pending: dict):
    docx_path = pending["docx_path"]
    data = pending["data"]
    script = pending["script"]

    try:
        fullname = data.get("fullname", "obektivka")
        script_label = "Кирилл" if script == "cyr" else "Lotin"

        with open(docx_path, "rb") as f:
            file_data = f.read()

        result = await bot.send_document(
            tg_id,
            document=BufferedInputFile(file_data, filename=f"{fullname}.docx"),
            caption=(
                f"<b>Obektivkangiz tayyor</b>\n"
                f"<i>asl nusxa, watermark yo'q</i>\n\n"
                f"<i>format</i>\n"
                f"<b>Word (.docx)</b>\n\n"
                f"<i>alifbo</i>\n"
                f"<b>{script_label}</b>\n\n"
                f"<i>Hujjat «Hujjatlarim» bo'limida saqlandi —\n"
                f"istalgan vaqt qayta yuklab olishingiz mumkin.</i>"
            ),
        )

        if result.document:
            await save_document(
                tg_id=tg_id,
                file_id=result.document.file_id,
                file_name=f"{fullname}.docx",
                fullname=fullname,
                script=script,
                price_paid=DOC_PRICE,
            )

        _pending_docs.pop(tg_id, None)
        try:
            os.remove(docx_path)
        except OSError:
            pass

        user = await get_user(tg_id)
        if user:
            await bot.send_message(
                tg_id,
                f"<i>qoldiq balans</i>\n"
                f"{balance_text(user)}"
            )

    except Exception as e:
        logger.error(f"Fayl berish xatosi: {e}", exc_info=True)
        await bot.send_message(
            tg_id,
            f"<b>Faylni yuborib bo'lmadi</b>\n"
            f"<i>texnik nosozlik yuz berdi</i>\n\n"
            f"<i>sabab</i>\n"
            f"<code>{str(e)[:200]}</code>\n\n"
            f"<i>Hisobingizdan summa yechilmadi.\n"
            f"Qayta urinib ko'ring.</i>"
        )


@router.callback_query(F.data == "cancel_doc")
async def cancel_doc(callback: CallbackQuery):
    tg_id = callback.from_user.id
    pending = _pending_docs.pop(tg_id, None)
    if pending:
        try:
            os.remove(pending["docx_path"])
        except OSError:
            pass

    await callback.answer("Bekor qilindi")
    await callback.message.answer(
        "<b>Bekor qilindi</b>\n"
        "<i>hujjat yaratish to'xtatildi</i>\n\n"
        "\u00a0\u00a0\u00a0Hech qanday summa yechilmadi.\n"
        "\u00a0\u00a0\u00a0Istalgan vaqt qayta boshlashingiz\n"
        "\u00a0\u00a0\u00a0mumkin.\n\n"
        "<i>Yangi obektivka uchun /start bosing.</i>"
    )


# ══════════════════════════════════════════════════════════════
#  5. ARXIV — "MENING HUJJATLARIM"
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_docs")
async def my_docs_handler(callback: CallbackQuery):
    await callback.answer()
    await send_docs_list(callback.from_user.id)


@router.message(Command("docs"))
async def cmd_docs(message: Message):
    await send_docs_list(message.from_user.id)


async def send_docs_list(tg_id: int):
    docs = await get_user_documents(tg_id, limit=10)

    if not docs:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◆  Birinchi hujjatni yaratish", callback_data="back_main")],
        ])
        await bot.send_message(
            tg_id,
            "<b>Hujjatlarim</b>\n"
            "<i>shaxsiy arxiv</i>\n\n"
            "\u00a0\u00a0\u00a0Hozircha hech qanday hujjat\n"
            "\u00a0\u00a0\u00a0yaratilmagan.\n\n"
            "<i>Birinchi obektivkangizni yarating —\n"
            "u shu yerda saqlanadi.</i>",
            reply_markup=kb,
        )
        return

    text = (
        f"<b>Hujjatlarim</b>\n"
        f"<i>oxirgi {len(docs)} ta hujjat</i>\n\n"
    )
    buttons = []
    for i, doc in enumerate(docs, 1):
        date_str = fmt_date(doc.created_at)
        script_label = "Кирилл" if doc.script == "cyr" else "Lotin"
        text += (
            f"<b>{i}.  {doc.fullname or '—'}</b>\n"
            f"\u00a0\u00a0\u00a0\u00a0<i>{date_str}  ·  {script_label}</i>\n\n"
        )
        buttons.append([InlineKeyboardButton(
            text=f"⬇  {i}.  {doc.fullname or 'Hujjat'}",
            callback_data=f"dl_doc_{doc.id}",
        )])

    buttons.append([InlineKeyboardButton(text="←  Bosh menyu", callback_data="back_main")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await bot.send_message(tg_id, text, reply_markup=kb)


@router.callback_query(F.data.startswith("dl_doc_"))
async def download_doc(callback: CallbackQuery):
    tg_id = callback.from_user.id
    doc_id = int(callback.data.replace("dl_doc_", ""))
    await callback.answer()

    docs = await get_user_documents(tg_id)
    doc = next((d for d in docs if d.id == doc_id), None)

    if not doc:
        await callback.message.answer(
            "<b>Hujjat topilmadi</b>\n"
            "<i>arxivda mavjud emas</i>"
        )
        return

    try:
        await bot.send_document(
            tg_id,
            document=doc.file_id,
            caption=(
                f"<b>{doc.fullname}</b>\n"
                f"<i>{fmt_date(doc.created_at)}</i>"
            ),
        )
    except Exception as e:
        logger.error(f"Arxivdan yuklab bo'lmadi: {e}")
        await callback.message.answer(
            "<b>Faylni yuklab bo'lmadi</b>\n"
            "<i>hujjat eskirgan bo'lishi mumkin</i>\n\n"
            "\u00a0\u00a0\u00a0Telegram fayl serverida hujjat\n"
            "\u00a0\u00a0\u00a0muddati o'tib ketgan.\n\n"
            "<i>Yangisini yarating — /start</i>"
        )


# ══════════════════════════════════════════════════════════════
#  6. QOLGAN BUYRUQLAR
# ══════════════════════════════════════════════════════════════

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    user = await get_or_create_user(message.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✦  Hisobni to'ldirish", callback_data="topup_menu")],
    ])

    await message.answer(
        f"<b>Hisobim</b>\n"
        f"<i>shaxsiy hisob holati</i>\n\n"
        f"<i>joriy balans</i>\n"
        f"{balance_text(user)}\n\n"
        f"<i>yaratilgan hujjatlar</i>\n"
        f"<b>{user.docs_count} ta</b>",
        reply_markup=kb,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        f"<b>Yordam</b>\n"
        f"<i>bot bilan ishlash bo'yicha qo'llanma</i>\n\n"
        f"<b>Buyruqlar</b>\n\n"
        f"<i>/start</i>\n"
        f"Bosh menyu va yangi hujjat yaratish\n\n"
        f"<i>/balance</i>\n"
        f"Hisobingizdagi mablag'\n\n"
        f"<i>/docs</i>\n"
        f"Yaratilgan hujjatlar arxivi\n\n"
        f"<i>/help</i>\n"
        f"Ushbu sahifa\n\n"
        f"<b>Narxlar</b>\n\n"
        f"<i>bitta obektivka</i>\n"
        f"<b>{price_text(DOC_PRICE)}</b>"
    )


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    await callback.answer()
    await cmd_start(callback.message)


# ══════════════════════════════════════════════════════════════
#  7. APP ISHGA TUSHIRISH
# ══════════════════════════════════════════════════════════════

async def main():
    await init_db()

    app = web.Application()

    app.router.add_get("/app", serve_app)
    app.router.add_get("/api/template", serve_template)
    app.router.add_post("/submit", submit)
    app.router.add_post("/payment/callback", payment_webhook)

    await bot.set_webhook(
    f"{WEBHOOK_HOST}/webhook",
    allowed_updates=[
        "message",
        "callback_query",
        "pre_checkout_query",
        "successful_payment",
    ],
    drop_pending_updates=True,
)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logger.info(f"Bot ishlamoqda: {WEBHOOK_HOST}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
