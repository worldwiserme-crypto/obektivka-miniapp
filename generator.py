from docx import Document
from docx.shared import Pt, Cm, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

F  = "Times New Roman"
FS = Pt(11)


def _font(run, bold=False, size=None):
    run.font.name = F
    run.font.size = size or FS
    run.font.bold = bold
    try:
        rpr = run._element.get_or_add_rPr()
        rFonts = rpr.get_or_add_rFonts()
        rFonts.set(qn("w:eastAsia"), F)
    except Exception:
        pass


def _set_border(cell, val="single", sz="4", color="000000"):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    # Eski tcBorders ni o'chirish
    for old_borders in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old_borders)
    tcBorders = OxmlElement("w:tcBorders")
    for side in ["top", "left", "bottom", "right"]:
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), val)
        b.set(qn("w:sz"), sz)
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), color)
        tcBorders.append(b)
    tcPr.append(tcBorders)


def _no_border(cell):
    _set_border(cell, val="none", sz="0", color="FFFFFF")


def _cell_p(cell, text, bold=False, center=False, size=None):
    for p in cell.paragraphs:
        p.clear()
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(1)
    p.paragraph_format.line_spacing = Pt(13)
    r = p.add_run(text or "")
    _font(r, bold=bold, size=size)


def _para(doc, text="", bold=False, center=False, before=0, after=3, size=None):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after  = Pt(after)
    p.paragraph_format.line_spacing = Pt(13)
    if text:
        r = p.add_run(text)
        _font(r, bold=bold, size=size)
    return p


def _info_row(tbl, label1, val1, label2="", val2=""):
    """2 ustunli info jadvali qatori"""
    row = tbl.add_row()
    row.height = Pt(16)

    c0 = row.cells[0]
    c1 = row.cells[1]
    _no_border(c0)
    _no_border(c1)

    # Chap
    p0 = c0.paragraphs[0]
    p0.paragraph_format.space_before = Pt(0)
    p0.paragraph_format.space_after  = Pt(0)
    p0.paragraph_format.line_spacing = Pt(14)
    r = p0.add_run(label1 + " "); _font(r, bold=True)
    r = p0.add_run(val1 or "—"); _font(r)

    # O'ng
    if label2:
        p1 = c1.paragraphs[0]
        p1.paragraph_format.space_before = Pt(0)
        p1.paragraph_format.space_after  = Pt(0)
        p1.paragraph_format.line_spacing = Pt(14)
        r = p1.add_run(label2 + " "); _font(r, bold=True)
        r = p1.add_run(val2 or "—"); _font(r)


