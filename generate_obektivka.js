const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, ShadingType, VerticalAlign,
  PageBreak, HeadingLevel
} = require('docx');
const fs = require('fs');

// ═══════════════════════════════════════════
// BOT DAN KELADIGAN JSON MA'LUMOTLAR
// ═══════════════════════════════════════════
const data = {
  fullname: "Aliyev Valijon Alisher o'g'li",
  job_year: "2025-yil 2-sentyabrdan",
  current_job: "Toshkent transport universiteti 1-bosqich talabasi",
  birthdate: "2007-01-31",
  birthplace: "Toshkent shahri, Mirobod tumani",
  nationality: "O'zbek",
  party: "Yo'q",
  edu_level: "O'rta maxsus",
  university: "2025-yil, Toshkent shaxri, 2-umumiy o'rta ta'lim maktabi",
  speciality: "Iqtisodchi",
  science_degree: "Yo'q",
  science_title: "Yo'q",
  langs: ["Rus tili", "Ingliz tili"],
  awards: "Yo'q",
  departmental_awards: "Yo'q",
  deputy: "Yo'q (to'liq ko'rsatilishi lozim)",
  address: "Toshkent shahri, Shayxontohur tumani, Novza ko'chasi, 105-uy",
  passport: "AA1234567 / 30101070012345",
  phones: { me: "+998901234567", father: "+998912345678", mother: "+998987654321" },
  work_history: [
    "2019-2023 yillar. Toshkent tibbiyot instituti talabasi",
    "2023-2025 yillar. Toshkent Milliy universiteti magistranti",
    "2025-yildan Xalq talimi boshqarmasida iqtisodchi lavozimida",
  ],
  relatives: [
    { rel: "Otasi",       fio: "Mamadaliyev Yo'ldosh Mirzayevich",   birth: "1969-yil, Surxondaryo viloyati Termiz tumani",           job: "Vafot etgan",                                           addr: "" },
    { rel: "Onasi",       fio: "Mamadaliyeva Madina Ro'ziyevna",      birth: "1973-yil, Surxondaryo viloyati Termiz tumani",           job: "Nafaqada",                                              addr: "Surxondaryo viloyati Termiz tumani Adolat ko'chasi 48-uy" },
    { rel: "Opasi",       fio: "Mamadaliyeva Komila Yo'ldoshevna",    birth: "1993-yil, Surxondaryo viloyati Termiz tumani",           job: "Termiz tibbiyot birlashmasida Shifokor",                addr: "Surxondaryo viloyati Termiz tumani Adolat ko'chasi 48-uy" },
    { rel: "Ukasi",       fio: "Mamadaliyev Arslon Yo'ldoshevich",    birth: "2003-yil, Surxondaryo viloyati Termiz tumani",           job: "Harbiy xizmatda",                                       addr: "Surxondaryo viloyati Termiz tumani Adolat ko'chasi 48-uy" },
    { rel: "Turmush o'rtog'i", fio: "Xaydarov Anvar Turdiyevich",    birth: "1997-yil, Surxondaryo viloyati Jarqo'rg'on tuman",      job: "Xalq banki Termiz filiali, Bosh hisobchi",              addr: "Surxondaryo viloyati Jarqo'rg'on tumani Hurlik ko'chasi 12-uy" },
    { rel: "Qaynotasi",   fio: "Xudoyqulov Turdimurod Xudoyarovich", birth: "1971-yil, Surxondaryo viloyati Jarqo'rg'on tuman",      job: "Nafaqada",                                              addr: "Surxondaryo viloyati Jarqo'rg'on tumani Hurlik ko'chasi 12-uy" },
    { rel: "Qaynonasi",   fio: "Xudoyqulova Nilufar Xamzayevna",     birth: "1971-yil, Surxondaryo viloyati Jarqo'rg'on tuman",      job: "Nafaqada",                                              addr: "Surxondaryo viloyati Jarqo'rg'on tumani Hurlik ko'chasi 12-uy" },
    { rel: "Qizi",        fio: "Turdiyeva Shahzoda Anvarovna",        birth: "2016-yil, Surxondaryo viloyati Jarqo'rg'on tuman",      job: "O'quvchi",                                              addr: "Surxondaryo viloyati Jarqo'rg'on tumani Hurlik ko'chasi 12-uy" },
    { rel: "Qizi",        fio: "Turdiyeva Noila Anvarovna",           birth: "2018-yil, Surxondaryo viloyati Jarqo'rg'on tuman",      job: "O'quvchi",                                              addr: "Surxondaryo viloyati Jarqo'rg'on tumani Hurlik ko'chasi 12-uy" },
    { rel: "Qizi",        fio: "Turdiyeva Sumaya Anvarovna",          birth: "2022-yil, Surxondaryo viloyati Jarqo'rg'on tumani",     job: "Bog'chada",                                             addr: "Surxondaryo viloyati Jarqo'rg'on tumani Hurlik ko'chasi 12-uy" },
  ]
};

