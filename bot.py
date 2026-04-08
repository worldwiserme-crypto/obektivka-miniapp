"""
Yo'lchi Bot — Premium UI versiya
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
dp.include_router(payment_router)
dp.include_router(router)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(BASE_DIR, "index.html")


# ══════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ══════════════════════════════════════════════════════════════

_MONTHS_UZ = {
    1: "yan", 2: "fev", 3: "mar", 4: "apr", 5: "may", 6: "iyn",
    7: "iyl", 8: "avg", 9: "sen", 10: "okt", 11: "noy", 12: "dek",
}


def price_text(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"


def fmt_date(dt: datetime) -> str:
    return f"{dt.day} {_MONTHS_UZ[dt.month]} {dt.year}"


_pending_docs: dict[int, dict] = {}


# ══════════════════════════════════════════════════════════════
#  1. KIRISH SAHIFASI VA ASOSIY MENYU
# ══════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(message: Message):
    """Kirish sahifasi — har safar ko'rsatiladi."""
    tg_id = message.from_user.id
    await get_or_create_user(
        tg_id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Boshlash", callback_data="main_menu")],
    ])

    await message.answer(
        "<b>Assalomu alaykum!</b>\n\n"
        "Yo'lchi bot sizga rasmiy obektivka hujjatini "
        "bir necha daqiqada tayyorlab beradi.\n\n"
        "💳  Word formatda tayyor hujjat\n"
        "📄  Lotin va kirill alifbosida\n"
        "⚡  Bir necha daqiqada tayyor\n\n"
        "Hujjat rasmiy standartga to'liq mos va "
        "chop etishga tayyor holatda beriladi.",
        reply_markup=kb,
    )


@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery):
    """Asosiy menyu — Boshlash bosilgandan keyin."""
    tg_id = callback.from_user.id
    await callback.answer()

    user = await get_or_create_user(tg_id)
    url = f"{WEBHOOK_HOST}/app?tg_id={tg_id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Obektivka yaratish", web_app=WebAppInfo(url=url))],
        [InlineKeyboardButton(text="💰 Balansim", callback_data="my_balance")],
        [InlineKeyboardButton(text="📄 Hujjatlarim", callback_data="my_docs")],
    ])

    await callback.message.answer(
        f"<b>Tayyor!</b>\n\n"
        f"Quyidagi tugmalardan birini tanlang.\n\n"
        f"Sizning balansingiz: <b>{price_text(user.balance)}</b>",
        reply_markup=kb,
    )


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    await show_main_menu(callback)


# ══════════════════════════════════════════════════════════════
#  2. BALANS VA TO'LOV
# ══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_balance")
async def show_balance(callback: CallbackQuery):
    user = await get_or_create_user(callback.from_user.id)
    await callback.answer()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 To'ldirish", callback_data="topup_menu")],
        [InlineKeyboardButton(text="← Ortga", callback_data="main_menu")],
    ])

    await callback.message.answer(
        f"<b>Balansingiz</b>\n\n"
        f"Hozirgi balans: <b>{price_text(user.balance)}</b>\n"
        f"Yaratilgan hujjatlar: <b>{user.docs_count} ta</b>",
        reply_markup=kb,
    )


@router.callback_query(F.data == "topup_menu")
async def topup_menu(callback: CallbackQuery):
    await callback.answer()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"💳 Karta · {price_text(DOC_PRICE)}", callback_data="p2p_pay"),
            InlineKeyboardButton(text=f"⭐ Stars · {STARS_PER_DOC}", callback_data="topup_stars"),
        ],
        [InlineKeyboardButton(text="← Ortga", callback_data="my_balance")],
    ])

    await callback.message.answer(
        "<b>Hisobni to'ldirish</b>\n\n"
        "Quyidagi usullardan birini tanlang.\n\n"
        "Karta orqali to'lov admin tomonidan 5–15 daqiqada "
        "tasdiqlanadi. Telegram Stars esa darhol tasdiqlanadi.",
        reply_markup=kb,
    )


# ─── Telegram Stars bilan to'lov ───

@router.callback_query(F.data == "topup_stars")
async def topup_with_stars(callback: CallbackQuery):
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
    await pre_checkout.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
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
        f"<b>To'lov qabul qilindi!</b>\n\n"
        f"Hisobingiz <b>{price_text(DOC_PRICE)}</b> miqdorida to'ldirildi. "
        f"Endi obektivka yaratishingiz mumkin."
    )

    await _try_deliver_pending(tg_id)


