import { describe, expect, it } from "vitest";
import { joinLines, ocrLayout, pdfTextLayout, type PdfTextItem } from "./layout";

const S = 200 / 72; // 200 DPI
// pdf.js viewport for a US Letter page at 200 DPI: PDF user space (y up) -> image pixels (y down).
const LETTER = { transform: [S, 0, 0, -S, 0, 792 * S], width: 612 * S, height: 792 * S };
const STYLES = { F1: { descent: -0.25 } };

function item(str: string, x: number, y: number, width: number, size = 12): PdfTextItem {
  return { str, transform: [size, 0, 0, size, x, y], width, fontName: "F1" };
}

describe("pdfTextLayout", () => {
  it("splits items into words with char offsets into the joined text and pixel boxes", () => {
    const layout = pdfTextLayout(
      1,
      [item("Expiry date: 31/03/2027", 72, 700, 138), item("Batch EX-1001 released", 72, 684, 132)],
      STYLES,
      LETTER,
    )!;
    expect(layout.text).toBe("Expiry date: 31/03/2027\nBatch EX-1001 released");
    expect(layout.text_source).toBe("pdf");
    expect(layout.width).toBe(1700);
    expect(layout.height).toBe(2200);
    expect(layout.words.map((w) => [w.text, w.char_start, w.char_end])).toEqual([
      ["Expiry", 0, 6],
      ["date:", 7, 12],
      ["31/03/2027", 13, 23],
      ["Batch", 24, 29],
      ["EX-1001", 30, 37],
      ["released", 38, 46],
    ]);
    for (const w of layout.words) expect(layout.text.slice(w.char_start, w.char_end)).toBe(w.text);

    const date = layout.words[2];
    expect(date.confidence).toBeNull();
    // x by character share of the item's advance; y from the baseline, the descent and the size.
    expect(date.bbox.x0).toBeCloseTo((72 + (138 * 13) / 23) * S, 6);
    expect(date.bbox.x1).toBeCloseTo((72 + 138) * S, 6);
    expect(date.bbox.y1).toBeCloseTo((792 - 700 + 0.25 * 12) * S, 6);
    expect(date.bbox.y0).toBeCloseTo((792 - 700 + 0.25 * 12 - 12) * S, 6);
  });

  it("places words by measured glyph widths when a measure is given", () => {
    // "W" is three times as wide as any other character.
    const measure = (text: string) => [...text].reduce((w, c) => w + (c === "W" ? 3 : 1), 0);
    const layout = pdfTextLayout(1, [item("WWWW date 31/03/2027 here", 72, 700, 280)], STYLES, LETTER, measure)!;
    const date = layout.words.find((w) => w.text === "31/03/2027")!;
    const total = 12 + 21; // four W (3 each) + the other 21 characters
    expect(date.bbox.x0).toBeCloseTo((72 + (280 * (12 + 6)) / total) * S, 6);
    expect(date.bbox.x1).toBeCloseTo((72 + (280 * (12 + 16)) / total) * S, 6);
  });

  it("returns null when the text layer is too thin to trust (a scan)", () => {
    expect(pdfTextLayout(1, [item("Page 1 of 5", 72, 20, 60), item("   ", 72, 10, 10)], STYLES, LETTER)).toBeNull();
  });

  it("joins pieces of one word split across items and keeps spaced words apart", () => {
    const layout = pdfTextLayout(
      2,
      [
        item("Expiry date: 31/03/", 72, 700, 114),
        item("2027", 72 + 114 + 0.5, 700, 24), // kerned: same word
        item("Lot", 72 + 114 + 0.5 + 24 + 6, 700, 18), // 6 pt gap: a new word
        item("A1", 300, 700, 12),
      ],
      STYLES,
      LETTER,
    )!;
    expect(layout.n).toBe(2);
    expect(layout.text).toBe("Expiry date: 31/03/2027 Lot A1");
    expect(layout.words[2].text).toBe("31/03/2027");
    expect(layout.words[2].bbox.x1).toBeCloseTo((72 + 114 + 0.5 + 24) * S, 6);
  });

  it("orders words top to bottom, then left to right inside a line", () => {
    const layout = pdfTextLayout(
      1,
      [item("second line here", 72, 680, 90), item("right", 300, 700, 30), item("left side of the page", 72, 700, 120)],
      STYLES,
      LETTER,
    )!;
    expect(layout.text).toBe("left side of the page right\nsecond line here");
  });

  it("drops words outside the visible page and clamps boxes to it", () => {
    const layout = pdfTextLayout(
      1,
      [item("Approved on 20 March 2026", 470, 700, 150), item("off the page entirely", 700, 700, 100)],
      STYLES,
      LETTER,
    )!;
    expect(layout.text).toBe("Approved on 20 March 2026");
    expect(Math.max(...layout.words.map((w) => w.bbox.x1))).toBe(1700);
  });
});

describe("ocrLayout", () => {
  it("keeps Tesseract's lines, drops blank words and scales confidence to 0-1", () => {
    const box = (x0: number) => ({ x0, y0: 10, x1: x0 + 40, y1: 30 });
    const layout = ocrLayout(
      3,
      [
        [
          { text: "Expiry", bbox: box(0), confidence: 91 },
          { text: " ", bbox: box(50), confidence: 0 },
          { text: "31/03/2027", bbox: box(60), confidence: 88.5 },
        ],
        [{ text: "  ", bbox: box(0), confidence: 10 }],
        [{ text: "Lot", bbox: { x0: -5, y0: 40, x1: 2000, y1: 60 }, confidence: -1 }],
      ],
      1400,
      300,
    );
    expect(layout.text).toBe("Expiry 31/03/2027\nLot");
    expect(layout.text_source).toBe("ocr");
    expect(layout.words.map((w) => [w.text, w.char_start, w.char_end, w.confidence])).toEqual([
      ["Expiry", 0, 6, 0.91],
      ["31/03/2027", 7, 17, 0.885],
      ["Lot", 18, 21, null],
    ]);
    expect(layout.words[2].bbox).toEqual({ x0: 0, y0: 40, x1: 1400, y1: 60 });
  });
});

describe("joinLines", () => {
  it("gives an empty page an empty text", () => {
    expect(joinLines(1, [], 10, 10, "ocr")).toMatchObject({ text: "", words: [] });
  });
});