// ═══════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════
const FONT = "Times New Roman";
const SZ = 28; // 14pt in half-points

// A4: 11906 twips wide, margins: top=851(1.5cm), bottom=567(1cm), right=567(1cm), left=1134(2cm)
// Content width = 11906 - 567 - 1134 = 10205 twips
const CONTENT_W = 10205;

const B_SINGLE = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
const B_NONE   = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const ALL_BORDERS  = { top: B_SINGLE, bottom: B_SINGLE, left: B_SINGLE, right: B_SINGLE };
const NO_BORDERS   = { top: B_NONE, bottom: B_NONE, left: B_NONE, right: B_NONE };

function r(text, bold = false, size = SZ) {
  return new TextRun({ text, bold, size, font: FONT });
}

function p(children, opts = {}) {
  return new Paragraph({
    children: Array.isArray(children) ? children : [children],
    spacing: { line: 240, lineRule: "auto", before: 0, after: 0, ...opts.spacing },
    alignment: opts.alignment || AlignmentType.LEFT,
    ...opts
  });
}

function cell(children, width, opts = {}) {
  return new TableCell({
    children: Array.isArray(children) ? children : [children],
    width: { size: width, type: WidthType.DXA },
    borders: opts.borders || NO_BORDERS,
    margins: opts.margins || { top: 40, bottom: 40, left: 80, right: 80 },
    verticalAlign: opts.valign || VerticalAlign.TOP,
    ...opts
  });
}

function row(cells) {
  return new TableRow({ children: cells });
}

