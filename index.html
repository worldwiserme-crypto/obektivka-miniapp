from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

FONT_NAME = "Times New Roman"
FONT_SIZE = Pt(14)

def set_font(run, bold=False, size=None):
    run.font.name = FONT_NAME
    run.font.size = size or FONT_SIZE
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_NAME)

def add_paragraph(doc, text="", bold=False, align=WD_ALIGN_PARAGRAPH.LEFT, size=None, space_before=0, space_after=0):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = Pt(14)
    if text:
        run = p.add_run(text)
        set_font(run, bold=bold, size=size)
    return p

def add_labeled_para(doc, label, value, space_before=3):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = Pt(14)
    r1 = p.add_run(label + " ")
    set_font(r1, bold=True)
    r2 = p.add_run(value or "—")
    set_font(r2, bold=False)
    return p

def set_cell_border(cell):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for border_name in ["top", "left", "bottom", "right"]:
        border = OxmlElement(f"w:{border_name}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "4")
        border.set(qn("w:color"), "000000")
        tcPr.append(border)

def set_no_border(cell):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for border_name in ["top", "left", "bottom", "right"]:
        border = OxmlElement(f"w:{border_name}")
        border.set(qn("w:val"), "none")
        border.set(qn("w:sz"), "0")
        border.set(qn("w:color"), "FFFFFF")
        tcPr.append(border)

def cell_text(cell, text, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.paragraphs[0].clear()
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing = Pt(14)
    run = p.add_run(text or "—")
    set_font(run, bold=bold)

def generate(data: dict, output_path: str):
    doc = Document()

    # A4
    section = doc.sections[0]
    section.page_width  = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin    = Cm(1.5)
    section.bottom_margin = Cm(1.0)
    section.right_margin  = Cm(1.0)
    section.left_margin   = Cm(2.0)

    style = doc.styles["Normal"]
    style.font.name = FONT_NAME
    style.font.size = FONT_SIZE

    add_paragraph(doc, "MA'LUMOTNOMA", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)

    job_line = f"{data.get('job_year','')} {data.get('current_job','')}".strip()
    add_paragraph(doc, data.get("fullname", ""), bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    add_paragraph(doc, job_line, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT, space_after=6)

    # Photo block (2 columns)
    photo_table = doc.add_table(rows=1, cols=2)
    photo_table.alignment = WD_TABLE_ALIGNMENT.LEFT
    photo_table.columns[0].width = Cm(13)
    photo_table.columns[1].width = Cm(4)

    left_cell  = photo_table.cell(0, 0)
    right_cell = photo_table.cell(0, 1)
    set_no_border(left_cell)

    # Right cell border + text
    tc = right_cell._tc
    tcPr = tc.get_or_add_tcPr()
    for b in ["top","left","bottom","right"]:
        border = OxmlElement(f"w:{b}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "6")
        border.set(qn("w:color"), "000000")
        tcPr.append(border)
    right_cell.paragraphs[0].clear()
    p = right_cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for line in ["3×4 sm,", "oxirgi 3 oy", "ichida olingan", "rangli surat"]:
        run = p.add_run(line + "\n")
        run.font.name = FONT_NAME
        run.font.size = Pt(9)

    left_cell.paragraphs[0].clear()
    set_no_border(left_cell)

    def info_table_row(table, left_label, left_val, right_label, right_val):
        row = table.add_row()
        for cell in row.cells:
            set_no_border(cell)
        lc = row.cells[0]
        rc = row.cells[1]

        lc.paragraphs[0].clear()
        lp = lc.paragraphs[0]
        lp.paragraph_format.space_before = Pt(2)
        lp.paragraph_format.space_after  = Pt(0)
        lp.paragraph_format.line_spacing = Pt(14)
        if left_label:
            r = lp.add_run(left_label + " "); set_font(r, bold=True)
        if left_val:
            r = lp.add_run(left_val); set_font(r)

        rc.paragraphs[0].clear()
        rp = rc.paragraphs[0]
        rp.paragraph_format.space_before = Pt(2)
        rp.paragraph_format.space_after  = Pt(0)
        rp.paragraph_format.line_spacing = Pt(14)
        if right_label:
            r = rp.add_run(right_label + " "); set_font(r, bold=True)
        if right_val:
            r = rp.add_run(right_val); set_font(r)

    info_tbl = doc.add_table(rows=0, cols=2)
    info_tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    info_tbl.columns[0].width = Cm(8.5)
    info_tbl.columns[1].width = Cm(8.5)

    bdate = data.get("birthdate", "")
    if bdate and "-" in bdate:
        parts = bdate.split("-")
        if len(parts) == 3:
            bdate = f"{parts[2]}.{parts[1]}.{parts[0]}"

    info_table_row(info_tbl, "Tug'ilgan yili:", bdate, "Tug'ilgan joyi:", data.get("birthplace", ""))
    info_table_row(info_tbl, "Millati:", data.get("nationality", "O'zbek"), "Partiyaviyligi:", data.get("party", "Yo'q"))
    info_table_row(info_tbl, "Ma'lumoti:", data.get("edu_level", ""), "Tamomlagan:", data.get("university", ""))
    info_table_row(info_tbl, "Ma'lumoti bo'yicha mutaxassisligi:", data.get("speciality", ""), "", "")
    info_table_row(info_tbl, "Ilmiy darajasi:", data.get("science_degree", "Yo'q"), "Ilmiy unvoni:", data.get("science_title", "Yo'q"))

    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    langs = data.get("langs", [])
    langs_str = ", ".join(langs) if isinstance(langs, list) else str(langs)
    add_labeled_para(doc, "Qaysi chet tillarini biladi:", langs_str or "Yo'q")
    add_labeled_para(doc, "Davlat mukofotlari bilan taqdirlanganmi (qanaqa):", data.get("awards", "Yo'q"))
    add_labeled_para(doc, "Idoraviy mukofotlar bilan taqdirlanganmi (qanaqa):", data.get("departmental_awards", "Yo'q"))
    add_labeled_para(doc,
        "Xalq deputatlari, respublika, viloyat, shahar va tuman Kengashi deputatimi yoki boshqa "
        "saylanadigan organlarning a'zosimi (to'liq ko'rsatilishi lozim):",
        data.get("deputy", "Yo'q")
    )
    add_labeled_para(doc, "Doimiy yashash manzili (aniq ko'rsatilsin):", data.get("address", ""))

    if data.get("passport"):
        add_labeled_para(doc, "Pasport / JShShIR:", data.get("passport", ""))

    add_paragraph(doc, "", space_before=4)
    add_paragraph(doc, "MEHNAT FAOLIYATI", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_before=4, space_after=4)

    works = data.get("work_history", [])
    for w in works:
        if isinstance(w, dict):
            line = f"{w.get('from','')}–{w.get('to','')} yillar. {w.get('org','')} — {w.get('pos','')}"
        else:
            line = str(w)
        if line.strip("–— "):
            add_paragraph(doc, line, space_before=2, space_after=2)

    phones = data.get("phones", {}) or {}
    tel_parts = []
    if phones.get("me"):     tel_parts.append(f"Tel: {phones['me']}")
    if phones.get("father"): tel_parts.append(f"Otasi: {phones['father']}")
    if phones.get("mother"): tel_parts.append(f"Onasi: {phones['mother']}")
    if tel_parts:
        add_paragraph(doc, "     ".join(tel_parts), bold=True, space_before=8)

    # Page 2
    doc.add_page_break()

    fullname = data.get("fullname", "")
    add_paragraph(doc, f"{fullname}ning yaqin qarindoshlari haqida", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    add_paragraph(doc, "MA'LUMOT", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)

    relatives = data.get("relatives", []) or []
    if relatives:
        rel_tbl = doc.add_table(rows=1, cols=5)
        rel_tbl.alignment = WD_TABLE_ALIGNMENT.LEFT

        widths = [Cm(2.5), Cm(4.0), Cm(3.5), Cm(4.0), Cm(3.5)]
        for i, w in enumerate(widths):
            rel_tbl.columns[i].width = w

        headers = ["Qarindoshligi", "Familiyasi, ismi\nva otasining ismi",
                   "Tug'ilgan yili\nva joyi", "Ish joyi va\nlavozimi", "Turar joyi"]
        for i, hdr in enumerate(headers):
            cell = rel_tbl.cell(0, i)
            set_cell_border(cell)
            cell_text(cell, hdr, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
            tc = cell._tc
            tcPr = tc.get_or_add_tcPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:fill"), "F2F2F2")
            shd.set(qn("w:val"), "clear")
            tcPr.append(shd)

        for rel in relatives:
            row = rel_tbl.add_row()
            vals = [
                (rel or {}).get("rel", ""),
                (rel or {}).get("fio", ""),
                (rel or {}).get("birth", ""),   # endi keladi
                (rel or {}).get("job", ""),
                (rel or {}).get("addr", ""),
            ]
            for i, val in enumerate(vals):
                set_cell_border(row.cells[i])
                cell_text(row.cells[i], val)

    doc.save(output_path)
    return output_path
