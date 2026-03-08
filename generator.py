import base64, io
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

F   = "Times New Roman"
FS  = Pt(11)
F14 = Pt(14)


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


def generate(data: dict, output_path: str):
    doc = Document()

    sec = doc.sections[0]
    sec.page_width    = Cm(21)
    sec.page_height   = Cm(29.7)
    sec.top_margin    = Cm(1.5)
    sec.bottom_margin = Cm(1.1)
    sec.left_margin   = Cm(2.7)
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
    _run(p0, "MA'LUMOTNOMA", bold=True, size=F14)

    # ── 2. Fullname ──
    p1 = doc.add_paragraph()
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p1.paragraph_format.space_before = Pt(2)
    p1.paragraph_format.space_after  = Pt(0)
    p1.paragraph_format.line_spacing = Pt(16)
    _run(p1, fullname, bold=True, size=F14)

    # ── 3. JADVAL: 3 ustun ──
    # col0=7.5sm, col1=6.8sm, col2=3.2sm (rasm)
    # Qator 0: lavozim (col0+col1 merge) | rasm (col2, barcha qatorlarga merge)
    # Qator 1+: ma'lumotlar (col0=label, col1=label2)
    # Qator 2+: qiymatlar (col0=val1, col1=val2)

    # Nechta info qator kerakligini hisoblaymiz
    # har bir "row2" = 2 qator (label + value), long = 2 qator
    # Jami: 1 (lavozim) + 6*2 (row2) + 4*2 (long) = 1+12+8 = 21 qator
    N_ROWS = 21

    tbl = doc.add_table(rows=N_ROWS, cols=3)
    _kill_tbl_borders(tbl)
    tbl.columns[0].width = Cm(7.5)
    tbl.columns[1].width = Cm(6.8)
    tbl.columns[2].width = Cm(3.2)

    # Barcha celllardan border olib tashlash
    for row in tbl.rows:
        for cell in row.cells:
            _no_border(cell)

    # col2 ni barcha qatorlarda merge (rasm uchun)
    photo_cell = tbl.cell(0, 2)
    for i in range(1, N_ROWS):
        photo_cell = photo_cell.merge(tbl.cell(i, 2))

    # Rasmni o'ng cellga qo'yish
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

    # Qator 0: lavozim (col0 + col1 merge)
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

    # Info qatorlarni yozish (qator indexini kuzatamiz)
    ri = [1]  # mutable counter

    def row2(l1, v1, l2=None, v2=None):
        # Label qatori
        _cp(tbl.cell(ri[0], 0), l1, bold=True, before=5)
        _cp(tbl.cell(ri[0], 1), l2 or "", bold=True, before=5)
        ri[0] += 1
        # Qiymat qatori
        _cp(tbl.cell(ri[0], 0), v1)
        _cp(tbl.cell(ri[0], 1), v2 or "")
        ri[0] += 1

    def long2(label, val):
        # Label — col0+col1 merge
        mc = tbl.cell(ri[0], 0).merge(tbl.cell(ri[0], 1))
        _cp(mc, label, bold=True, before=5)
        ri[0] += 1
        # Qiymat — col0+col1 merge
        mc2 = tbl.cell(ri[0], 0).merge(tbl.cell(ri[0], 1))
        _cp(mc2, val)
        ri[0] += 1

    row2("Tug'ilgan yili:", bd, "Tug'ilgan joyi:", data.get("birthplace",""))
    row2("Millati:", data.get("nationality","o'zbek"), "Partiyaviyligi:", data.get("party","yo'q"))
    row2("Ma'lumoti:", data.get("edu_level",""), "Tamomlagan:", data.get("university",""))
    row2("Ma'lumoti bo'yicha mutaxassisligi:", data.get("speciality","") or "—")
    row2("Ilmiy darajasi:", data.get("science_degree","yo'q"), "Ilmiy unvoni:", data.get("science_title","yo'q"))
    row2("Qaysi chet tillarini biladi:", langs_str or "yo'q", "Harbiy (maxsus) unvoni:", data.get("military_rank","yo'q"))
    long2("Davlat mukofotlari va premiyalari bilan taqdirlangan (qanaqa):", data.get("awards","yo'q"))
    long2("Idoraviy mukofotlar bilan taqdirlangan (qanaqa):", data.get("departmental_awards","yo'q"))
    long2("Xalq deputatlari, respublika, viloyat, shahar va tuman Kengashi deputatimi "
          "yoki boshqa saylanadigan organlarning a'zosimi (to'liq ko'rsatilishi lozim):", data.get("deputy","yo'q"))
    long2("Doimiy yashash manzili (aniq ko'rsatilsin):", data.get("address",""))

    # ── MEHNAT FAOLIYATI ──
    _para(doc, "MEHNAT FAOLIYATI", bold=True,
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
            _para(doc, line, before=0, after=1)

    phones = data.get("phones", {})
    tel = []
    if phones.get("me"):     tel.append(phones["me"])
    if phones.get("father"): tel.append(f"ota: {phones['father']}")
    if phones.get("mother"): tel.append(f"ona: {phones['mother']}")
    if tel:
        _para(doc, "Tel.:  " + "     ".join(tel), bold=True, before=10)

    # ── SAHIFA 2: QARINDOSHLAR ──
    doc.add_page_break()

    _para(doc, f"{fullname}ning yaqin qarindoshlari haqida",
          bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    _para(doc, "MA'LUMOT",
          bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=10)

    relatives = data.get("relatives", [])
    if relatives:
        rt = doc.add_table(rows=1, cols=5)
        rt.style = "Table Grid"
        rt.alignment = WD_TABLE_ALIGNMENT.LEFT
        for i, w in enumerate([Cm(2.6), Cm(4.2), Cm(3.4), Cm(4.0), Cm(3.2)]):
            rt.columns[i].width = w
        for i, h in enumerate(["Qarindosh-\nligi",
                                "Familiyasi, ismi\nva otasining ismi",
                                "Tug'ilgan yili\nva joyi",
                                "Ish joyi va\nlavozimi",
                                "Turar joyi"]):
            _cell_borders(rt.cell(0, i))
            _cell_para(rt.cell(0, i), h, bold=True,
                       align=WD_ALIGN_PARAGRAPH.CENTER)
        for rel in relatives:
            row = rt.add_row()
            for i, v in enumerate([rel.get("rel",""), rel.get("fio",""),
                                    rel.get("birth",""), rel.get("job",""),
                                    rel.get("addr","")]):
                _cell_borders(row.cells[i])
                _cell_para(row.cells[i], v)

    doc.save(output_path)