# ─── Click/Payme webhook ───

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
                    f"<b>Hisob to'ldirildi!</b>\n\n"
                    f"Balansingizga <b>{price_text(amount)}</b> qo'shildi."
                )
                await _try_deliver_pending(tg_id)
            except Exception:
                pass

            return web.json_response({"error": 0, "error_note": "Success"})

    except Exception as e:
        logger.error(f"Payment webhook xatosi: {e}", exc_info=True)
        return web.json_response({"error": -1, "error_note": str(e)})


# ══════════════════════════════════════════════════════════════
#  3. WEBAPP /submit
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
            "<b>Hujjat tayyorlanmoqda...</b>\n\n"
            "Ma'lumotlaringiz qabul qilindi. Word fayl va namuna "
            "ko'rinishini tayyorlash bir necha soniya vaqt oladi."
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
                    text=f"✓ Hisobdan to'lash · {price_text(DOC_PRICE)}",
                    callback_data="pay_from_balance"
                )],
                [InlineKeyboardButton(text="✕ Bekor qilish", callback_data="cancel_doc")],
            ])
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text=f"💳 Karta · {price_text(DOC_PRICE)}", callback_data="p2p_pay"),
                    InlineKeyboardButton(text=f"⭐ Stars · {STARS_PER_DOC}", callback_data="topup_stars"),
                ],
                [InlineKeyboardButton(text="✕ Bekor qilish", callback_data="cancel_doc")],
            ])

        if preview_images:
            media_group = []
            for i, img_bytes in enumerate(preview_images[:2]):
                caption = None
                if i == 0:
                    caption = (
                        "<b>Namuna tayyor!</b>\n\n"
                        "Yuqoridagi rasm sizning hujjatingizning "
                        "ko'rinishi. Asl nusxani olish uchun to'lov qiling."
                    )
                media_group.append(InputMediaPhoto(
                    media=BufferedInputFile(img_bytes, filename=f"preview_{i+1}.jpg"),
                    caption=caption, parse_mode=ParseMode.HTML if caption else None,
                ))

            await bot.send_media_group(tg_id, media=media_group)
            await bot.send_message(
                tg_id,
                "Asl nusxani olish uchun to'lov usulini tanlang:",
                reply_markup=kb,
            )
        else:
            await bot.send_message(
                tg_id,
                f"<b>Hujjat tayyor!</b>\n\n"
                f"To'lovdan so'ng asl nusxa yuboriladi.\n\n"
                f"Narx: <b>{price_text(DOC_PRICE)}</b>",
                reply_markup=kb,
            )

        return web.json_response({"ok": True})

    except Exception as e:
        logger.error(f"Submit xatosi: {e}", exc_info=True)
        if tg_id:
            try:
                await bot.send_message(
                    tg_id,
                    "<b>Xatolik yuz berdi</b>\n\n"
                    "Hujjatni tayyorlab bo'lmadi. Iltimos, /start "
                    "orqali qayta urinib ko'ring."
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
            "<b>Hujjat topilmadi</b>\n\n"
            "Kutayotgan namuna mavjud emas. Yangi obektivka "
            "yaratish uchun /start bosing."
        )
        return

    tx = await deduct_balance(tg_id, DOC_PRICE, description="Obektivka yaratish")
    if not tx:
        user = await get_user(tg_id)
        await callback.message.answer(
            f"<b>Mablag' yetarli emas</b>\n\n"
            f"Hozirgi balans: <b>{price_text(user.balance)}</b>\n"
            f"Kerak: <b>{price_text(DOC_PRICE)}</b>\n"
            f"Yetishmaydi: <b>{price_text(DOC_PRICE - user.balance)}</b>"
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
                f"<b>Obektivkangiz tayyor!</b>\n\n"
                f"Asl nusxa, watermarkasiz. Word formatda, "
                f"{script_label} alifbosida.\n\n"
                f"Hujjat arxivda saqlandi — istalgan vaqtda "
                f"\"Hujjatlarim\" bo'limidan qayta yuklab olishingiz mumkin."
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
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Yangi obektivka", callback_data="main_menu")],
            ])
            await bot.send_message(
                tg_id,
                f"Qoldiq balans: <b>{price_text(user.balance)}</b>",
                reply_markup=kb,
            )

    except Exception as e:
        logger.error(f"Fayl berish xatosi: {e}", exc_info=True)
        await bot.send_message(
            tg_id,
            "<b>Faylni yuborib bo'lmadi</b>\n\n"
            "Texnik nosozlik yuz berdi. Hisobingizdan summa "
            "yechilmadi. Qayta urinib ko'ring."
        )


