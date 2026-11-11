/**
 * Page layouts built in the browser, in the same shape the server's `layout.py` produces:
 * `text` joins words with spaces and lines with newlines, each word's `char_start/char_end` index
 * into it, and boxes are page-image pixels (origin top-left) clamped to the page.
 */
import type { BBox } from "../api/types";

export interface Word {
  text: string;
  bbox: BBox;
  char_start: number;
  char_end: number;
  /** Tesseract word confidence 0-1; null for a PDF text layer. */
  confidence: number | null;
}

export interface PageLayout {
  n: number;
  width: number;
  height: number;
  text: string;
  text_source: "pdf" | "ocr";
  words: Word[];
  transcription: string | null;
}

/** A word before joining: its text, box and OCR confidence. */
export interface LineWord {
  text: string;
  bbox: BBox;
  confidence: number | null;
}

/** A page whose text layer has fewer non-space characters than this is read with OCR (as the server). */
export const MIN_TEXT_LAYER_CHARS = 20;
/** pdfplumber's default: characters closer than 3 PDF points join into one word. */
const X_TOLERANCE_PT = 3;

/** The parts of a pdf.js `TextItem` the layout needs. */
export interface PdfTextItem {
  str: string;
  /** Text matrix [a, b, c, d, e, f] in PDF user space. */
  transform: number[];
  /** Advance width in PDF user space. */
  width: number;
  fontName?: string;
}

/** The parts of a pdf.js `TextStyle` the layout needs (font metrics as a fraction of the size). */
export interface PdfTextStyle {
  descent?: number;
  fontFamily?: string;
}

/** The width of `text` in a font family at any fixed size (only ratios are used). */
export type Measure = (text: string, fontFamily: string | undefined) => number;

/** The page as pdf.js renders it: the viewport's transform (PDF user space -> image pixels) and size. */
export interface PdfViewport {
  transform: number[];
  width: number;
  height: number;
}

function multiply(m1: number[], m2: number[]): number[] {
  return [
    m1[0] * m2[0] + m1[2] * m2[1],
    m1[1] * m2[0] + m1[3] * m2[1],
    m1[0] * m2[2] + m1[2] * m2[3],
    m1[1] * m2[2] + m1[3] * m2[3],
    m1[0] * m2[4] + m1[2] * m2[5] + m1[4],
    m1[1] * m2[4] + m1[3] * m2[5] + m1[5],
  ];
}

interface Fragment extends LineWord {
  /** Whitespace separates this fragment from the one before it in its item. */
  spaceBefore: boolean;
  spaceAfter: boolean;
}

/**
 * The layout of a native PDF page from pdf.js text items, or null when the text layer has too
 * little text to trust (the caller then reads the page with OCR). Items are split into words at
 * whitespace (each word's box takes its share of the item's width as `measure` sizes its text, or
 * by character count without one); pieces of
 * one word that pdf.js returns as separate items join when they are closer than pdfplumber's
 * tolerance. Words group into lines as the server does: sorted top to bottom, a word starts a new
 * line when its middle is below the bottom of the line's first word.
 */
export function pdfTextLayout(
  n: number,
  items: PdfTextItem[],
  styles: Record<string, PdfTextStyle>,
  viewport: PdfViewport,
  measure?: Measure,
): PageLayout | null {
  const nonSpace = items.reduce((sum, item) => sum + item.str.replace(/\s/g, "").length, 0);
  if (nonSpace < MIN_TEXT_LAYER_CHARS) return null;
  const scale = Math.hypot(viewport.transform[0], viewport.transform[1]);
  const width = Math.round(viewport.width);
  const height = Math.round(viewport.height);

  const fragments: Fragment[] = [];
  for (const item of items) {
    if (!item.str.trim()) continue;
    const m = multiply(viewport.transform, item.transform);
    const size = Math.hypot(m[2], m[3]);
    const style = styles[item.fontName ?? ""];
    const descent = style?.descent ?? -0.2;
    // pdfminer's character box: from baseline + descent, one font size tall.
    const bottom = m[5] - descent * size;
    const top = bottom - size;
    const advance = item.width * scale;
    const length = item.str.length;
    const total = measure?.(item.str, style?.fontFamily) ?? 0;
    // The share of the item's advance before character k.
    const at = (k: number) => (total > 0 ? measure!(item.str.slice(0, k), style?.fontFamily) / total : k / length);
    for (const match of item.str.matchAll(/\S+/g)) {
      const start = match.index;
      const end = start + match[0].length;
      fragments.push({
        text: match[0],
        bbox: { x0: m[4] + advance * at(start), y0: top, x1: m[4] + advance * at(end), y1: bottom },
        confidence: null,
        spaceBefore: start > 0,
        spaceAfter: end < length,
      });
    }
  }
  const visible = fragments.filter((f) => f.bbox.x1 > 0 && f.bbox.x0 < width && f.bbox.y1 > 0 && f.bbox.y0 < height);
  const lines = groupLines(visible).map((line) => mergeAdjacent(line, X_TOLERANCE_PT * scale));
  return joinLines(n, lines, width, height, "pdf");
}

