// Builds the chapter 4 Word file from chapter4-source.txt (RTL Arabic, university formatting).
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType,
  AlignmentType, HeadingLevel, Footer, PageNumber, ShadingType, BorderStyle, LevelFormat,
  SimpleField, Bookmark, VerticalAlign,
} = require("docx");

const SRC = process.argv[2];
const OUT = process.argv[3];
const HERE = __dirname;
const manifest = JSON.parse(fs.readFileSync(path.join(HERE, "manifest.json"), "utf8"));

const CH = "4";                       // chapter number used in "(n-4)" captions
const TEXT_W = 11906 - 1701 - 1440;   // A4 width minus right (3 cm) and left (2.54 cm) margins, in DXA
const FONT = { ascii: "Times New Roman", hAnsi: "Times New Roman", cs: "Simplified Arabic", eastAsia: "Times New Roman" };
const BODY_AR = 27, BODY_EN = 24;     // half-points: Arabic 13.5 pt, English 12 pt (methodology)
const HEAD = { 1: 32, 2: 29, 3: 28, 4: 27 };

// ---- pre-scan: number tables in document order -------------------------------------------
const lines = fs.readFileSync(SRC, "utf8").split(/\r?\n/);
const tableNum = {};
let tcount = 0;
for (const l of lines) if (l.startsWith("@table ")) tableNum[l.slice(7).split("|")[0].trim()] = ++tcount;
const figNum = Object.fromEntries(Object.entries(manifest).map(([k, v]) => [k, v.num]));