@router.callback_query(F.data == "cancel_doc")
async def cancel_doc(callback: CallbackQuery):
    tg_id = callback.from_user.id
    pending = _pending_docs.pop(tg_id, None)

    # Tugmalarni o'chirish — qayta bosilmasin
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if pending:
        # Haqiqiy bekor qilish — fayl hali berilmagan edi
        try:
            os.remove(pending["docx_path"])
        except OSError:
            pass
        await callback.answer("Bekor qilindi")
        text = (
            "<b>Bekor qilindi</b>\n\n"
            "Hujjat o'chirildi. Hech qanday summa yechilmadi."
        )
    else:
        # Pending yo'q — fayl allaqachon berilgan yoki avval bekor qilingan
        await callback.answer()
        text = (
            "<b>Bu amal allaqachon yakunlangan</b>\n\n"
            "Yangi obektivka uchun bosh menyuga qayting."
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Bosh menyu", callback_data="main_menu")],
    ])
    await callback.message.answer(text, reply_markup=kb)


# ══════════════════════════════════════════════════════════════
#  5. HUJJATLARIM ARXIVI
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
            [InlineKeyboardButton(text="📝 Birinchi hujjatni yaratish", callback_data="main_menu")],
        ])
        await bot.send_message(
            tg_id,
            "<b>Hujjatlarim</b>\n\n"
            "Hozircha hech qanday hujjat yaratilmagan. "
            "Birinchi obektivkangizni yarating — u shu yerda saqlanadi.",
            reply_markup=kb,
        )
        return

    text = f"<b>Hujjatlarim</b>\n\nOxirgi {len(docs)} ta hujjat:\n\n"
    buttons = []
    for i, doc in enumerate(docs, 1):
        date_str = fmt_date(doc.created_at)
        script_label = "Кирилл" if doc.script == "cyr" else "Lotin"
        text += f"<b>{i}. {doc.fullname or '—'}</b>\n{date_str} · {script_label}\n\n"
        buttons.append([InlineKeyboardButton(
            text=f"⬇ {i}. {doc.fullname or 'Hujjat'}",
            callback_data=f"dl_doc_{doc.id}",
        )])

    buttons.append([InlineKeyboardButton(text="← Bosh menyu", callback_data="main_menu")])

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
        await callback.message.answer("<b>Hujjat topilmadi</b>")
        return

    try:
        await bot.send_document(
            tg_id,
            document=doc.file_id,
            caption=f"<b>{doc.fullname}</b>\n{fmt_date(doc.created_at)}",
        )
    except Exception as e:
        logger.error(f"Arxivdan yuklab bo'lmadi: {e}")
        await callback.message.answer(
            "<b>Faylni yuklab bo'lmadi</b>\n\n"
            "Hujjat eskirgan bo'lishi mumkin. Yangisini yarating."
        )


# ══════════════════════════════════════════════════════════════
#  6. QOLGAN BUYRUQLAR
# ══════════════════════════════════════════════════════════════

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    user = await get_or_create_user(message.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 To'ldirish", callback_data="topup_menu")],
        [InlineKeyboardButton(text="← Bosh menyu", callback_data="main_menu")],
    ])

    await message.answer(
        f"<b>Balansingiz</b>\n\n"
        f"Hozirgi balans: <b>{price_text(user.balance)}</b>\n"
        f"Yaratilgan hujjatlar: <b>{user.docs_count} ta</b>",
        reply_markup=kb,
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Bosh menyu", callback_data="main_menu")],
    ])

    await message.answer(
        f"<b>Yordam</b>\n\n"
        f"Yo'lchi bot rasmiy obektivka hujjatini tayyorlaydi. "
        f"Ma'lumotlarni to'ldirasiz, namunani ko'rasiz, to'lov "
        f"qilasiz va tayyor Word faylni olasiz.\n\n"
        f"<b>Buyruqlar:</b>\n"
        f"/start — bosh menyu\n"
        f"/balance — hisobingiz\n"
        f"/docs — hujjatlaringiz\n\n"
        f"Narx: <b>{price_text(DOC_PRICE)}</b> bir hujjat uchun.",
        reply_markup=kb,
    )


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
