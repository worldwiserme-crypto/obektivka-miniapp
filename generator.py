import base64, io, os
from docx import Document
from docx.shared import Pt, Cm, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn, nsmap
from docx.oxml import OxmlElement
from lxml import etree

F  = "Times New Roman"
FS = Pt(11)
F14 = Pt(14)


def font(run, bold=False, size=None):
    run.font.name = F
    run.font.size = size or FS
    run.font.bold = bold
    try:
        rpr = run._element.get_or_add_rPr()
        rpr.get_or_add_rFonts().set(qn("w:eastAsia"), F)
    except Exception:
        pass


def add_run(p, text, bold=False, size=None):
    r = p.add_run(text)
    font(r, bold=bold, size=size)
    return r


def new_para(doc, align=WD_ALIGN_PARAGRAPH.LEFT, before=0, after=0):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after  = Pt(after)
    p.paragraph_format.line_spacing = Pt(14)
    return p


def tab_stop(p, pos=5040):
    pPr = p._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "left")
    tab.set(qn("w:pos"), str(pos))
    tabs.append(tab)
    pPr.append(tabs)


def set_borders(cell):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    borders = OxmlElement("w:tcBorders")
    for side in ["top", "left", "bottom", "right"]:
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), "000000")
        borders.append(b)
    tcPr.append(borders)


def no_border(cell):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    borders = OxmlElement("w:tcBorders")
    for side in ["top", "left", "bottom", "right"]:
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "none")
        b.set(qn("w:sz"), "0")
        b.set(qn("w:color"), "auto")
        borders.append(b)
    tcPr.append(borders)


def cell_para(cell, text, bold=False, center=False):
    p = cell.paragraphs[0]
    p.clear()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after  = Pt(1)
    p.paragraph_format.line_spacing = Pt(13)
    r = p.add_run(text or "—")
    font(r, bold=bold)


def add_floating_photo(doc, para, img_bytes, width_cm=3.0, height_cm=4.0):
    """Rasmni floating anchor sifatida paragrafga qo'shish"""
    from docx.oxml.ns import nsmap as doc_nsmap

    # Rasmni doc ga qo'shish
    pic_part = doc.part.new_pic_inline(img_bytes, width_cm=Cm(width_cm), height_cm=Cm(height_cm))

    # inline -> anchor ga o'zgartirish
    # Oddiy inline picture qo'shamiz, keyin to'g'ri o'ng burchakka joylashtiramiz
    run = para.add_run()
    run._element.append(make_pic_anchor(doc, img_bytes, width_cm, height_cm))


def make_pic_anchor(doc, img_bytes, w_cm, h_cm):
    """Anchored (floating) picture XML yaratish"""
    from docx.shared import Cm
    import hashlib

    # Rasmni part ga saqlash
    image_stream = io.BytesIO(img_bytes)
    pic_part, rId = doc.part.get_or_add_image(image_stream)

    w_emu = int(Cm(w_cm))
    h_emu = int(Cm(h_cm))

    # O'ng margin dan offset: sahifa kengligi - o'ng margin - rasm kengligi
    # chap margin = 3cm, o'ng margin = 1cm, sahifa = 21cm
    # Rasmning horizontal pozitsiyasi: sahifa o'ngidan 1cm
    pos_x = int(Cm(21 - 1.0 - w_cm))  # o'ng tomondan
    pos_y = int(Cm(0.5))               # yuqoridan

    anchor_xml = f'''<wp:anchor distT="0" distB="0" distL="114300" distR="114300"
        simplePos="0" relativeHeight="251658240" behindDoc="0"
        locked="0" layoutInCell="1" allowOverlap="1"
        xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
  <wp:simplePos x="0" y="0"/>
  <wp:positionH relativeFrom="page">
    <wp:posOffset>{pos_x}</wp:posOffset>
  </wp:positionH>
  <wp:positionV relativeFrom="page">
    <wp:posOffset>{pos_y}</wp:posOffset>
  </wp:positionV>
  <wp:extent cx="{w_emu}" cy="{h_emu}"/>
  <wp:effectExtent l="0" t="0" r="0" b="0"/>
  <wp:wrapSquare wrapText="bothSides"/>
  <wp:docPr id="1" name="Photo"/>
  <wp:cNvGraphicFramePr>
    <a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>
  </wp:cNvGraphicFramePr>
  <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
    <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
      <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
        <pic:nvPicPr>
          <pic:cNvPr id="0" name="Photo"/>
          <pic:cNvPicPr/>
        </pic:nvPicPr>
        <pic:blipFill>
          <a:blip r:embed="{rId}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>
          <a:stretch><a:fillRect/></a:stretch>
        </pic:blipFill>
        <pic:spPr>
          <a:xfrm><a:off x="0" y="0"/><a:ext cx="{w_emu}" cy="{h_emu}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </pic:spPr>
      </pic:pic>
    </a:graphicData>
  </a:graphic>
</wp:anchor>'''

    drawing = OxmlElement("w:drawing")
    drawing.append(etree.fromstring(anchor_xml))
    return drawing


