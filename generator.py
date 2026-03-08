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


def _para(container, text="", bold=False, size=None,
          align=WD_ALIGN_PARAGRAPH.LEFT, before=0, after=0, spacing=14):
    p = container.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after  = Pt(after)
    p.paragraph_format.line_spacing = Pt(spacing)
    if text:
        _run(p, text, bold=bold, size=size)
    return p


def _tab_stop(p, pos=4800):
    pPr = p._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    t = OxmlElement("w:tab")
    t.set(qn("w:val"), "left")
    t.set(qn("w:pos"), str(pos))
    tabs.append(t)
    pPr.append(tabs)


def _kill_table_borders(tbl):
    """Jadval va barcha celllardan har qanday borderlarni o'chiradi"""
    tblEl = tbl._tbl
    tblPr = tblEl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tblEl.insert(0, tblPr)
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    tb = OxmlElement("w:tblBorders")
    for side in ["top","left","bottom","right","insideH","insideV"]:
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "none")
        b.set(qn("w:sz"), "0")
        b.set(qn("w:color"), "auto")
        tb.append(b)
    tblPr.append(tb)
    for row in tbl.rows:
        for cell in row.cells:
            _cell_no_border(cell)


def _cell_borders(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    cb = OxmlElement("w:tcBorders")
    for side in ["top","left","bottom","right"]:
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), "000000")
        cb.append(b)
    tcPr.append(cb)


def _cell_no_border(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    cb = OxmlElement("w:tcBorders")
    for side in ["top","left","bottom","right"]:
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "none")
        b.set(qn("w:sz"), "0")
        b.set(qn("w:color"), "auto")
        cb.append(b)
    tcPr.append(cb)


