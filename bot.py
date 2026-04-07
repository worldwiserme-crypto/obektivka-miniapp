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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(payment_router)# P2P to'lov — birinchi (FSM handler'lar ustuvorlik oladi)
dp.include_router(router)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")


# ══════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ══════════════════════════════════════════════════════════════

def price_text(amount: int) -> str:
    """Narxni chiroyli formatda ko'rsatish."""
    return f"{amount:,}".replace(",", " ") + " so'm"


def balance_text(user) -> str:
    return f"<b>{price_text(user.balance)}</b>"


# ──────────────────────────────────────────────
#  Vaqtinchalik fayl ma'lumotlarini xotirada saqlash
#  (foydalanuvchi preview ko'rgandan keyin to'lov qilguncha)
#  Production'da Redis ishlatish tavsiya qilinadi.
# ──────────────────────────────────────────────
_pending_docs: dict[int, dict] = {}
# Struktura: { tg_id: { "docx_path": str, "data": dict, "script": str, "created_at": datetime } }


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
            text="📝  Obektivkani to'ldirish",
            web_app=WebAppInfo(url=url)
        )],
        [
            InlineKeyboardButton(text="💰  Balans", callback_data="my_balance"),
            InlineKeyboardButton(text="📂  Hujjatlarim", callback_data="my_docs"),
        ],
        [InlineKeyboardButton(text="💳  Hisobni to'ldirish", callback_data="topup_menu")],
    ])

    await message.answer(
        f"<b>Obektivka Bot</b>\n"
        f"<i>Rasmiy ma'lumotnoma — bir necha daqiqada</i>\n\n"
        f"Forma orqali ma'lumotlaringizni kiriting va tayyor Word hujjatini oling.\n\n"
        f"Bitta hujjat   <b>{price_text(DOC_PRICE)}</b>\n"
        f"Balansingiz   {balance_text(user)}",
        reply_markup=kb,
    )


# ══════════════════════════════════════════════════════════════
#  2. BALANS VA TO'LOV
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_balance")
async def show_balance(callback: CallbackQuery):
    user = await get_or_create_user(callback.from_user.id)
    await callback.answer()
    await callback.message.answer(
        f"<b>Hisobingiz</b>\n\n"
        f"Joriy balans   {balance_text(user)}\n"
        f"Yaratilgan hujjatlar   <b>{user.docs_count}</b>"
    )


