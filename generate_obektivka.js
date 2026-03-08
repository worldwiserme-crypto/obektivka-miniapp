const fs = require('fs');
const {
  AlignmentType,
  BorderStyle,
  Document,
  Footer,
  Header,
  Packer,
  PageBreak,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} = require('docx');

const [,, inputPath, outputPath] = process.argv;
if (!inputPath || !outputPath) {
  console.error('Usage: node generate_obektivka.js input.json output.docx');
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(inputPath, 'utf-8'));
const font = 'Times New Roman';
const size = 28; // 14 pt
const NO_BORDER = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };

function run(text, bold = false) {
  return new TextRun({ text: String(text || '—'), bold, font, size });
}

function para(text, bold = false, align = AlignmentType.LEFT) {
  return new Paragraph({ children: [run(text, bold)], alignment: align, spacing: { before: 60, after: 60 } });
}

function twoColRow(lk, lv, rk, rv) {
  return new TableRow({
    children: [
      new TableCell({ children: [para(`${lk} ${lv || '—'}`)], width: { size: 50, type: WidthType.PERCENTAGE } }),
      new TableCell({ children: [para(`${rk} ${rv || '—'}`)], width: { size: 50, type: WidthType.PERCENTAGE } }),
    ],
  });
}

const languageText = (Array.isArray(data.languages) ? data.languages : []).map(l => `${l.name || ''} (${l.level || ''})`).join(', ') || '—';

const workParagraphs = (Array.isArray(data.work_history) ? data.work_history : []).map((item) => {
  const row = `${item.period || '—'} ${item.organization || '—'} ${item.position || '—'}`.trim();
  return para(row);
});

const familyRows = [
  new TableRow({ children: [
    new TableCell({ children: [para("Qarindoshligi", true)], width: { size: 16, type: WidthType.PERCENTAGE } }),
    new TableCell({ children: [para("F.I.Sh.", true)], width: { size: 21, type: WidthType.PERCENTAGE } }),
    new TableCell({ children: [para("Tug'ilgan yili va joyi", true)], width: { size: 21, type: WidthType.PERCENTAGE } }),
    new TableCell({ children: [para("Ish joyi va lavozimi", true)], width: { size: 22, type: WidthType.PERCENTAGE } }),
    new TableCell({ children: [para("Yashash manzili", true)], width: { size: 20, type: WidthType.PERCENTAGE } }),
  ]})
];

(Array.isArray(data.family_members) ? data.family_members : []).forEach((m) => {
  familyRows.push(new TableRow({ children: [
    new TableCell({ children: [para(m.relation)] }),
    new TableCell({ children: [para(m.full_name)] }),
    new TableCell({ children: [para(m.birth_info)] }),
    new TableCell({ children: [para(m.workplace)] }),
    new TableCell({ children: [para(m.address)] }),
  ]}));
});

const doc = new Document({
  sections: [
    {
      properties: {
        page: {
          margin: {
            top: 850, // 1.5cm
            bottom: 567, // 1cm
            left: 1134, // 2cm
            right: 567, // 1cm
          },
          size: { width: 11906, height: 16838 }, // A4
        },
      },
      headers: { default: new Header({ children: [] }) },
      footers: { default: new Footer({ children: [] }) },
      children: [
        para("MA'LUMOTNOMA", true, AlignmentType.CENTER),
        new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          borders: { top: NO_BORDER, bottom: NO_BORDER, left: NO_BORDER, right: NO_BORDER, insideH: NO_BORDER, insideV: NO_BORDER },
          rows: [new TableRow({ children: [
            new TableCell({ children: [para(data.full_name, true), para(data.workplace || '')], width: { size: 70, type: WidthType.PERCENTAGE } }),
            new TableCell({ children: [para('3x4 rasm', false, AlignmentType.CENTER)], width: { size: 30, type: WidthType.PERCENTAGE } }),
          ]})],
        }),
        new Table({
          width: { size: 100, type: WidthType.PERCENTAGE },
          rows: [
            twoColRow("Tug'ilgan sana:", data.birth_date, "Tug'ilgan joyi:", data.birth_place),
            twoColRow("Millati:", data.nationality, "Partiyaviyligi:", data.party_affiliation),
            twoColRow("Ma'lumoti:", data.education, "Ilmiy darajasi:", data.academic_degree),
            twoColRow("Deputatlik holati:", data.deputation_status, "Telefon raqamlari:", data.phone_numbers),
            twoColRow("Pasport ma'lumotlari:", data.passport_info, "Doimiy manzil:", data.address),
          ],
        }),
        para(`Tillar: ${languageText}`),
        para(`Mukofotlar: ${data.awards || '—'}`),
        para('MEHNAT FAOLIYATI', true, AlignmentType.CENTER),
        ...workParagraphs,
        new Paragraph({ children: [new PageBreak()] }),
        para(`${data.full_name || 'Fuqaro'}ning yaqin qarindoshlari haqida MA'LUMOT`, true, AlignmentType.CENTER),
        new Table({ width: { size: 100, type: WidthType.PERCENTAGE }, rows: familyRows }),
      ],
    },
  ],
});

Packer.toBuffer(doc)
  .then((buffer) => fs.writeFileSync(outputPath, buffer))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