def _cell_para(cell, text, bold=False,
               align=WD_ALIGN_PARAGRAPH.LEFT):
    p = cell.paragraphs[0]
    p.clear()
    p.alignment = align
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(1)
    p.paragraph_format.line_spacing = Pt(13)
    r = p.add_run(text or "—")
    _font(r, bold=bold)


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

    # ═══════════════════════════════════════════════
    # BLOK 1A: MA'LUMOTNOMA — to'liq kenglikda, markazda
    # ═══════════════════════════════════════════════
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after  = Pt(0)
    p_title.paragraph_format.line_spacing = Pt(16)
    _run(p_title, "MA'LUMOTNOMA", size=F14)

    # ═══════════════════════════════════════════════
    # BLOK 1B: Fullname — to'liq kenglikda, markazda, bold, 14pt
    # ═══════════════════════════════════════════════
    p_name = doc.add_paragraph()
    p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_name.paragraph_format.space_before = Pt(2)
    p_name.paragraph_format.space_after  = Pt(0)
    p_name.paragraph_format.line_spacing = Pt(16)
    _run(p_name, fullname, bold=True, size=F14)

    # ═══════════════════════════════════════════════
    # BLOK 1C: LAVOZIM (chap) | RASM (o'ng)
    # Jadval: borders YO'Q, faqat mazmun
    # ═══════════════════════════════════════════════
    tbl = doc.add_table(rows=1, cols=2)
    _kill_table_borders(tbl)
    tbl.columns[0].width = Cm(13.5)
    tbl.columns[1].width = Cm(3.0)

    lc = tbl.cell(0, 0)
    rc = tbl.cell(0, 1)
    _cell_no_border(lc)
    _cell_no_border(rc)

    # Chap cell: lavozim yili + nomi
    lc.paragraphs[0].clear()
    first = True
    if job_year:
        p = lc.paragraphs[0] if first else lc.add_paragraph()
        first = False
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after  = Pt(0)
        p.paragraph_format.line_spacing = Pt(14)
        _run(p, job_year, size=FS)
    if current_job:
        p = lc.paragraphs[0] if first else lc.add_paragraph()
        first = False
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(0)
        p.paragraph_format.line_spacing = Pt(14)
        _run(p, current_job, size=FS)

    # O'ng cell: rasm — to'liq 3x4 sm, hech qanday border yo'q
    rc.paragraphs[0].clear()
    rp = rc.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rp.paragraph_format.space_before = Pt(0)
    rp.paragraph_format.space_after  = Pt(0)
    # line_spacing YO'Q — rasm balandligini cheklamasligi uchun
    rp.paragraph_format.line_spacing = None

    if photo_b64:
        try:
            img_bytes = base64.b64decode(photo_b64.split(",")[-1])
            run = rp.add_run()
            run.add_picture(io.BytesIO(img_bytes), width=Cm(3.0), height=Cm(4.0))
        except Exception:
            pass

    # ═══════════════════════════════════════════════
    # BLOK 2: MA'LUMOTLAR
    # ═══════════════════════════════════════════════
    C = WD_ALIGN_PARAGRAPH
    TAB = 4800  # ~8.5 sm

    def label_row(l1, l2=None):
        p = doc.add_paragraph()
        p.alignment = C.LEFT
        p.paragraph_format.space_before = Pt(7)
        p.paragraph_format.space_after  = Pt(0)
        p.paragraph_format.line_spacing = Pt(14)
        if l2:
            _tab_stop(p, TAB)
        _run(p, l1, bold=True, size=FS)
        if l2:
            _run(p, "\t", size=FS)
            _run(p, l2, bold=True, size=FS)

    def value_row(v1, v2=None):
        p = doc.add_paragraph()
        p.alignment = C.LEFT
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after  = Pt(0)
        p.paragraph_format.line_spacing = Pt(14)
        if v2 is not None:
            _tab_stop(p, TAB)
        _run(p, v1 or "—", size=FS)
        if v2 is not None:
            _run(p, "\t", size=FS)
            _run(p, v2 or "—", size=FS)

    def long_lv(label, val):
        label_row(label)
        value_row(val or "yo'q")

    bd = data.get("birthdate", "")
    if bd and "-" in bd:
        y, m, d = bd.split("-")
        bd = f"{d}.{m}.{y}"

    label_row("Tug'ilgan yili:", "Tug'ilgan joyi:")
    value_row(bd, data.get("birthplace", ""))

    label_row("Millati:", "Partiyaviyligi:")
    value_row(data.get("nationality","o'zbek"), data.get("party","yo'q"))

    label_row("Ma'lumoti:", "Tamomlagan:")
    value_row(data.get("edu_level",""), data.get("university",""))

    label_row("Ma'lumoti bo'yicha mutaxassisligi:\t" + (data.get("speciality","") or "—"))

    label_row("Ilmiy darajasi:", "Ilmiy unvoni:")
    value_row(data.get("science_degree","yo'q"), data.get("science_title","yo'q"))

    langs = data.get("langs", [])
    langs_str = ", ".join(langs) if isinstance(langs, list) else str(langs)
    label_row("Qaysi chet tillarini biladi:", "Harbiy (maxsus) unvoni:")
    value_row(langs_str or "yo'q", data.get("military_rank","yo'q"))

    long_lv("Davlat mukofotlari va premiyalari bilan taqdirlangan (qanaqa):",
            data.get("awards","yo'q"))

    long_lv("Idoraviy mukofotlar bilan taqdirlangan (qanaqa):",
            data.get("departmental_awards","yo'q"))

    long_lv("Xalq deputatlari, respublika, viloyat, shahar va tuman Kengashi deputatimi "
            "yoki boshqa saylanadigan organlarning a'zosimi (to'liq ko'rsatilishi lozim):",
            data.get("deputy","yo'q"))

    long_lv("Doimiy yashash manzili (aniq ko'rsatilsin):",
            data.get("address",""))

    # ═══════════════════════════════════════════════
    # BLOK 3: MEHNAT FAOLIYATI
    # ═══════════════════════════════════════════════
    _para(doc, "MEHNAT FAOLIYATI", bold=True,
          align=WD_ALIGN_PARAGRAPH.CENTER, before=10, after=6)

    for w in data.get("work_history", []):
        if isinstance(w, dict):
            f   = w.get("from","")
            t   = w.get("to","")
            org = w.get("org","")
            pos = w.get("pos","")
            if f and t:
                line = f"{f}-{t} yy. - {org}"
            elif f:
                line = f"{f} y. - h.v. - {org}"
            else:
                line = org
            if pos:
                line += f" {pos}"
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

    # ═══════════════════════════════════════════════
    # BLOK 4: SAHIFA 2 — QARINDOSHLAR
    # ═══════════════════════════════════════════════
    doc.add_page_break()

    _para(doc, f"{fullname}ning yaqin qarindoshlari haqida",
          bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
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
            _cell_para(rt.cell(0, i), h, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)

        for rel in relatives:
            row = rt.add_row()
            for i, v in enumerate([rel.get("rel",""), rel.get("fio",""),
                                    rel.get("birth",""), rel.get("job",""),
                                    rel.get("addr","")]):
                _cell_borders(row.cells[i])
                _cell_para(row.cells[i], v)

    doc.save(output_path)
