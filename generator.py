import base64, io, re
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

F   = "Times New Roman"
FS  = Pt(11)
F14 = Pt(14)


# ═══════════════════════════════════════════════════════════════════
#  TRANSLITERATSIYA DVIGATEL  (Lotin → Kirill)
#  Qoidalar:
#   1. Barcha apostrof turlarini standartlashtirish
#   2. O' → Ў,  G' → Ғ  (apostrof bilan birikkan)
#   3. Qo'shaloq harflar: SH→Ш, CH→Ч, NG→НГ, TS→Ц
#   4. YA→Я, YO→Ё, YU→Ю, YE→Е
#   5. E qoidasi: so'z boshida → Э, o'rtada → Е
#   6. Kirill matn bo'lsa — o'zgartirmasdan o'tkazish
# ═══════════════════════════════════════════════════════════════════

def _is_cyrillic_char(c: str) -> bool:
    return '\u0400' <= c <= '\u04FF'

def _has_cyrillic(text: str) -> bool:
    return any(_is_cyrillic_char(c) for c in text)

def _normalize_apostrophe(text: str) -> str:
    """Barcha apostrof/tutu belgisi turlarini bitta standartga keltirish."""
    for ch in ['\u2018', '\u2019', '\u02BC', '\u02BB', '\u0060', '\u00B4',
               '\u044A', '\u044B', '\u042A', '\u0027']:
        text = text.replace(ch, "'")
    return text

def _word_lat_to_cyr(word: str) -> str:
    """Bitta so'zni lotinchadan kirillchaga o'girish."""

    # Kirill harflari ko'p bo'lsa — o'zgartirmasdan qaytarish
    if _has_cyrillic(word):
        return word

    # Belgilar jadvali (tartibi muhim: avval qo'shaloq, keyin birlik)
    DIGRAPHS = [
        # katta harf
        ('SH', 'Ш'), ('CH', 'Ч'), ('NG', 'НГ'), ('TS', 'Ц'),
        ('YA', 'Я'), ('YO', 'Ё'), ('YU', 'Ю'), ('YE', 'Е'),
        # bosh harf (birinchi katta, ikkinchi kichik)
        ('Sh', 'Ш'), ('Ch', 'Ч'), ('Ng', 'НГ'), ('Ts', 'Ц'),
        ('Ya', 'Я'), ('Yo', 'Ё'), ('Yu', 'Ю'), ('Ye', 'Е'),
        # kichik harf
        ('sh', 'ш'), ('ch', 'ч'), ('ng', 'нг'), ('ts', 'ц'),
        ('ya', 'я'), ('yo', 'ё'), ('yu', 'ю'), ('ye', 'е'),
    ]
    # O' va G' (apostrof bilan)
    APOSTROPHE_PAIRS = [
        ("O'", 'Ў'), ("G'", 'Ғ'),
        ("o'", 'ў'), ("g'", 'ғ'),
    ]
    SINGLES = {
        'A': 'А', 'B': 'Б', 'D': 'Д', 'E': 'Е', 'F': 'Ф', 'G': 'Г',
        'H': 'Ҳ', 'I': 'И', 'J': 'Ж', 'K': 'К', 'L': 'Л', 'M': 'М',
        'N': 'Н', 'O': 'О', 'P': 'П', 'Q': 'Қ', 'R': 'Р', 'S': 'С',
        'T': 'Т', 'U': 'У', 'V': 'В', 'X': 'Х', 'Y': 'Й', 'Z': 'З',
        'a': 'а', 'b': 'б', 'd': 'д', 'e': 'е', 'f': 'ф', 'g': 'г',
        'h': 'ҳ', 'i': 'и', 'j': 'ж', 'k': 'к', 'l': 'л', 'm': 'м',
        'n': 'н', 'o': 'о', 'p': 'п', 'q': 'қ', 'r': 'р', 's': 'с',
        't': 'т', 'u': 'у', 'v': 'в', 'x': 'х', 'y': 'й', 'z': 'з',
    }

    s = _normalize_apostrophe(word)

    # O' va G' ni almashtirish
    for lat, cyr in APOSTROPHE_PAIRS:
        s = s.replace(lat, cyr)

    # Qo'shaloq harflarni placeholder bilan almashtirish
    placeholders = {}
    ph_idx = [0]
    result_parts = [s]

    def replace_all(pairs, text):
        for lat, cyr in pairs:
            text = text.replace(lat, cyr)
        return text

    s = replace_all(DIGRAPHS, s)

    # Birlik harflar
    out = []
    for i, ch in enumerate(s):
        if ch in SINGLES:
            # E qoidasi: so'z boshida (yoki kirill bo'lmagan belgidan keyin) → Э/э
            if ch == 'E':
                prev = s[i-1] if i > 0 else ''
                if i == 0 or (prev not in 'aeiouAEIOUаеёиоуыэюяўАЕЁИОУЫЭЮЯЎ' and not _is_cyrillic_char(prev) and prev not in 'аеёиоуыэюяўbdfghjklmnpqrstvxyz'):
                    out.append('Э')
                else:
                    out.append(SINGLES[ch])
            elif ch == 'e':
                prev = s[i-1] if i > 0 else ''
                if i == 0 or prev in ' \t\n\r-–—.,;:!?()"«»':
                    out.append('э')
                else:
                    out.append(SINGLES[ch])
            else:
                out.append(SINGLES[ch])
        else:
            out.append(ch)
    return ''.join(out)


