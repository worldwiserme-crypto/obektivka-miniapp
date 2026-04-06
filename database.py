"""
Obektivka Bot — Asinxron Ma'lumotlar Bazasi
SQLAlchemy 2.0 + asyncpg | Connection Pooling | Railway PostgreSQL
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import BigInteger, Integer, String, DateTime, func, select
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
#  1. ASINXRON ULANISH VA POOLING
# ══════════════════════════════════════════════════════════════

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:pass@localhost:5432/obektivka",
)

# Railway ko'pincha "postgresql://" beradi — asyncpg uchun almashtirish
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DATABASE_URL,
    # ─── Connection Pool sozlamalari ───
    pool_size=5,           # Doimiy ochiq ulanishlar soni
    max_overflow=10,       # Yuqori yuklamada qo'shimcha ulanishlar (jami: 15)
    pool_timeout=30,       # Bo'sh ulanish kutish vaqti (soniya)
    pool_recycle=1800,     # Ulanishni yangilash (30 daqiqa) — Railway idle timeout uchun
    pool_pre_ping=True,    # Har bir so'rovdan oldin ulanishni tekshirish (stale connection himoya)
    echo=False,            # True = SQL loglarni ko'rsatish (debug uchun)
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Commit'dan keyin obyektlar "expired" bo'lmasin
)


@asynccontextmanager
async def get_session() -> AsyncSession:
    """
    Xavfsiz session context manager.
    
    Foydalanish:
        async with get_session() as session:
            user = await session.get(User, 123)
    
    Xatolik bo'lsa → rollback → log → raise
    Muvaffaqiyatli bo'lsa → commit → close
    """
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"DB session xatosi: {e}", exc_info=True)
        raise
    finally:
        await session.close()


async def init_db():
    """Jadvallarni yaratish (birinchi ishga tushirishda)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ DB jadvallar tayyor.")


async def dispose_db():
    """Graceful shutdown — barcha ulanishlarni yopish."""
    await engine.dispose()
    logger.info("🔌 DB ulanishlar yopildi.")


# ══════════════════════════════════════════════════════════════
#  2. MODEL — Users jadvali
# ══════════════════════════════════════════════════════════════

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, comment="Telegram user ID"
    )
    username: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    full_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    balance: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Balans (so'mda)"
    )
    docs_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def has_enough_balance(self, price: int) -> bool:
        return self.balance >= price

    def __repr__(self) -> str:
        return f"<User tg_id={self.tg_id} balance={self.balance}>"


# ══════════════════════════════════════════════════════════════
#  3. CRUD NAMUNA — get_or_create_user
# ══════════════════════════════════════════════════════════════

async def get_or_create_user(
    tg_id: int,
    username: str | None = None,
    full_name: str | None = None,
) -> User | None:
    """
    Foydalanuvchini olish yoki yangi yaratish.

    Xavfsizlik:
      - try/except ichida — bot hech qachon crash bo'lmaydi
      - Session auto-commit / auto-rollback (get_session context manager)
      - Race condition: ikki so'rov bir vaqtda kelsa ham xavfsiz

    Returns:
        User obyekti yoki None (faqat jiddiy DB xatosida)
    """
    try:
        async with get_session() as session:
            user = await session.get(User, tg_id)

            if user is not None:
                # Mavjud foydalanuvchi — username/full_name yangilash
                if username and user.username != username:
                    user.username = username
                if full_name and user.full_name != full_name:
                    user.full_name = full_name
                return user

            # Yangi foydalanuvchi yaratish
            user = User(
                tg_id=tg_id,
                username=username,
                full_name=full_name,
                balance=0,
                docs_count=0,
            )
            session.add(user)
            await session.flush()  # ID ni olish uchun
            logger.info(f"Yangi foydalanuvchi: tg_id={tg_id}, name={full_name}")
            return user

    except Exception as e:
        logger.error(
            f"get_or_create_user xatosi: tg_id={tg_id}, error={e}",
            exc_info=True,
        )
        return None
