"""
Obektivka Bot — Konfiguratsiya va Narxlar
"""
import os

# ─── Bot sozlamalari ───
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")
PORT = int(os.getenv("PORT", 8080))
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/obektivka")

# ─── Narxlar (so'mda) ───
DOC_PRICE = 5000            # Bitta obektivka narxi
MIN_TOPUP = 5000            # Minimal to'ldirish summasi
MAX_TOPUP = 500_000         # Maksimal to'ldirish summasi

# ─── Telegram Stars (agar ishlatilsa) ───
STARS_PER_DOC = 1           # 1 Star = 1 hujjat (oddiy narx)

# ─── Preview sozlamalari ───
PREVIEW_DPI = 200
WATERMARK_TEXT = "NAMUNA"

# ─── Fayl saqlash ───
TEMP_DIR = "/tmp/obj"
# ─── Admin panel sozlamalari ───
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))
ADMIN_LIST = [
    int(x.strip()) for x in os.getenv("ADMIN_LIST", "").split(",") if x.strip().isdigit()
]
