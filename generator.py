from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def _font(run, bold=False):
    run.font.name = "Times New Roman"
    run.font.size = Pt(14)
    run.font.bold = bold
    try:
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    except Exception:
        pass


def _para(doc, text="", bold=False, center=False, before=0, after=2):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = Pt(16)
    if text:
        r = p.add_run(text)
        _font(r, bold)
    return p


def _row(doc, label, value):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing = Pt(16)
    r1 = p.add_run(label + " ")
    _font(r1, bold=True)
    r2 = p.add_run(value or "—")
    _font(r2, bold=False)


def _border(cell):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    for side in ["top", "left", "bottom", "right"]:
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:color"), "000000")
        tcPr.append(b)


def _cell(cell, text, bold=False, center=False):
    p = cell.paragraphs[0]
    p.clear()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing = Pt(14)
    r = p.add_run(text or "—")
    _font(r, bold)


def generate(data: dict, output_path: str):
    doc = Document()

    sec = doc.sections[0]
    sec.page_width  = Cm(21)
    sec.page_height = Cm(29.7)
    sec.top_margin    = Cm(1.5)
    sec.bottom_margin = Cm(1.0)
    sec.right_margin  = Cm(1.0)
    sec.left_margin   = Cm(2.0)

    doc.styles["Normal"].font.name = "Times New Roman"
    doc.styles["Normal"].font.size = Pt(14)

    # Sarlavha
    _para(doc, "MA'LUMOTNOMA", bold=True, center=True, after=4)

    # Ism va lavozim
    _para(doc, data.get("fullname", ""), bold=True, center=True, after=2)
    job = f"{data.get('job_year','')} {data.get('current_job','')}".strip()
    _para(doc, job, bold=True, after=6)

    # Sana formatlash
    bd = data.get("birthdate", "")
    if bd and "-" in bd:
        y, m, d = bd.split("-")
        bd = f"{d}.{m}.{y}"

    # Ma'lumotlar
    _row(doc, "Tug'ilgan yili:", bd)
    _row(doc, "Tug'ilgan joyi:", data.get("birthplace", ""))
    _row(doc, "Millati:", data.get("nationality", "O'zbek"))
    _row(doc, "Partiyaviyligi:", data.get("party", "Partiyasiz"))
    _row(doc, "Ma'lumoti:", data.get("edu_level", ""))
    _row(doc, "Tamomlagan joyi va yili:", data.get("university", ""))
    _row(doc, "Mutaxassisligi:", data.get("speciality", ""))
    _row(doc, "Ilmiy darajasi:", data.get("science_degree", "Yo'q"))
    _row(doc, "Ilmiy unvoni:", data.get("science_title", "Yo'q"))

    # Tillar
    langs = data.get("langs", [])
    if isinstance(langs, list):
        langs_str = ", ".join(langs)
    else:
        langs_str = str(langs)
    _row(doc, "Chet tillari:", langs_str or "Yo'q")

    # Mukofotlar
    _row(doc, "Davlat mukofotlari:", data.get("awards", "Yo'q"))
    _row(doc, "Idoraviy mukofotlar:", data.get("departmental_awards", "Yo'q"))
    _row(doc, "Deputatlik:", data.get("deputy", "Yo'q"))
    _row(doc, "Yashash manzili:", data.get("address", ""))
    if data.get("passport"):
        _row(doc, "Pasport / JShShIR:", data.get("passport", ""))

    # Telefon
    phones = data.get("phones", {})
    tel = []
    if phones.get("me"):     tel.append(f"O'zi: {phones['me']}")
    if phones.get("father"): tel.append(f"Otasi: {phones['father']}")
    if phones.get("mother"): tel.append(f"Onasi: {phones['mother']}")
    if tel:
        _row(doc, "Telefon:", "   ".join(tel))

    # Mehnat faoliyati
    _para(doc, "", before=6, after=0)
    _para(doc, "MEHNAT FAOLIYATI", bold=True, center=True, before=0, after=4)

    works = data.get("work_history", [])
    for w in works:
        if isinstance(w, dict):
            line = f"{w.get('from','')}–{w.get('to','')}   {w.get('org','')}   {w.get('pos','')}".strip("– ")
        else:
            line = str(w)
        if line.strip():
            _para(doc, line, before=1, after=1)

    # Sahifa 2 — Qarindoshlar
    doc.add_page_break()

    _para(doc, f"{data.get('fullname','')}ning yaqin qarindoshlari haqida",
          bold=True, center=True, after=0)
    _para(doc, "MA'LUMOT", bold=True, center=True, before=0, after=6)

    relatives = data.get("relatives", [])
    if relatives:
        tbl = doc.add_table(rows=1, cols=5)
        headers = [
            "Qarindoshligi",
            "F.I.Sh va tug'ilgan yili",
            "Tug'ilgan joyi",
            "Ish joyi va lavozimi",
            "Turar joyi"
        ]
        widths = [Cm(2.8), Cm(4.0), Cm(3.2), Cm(4.0), Cm(3.2)]
        for i, w in enumerate(widths):
            tbl.columns[i].width = w
        for i, h in enumerate(headers):
            c = tbl.cell(0, i)
            _border(c)
            _cell(c, h, bold=True, center=True)

        for rel in relatives:
            row = tbl.add_row()
            vals = [
                rel.get("rel", ""),
                rel.get("fio", ""),
                rel.get("birth", ""),
                rel.get("job", ""),
                rel.get("addr", ""),
            ]
            for i, v in enumerate(vals):
                _border(row.cells[i])
                _cell(row.cells[i], v)

    doc.save(output_path)
