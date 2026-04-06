"""
Obektivka Bot — Preview (Namuna) Rasm Generatori.

Mantiq:
  1. DOCX faylni oladi.
  2. Har bir sahifani rasmga aylantiradi (LibreOffice + pdf2image).
  3. Rasmlarning ustiga diagonal "NAMUNA" watermark chizadi.
  4. Tayyor rasmlarni bytes sifatida qaytaradi.

Muhim: Barcha og'ir operatsiyalar run_in_executor orqali bajariladi,
shuning uchun async event loop bloklanmaydi.
"""

import asyncio
import os
import subprocess
import tempfile
import logging
from pathlib import Path
from functools import partial
from concurrent.futures import ProcessPoolExecutor

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Process pool — bir nechta so'rovni parallel qayta ishlash
_executor = ProcessPoolExecutor(max_workers=2)

# Watermark sozlamalari
WATERMARK_TEXT = "NAMUNA"
WATERMARK_COLOR = (220, 50, 50, 90)   # Qizil, yarim shaffof
WATERMARK_FONT_SIZE = 80
DPI = 200                              # Rasm sifati (150-200 optimal)


def _convert_docx_to_images(docx_path: str, dpi: int = DPI) -> list[bytes]:
    """
    DOCX → PDF → PNG rasmlar.
    Bu funksiya sinxron — alohida jarayonda (process) ishga tushadi.
    
    Talab: servarda LibreOffice va poppler-utils o'rnatilgan bo'lishi kerak.
      apt install libreoffice-writer poppler-utils
    """
    with tempfile.TemporaryDirectory(prefix="obj_preview_") as tmp_dir:
        # 1-qadam: DOCX → PDF (LibreOffice headless)
        subprocess.run(
            [
                "libreoffice", "--headless", "--convert-to", "pdf",
                "--outdir", tmp_dir, docx_path
            ],
            capture_output=True, timeout=30,
            check=True,
        )

        # PDF fayl nomini topish
        pdf_name = Path(docx_path).stem + ".pdf"
        pdf_path = os.path.join(tmp_dir, pdf_name)

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF yaratilmadi: {pdf_path}")

        # 2-qadam: PDF → rasmlar (pdftoppm — poppler-utils)
        img_prefix = os.path.join(tmp_dir, "page")
        subprocess.run(
            [
                "pdftoppm", "-png", "-r", str(dpi),
                pdf_path, img_prefix
            ],
            capture_output=True, timeout=30,
            check=True,
        )

        # 3-qadam: Rasmlarni o'qib olish
        image_files = sorted(Path(tmp_dir).glob("page-*.png"))
        if not image_files:
            raise FileNotFoundError("Rasmlar yaratilmadi")

        result = []
        for img_file in image_files:
            result.append(img_file.read_bytes())

        return result


def _add_watermark(image_bytes: bytes) -> bytes:
    """
    Rasmga diagonal "NAMUNA" watermark qo'shadi.
    """
    img = Image.open(__import__("io").BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size

    # Shaffof overlay yaratish
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Shrift (sistema shrifti yoki fallback)
    font_size = max(w // 10, WATERMARK_FONT_SIZE)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", font_size)
        except (IOError, OSError):
            font = ImageFont.load_default()

    # Matn o'lchamini hisoblash
    bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Matnni bir necha marta diagonal chizish (butun sahifani qoplash)
    import math
    diagonal = math.sqrt(w ** 2 + h ** 2)
    angle = -35  # Burchak (gradus)

    # Kattaroq vaqtinchalik rasm — burilganda kesib ketmasin
    txt_layer = Image.new("RGBA", (int(diagonal * 1.5), int(diagonal * 1.5)), (0, 0, 0, 0))
    txt_draw = ImageDraw.Draw(txt_layer)

    # Grid shaklida yozish
    spacing_x = text_w + 120
    spacing_y = text_h + 200

    for y_pos in range(0, txt_layer.height, spacing_y):
        for x_pos in range(0, txt_layer.width, spacing_x):
            txt_draw.text((x_pos, y_pos), WATERMARK_TEXT, fill=WATERMARK_COLOR, font=font)

    # Burish
    txt_layer = txt_layer.rotate(angle, resample=Image.BICUBIC, expand=False)

    # Markazga moslashtirish va qirqish
    cx = (txt_layer.width - w) // 2
    cy = (txt_layer.height - h) // 2
    txt_layer = txt_layer.crop((cx, cy, cx + w, cy + h))

    # Birlashtirish
    result = Image.alpha_composite(img, txt_layer)
    result = result.convert("RGB")

    # Bytes ga aylantirish
    import io
    buf = io.BytesIO()
    result.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


def _generate_preview_sync(docx_path: str) -> list[bytes]:
    """
    Sinxron funksiya: DOCX → rasmlar → watermark qo'shilgan rasmlar.
    ProcessPoolExecutor ichida ishlaydi.
    """
    raw_images = _convert_docx_to_images(docx_path)

    watermarked = []
    for img_bytes in raw_images:
        watermarked.append(_add_watermark(img_bytes))

    return watermarked


async def generate_preview(docx_path: str) -> list[bytes]:
    """
    Async wrapper. Event loop'ni bloklamaydi.
    
    Returns:
        Har bir sahifaning watermark qo'shilgan JPEG rasmi (bytes ro'yxati).
    """
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            _generate_preview_sync,
            docx_path
        )
        return result
    except Exception as e:
        logger.error(f"Preview yaratishda xato: {e}", exc_info=True)
        raise


# ──────────────────────────────────────────────
#  Alternativ: LibreOffice o'rnatilmagan bo'lsa
#  python-docx2pdf yoki docx2pdf kutubxonasi
#  ishlatish mumkin, lekin Linux'da LibreOffice
#  baribir kerak bo'ladi.
# ──────────────────────────────────────────────