def add_photo_placeholder(doc, para):
    """Rasm o'rniga to'rtburchak placeholder"""
    # Jadval orqali o'ng burchakda 3x4 sm quti
    pass


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

    fullname = data.get("fullname", "")
    photo_b64 = data.get("photo_base64", "")

    # ── 1. MA'LUMOTNOMA ──
    p = new_para(doc, WD_ALIGN_PARAGRAPH.LEFT, before=0, after=0)
    add_run(p, "MA'LUMOTNOMA", bold=False, size=F14)

    # Rasm: floating anchor
    if photo_b64:
        try:
            img_bytes = base64.b64decode(photo_b64.split(",")[-1])
            p._p.append(make_pic_anchor(doc, img_bytes, w_cm=3.0, h_cm=4.0))
        except Exception as e:
            pass
    else:
        # Placeholder: jadval bilan o'ng burchakda
        # Oddiy text box o'rniga jadval ishlatamiz - sahifa o'ngiga joylashtiramiz
        tbl = doc.add_table(rows=1, cols=2)
        tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
        tbl.columns[0].width = Cm(13.7)
        tbl.columns[1].width = Cm(3.0)
        lc = tbl.cell(0, 0)
        rc = tbl.cell(0, 1)
        no_border(lc)
        set_borders(rc)
        lc.paragraphs[0].clear()
        rc.paragraphs[0].clear()
        rp = rc.paragraphs[0]
        rp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        rp.paragraph_format.space_before = Pt(8)
        rp.paragraph_format.line_spacing = Pt(12)
        for line in ["3×4 sm,", "oxirgi 3 oy", "ichida olingan", "rangli surat"]:
            add_run(rp, line + "\n", size=Pt(8))

    # ── 2. Bo'sh qator (CENTER) ──
    p2 = new_para(doc, WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)

    # ── 3. Fullname — CENTER, bold, 14pt ──
    p3 = new_para(doc, WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    add_run(p3, fullname, bold=True, size=F14)

    # ── 4. Bo'sh qator ──
    new_para(doc, before=0, after=0)

    # ── 5. Lavozim (chap, 11pt) ──
    job_year = data.get("job_year", "")
    current_job = data.get("current_job", "")
    if job_year:
        p4 = new_para(doc, before=0, after=0)
        add_run(p4, job_year, size=FS)
    if current_job:
        p5 = new_para(doc, before=0, after=0)
        add_run(p5, current_job, size=FS)

    # ── 6. MA'LUMOTLAR (label qator + qiymat qator, tab bilan) ──
    def label_row(l1, l2=""):
        p = new_para(doc, before=8, after=0)
        tab_stop(p)
        add_run(p, l1, bold=True, size=FS)
        if l2:
            add_run(p, "\t", size=FS)
            add_run(p, l2, bold=True, size=FS)

    def value_row(v1, v2=""):
        p = new_para(doc, before=0, after=0)
        tab_stop(p)
        add_run(p, v1 or "—", size=FS)
        if v2 is not None:
            add_run(p, "\t", size=FS)
            add_run(p, v2 or "—", size=FS)

    def label_value_inline(label, val):
        p = new_para(doc, before=8, after=0)
        add_run(p, label + " ", bold=True, size=FS)
        add_run(p, val or "—", size=FS)

    bd = data.get("birthdate", "")
    if bd and "-" in bd:
        y, m, d = bd.split("-")
        bd = f"{d}.{m}.{y}"

    label_row("Tug'ilgan yili:", "Tug'ilgan joyi:")
    value_row(bd, data.get("birthplace", ""))

    label_row("Millati:", "Partiyaviyligi:")
    value_row(data.get("nationality", "o'zbek"), data.get("party", "yo'q"))

    label_row("Ma'lumoti:", "Tamomlagan:")
    value_row(data.get("edu_level", ""), data.get("university", ""))

    label_value_inline("Ma'lumoti bo'yicha mutaxassisligi:", data.get("speciality", ""))

    label_row("Ilmiy darajasi:", "Ilmiy unvoni:")
    value_row(data.get("science_degree", "yo'q"), data.get("science_title", "yo'q"))

    langs = data.get("langs", [])
    langs_str = ", ".join(langs) if isinstance(langs, list) else str(langs)
    label_row("Qaysi chet tillarini biladi:", "Harbiy (maxsus) unvoni:")
    value_row(langs_str or "yo'q", data.get("military_rank", "yo'q"))

    def long_label_val(label, val):
        p = new_para(doc, before=8, after=0)
        add_run(p, label, bold=True, size=FS)
        p2 = new_para(doc, before=0, after=0)
        add_run(p2, val or "yo'q", size=FS)

    long_label_val(
        "Davlat mukofotlari va premiyalari bilan taqdirlangan (qanaqa):",
        data.get("awards", "yo'q"))

    long_label_val(
        "Idoraviy mukofotlar bilan taqdirlangan (qanaqa):",
        data.get("departmental_awards", "yo'q"))

    long_label_val(
        "Xalq deputatlari, respublika, viloyat, shahar va tuman Kengashi deputatimi yoki "
        "boshqa saylanadigan organlarning a'zosimi (to'liq ko'rsatilishi lozim):",
        data.get("deputy", "yo'q"))

    long_label_val(
        "Doimiy yashash manzili (aniq ko'rsatilsin):",
        data.get("address", ""))

    # ── 7. MEHNAT FAOLIYATI ──
    p = new_para(doc, WD_ALIGN_PARAGRAPH.CENTER, before=10, after=8)
    add_run(p, "MEHNAT FAOLIYATI", bold=True, size=FS)

    for w in data.get("work_history", []):
        if isinstance(w, dict):
            f   = w.get("from", "")
            t   = w.get("to", "")
            org = w.get("org", "")
            pos = w.get("pos", "")
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
            p = new_para(doc, before=0, after=1)
            add_run(p, line, size=FS)

    phones = data.get("phones", {})
    tel = []
    if phones.get("me"):     tel.append(phones["me"])
    if phones.get("father"): tel.append(f"ota: {phones['father']}")
    if phones.get("mother"): tel.append(f"ona: {phones['mother']}")
    if tel:
        p = new_para(doc, before=10, after=0)
        add_run(p, "Tel.:  " + "     ".join(tel), bold=True, size=FS)

    # ── 8. SAHIFA 2: QARINDOSHLAR ──
    doc.add_page_break()

    p = new_para(doc, WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0)
    add_run(p, f"{fullname}ning yaqin qarindoshlari haqida", bold=True, size=FS)

    p = new_para(doc, WD_ALIGN_PARAGRAPH.CENTER, before=0, after=10)
    add_run(p, "MA'LUMOT", bold=True, size=FS)

    relatives = data.get("relatives", [])
    if relatives:
        tbl = doc.add_table(rows=1, cols=5)
        tbl.style = "Table Grid"
        tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
        for i, w in enumerate([Cm(2.6), Cm(4.2), Cm(3.4), Cm(4.0), Cm(3.2)]):
            tbl.columns[i].width = w

        headers = ["Qarindosh-\nligi",
                   "Familiyasi, ismi\nva otasining ismi",
                   "Tug'ilgan yili\nva joyi",
                   "Ish joyi va\nlavozimi",
                   "Turar joyi"]
        for i, h in enumerate(headers):
            c = tbl.cell(0, i)
            set_borders(c)
            cell_para(c, h, bold=True, center=True)

        for rel in relatives:
            row = tbl.add_row()
            for i, v in enumerate([rel.get("rel",""), rel.get("fio",""),
                                    rel.get("birth",""), rel.get("job",""), rel.get("addr","")]):
                set_borders(row.cells[i])
                cell_para(row.cells[i], v)

    doc.save(output_path)
