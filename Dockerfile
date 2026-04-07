# ════════════════════════════════════════════════════════════════
#  Obektivka Bot — Dockerfile for Railway
#  Python 3.11 + LibreOffice + poppler-utils (preview uchun)
# ════════════════════════════════════════════════════════════════

FROM python:3.11-slim

# ─── Tizim paketlari ───
# libreoffice-writer  → DOCX → PDF konvertatsiya
# poppler-utils       → PDF → PNG konvertatsiya (pdftoppm)
# fonts-dejavu        → Watermark uchun shrift
# fonts-liberation    → Times New Roman almashtirish
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-core \
    poppler-utils \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

# ─── Ishchi papka ───
WORKDIR /app

# ─── Python kutubxonalar ───
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─── Loyiha fayllari ───
COPY . .

# ─── LibreOffice cache papkasini tayyorlash (root bo'lmagan user uchun) ───
RUN mkdir -p /tmp/.config/libreoffice && \
    chmod -R 777 /tmp/.config

ENV HOME=/tmp
ENV PYTHONUNBUFFERED=1

# ─── Botni ishga tushirish ───
CMD ["python", "bot.py"]