def generate(data: dict, output_path: str):
    doc = Document()

    sec = doc.sections[0]
    sec.page_width    = Cm(21)
    sec.page_height   = Cm(29.7)
    sec.top_margin    = Cm(2.0)
    sec.bottom_margin = Cm(2.0)
    sec.left_margin   = Cm(3.0)
    sec.right_margin  = Cm(1.5)

    doc.styles["Normal"].font.name = F
    doc.styles["Normal"].font.size = FS

    # ── SARLAVHA ──
    _para(doc, "MA'LUMOTNOMA", bold=True, center=True, before=0, after=6)

    # ── ISM + RASM JADVALI ──
    # 2 ustun: chap=ism+lavozim, o'ng=rasm
    header_tbl = doc.add_table(rows=1, cols=2)
    header_tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    header_tbl.columns[0].width = Cm(13.5)
    header_tbl.columns[1].width = Cm(3.0)

    lc = header_tbl.cell(0, 0)
    rc = header_tbl.cell(0, 1)
    _no_border(lc)

    # Ism
    lp = lc.paragraphs[0]
    lp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    lp.paragraph_format.space_before = Pt(0)
    lp.paragraph_format.space_after  = Pt(4)
    lp.paragraph_format.line_spacing = Pt(14)
    r = lp.add_run(data.get("fullname", "")); _font(r, bold=True)

    # Lavozim
    job = f"{data.get('job_year','')} {data.get('current_job','')}".strip()
    lp2 = lc.add_paragraph()
    lp2.paragraph_format.space_before = Pt(0)
    lp2.paragraph_format.space_after  = Pt(0)
    lp2.paragraph_format.line_spacing = Pt(14)
    r = lp2.add_run(job); _font(r)

    # Rasm joyi — chegara bilan
    _set_border(rc)
    rc.width = Cm(3.0)
    rp = rc.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rp.paragraph_format.space_before = Pt(2)
    rp.paragraph_format.space_after  = Pt(2)
    rp.paragraph_format.line_spacing = Pt(13)
    for line in ["3×4 sm", "oxirgi 3 oy", "ichida olingan", "rangli surat"]:
        r = rp.add_run(line + "\n"); _font(r, size=Pt(8))

    _para(doc, "", before=6, after=0)

    # ── 2 USTUNLI MA'LUMOTLAR JADVALI ──
    bd = data.get("birthdate", "")
    if bd and "-" in bd:
        y, m, d = bd.split("-")
        bd = f"{d}.{m}.{y}"

    info_tbl = doc.add_table(rows=0, cols=2)
    info_tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    info_tbl.columns[0].width = Cm(8.0)
    info_tbl.columns[1].width = Cm(8.5)

    _info_row(info_tbl, "Tug'ilgan yili:", bd, "Tug'ilgan joyi:", data.get("birthplace",""))
    _info_row(info_tbl, "Millati:", data.get("nationality","o'zbek"), "Partiyaviyligi:", data.get("party","yo'q"))
    _info_row(info_tbl, "Ma'lumoti:", data.get("edu_level",""), "Tamomlagan:", data.get("university",""))
    _info_row(info_tbl, "Ma'lumoti bo'yicha mutaxassisligi:", data.get("speciality",""))
    _info_row(info_tbl, "Ilmiy darajasi:", data.get("science_degree","yo'q"), "Ilmiy unvoni:", data.get("science_title","yo'q"))

    langs = data.get("langs", [])
    langs_str = ", ".join(langs) if isinstance(langs, list) else str(langs)
    _info_row(info_tbl, "Qaysi chet tillarini biladi:", langs_str or "yo'q", "Harbiy (maxsus) unvoni:", "yo'q")

    _para(doc, "", before=4, after=0)

    # Uzoq labellar — alohida paragraf
    def long_row(label, val):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after  = Pt(2)
        p.paragraph_format.line_spacing = Pt(14)
        r1 = p.add_run(label + " "); _font(r1, bold=True)
        r2 = p.add_run(val or "yo'q"); _font(r2)

    long_row("Davlat mukofotlari va preemiyalari bilan taqdirlangan (qanaqa):", data.get("awards","yo'q"))
    long_row("Idoraviy mukofotlar bilan taqdirlangan (qanaqa):", data.get("departmental_awards","yo'q"))
    long_row(
        "Xalq deputatlari, respublika, viloyat, shahar va tuman Kengashi deputatimi yoki boshqa "
        "saylanadigan organlarning a'zosimi (to'liq ko'rsatilishi lozim):",
        data.get("deputy","yo'q"))
    long_row("Doimiy yashash manzili (aniq ko'rsatilsin):", data.get("address",""))
    if data.get("passport"):
        long_row("Pasport / JShShIR:", data.get("passport",""))

    # ── MEHNAT FAOLIYATI ──
    _para(doc, "", before=6, after=0)
    _para(doc, "MEHNAT FAOLIYATI", bold=True, center=True, before=0, after=6)

    for w in data.get("work_history", []):
        if isinstance(w, dict):
            f, t, o, pos = w.get("from",""), w.get("to",""), w.get("org",""), w.get("pos","")
            line = f"{f}–{t} yy. – {o}" + (f", {pos}" if pos else "")
        else:
            line = str(w)
        if line.strip("–- "):
            _para(doc, line, before=1, after=1)

    phones = data.get("phones", {})
    tel = []
    if phones.get("me"):     tel.append(phones["me"])
    if phones.get("father"): tel.append(f"ota: {phones['father']}")
    if phones.get("mother"): tel.append(f"ona: {phones['mother']}")
    if tel:
        _para(doc, "Tel.: " + "   ".join(tel), bold=True, before=8, after=0)

    # ── SAHIFA 2: QARINDOSHLAR ──
    doc.add_page_break()

    fullname = data.get("fullname", "")
    _para(doc, f"{fullname}ning yaqin qarindoshlari haqida", bold=True, center=True, before=0, after=0)
    _para(doc, "MA'LUMOT", bold=True, center=True, before=0, after=8)

    relatives = data.get("relatives", [])
    if relatives:
        tbl = doc.add_table(rows=1, cols=5)
        tbl.style = "Table Grid"
        tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
        for i, w in enumerate([Cm(2.5), Cm(4.0), Cm(3.5), Cm(4.0), Cm(3.0)]):
            tbl.columns[i].width = w

        for i, h in enumerate([
            "Qarindosh-\nligi",
            "Familiyasi, ismi\nva otasining ismi",
            "Tug'ilgan yili\nva joyi",
            "Ish joyi va\nlavozimi",
            "Turar joyi"
        ]):
            c = tbl.cell(0, i)
            _set_border(c)
            _cell_p(c, h, bold=True, center=True)

        for rel in relatives:
            row = tbl.add_row()
            for i, v in enumerate([
                rel.get("rel",""), rel.get("fio",""),
                rel.get("birth",""), rel.get("job",""), rel.get("addr","")
            ]):
                _set_border(row.cells[i])
                _cell_p(row.cells[i], v)

    doc.save(output_path)
