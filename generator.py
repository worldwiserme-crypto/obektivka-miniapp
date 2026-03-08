import base64, io
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from lxml import etree

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


def _tab_stop(p, pos=4800):
    pPr = p._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    t = OxmlElement("w:tab")
    t.set(qn("w:val"), "left")
    t.set(qn("w:pos"), str(pos))
    tabs.append(t)
    pPr.append(tabs)


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


def _cell_para(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT):
    p = cell.paragraphs[0]
    p.clear()
    p.alignment = align
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(1)
    p.paragraph_format.line_spacing = Pt(13)
    r = p.add_run(text or "—")
    _font(r, bold=bold)


def _add_floating_photo(para, doc, img_bytes, w_cm=3.0, h_cm=4.0):
    """Rasmni paragraph ga floating anchor sifatida qo'shish"""
    # Rasmni doc.part ga saqlash
    img_stream = io.BytesIO(img_bytes)
    pic_part, rId = doc.part.get_or_add_image(img_stream)

    # EMU hisoblash
    w_emu = int(w_cm * 360000)
    h_emu = int(h_cm * 360000)

    # posH: sahifa o'ng chetidan 1 cm qoldirib
    # text kengligi = 21 - 2.7 - 1.0 = 17.3 cm
    # foto x pozitsiya = 17.3 - 3.0 = 14.3 cm = 5148000 EMU
    pos_h = int((17.3 - w_cm) * 360000)
    pos_v = 24130  # paragrafdan 0.067 cm pastda

    anchor_xml = (
        '<wp:anchor distT="0" distB="0" distL="114300" distR="114300" '
        'simplePos="0" relativeHeight="251655168" behindDoc="0" '
        'locked="0" layoutInCell="1" allowOverlap="1" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        '<wp:simplePos x="0" y="0"/>'
        f'<wp:positionH relativeFrom="column"><wp:posOffset>{pos_h}</wp:posOffset></wp:positionH>'
        f'<wp:positionV relativeFrom="paragraph"><wp:posOffset>{pos_v}</wp:posOffset></wp:positionV>'
        f'<wp:extent cx="{w_emu}" cy="{h_emu}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        '<wp:wrapNone/>'
        '<wp:docPr id="100" name="Photo"/>'
        '<wp:cNvGraphicFramePr>'
        '<a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>'
        '</wp:cNvGraphicFramePr>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:nvPicPr>'
        '<pic:cNvPr id="101" name="Photo"/>'
        '<pic:cNvPicPr><a:picLocks noChangeAspect="1" noChangeArrowheads="1"/></pic:cNvPicPr>'
        '</pic:nvPicPr>'
        '<pic:blipFill>'
        f'<a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:embed="{rId}"/>'
        '<a:stretch><a:fillRect/></a:stretch>'
        '</pic:blipFill>'
        '<pic:spPr bwMode="auto">'
        f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{w_emu}" cy="{h_emu}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        '<a:noFill/>'
        '</pic:spPr>'
        '</pic:pic>'
        '</a:graphicData>'
        '</a:graphic>'
        '</wp:anchor>'
    )

    drawing = OxmlElement("w:drawing")
    drawing.append(etree.fromstring(anchor_xml))

    run = para.add_run()
    run._element.append(drawing)


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

    # ── JADVAL: [matn | rasm] — borders YO'Q ──
    # Chap katta cell: MA'LUMOTNOMA + fullname + lavozim
    # O'ng kichik cell: rasm 3x4 sm
    tbl = doc.add_table(rows=1, cols=2)
    # Jadval borderlarini o'chirish
    tblEl = tbl._tbl
    tblPr = tblEl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tblEl.insert(0, tblPr)
    tblBord = OxmlElement("w:tblBorders")
    for side in ["top","left","bottom","right","insideH","insideV"]:
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "none")
        tblBord.append(b)
    tblPr.append(tblBord)

    tbl.columns[0].width = Cm(13.5)
    tbl.columns[1].width = Cm(3.0)

    lc = tbl.cell(0, 0)
    rc = tbl.cell(0, 1)

    # Har ikki celldan border olib tashlash
    for cell in [lc, rc]:
        tcPr = cell._tc.get_or_add_tcPr()
        tcBord = OxmlElement("w:tcBorders")
        for side in ["top","left","bottom","right"]:
            b = OxmlElement(f"w:{side}")
            b.set(qn("w:val"), "none")
            tcBord.append(b)
        tcPr.append(tcBord)

    # ── Chap cell: MA'LUMOTNOMA ──
    lc.paragraphs[0].clear()

    p0 = lc.paragraphs[0]
    p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p0.paragraph_format.space_before = Pt(0)
    p0.paragraph_format.space_after  = Pt(0)
    p0.paragraph_format.line_spacing = Pt(16)
    _run(p0, "MA'LUMOTNOMA", bold=True, size=F14)

    # ── Chap cell: bo'sh qator ──
    pb = lc.add_paragraph()
    pb.paragraph_format.space_before = Pt(0)
    pb.paragraph_format.space_after  = Pt(0)
    pb.paragraph_format.line_spacing = Pt(8)

    # ── Chap cell: fullname ──
    p2 = lc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_before = Pt(0)
    p2.paragraph_format.space_after  = Pt(0)
    p2.paragraph_format.line_spacing = Pt(16)
    _run(p2, fullname, bold=True, size=F14)

    # ── Chap cell: lavozim yili ──
    if job_year:
        p4 = lc.add_paragraph()
        p4.paragraph_format.space_before = Pt(6)
        p4.paragraph_format.space_after  = Pt(0)
        p4.paragraph_format.line_spacing = Pt(14)
        _run(p4, job_year, size=FS)

    # ── Chap cell: lavozim nomi ──
    if current_job:
        p5 = lc.add_paragraph()
        p5.paragraph_format.space_before = Pt(0)
        p5.paragraph_format.space_after  = Pt(0)
        p5.paragraph_format.line_spacing = Pt(14)
        _run(p5, current_job, size=FS)

    # ── O'ng cell: rasm ──
    rc.paragraphs[0].clear()
    rp = rc.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.CENTER
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

    # ══════════════════════════════════════
    # MA'LUMOTLAR
    # ══════════════════════════════════════
    TAB = 4800

    def label_row(l1, l2=None):
        p = doc.add_paragraph()
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
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(7)
        p.paragraph_format.space_after  = Pt(0)
        p.paragraph_format.line_spacing = Pt(14)
        _run(p, label, bold=True, size=FS)
        p2 = doc.add_paragraph()
        p2.paragraph_format.space_before = Pt(0)
        p2.paragraph_format.space_after  = Pt(0)
        p2.paragraph_format.line_spacing = Pt(14)
        _run(p2, val or "yo'q", size=FS)

    bd = data.get("birthdate", "")
    if bd and "-" in bd:
        y, m, d = bd.split("-")
        bd = f"{d}.{m}.{y}"

    label_row("Tug'ilgan yili:", "Tug'ilgan joyi:")
    value_row(bd, data.get("birthplace",""))

    label_row("Millati:", "Partiyaviyligi:")
    value_row(data.get("nationality","o'zbek"), data.get("party","yo'q"))

    label_row("Ma'lumoti:", "Tamomlagan:")
    value_row(data.get("edu_level",""), data.get("university",""))

    # Mutaxassislik — label + tab + qiymat
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(7)
    p.paragraph_format.space_after  = Pt(0)
    p.paragraph_format.line_spacing = Pt(14)
    _tab_stop(p, TAB)
    _run(p, "Ma'lumoti bo'yicha mutaxassisligi:", bold=True, size=FS)
    _run(p, "\t", size=FS)
    _run(p, data.get("speciality","") or "—", size=FS)

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

    # ══════════════════════════════════════
    # MEHNAT FAOLIYATI
    # ══════════════════════════════════════
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

    # ══════════════════════════════════════
    # SAHIFA 2 — QARINDOSHLAR
    # ══════════════════════════════════════
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