@router.callback_query(F.data == "topup_menu")
async def topup_menu(callback: CallbackQuery):
    """To'ldirish variantlarini ko'rsatish — P2P (karta-ga o'tkazma)."""
    await callback.answer()

    amounts = [5_000, 10_000, 25_000, 50_000]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"  {price_text(a)}  ",
            callback_data=f"p2p_topup_{a}"       # ← P2P router'ga yo'naltiriladi
        )] for a in amounts
    ] + [
        [InlineKeyboardButton(text="⭐  Telegram Stars bilan to'lash", callback_data="topup_stars")],
        [InlineKeyboardButton(text="←  Ortga", callback_data="back_main")],
    ])

    await callback.message.answer(
        "<b>Hisobni to'ldirish</b>\n\n"
        "Karta orqali xohlagan summani tanlang.\n"
        "<i>To'lov bir necha daqiqa ichida tasdiqlanadi.</i>",
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
        currency="XTR",  # Telegram Stars valyutasi
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

    # Balansga qo'shish
    await topup_balance(
        tg_id=tg_id,
        amount=DOC_PRICE,  # 1 Star = 1 hujjat narxiga teng
        provider="telegram_stars",
        provider_tx_id=payment.telegram_payment_charge_id,
    )

    user = await get_user(tg_id)
    await message.answer(
        f"✅  <b>To'lov qabul qilindi</b>\n\n"
        f"Qo'shildi   <b>{STARS_PER_DOC} ⭐</b>\n"
        f"Balansingiz   {balance_text(user)}"
    )

    # Agar kutayotgan hujjat bo'lsa, avtomatik berish
    await _try_deliver_pending(tg_id)


# ─── Click/Payme to'lov (webhook callback) ───

async def payment_webhook(request):
    """
    Click yoki Payme serveridan keladigan callback.
    
    Har bir provayderning o'z formati bor. Bu yerda umumiy mantiq berilgan.
    Haqiqiy integratsiyada provayder hujjatiga qarab moslashtiring.
    """
    try:
        body = await request.json()
        action = body.get("action")  # "prepare" yoki "complete"
        tg_id = int(body.get("merchant_trans_id", 0))
        amount = int(body.get("amount", 0))
        tx_id = body.get("click_trans_id") or body.get("id")

        if action == "prepare":
            # Foydalanuvchini tekshirish
            user = await get_user(tg_id)
            if not user:
                return web.json_response({"error": -5, "error_note": "User not found"})
            return web.json_response({"error": 0, "error_note": "Success"})

        elif action == "complete":
            # Hisobni to'ldirish
            await topup_balance(tg_id, amount, provider="click", provider_tx_id=str(tx_id))

            # Foydalanuvchiga xabar
            user = await get_user(tg_id)
            try:
                await bot.send_message(
                    tg_id,
                    f"✅  <b>Hisobingiz to'ldirildi</b>\n\n"
                    f"Qo'shildi   <b>+{price_text(amount)}</b>\n"
                    f"Balansingiz   {balance_text(user)}"
                )
                # Kutayotgan hujjatni berish
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
    """WebApp sahifasini ko'rsatish + shablon ma'lumotlarini yuklash."""
    tg_id = request.rel_url.query.get("tg_id", "")
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("__TG_ID__", str(tg_id))
    return web.Response(text=html, content_type="text/html")


async def serve_template(request):
    """
    WebApp uchun API: foydalanuvchining saqlangan shablonini qaytarish.
    GET /api/template?tg_id=12345
    """
    tg_id = int(request.rel_url.query.get("tg_id", 0))
    if not tg_id:
        return web.json_response({"ok": False, "data": None})

    data = await get_default_template(tg_id)
    return web.json_response({"ok": True, "data": data})


async def submit(request):
    """
    WebApp'dan ma'lumot qabul qilish.
    
    OQIM:
      1. Ma'lumotni qabul qilish
      2. Shablonni bazaga saqlash
      3. DOCX faylni generatsiya qilish
      4. Preview rasmlarni yaratish (watermark bilan)
      5. Foydalanuvchiga preview + to'lov tugmasini yuborish
    """
    tg_id = 0
    try:
        body = await request.json()
        tg_id = int(body.get("tg_id", 0))
        data = body.get("data", {})
        script = body.get("script", "lat")

        if not tg_id:
            return web.json_response({"ok": False, "error": "tg_id yo'q"})

        logger.info(f"Submit: tg_id={tg_id}, fullname={data.get('fullname')}")

        # 1-qadam: Shablonni saqlash (kelgusi safar uchun)
        # photo_base64 ni saqlamaslik (katta hajm)
        template_data = {k: v for k, v in data.items() if k != "photo_base64"}
        await save_template(tg_id, template_data, name=data.get("fullname"))

        loading_msg = await bot.send_message(
            tg_id,
            "⏳  <b>Hujjat tayyorlanmoqda</b>\n"
            "<i>Bir necha soniya kuting...</i>"
        )

        # 2-qadam: DOCX yaratish
        os.makedirs(TEMP_DIR, exist_ok=True)
        docx_path = f"{TEMP_DIR}/{tg_id}_{int(datetime.now().timestamp())}.docx"
        generate(data, docx_path, script=script)

        # 3-qadam: Preview rasmlarni yaratish
        try:
            preview_images = await generate_preview(docx_path)
        except Exception as e:
            logger.warning(f"Preview yaratib bo'lmadi, to'g'ridan-to'g'ri to'lov so'raladi: {e}")
            preview_images = []

        await bot.delete_message(tg_id, loading_msg.message_id)

        # 4-qadam: Xotirada saqlash (to'lov kutish uchun)
        _pending_docs[tg_id] = {
            "docx_path": docx_path,
            "data": data,
            "script": script,
            "created_at": datetime.now(),
        }

        # 5-qadam: Balans tekshirish
        user = await get_or_create_user(tg_id)

        if user.has_enough_balance(DOC_PRICE):
            # Yetarli mablag' bor — darhol berish variantini taklif qilish
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"✅  Balansdan to'lash  ·  {price_text(DOC_PRICE)}",
                    callback_data="pay_from_balance"
                )],
                [InlineKeyboardButton(text="✕  Bekor qilish", callback_data="cancel_doc")],
            ])
        else:
            # Mablag' yetarli emas — P2P to'lov asosiy variant
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"💳  Karta orqali to'lash  ·  {price_text(DOC_PRICE)}",
                    callback_data="p2p_pay"               # ← P2P to'lov
                )],
                [InlineKeyboardButton(
                    text=f"⭐  Telegram Stars  ·  {STARS_PER_DOC} ⭐",
                    callback_data="topup_stars"
                )],
                [InlineKeyboardButton(text="✕  Bekor qilish", callback_data="cancel_doc")],
            ])

        # Preview rasmlarni yuborish
        if preview_images:
            media_group = []
            for i, img_bytes in enumerate(preview_images[:2]):  # Faqat 2 sahifa
                caption = None
                if i == 0:
                    script_label = "Кирилл" if script == "cyr" else "Lotin"
                    caption = (
                        f"<b>Namuna tayyor</b>\n"
                        f"<i>Quyida hujjatingizning ko'rinishi</i>\n\n"
                        f"Kim uchun   <b>{data.get('fullname', '—')}</b>\n"
                        f"Alifbo   <b>{script_label}</b>\n\n"
                        f"Narx   <b>{price_text(DOC_PRICE)}</b>\n"
                        f"Balans   <b>{price_text(user.balance)}</b>"
                    )
                media_group.append(InputMediaPhoto(
                    media=BufferedInputFile(img_bytes, filename=f"preview_{i+1}.jpg"),
                    caption=caption, parse_mode=ParseMode.HTML if caption else None,
                ))

            await bot.send_media_group(tg_id, media=media_group)
            await bot.send_message(
                tg_id,
                "Asl nusxani olish uchun to'lov usulini tanlang",
                reply_markup=kb,
            )
        else:
            # Preview bo'lmasa — faqat matn bilan
            await bot.send_message(
                tg_id,
                f"<b>Hujjat tayyor</b>\n\n"
                f"Kim uchun   <b>{data.get('fullname', '—')}</b>\n\n"
                f"Narx   <b>{price_text(DOC_PRICE)}</b>\n"
                f"Balans   <b>{price_text(user.balance)}</b>",
                reply_markup=kb,
            )

        return web.json_response({"ok": True})

    except Exception as e:
        logger.error(f"Submit xatosi: {e}", exc_info=True)
        if tg_id:
            try:
                await bot.send_message(
                    tg_id,
                    f"⚠️  <b>Xatolik yuz berdi</b>\n\n"
                    f"<i>{str(e)[:300]}</i>\n\n"
                    f"Qayta urinib ko'ring yoki /start bosing."
                )
            except Exception:
                pass
        return web.json_response({"ok": False, "error": str(e)})