function groupLines<W extends LineWord>(words: W[]): W[][] {
  const sorted = [...words].sort((a, b) => a.bbox.y0 - b.bbox.y0 || a.bbox.x0 - b.bbox.x0);
  const lines: W[][] = [];
  let lineBottom: number | null = null;
  for (const word of sorted) {
    const middle = (word.bbox.y0 + word.bbox.y1) / 2;
    if (lineBottom === null || middle > lineBottom) {
      lines.push([]);
      lineBottom = word.bbox.y1;
    }
    lines[lines.length - 1].push(word);
  }
  return lines.map((line) => [...line].sort((a, b) => a.bbox.x0 - b.bbox.x0));
}

function mergeAdjacent(line: Fragment[], tolerance: number): LineWord[] {
  const out: Fragment[] = [];
  for (const fragment of line) {
    const last = out[out.length - 1];
    if (last && !last.spaceAfter && !fragment.spaceBefore && fragment.bbox.x0 - last.bbox.x1 <= tolerance) {
      out[out.length - 1] = {
        ...last,
        text: last.text + fragment.text,
        bbox: {
          x0: Math.min(last.bbox.x0, fragment.bbox.x0),
          y0: Math.min(last.bbox.y0, fragment.bbox.y0),
          x1: Math.max(last.bbox.x1, fragment.bbox.x1),
          y1: Math.max(last.bbox.y1, fragment.bbox.y1),
        },
        spaceAfter: fragment.spaceAfter,
      };
    } else {
      out.push(fragment);
    }
  }
  return out.map(({ text, bbox, confidence }) => ({ text, bbox, confidence }));
}

/** The parts of a tesseract.js word the layout needs (confidence 0-100). */
export interface OcrWord {
  text: string;
  bbox: BBox;
  confidence: number;
}

/** The layout of a page from Tesseract's lines of words (blank words dropped, as the server does). */
export function ocrLayout(n: number, lines: OcrWord[][], width: number, height: number): PageLayout {
  const kept = lines
    .map((line) =>
      line
        .map((w) => ({ text: w.text.trim(), bbox: w.bbox, confidence: w.confidence >= 0 ? w.confidence / 100 : null }))
        .filter((w) => w.text),
    )
    .filter((line) => line.length > 0);
  return joinLines(n, kept, width, height, "ocr");
}

/** Port of `layout._join`: words with spaces, lines with newlines, boxes clamped to the page. */
export function joinLines(
  n: number,
  lines: LineWord[][],
  width: number,
  height: number,
  source: "pdf" | "ocr",
): PageLayout {
  const clamp = (v: number, max: number) => Math.min(Math.max(v, 0), max);
  const parts: string[] = [];
  const words: Word[] = [];
  let pos = 0;
  lines.forEach((line, li) => {
    if (li) {
      parts.push("\n");
      pos += 1;
    }
    line.forEach((w, wi) => {
      if (wi) {
        parts.push(" ");
        pos += 1;
      }
      words.push({
        text: w.text,
        bbox: {
          x0: clamp(w.bbox.x0, width),
          y0: clamp(w.bbox.y0, height),
          x1: clamp(w.bbox.x1, width),
          y1: clamp(w.bbox.y1, height),
        },
        char_start: pos,
        char_end: pos + w.text.length,
        confidence: w.confidence,
      });
      parts.push(w.text);
      pos += w.text.length;
    });
  });
  return { n, width, height, text: parts.join(""), text_source: source, words, transcription: null };
}