// ═══════════════════════════════════════════
// PAGE 1: MA'LUMOTNOMA
// ═══════════════════════════════════════════
function buildPage1() {
  const items = [];

  // ── Sarlavha: MA'LUMOTNOMA ──
  items.push(p(r("MA'LUMOTNOMA", true, SZ), {
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 120, line: 240 }
  }));

  // ── Ism va lavozim + rasm (2 ustunli jadval) ──
  const nameJobText = `${data.job_year}: ${data.current_job}`;

  const photoBox = new Table({
    width: { size: 1800, type: WidthType.DXA },
    columnWidths: [1800],
    borders: { top: B_NONE, bottom: B_NONE, left: B_NONE, right: B_NONE, insideH: B_NONE, insideV: B_NONE },
    rows: [row([new TableCell({
      children: [
        p(r("3×4 sm,", false, 22), { alignment: AlignmentType.CENTER }),
        p(r("oxirgi 3 oy", false, 22), { alignment: AlignmentType.CENTER }),
        p(r("ichida olingan", false, 22), { alignment: AlignmentType.CENTER }),
        p(r("rangli surat", false, 22), { alignment: AlignmentType.CENTER }),
      ],
      width: { size: 1800, type: WidthType.DXA },
      borders: ALL_BORDERS,
      margins: { top: 80, bottom: 80, left: 60, right: 60 },
      verticalAlign: VerticalAlign.CENTER
    })])]
  });

  const headerTable = new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W - 1900, 1900],
    borders: { top: B_NONE, bottom: B_NONE, left: B_NONE, right: B_NONE, insideH: B_NONE, insideV: B_NONE },
    rows: [row([
      cell([
        p(r(data.fullname, true, SZ), { alignment: AlignmentType.CENTER, spacing: { before: 0, after: 80 } }),
        p(r(nameJobText, true, SZ), { alignment: AlignmentType.LEFT, spacing: { before: 0, after: 0 } }),
      ], CONTENT_W - 1900, { margins: { top: 0, bottom: 0, left: 0, right: 120 } }),
      cell([photoBox], 1900, { margins: { top: 0, bottom: 0, left: 0, right: 0 } })
    ])]
  });

  items.push(headerTable);
  items.push(p(r(" "), { spacing: { before: 60, after: 0 } }));

  // ── 2 ustunli ma'lumotlar jadvali ──
  const HALF = Math.floor(CONTENT_W / 2);

  function infoRow(leftLabel, leftVal, rightLabel, rightVal) {
    return row([
      cell([
        p(r(leftLabel, true, SZ)),
        p(r(leftVal || "—", false, SZ), { spacing: { before: 20 } })
      ], HALF),
      cell([
        p(r(rightLabel, true, SZ)),
        p(r(rightVal || "—", false, SZ), { spacing: { before: 20 } })
      ], HALF)
    ]);
  }

  const langs = Array.isArray(data.langs) ? data.langs.join(", ") : (data.langs || "—");

  const infoTable = new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [HALF, HALF],
    borders: { top: B_NONE, bottom: B_NONE, left: B_NONE, right: B_NONE, insideH: B_NONE, insideV: B_NONE },
    rows: [
      infoRow("Tug'ilgan yili:", data.birthdate?.split("-").reverse().join(".") || "—",
              "Tug'ilgan joyi:", data.birthplace),
      infoRow("Millati:", data.nationality,
              "Partiyaviyligi:", data.party),
      infoRow("Ma'lumoti:", data.edu_level,
              "Tamomlagan:", data.university),
      infoRow("Ma'lumoti bo'yicha mutaxassisligi:", data.speciality,
              "", ""),
      infoRow("Ilmiy darajasi:", data.science_degree || "Yo'q",
              "Ilmiy unvoni:", data.science_title || "Yo'q"),
    ]
  });
  items.push(infoTable);
  items.push(p(r(" "), { spacing: { before: 40, after: 0 } }));

  // ── Tillar (to'liq qator) ──
  items.push(p([r("Qaysi chet tillarini biladi: ", true, SZ), r(langs, false, SZ)]));
  items.push(p(r(" "), { spacing: { before: 20, after: 0 } }));

  // ── Mukofotlar ──
  items.push(p([r("Davlat mukofotlari va premiyalari bilan taqdirlanganmi (qanaqa): ", true, SZ), r(data.awards || "Yo'q", false, SZ)]));
  items.push(p(r(" "), { spacing: { before: 20, after: 0 } }));

  // ── Idoraviy mukofotlar ──
  items.push(p([r("Idoraviy mukofotlar bilan taqdirlanganmi (qanaqa): ", true, SZ), r(data.departmental_awards || "Yo'q", false, SZ)]));
  items.push(p(r(" "), { spacing: { before: 20, after: 0 } }));

  // ── Deputatlik ──
  items.push(p([
    r("Xalq deputatlari, respublika, viloyat, shahar va tuman Kengashi deputatimi yoki boshqa saylanadigan organlarning a'zosimi (to'liq ko'rsatilishi lozim): ", true, SZ),
    r(data.deputy || "Yo'q", false, SZ)
  ]));
  items.push(p(r(" "), { spacing: { before: 20, after: 0 } }));

  // ── Manzil ──
  items.push(p([r("Doimiy yashash manzili (aniq ko'rsatilsin): ", true, SZ), r(data.address || "—", false, SZ)]));
  items.push(p(r(" "), { spacing: { before: 40, after: 0 } }));

  // ── Pasport ──
  if (data.passport) {
    items.push(p([r("Pasport seriyasi va raqami / JShShIR: ", true, SZ), r(data.passport, false, SZ)]));
    items.push(p(r(" "), { spacing: { before: 20, after: 0 } }));
  }

  // ── MEHNAT FAOLIYATI ──
  items.push(p(r(" "), { spacing: { before: 60, after: 0 } }));
  items.push(p(r("MEHNAT FAOLIYATI", true, SZ), {
    alignment: AlignmentType.CENTER,
    spacing: { before: 60, after: 60 }
  }));

  const works = Array.isArray(data.work_history) ? data.work_history : [];
  works.forEach(w => {
    const text = typeof w === "string" ? w : `${w.from}-${w.to} yillar. ${w.org} — ${w.pos}`;
    items.push(p(r(text, false, SZ), { spacing: { before: 40, after: 40 } }));
  });

  // ── Telefon ──
  items.push(p(r(" "), { spacing: { before: 60, after: 0 } }));
  const phones = [];
  if (data.phones?.me) phones.push(`Tel: ${data.phones.me}`);
  if (data.phones?.father) phones.push(`Otasi: ${data.phones.father}`);
  if (data.phones?.mother) phones.push(`Onasi: ${data.phones.mother}`);
  if (phones.length) {
    items.push(p(r(phones.join("     "), true, SZ)));
  }

  return items;
}