# ══════════════════════════════════════════════════════════════
#  4. TO'LOV TASDIQLASH VA FAYL BERISH
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "pay_from_balance")
async def pay_from_balance(callback: CallbackQuery):
    """Balansdan to'lov yechib, asl faylni berish."""
    tg_id = callback.from_user.id
    await callback.answer()

    pending = _pending_docs.get(tg_id)
    if not pending:
        await callback.message.answer(
            "⚠️  <b>Kutayotgan hujjat topilmadi</b>\n\n"
            "<i>Formani qaytadan to'ldiring.</i>"
        )
        return

    # Balansdan yechish (atomik)
    tx = await deduct_balance(tg_id, DOC_PRICE, description="Obektivka yaratish")
    if not tx:
        user = await get_user(tg_id)
        await callback.message.answer(
            f"⚠️  <b>Mablag' yetarli emas</b>\n\n"
            f"Joriy balans   {balance_text(user)}\n"
            f"Kerakli summa   <b>{price_text(DOC_PRICE)}</b>\n\n"
            f"<i>Hisobingizni to'ldiring va qayta urinib ko'ring.</i>"
        )
        return

    # Faylni berish
    await _deliver_document(tg_id, pending)


async def _try_deliver_pending(tg_id: int):
    """
    Agar to'lov muvaffaqiyatli bo'lsa va kutayotgan hujjat bo'lsa,
    avtomatik berish.
    """
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
    """Asl DOCX faylni foydalanuvchiga yuborish va arxivga saqlash."""
    docx_path = pending["docx_path"]
    data = pending["data"]
    script = pending["script"]

    try:
        fullname = data.get("fullname", "obektivka")
        script_label = "Кирилл" if script == "cyr" else "Lotin"

        with open(docx_path, "rb") as f:
            file_data = f.read()

        # Faylni Telegram orqali yuborish
        result = await bot.send_document(
            tg_id,
            document=BufferedInputFile(file_data, filename=f"{fullname}.docx"),
            caption=(
                f"✅  <b>Obektivkangiz tayyor</b>\n\n"
                f"Format   <b>Word (.docx)</b>\n"
                f"Alifbo   <b>{script_label}</b>\n\n"
                f"<i>Hujjat «Hujjatlarim» bo'limida saqlandi.</i>"
            ),
        )

        # Arxivga saqlash (file_id bilan)
        if result.document:
            await save_document(
                tg_id=tg_id,
                file_id=result.document.file_id,
                file_name=f"{fullname}.docx",
                fullname=fullname,
                script=script,
                price_paid=DOC_PRICE,
            )

        # Vaqtinchalik fayllarni tozalash
        _pending_docs.pop(tg_id, None)
        try:
            os.remove(docx_path)
        except OSError:
            pass

        user = await get_user(tg_id)
        if user:
            await bot.send_message(
                tg_id,
                f"Qoldiq balans   {balance_text(user)}"
            )

    except Exception as e:
        logger.error(f"Fayl berish xatosi: {e}", exc_info=True)
        await bot.send_message(
            tg_id,
            f"⚠️  <b>Faylni yuborishda xatolik</b>\n\n"
            f"<i>{str(e)[:200]}</i>"
        )