// ---- inline runs -------------------------------------------------------------------------
const LATIN = /([A-Za-z][A-Za-z0-9_.\-+\/:@#×*]*(?:[ ]+[A-Za-z0-9(][A-Za-z0-9_.\-+\/:@#×*()]*)*)/;

function scriptRuns(text, o) {
  const out = [];
  for (const part of text.split(LATIN)) {
    if (!part) continue;
    const latin = LATIN.test(part) && /^[A-Za-z]/.test(part);
    out.push(new TextRun({
      text: part, font: FONT, bold: o.bold, boldComplexScript: o.bold, italics: o.italic,
      italicsComplexScript: o.italic, color: o.color,
      size: latin ? o.en : o.ar, sizeComplexScript: o.ar, rightToLeft: !latin,
    }));
  }
  return out;
}

function ltrRun(text, o) {
  return new TextRun({ text, font: FONT, bold: o.bold, size: o.en, sizeComplexScript: o.ar, rightToLeft: false });
}

function refField(kind, key, o) {
  const num = kind === "fig" ? figNum[key] : tableNum[key];
  if (!num) throw new Error(`unknown ${kind} reference: ${key}`);
  return [new SimpleField(`REF _Ref_${kind}_${key} \\h`, String(num)), ltrRun(`-${CH}`, o)];
}

function runs(text, opt = {}) {
  const o = { ar: BODY_AR, en: BODY_EN, bold: false, italic: false, color: undefined, ...opt };
  const out = [];
  for (const tok of text.split(/(\*\*[^*]+\*\*|`[^`]+`|\{(?:fig|tab):[a-z]+\})/)) {
    if (!tok) continue;
    if (tok.startsWith("**")) out.push(...runs(tok.slice(2, -2), { ...o, bold: true }));
    else if (tok.startsWith("`")) out.push(ltrRun(tok.slice(1, -1), o));
    else if (tok.startsWith("{")) { const [k, key] = tok.slice(1, -1).split(":"); out.push(...refField(k, key, o)); }
    else out.push(...scriptRuns(tok, o));
  }
  return out;
}

const P = (children, extra = {}) => new Paragraph({ bidirectional: true, children, ...extra });

// ---- block builders ----------------------------------------------------------------------
function caption(kind, key, text) {
  const label = kind === "fig" ? "الشكل" : "الجدول";
  const num = kind === "fig" ? figNum[key] : tableNum[key];
  const o = { ar: 24, en: 22, bold: true };
  return P([
    ...runs(`${label} (`, o),
    new Bookmark({ id: `_Ref_${kind}_${key}`, children: [new SimpleField(`SEQ ${label} \\* ARABIC`, String(num))] }),
    ltrRun(`-${CH}`, o),
    ...runs("): ", o),
    ...runs(text, { ar: 24, en: 22, bold: true }),
  ], { alignment: AlignmentType.CENTER, spacing: { before: 60, after: 240 }, keepNext: kind === "tab" });
}

function figure(key) {
  const f = manifest[key];
  const maxW = (f.width_cm / 2.54) * 96, maxH = (21.0 / 2.54) * 96;
  const scale = Math.min(maxW / f.w, maxH / f.h);
  const img = new ImageRun({
    type: path.extname(f.file).slice(1).replace("jpeg", "jpg"),
    data: fs.readFileSync(path.join(HERE, "images", f.file)),
    transformation: { width: Math.round(f.w * scale), height: Math.round(f.h * scale) },
  });
  return [P([img], { alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 60 } }),
          caption("fig", key, f.caption)];
}

const border = { style: BorderStyle.SINGLE, size: 4, color: "808080" };
const borders = { top: border, bottom: border, left: border, right: border };

function table(key, cap, weights, rows) {
  const total = weights.reduce((a, b) => a + b, 0);
  const widths = weights.map(w => Math.floor((w / total) * TEXT_W));
  widths[widths.length - 1] += TEXT_W - widths.reduce((a, b) => a + b, 0);
  const trs = rows.map((cells, ri) => new TableRow({
    tableHeader: ri === 0, cantSplit: true,
    children: cells.map((c, ci) => new TableCell({
      borders, width: { size: widths[ci], type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
      margins: { top: 50, bottom: 50, left: 90, right: 90 },
      shading: ri === 0 ? { fill: "D9E2F3", type: ShadingType.CLEAR, color: "auto" } : undefined,
      children: [P(runs(c, { ar: 22, en: 20, bold: ri === 0 }), {
        alignment: c.length > 30 && ri > 0 ? AlignmentType.BOTH : AlignmentType.CENTER,
        spacing: { before: 0, after: 0, line: 240 },
      })],
    })),
  }));
  return [caption("tab", key, cap),
          new Table({ width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: widths, visuallyRightToLeft: true, rows: trs }),
          P([], { spacing: { after: 120 } })];
}

// ---- parse source ------------------------------------------------------------------------
const body = [];
let para = [];
let listInstance = 0, inList = null;
const flush = () => { if (para.length) { body.push(P(runs(para.join(" ")), { alignment: AlignmentType.BOTH })); para = []; } };

for (let i = 0; i < lines.length; i++) {
  const l = lines[i];
  const listType = /^\d+\. /.test(l) ? "numbers" : l.startsWith("- ") ? "bullets" : null;
  if (!listType) inList = null;

  if (!l.trim()) { flush(); continue; }
  const h = l.match(/^(#{1,4}) (.*)$/);
  if (h) {
    flush();
    const level = h[1].length;
    body.push(P(runs(h[2], { ar: HEAD[level], en: HEAD[level] - 2, bold: true }), {
      heading: [null, HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3, HeadingLevel.HEADING_4][level],
      alignment: level === 1 ? AlignmentType.CENTER : undefined,
      keepNext: true, spacing: { before: level <= 2 ? 360 : 240, after: 120 },
    }));
    continue;
  }
  if (l.startsWith("@title ")) {
    flush(); body.push(P(runs(l.slice(7), { ar: 32, en: 30, bold: true }), { alignment: AlignmentType.CENTER, spacing: { after: 360 } }));
    continue;
  }
  if (l.startsWith("@todo ")) {
    flush(); body.push(P(runs(`[${l.slice(6)}]`, { italic: true, color: "7F7F7F" }), { alignment: AlignmentType.BOTH }));
    continue;
  }
  if (l.startsWith("@fig ")) { flush(); body.push(...figure(l.slice(5).split("|")[0].trim())); continue; }
  if (l.startsWith("@table ")) {
    flush();
    const [key, cap, w] = l.slice(7).split("|").map(s => s.trim());
    const rows = [];
    while (i + 1 < lines.length && lines[i + 1].startsWith("|")) {
      i++;
      if (/^\|[-\s|]+\|$/.test(lines[i])) continue;
      rows.push(lines[i].split("|").slice(1, -1).map(s => s.trim()));
    }
    body.push(...table(key, cap, w.split(",").map(Number), rows));
    continue;
  }
  if (l.startsWith("@ref ")) {
    flush();
    body.push(new Paragraph({
      children: [new TextRun({ text: l.slice(5), font: FONT, size: 24 })],
      alignment: AlignmentType.LEFT, indent: { left: 567, hanging: 567 }, spacing: { after: 100 },
    }));
    continue;
  }
  if (listType) {
    flush();
    if (inList !== listType) { inList = listType; listInstance++; }
    const text = listType === "numbers" ? l.replace(/^\d+\. /, "") : l.slice(2);
    body.push(P(runs(text), { alignment: AlignmentType.BOTH, numbering: { reference: listType, level: 0, instance: listInstance } }));
    continue;
  }
  para.push(l.trim());
}
flush();

// ---- document ----------------------------------------------------------------------------
const headingStyle = (id, name, lvl) => ({
  id, name, basedOn: "Normal", next: "Normal", quickFormat: true,
  run: { font: FONT, bold: true, boldComplexScript: true, size: HEAD[lvl], sizeComplexScript: HEAD[lvl], color: "000000" },
  paragraph: { keepNext: true, outlineLevel: lvl - 1 },
});

const doc = new Document({
  creator: "Smart Facilities Monitor System team",
  title: "الفصل الرابع: التطبيق العملي",
  styles: {
    default: { document: { run: { font: FONT, size: BODY_EN, sizeComplexScript: BODY_AR }, paragraph: { spacing: { line: 276, after: 120 } } } },
    paragraphStyles: [headingStyle("Heading1", "Heading 1", 1), headingStyle("Heading2", "Heading 2", 2),
                      headingStyle("Heading3", "Heading 3", 3), headingStyle("Heading4", "Heading 4", 4)],
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 567, hanging: 283 } } } }] },
      { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 567, hanging: 340 } } } }] },
    ],
  },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 },
                           margin: { top: 1440, bottom: 1440, right: 1701, left: 1440, header: 709, footer: 709 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 22 })] })] }) },
    children: body,
  }],
});

const JSZip = require("jszip");
const RPR = (bold, sz) => `<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Simplified Arabic"/>${bold ? "<w:b/><w:bCs/>" : ""}<w:sz w:val="${sz}"/><w:szCs w:val="${sz}"/></w:rPr>`;
Packer.toBuffer(doc).then(async raw => {
  const zip = await JSZip.loadAsync(raw);
  let xml = await zip.file("word/document.xml").async("string");
  xml = xml.replace(/(<w:fldSimple w:instr="SEQ [^"]*">)<w:r>/g, `$1<w:r>${RPR(true, 22)}`)
           .replace(/(<w:fldSimple w:instr="REF [^"]*">)<w:r>/g, `$1<w:r>${RPR(false, 24)}`);
  zip.file("word/document.xml", xml);
  const buf = await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
  fs.writeFileSync(OUT, buf); console.log("wrote", OUT, `(${Object.keys(manifest).length} figures, ${tcount} tables)`); });