// ═══════════════════════════════════════════
// PAGE 2: QARINDOSHLAR JADVALI
// ═══════════════════════════════════════════
function buildPage2() {
  const items = [];

  // Sarlavha
  items.push(p(
    r(`${data.fullname}ning yaqin qarindoshlari haqida`, true, SZ),
    { alignment: AlignmentType.CENTER, spacing: { before: 0, after: 80 } }
  ));
  items.push(p(r("MA'LUMOT", true, SZ), {
    alignment: AlignmentType.CENTER,
    spacing: { before: 0, after: 120 }
  }));

  // Jadval ustun kengliklari
  // Jami = CONTENT_W = 10205
  const C1 = 1300;  // Qarindoshligi
  const C2 = 2400;  // F.I.Sh
  const C3 = 2200;  // Tug'ilgan yili va joyi
  const C4 = 2405;  // Ish joyi
  const C5 = 1900;  // Turar joyi
  // Sum = 10205 ✓

  function hCell(text, w) {
    return new TableCell({
      children: [p(r(text, true, 22), { alignment: AlignmentType.CENTER })],
      width: { size: w, type: WidthType.DXA },
      borders: ALL_BORDERS,
      margins: { top: 60, bottom: 60, left: 80, right: 80 },
      shading: { fill: "F0F0F0", type: ShadingType.CLEAR },
      verticalAlign: VerticalAlign.CENTER
    });
  }

  function dCell(text, w) {
    return new TableCell({
      children: [p(r(text || "—", false, SZ), { alignment: AlignmentType.LEFT })],
      width: { size: w, type: WidthType.DXA },
      borders: ALL_BORDERS,
      margins: { top: 60, bottom: 60, left: 80, right: 80 },
      verticalAlign: VerticalAlign.TOP
    });
  }

  // Header qatori
  const headerRow = new TableRow({
    tableHeader: true,
    children: [
      hCell("Qarindoshligi", C1),
      hCell("Familiyasi, ismi va otasining ismi", C2),
      hCell("Tug'ilgan yili va joyi", C3),
      hCell("Ish joyi va lavozimi", C4),
      hCell("Turar joyi", C5),
    ]
  });

  const dataRows = data.relatives.map(rel => new TableRow({
    children: [
      dCell(rel.rel, C1),
      dCell(rel.fio, C2),
      dCell(rel.birth, C3),
      dCell(rel.job, C4),
      dCell(rel.addr, C5),
    ]
  }));

  const table = new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [C1, C2, C3, C4, C5],
    rows: [headerRow, ...dataRows]
  });

  items.push(table);
  return items;
}

// ═══════════════════════════════════════════
// HUJJAT YIG'ISH
// ═══════════════════════════════════════════
async function generate(outputPath) {
  const page1 = buildPage1();
  const page2 = buildPage2();

  // Page break paragraph
  const pageBreak = new Paragraph({
    children: [new PageBreak()],
    spacing: { before: 0, after: 0 }
  });

  const doc = new Document({
    styles: {
      default: {
        document: {
          run: { font: FONT, size: SZ }
        }
      }
    },
    sections: [
      {
        properties: {
          page: {
            size: { width: 11906, height: 16838 }, // A4
            margin: { top: 851, bottom: 567, right: 567, left: 1134 }
          }
        },
        children: [
          ...page1,
          pageBreak,
          ...page2
        ]
      }
    ]
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
  console.log("✅ Yaratildi:", outputPath);
}

generate("/home/claude/obektivka_output.docx").catch(console.error);
