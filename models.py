"""
Obektivka Bot — Ma'lumotlar Bazasi Modellari
PostgreSQL + SQLAlchemy (async) asosida.

Jadvallar:
  - users         : foydalanuvchilar va balans
  - transactions  : to'lov tarixi (kirim/chiqim)
  - templates     : saqlangan shablonlar (JSON)
  - documents     : sotib olingan hujjatlar (file_id bilan)
"""

from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, DateTime,
    Boolean, ForeignKey, Index, Numeric, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    tg_id = Column(BigInteger, primary_key=True)                  # Telegram user ID
    username = Column(String(64), nullable=True)
    full_name = Column(String(200), nullable=True)
    balance = Column(Integer, default=0, nullable=False)          # Balans (so'mda yoki tiyinda)
    docs_count = Column(Integer, default=0, nullable=False)       # Jami yaratilgan hujjatlar soni
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    transactions = relationship("Transaction", back_populates="user", lazy="selectin")
    templates = relationship("Template", back_populates="user", lazy="selectin")
    documents = relationship("Document", back_populates="user", lazy="selectin")

    def has_enough_balance(self, price: int) -> bool:
        return self.balance >= price


class Transaction(Base):
    """
    Har bir to'lov / yechim alohida yozib boriladi.
    tx_type:
      - "topup"    : hisobni to'ldirish
      - "purchase" : hujjat uchun to'lov (chiqim)
      - "refund"   : qaytarish
    status:
      - "pending"  : kutilmoqda
      - "success"  : muvaffaqiyatli
      - "failed"   : muvaffaqiyatsiz
    provider:
      - "click", "payme", "telegram_stars", "admin", "promo"
    """
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_tg_id = Column(BigInteger, ForeignKey("users.tg_id"), nullable=False, index=True)
    tx_type = Column(String(20), nullable=False)                  # topup / purchase / refund
    amount = Column(Integer, nullable=False)                      # Summa (musbat)
    provider = Column(String(30), nullable=True)                  # click / payme / telegram_stars
    provider_tx_id = Column(String(200), nullable=True)           # Provayderning tranzaksiya ID-si
    status = Column(String(20), default="pending", nullable=False)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    user = relationship("User", back_populates="transactions")

    __table_args__ = (
        Index("ix_tx_status", "status"),
        Index("ix_tx_created", "created_at"),
    )


class Template(Base):
    """
    Foydalanuvchining saqlangan shabloni.
    Bir foydalanuvchi bir nechta shablonga ega bo'lishi mumkin,
    lekin "is_default" faqat bitta bo'ladi (oxirgi to'ldirgan).
    """
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_tg_id = Column(BigInteger, ForeignKey("users.tg_id"), nullable=False, index=True)
    name = Column(String(200), nullable=True)                     # Shablon nomi (F.I.Sh.)
    data = Column(JSONB, nullable=False)                          # To'liq forma ma'lumotlari
    is_default = Column(Boolean, default=True, nullable=False)    # Standart shablon
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="templates")


class Document(Base):
    """
    Sotib olingan hujjatlar arxivi.
    Fayl Telegram serverlarida saqlanadi — biz faqat file_id ni olamiz.
    """
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_tg_id = Column(BigInteger, ForeignKey("users.tg_id"), nullable=False, index=True)
    file_id = Column(String(500), nullable=False)                 # Telegram file_id
    file_name = Column(String(300), nullable=True)
    fullname = Column(String(200), nullable=True)                 # Kimga tegishli obektivka
    script = Column(String(5), default="lat")                     # lat / cyr
    price_paid = Column(Integer, default=0)                       # To'langan narx
    created_at = Column(DateTime, default=func.now(), nullable=False)

    user = relationship("User", back_populates="documents")

    __table_args__ = (
        Index("ix_doc_user_created", "user_tg_id", "created_at"),
    )