def lat_to_cyr(text: str) -> str:
    """
    Matnni lotinchadan kirillchaga o'girish.
    Aralash matnda ham ishlaydi: har bir so'zni alohida qayta ishlaydi.
    Kirill harflari o'zgarmasdan qoladi.
    """
    if not text:
        return text

    # Agar matn asosan kirill bo'lsa — o'zgartirmasdan qaytarish
    cyr_count = sum(1 for c in text if _is_cyrillic_char(c))
    lat_count  = sum(1 for c in text if c.isalpha() and not _is_cyrillic_char(c))
    if cyr_count > lat_count:
        return text

    # So'zlarga bo'lib qayta ishlash (tinish belgilari saqlanadi)
    parts = re.split(r'(\s+)', text)
    return ''.join(_word_lat_to_cyr(p) if p.strip() else p for p in parts)


def apply_script(data: dict, script: str) -> dict:
    """
    Agar script == 'cyr' bo'lsa, barcha matn maydonlarini kirillchaga o'girish.
    Aks holda — o'zgartirmasdan qaytarish.
    """
    if script != 'cyr':
        return data

    TEXT_FIELDS = [
        'fullname', 'birthplace', 'nationality', 'party',
        'edu_level', 'university', 'speciality',
        'science_degree', 'science_title', 'military_rank',
        'langs', 'awards', 'departmental_awards', 'deputy',
        'address', 'current_job', 'job_year',
    ]

    result = dict(data)

    for field in TEXT_FIELDS:
        val = result.get(field)
        if isinstance(val, str):
            result[field] = lat_to_cyr(val)
        elif isinstance(val, list):
            result[field] = [lat_to_cyr(v) if isinstance(v, str) else v for v in val]

    # Mehnat tarixi
    wh = result.get('work_history', [])
    result['work_history'] = [
        {k: lat_to_cyr(v) if isinstance(v, str) else v for k, v in w.items()}
        for w in wh if isinstance(w, dict)
    ]

    # Qarindoshlar
    rels = result.get('relatives', [])
    result['relatives'] = [
        {k: lat_to_cyr(v) if isinstance(v, str) else v for k, v in r.items()}
        for r in rels if isinstance(r, dict)
    ]

    return result


# ═══════════════════════════════════════════════════════════════════
#  DOCX GENERATSIYA
# ═══════════════════════════════════════════════════════════════════

def _font(run, bold=False, size=None):
    run.font.name = F
    run.font.size = size or FS
    run.font.bold = bold


def _run(p, text, bold=False, size=None):
    r = p.add_run(text)
    _font(r, bold=bold, size=size)
    return r