@router.callback_query(F.data == "cancel_doc")
async def cancel_doc(callback: CallbackQuery):
    """Hujjat yaratishni bekor qilish."""
    tg_id = callback.from_user.id
    pending = _pending_docs.pop(tg_id, None)
    if pending:
        try:
            os.remove(pending["docx_path"])
        except OSError:
            pass

    await callback.answer("Bekor qilindi", show_alert=False)
    await callback.message.answer(
        "✕  <b>Bekor qilindi</b>\n\n"
        "<i>Yangi hujjat yaratish uchun /start bosing.</i>"
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
    """Foydalanuvchining hujjatlari ro'yxatini ko'rsatish."""
    docs = await get_user_documents(tg_id, limit=10)

    if not docs:
        await bot.send_message(
            tg_id,
            "<b>Hujjatlarim</b>\n\n"
            "Hozircha hech qanday hujjat yo'q.\n\n"
            "<i>Birinchi obektivkangizni yaratish uchun /start bosing.</i>"
        )
        return

    text = "<b>Hujjatlarim</b>\n<i>Oxirgi 10 ta hujjat</i>\n\n"
    buttons = []
    for i, doc in enumerate(docs, 1):
        date_str = doc.created_at.strftime("%d.%m.%Y")
        script_label = "Кир" if doc.script == "cyr" else "Lot"
        text += f"{i}.  <b>{doc.fullname or '—'}</b>\n"
        text += f"     <i>{date_str}  ·  {script_label}</i>\n\n"
        buttons.append([InlineKeyboardButton(
            text=f"⬇  {i}. {doc.fullname or 'Hujjat'}",
            callback_data=f"dl_doc_{doc.id}",
        )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await bot.send_message(tg_id, text, reply_markup=kb)


@router.callback_query(F.data.startswith("dl_doc_"))
async def download_doc(callback: CallbackQuery):
    """Arxivdan hujjatni qayta yuklab olish (file_id orqali)."""
    tg_id = callback.from_user.id
    doc_id = int(callback.data.replace("dl_doc_", ""))
    await callback.answer()

    docs = await get_user_documents(tg_id)
    doc = next((d for d in docs if d.id == doc_id), None)

    if not doc:
        await callback.message.answer(
            "⚠️  <b>Hujjat topilmadi</b>"
        )
        return

    try:
        await bot.send_document(
            tg_id,
            document=doc.file_id,
            caption=(
                f"<b>{doc.fullname}</b>\n"
                f"<i>{doc.created_at.strftime('%d.%m.%Y')}</i>"
            ),
        )
    except Exception as e:
        logger.error(f"Arxivdan yuklab bo'lmadi: {e}")
        await callback.message.answer(
            "⚠️  <b>Faylni yuklab bo'lmadi</b>\n\n"
            "<i>Hujjat eskirgan bo'lishi mumkin. Yangisini yarating.</i>"
        )


# ══════════════════════════════════════════════════════════════
#  6. QOLGAN BUYRUQLAR
# ══════════════════════════════════════════════════════════════

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    user = await get_or_create_user(message.from_user.id)
    await message.answer(
        f"<b>Hisobingiz</b>\n\n"
        f"Joriy balans   {balance_text(user)}\n"
        f"Yaratilgan hujjatlar   <b>{user.docs_count}</b>"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        f"<b>Yordam</b>\n"
        f"<i>Bot bilan ishlash bo'yicha qisqa qo'llanma</i>\n\n"
        f"<b>Buyruqlar</b>\n\n"
        f"/start   ·   Asosiy menyu\n"
        f"/balance   ·   Balansni ko'rish\n"
        f"/docs   ·   Hujjatlarim\n"
        f"/help   ·   Ushbu sahifa\n\n"
        f"<b>Narxlar</b>\n\n"
        f"Bitta obektivka   <b>{price_text(DOC_PRICE)}</b>"
    )


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    await callback.answer()
    await cmd_start(callback.message)


# ══════════════════════════════════════════════════════════════
#  7. APP ISHGA TUSHIRISH
# ══════════════════════════════════════════════════════════════

async def main():
    # DB ni tayyorlash
    await init_db()

    app = web.Application()

    # Web routes
    app.router.add_get("/app", serve_app)
    app.router.add_get("/api/template", serve_template)
    app.router.add_post("/submit", submit)
    app.router.add_post("/payment/callback", payment_webhook)

    # Telegram webhook
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
