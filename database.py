"""
Obektivka Bot — Ma'lumotlar Bazasi Bilan Ishlash
AsyncSession orqali CRUD operatsiyalari.
"""

import os
import logging
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, update
from models import Base, User, Transaction, Template, Document

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/obektivka")

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

logger = logging.getLogger(__name__)


async def init_db():
    """Jadvallarni yaratish (birinchi ishga tushirishda)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("DB jadvallar tayyor.")


@asynccontextmanager
async def get_session():
    """Har bir operatsiya uchun session ochib-yopish."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ──────────────────────────────────────────────
#  USER CRUD
# ──────────────────────────────────────────────
async def get_or_create_user(tg_id: int, username: str = None, full_name: str = None) -> User:
    """Foydalanuvchini olish yoki yangi yaratish."""
    async with get_session() as session:
        user = await session.get(User, tg_id)
        if not user:
            user = User(tg_id=tg_id, username=username, full_name=full_name, balance=0)
            session.add(user)
            await session.flush()
            logger.info(f"Yangi foydalanuvchi: {tg_id}")
        return user


async def get_user(tg_id: int) -> User | None:
    async with get_session() as session:
        return await session.get(User, tg_id)


# ──────────────────────────────────────────────
#  BALANS OPERATSIYALARI (atomik)
# ──────────────────────────────────────────────
async def topup_balance(tg_id: int, amount: int, provider: str, provider_tx_id: str = None) -> Transaction:
    """Hisobni to'ldirish. Tranzaksiyani yozish + balansni oshirish — bitta atomik operatsiya."""
    async with get_session() as session:
        user = await session.get(User, tg_id)
        if not user:
            raise ValueError(f"Foydalanuvchi topilmadi: {tg_id}")

        user.balance += amount

        tx = Transaction(
            user_tg_id=tg_id,
            tx_type="topup",
            amount=amount,
            provider=provider,
            provider_tx_id=provider_tx_id,
            status="success",
            description=f"{provider} orqali {amount} so'm kiritildi"
        )
        session.add(tx)
        await session.flush()
        logger.info(f"Topup: user={tg_id}, amount={amount}, provider={provider}")
        return tx


async def deduct_balance(tg_id: int, price: int, description: str = "") -> Transaction | None:
    """
    Balansdan pul yechish. 
    Yetarli mablag' bo'lmasa None qaytaradi.
    Race condition'dan himoya: SELECT ... FOR UPDATE.
    """
    async with get_session() as session:
        # FOR UPDATE — boshqa jarayonlar kutadi
        result = await session.execute(
            select(User).where(User.tg_id == tg_id).with_for_update()
        )
        user = result.scalar_one_or_none()

        if not user or user.balance < price:
            return None

        user.balance -= price
        user.docs_count += 1

        tx = Transaction(
            user_tg_id=tg_id,
            tx_type="purchase",
            amount=price,
            provider="internal",
            status="success",
            description=description or f"Obektivka uchun {price} so'm"
        )
        session.add(tx)
        await session.flush()
        logger.info(f"Deduct: user={tg_id}, price={price}, new_balance={user.balance}")
        return tx


# ──────────────────────────────────────────────
#  SHABLON (TEMPLATE)
# ──────────────────────────────────────────────
async def save_template(tg_id: int, data: dict, name: str = None) -> Template:
    """
    Foydalanuvchining shablonini saqlash.
    Avvalgi default shablonni o'chirib, yangisini qo'shadi.
    """
    async with get_session() as session:
        # Eski default-ni o'chirish
        await session.execute(
            update(Template)
            .where(Template.user_tg_id == tg_id, Template.is_default == True)
            .values(is_default=False)
        )

        tpl = Template(
            user_tg_id=tg_id,
            name=name or data.get("fullname", "Nomsiz"),
            data=data,
            is_default=True,
        )
        session.add(tpl)
        await session.flush()
        return tpl


async def get_default_template(tg_id: int) -> dict | None:
    """Foydalanuvchining oxirgi shablonini qaytarish."""
    async with get_session() as session:
        result = await session.execute(
            select(Template)
            .where(Template.user_tg_id == tg_id, Template.is_default == True)
            .order_by(Template.updated_at.desc())
            .limit(1)
        )
        tpl = result.scalar_one_or_none()
        return tpl.data if tpl else None


# ──────────────────────────────────────────────
#  HUJJAT ARXIVI
# ──────────────────────────────────────────────
async def save_document(
    tg_id: int, file_id: str, file_name: str,
    fullname: str, script: str, price_paid: int
) -> Document:
    async with get_session() as session:
        doc = Document(
            user_tg_id=tg_id,
            file_id=file_id,
            file_name=file_name,
            fullname=fullname,
            script=script,
            price_paid=price_paid,
        )
        session.add(doc)
        await session.flush()
        return doc


async def get_user_documents(tg_id: int, limit: int = 20) -> list[Document]:
    """Foydalanuvchining oxirgi hujjatlari (arxiv)."""
    async with get_session() as session:
        result = await session.execute(
            select(Document)
            .where(Document.user_tg_id == tg_id)
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