def _para(doc, text="", bold=False, size=None,
          align=WD_ALIGN_PARAGRAPH.LEFT, before=0, after=0, spacing=14):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after  = Pt(after)
    p.paragraph_format.line_spacing = Pt(spacing)
    if text:
        _run(p, text, bold=bold, size=size)
    return p


def _no_border(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    cb = OxmlElement("w:tcBorders")
    for s in ["top","left","bottom","right"]:
        b = OxmlElement(f"w:{s}")
        b.set(qn("w:val"), "none")
        b.set(qn("w:sz"), "0")
        b.set(qn("w:color"), "auto")
        cb.append(b)
    tcPr.append(cb)


def _cell_borders(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    cb = OxmlElement("w:tcBorders")
    for s in ["top","left","bottom","right"]:
        b = OxmlElement(f"w:{s}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), "000000")
        cb.append(b)
    tcPr.append(cb)


def _kill_tbl_borders(tbl):
    tblEl = tbl._tbl
    tblPr = tblEl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tblEl.insert(0, tblPr)
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    tb = OxmlElement("w:tblBorders")
    for s in ["top","left","bottom","right","insideH","insideV"]:
        b = OxmlElement(f"w:{s}")
        b.set(qn("w:val"), "none")
        b.set(qn("w:sz"), "0")
        b.set(qn("w:color"), "auto")
        tb.append(b)
    tblPr.append(tb)


def _cp(cell, text, bold=False, before=0, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.paragraphs[0].clear()
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after  = Pt(0)
    p.paragraph_format.line_spacing = Pt(14)
    _run(p, text or "", bold=bold, size=FS)


def _cell_para(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT):
    p = cell.paragraphs[0]
    p.clear()
    p.alignment = align
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(1)
    p.paragraph_format.line_spacing = Pt(13)
    _run(p, text or "—", bold=bold)


def generate(data: dict, output_path: str, script: str = 'lat'):
    """
    Hujjat yaratish.
    script: 'lat' = lotin alifbosi (o'zgartirmasdan),
            'cyr' = kirill alifbosi (transliteratsiya qilinadi)
    """
    # Transliteratsiya nuqtasi — faqat hujjat yaratishdan oldin
    data = apply_script(data, script)

    doc = Document()

    sec = doc.sections[0]
    sec.page_width    = Cm(21)
    sec.page_height   = Cm(29.7)
    sec.top_margin    = Cm(1.5)
    sec.bottom_margin = Cm(1.0)
    sec.left_margin   = Cm(2.0)
    sec.right_margin  = Cm(1.0)

    doc.styles["Normal"].font.name = F
    doc.styles["Normal"].font.size = FS

    fullname    = data.get("fullname", "")
    job_year    = data.get("job_year", "")
    current_job = data.get("current_job", "")
    photo_b64   = data.get("photo_base64", "")

    bd = data.get("birthdate", "")
    if bd and "-" in bd:
        y, m, d = bd.split("-")
        bd = f"{d}.{m}.{y}"
    langs = data.get("langs", [])
    langs_str = ", ".join(langs) if isinstance(langs, list) else str(langs)

    # ── 1. MA'LUMOTNOMA ──
    p0 = doc.add_paragraph()
    p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p0.paragraph_format.space_before = Pt(0)
    p0.paragraph_format.space_after  = Pt(0)
    p0.paragraph_format.line_spacing = Pt(16)
    _run(p0, L("MA'LUMOTNOMA","МАЪЛУМОТНОМА"), bold=True, size=F14)

    # ── 2. Fullname ──
    p1 = doc.add_paragraph()
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p1.paragraph_format.space_before = Pt(2)
    p1.paragraph_format.space_after  = Pt(0)
    p1.paragraph_format.line_spacing = Pt(16)
    _run(p1, fullname, bold=True, size=F14)

    N_ROWS = 20

    tbl = doc.add_table(rows=N_ROWS, cols=3)
    _kill_tbl_borders(tbl)
    tbl.columns[0].width = Cm(7.5)
    tbl.columns[1].width = Cm(7.5)
    tbl.columns[2].width = Cm(3.0)

    for row in tbl.rows:
        for cell in row.cells:
            _no_border(cell)

    photo_cell = tbl.cell(0, 2)
    for i in range(1, N_ROWS):
        photo_cell = photo_cell.merge(tbl.cell(i, 2))

    photo_cell.paragraphs[0].clear()
    rp = photo_cell.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    rp.paragraph_format.space_before = Pt(0)
    rp.paragraph_format.space_after  = Pt(0)
    rp.paragraph_format.line_spacing = None
    if photo_b64:
        try:
            img_bytes = base64.b64decode(photo_b64.split(",")[-1])
            run = rp.add_run()
            run.add_picture(io.BytesIO(img_bytes), width=Cm(3.0), height=Cm(4.0))
        except Exception:
            pass

    lav_cell = tbl.cell(0, 0).merge(tbl.cell(0, 1))
    lav_cell.paragraphs[0].clear()
    lp = lav_cell.paragraphs[0]
    lp.paragraph_format.space_before = Pt(2)
    lp.paragraph_format.space_after  = Pt(0)
    lp.paragraph_format.line_spacing = Pt(14)
    if job_year:
        _run(lp, job_year, size=FS)
    if current_job:
        lp2 = lav_cell.add_paragraph()
        lp2.paragraph_format.space_before = Pt(0)
        lp2.paragraph_format.space_after  = Pt(0)
        lp2.paragraph_format.line_spacing = Pt(14)
        _run(lp2, current_job, size=FS)

    ri = [1]

    def row2(l1, v1, l2=None, v2=None):
        _cp(tbl.cell(ri[0], 0), l1, bold=True, before=5)
        _cp(tbl.cell(ri[0], 1), l2 or "", bold=True, before=5)
        ri[0] += 1
        _cp(tbl.cell(ri[0], 0), v1)
        _cp(tbl.cell(ri[0], 1), v2 or "")
        ri[0] += 1

    def inline2(label, val):
        _cp(tbl.cell(ri[0], 0), label, bold=True, before=8)
        _cp(tbl.cell(ri[0], 1), val or "—", before=8)
        ri[0] += 1

    def long2(label, val):
        mc = tbl.cell(ri[0], 0).merge(tbl.cell(ri[0], 1))
        _cp(mc, label, bold=True, before=8)
        ri[0] += 1
        mc2 = tbl.cell(ri[0], 0).merge(tbl.cell(ri[0], 1))
        _cp(mc2, val)
        ri[0] += 1

    IS_CYR = script == "cyr"
    YOQ = "йўқ" if IS_CYR else "yo'q"

    def L(lat, cyr): return cyr if IS_CYR else lat

    row2(L("Tug'ilgan yili:","Туғилган йили:"), bd,
         L("Tug'ilgan joyi:","Туғилган жойи:"), data.get("birthplace",""))
    row2(L("Millati:","Миллати:"), data.get("nationality","o'zbek"),
         L("Partiyaviyligi:","Партиявийлиги:"), data.get("party", YOQ))
    row2(L("Ma'lumoti:","Маълумоти:"), data.get("edu_level",""),
         L("Tamomlagan:","Тамомлаган:"), data.get("university",""))
    inline2(L("Ma'lumoti bo'yicha mutaxassisligi:","Маълумоти бўйича мутахассислиги:"),
            data.get("speciality","") or "—")
    row2(L("Ilmiy darajasi:","Илмий даражаси:"), data.get("science_degree", YOQ),
         L("Ilmiy unvoni:","Илмий унвони:"), data.get("science_title", YOQ))
    row2(L("Qaysi chet tillarini biladi:","Қайси чет тилларини билади:"), langs_str or YOQ,
         L("Harbiy (maxsus) unvoni:","Ҳарбий (махсус) унвони:"), data.get("military_rank", YOQ))
    long2(L("Davlat mukofotlari va premiyalari bilan taqdirlangan (qanaqa):",
             "Давлат мукофотлари ва мукофотлари билан тақдирланган (қанақа):"),
          data.get("awards", YOQ))
    long2(L("Idoraviy mukofotlar bilan taqdirlangan (qanaqa):",
             "Идоравий мукофотлар билан тақдирланган (қанақа):"),
          data.get("departmental_awards", YOQ))
    long2(L("Xalq deputatlari, respublika, viloyat, shahar va tuman Kengashi deputatimi "
            "yoki boshqa saylanadigan organlarning a'zosimi (to'liq ko'rsatilishi lozim):",
            "Халқ депутатлари, республика, вилоят, шаҳар ва туман Кенгаши депутатими "
            "ёки бошқа сайланадиган органларнинг аъзосими (тўлиқ кўрсатилиши лозим):"),
          data.get("deputy", YOQ))
    long2(L("Doimiy yashash manzili (aniq ko'rsatilsin):",
             "Доимий яшаш манзили (аниқ кўрсатилсин):"),
          data.get("address",""))

    # ── MEHNAT FAOLIYATI ──
    _para(doc, L("MEHNAT FAOLIYATI","МЕҲНАТ ФАОЛИЯТИ"), bold=True, size=F14,
          align=WD_ALIGN_PARAGRAPH.CENTER, before=10, after=6)

    for w in data.get("work_history", []):
        if isinstance(w, dict):
            f, t = w.get("from",""), w.get("to","")
            org, pos = w.get("org",""), w.get("pos","")
            if f and t:   line = f"{f}-{t} yy. - {org}"
            elif f:       line = f"{f} y. - h.v. - {org}"
            else:         line = org
            if pos: line += f" {pos}"
        else:
            line = str(w)
        if line.strip():
            _para(doc, line, before=0, after=4)

    phones = data.get("phones", {})
    tel = []
    if phones.get("me"):     tel.append(phones["me"])
    if phones.get("father"): tel.append(f"ota: {phones['father']}")
    if phones.get("mother"): tel.append(f"ona: {phones['mother']}")
    if tel:
        _para(doc, L("Tel.: ","Тел.: ") + "     ".join(tel), bold=True, before=10)

    # ── SAHIFA 2: QARINDOSHLAR ──
    doc.add_page_break()

    _para(doc, fullname + L("ning yaqin qarindoshlari haqida","нинг яқин қариндошлари ҳақида"),
          bold=True, size=Pt(12), align=WD_ALIGN_PARAGRAPH.CENTER)
    _para(doc, L("MA'LUMOT","МАЪЛУМОТ"),
          bold=True, size=Pt(12), align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=10)

    relatives = data.get("relatives", [])
    if relatives:
        rt = doc.add_table(rows=1, cols=5)
        rt.style = "Table Grid"
        rt.alignment = WD_TABLE_ALIGNMENT.LEFT
        for i, w in enumerate([Cm(2.6), Cm(4.2), Cm(3.4), Cm(4.0), Cm(3.2)]):
            rt.columns[i].width = w
        headers_lat = ["Qarindosh-\nligi","Familiyasi, ismi\nva otasining ismi",
                       "Tug'ilgan yili\nva joyi","Ish joyi va\nlavozimi","Turar joyi"]
        headers_cyr = ["Қариндош-\nлиги","Фамилияси, исми\nва отасининг исми",
                       "Туғилган йили\nва жойи","Иш жойи ва\nлавозими","Турар жойи"]
        headers = headers_cyr if IS_CYR else headers_lat
        for i, h in enumerate(headers):
            _cell_borders(rt.cell(0, i))
            _cell_para(rt.cell(0, i), h, bold=True,
                       align=WD_ALIGN_PARAGRAPH.CENTER)
        for rel in relatives:
            row = rt.add_row()
            byear = rel.get("byear","")
            bplace = rel.get("bplace","")
            birth = f"{byear} y., {bplace}" if byear and bplace else (byear or bplace)
            vals = [rel.get("rel",""), rel.get("fio",""),
                    birth, rel.get("job",""),
                    rel.get("addr","")]
            for i, v in enumerate(vals):
                _cell_borders(row.cells[i])
                if i == 0:
                    _cell_para(row.cells[i], v, bold=True,
                               align=WD_ALIGN_PARAGRAPH.CENTER)
                else:
                    _cell_para(row.cells[i], v)

    doc.save(output_path)
