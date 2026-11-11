/**
 * Reading a document in the browser: pdf.js renders each PDF page at 200 DPI and gives its text
 * layer; a page with too little text, and every image, is read with OCR. Same limits and messages
 * as the server's `ingest.py`.
 */
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from "pdfjs-dist";
import pdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { pdfTextLayout, type PdfTextItem, type PdfTextStyle } from "./layout";
import { ocrPage } from "./ocr";
import { EngineError, type ReadPage } from "./types";

GlobalWorkerOptions.workerSrc = pdfWorker;

export const RENDER_DPI = 200;
export const MAX_PAGES = 100;
/** Pillow's decompression-bomb limit, which the server applies to every page. */
const MAX_PIXELS = 89_478_485;
const PDFJS_ASSETS = `${import.meta.env.BASE_URL}pdfjs/`;

export const DAMAGED = "This file is damaged or incomplete and cannot be read.";
export const NO_PAGES = "This document has no readable pages.";
export const TOO_LARGE = "This document has a page too large to process (too many pixels).";
export const ENCRYPTED = "This PDF is password-protected. Remove the password and upload it again.";
export const TIFF_IN_BROWSER = "This browser cannot open TIFF files. Save the scan as PDF, PNG or JPG and upload it again.";

let measurer: CanvasRenderingContext2D | null = null;

/** Glyph widths from the browser's own font for the family pdf.js names (as its text layer does). */
function measure(text: string, fontFamily: string | undefined): number {
  measurer ??= document.createElement("canvas").getContext("2d");
  if (!measurer) return 0;
  measurer.font = `100px ${fontFamily || "sans-serif"}`;
  return measurer.measureText(text).width;
}

function checkPageCount(count: number) {
  if (count === 0) throw new EngineError(NO_PAGES);
  if (count > MAX_PAGES) throw new EngineError(`This document has ${count} pages; the limit is ${MAX_PAGES}.`);
}

function checkPixels(width: number, height: number) {
  if (width * height > MAX_PIXELS) throw new EngineError(TOO_LARGE);
}

function canvasOf(width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function png(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new EngineError(TOO_LARGE))), "image/png"),
  );
}

async function openPdf(bytes: ArrayBuffer): Promise<{ pdf: PDFDocumentProxy; close: () => Promise<void> }> {
  const task = getDocument({
      data: new Uint8Array(bytes),
      wasmUrl: `${PDFJS_ASSETS}wasm/`,
      standardFontDataUrl: `${PDFJS_ASSETS}standard_fonts/`,
      cMapUrl: `${PDFJS_ASSETS}cmaps/`,
      iccUrl: `${PDFJS_ASSETS}iccs/`,
      stopAtErrors: false,
  });
  try {
    return { pdf: await task.promise, close: () => task.destroy() };
  } catch (error) {
    void task.destroy();
    const name = (error as Error)?.name;
    if (name === "PasswordException") throw new EngineError(ENCRYPTED);
    throw new EngineError(DAMAGED);
  }
}

async function readPdf(bytes: ArrayBuffer): Promise<ReadPage[]> {
  const { pdf, close } = await openPdf(bytes);
  try {
    checkPageCount(pdf.numPages);
    const scale = RENDER_DPI / 72;
    const pages = [];
    for (let n = 1; n <= pdf.numPages; n++) {
      try {
        pages.push(await pdf.getPage(n));
      } catch {
        throw new EngineError(DAMAGED);
      }
    }
    for (const page of pages) {
      const { width, height } = page.getViewport({ scale });
      checkPixels(Math.round(width), Math.round(height));
    }
    const out: ReadPage[] = [];
    for (const page of pages) {
      const viewport = page.getViewport({ scale });
      const canvas = canvasOf(Math.round(viewport.width), Math.round(viewport.height));
      let content;
      try {
        await page.render({ canvas, viewport, background: "#ffffff" }).promise;
        content = await page.getTextContent();
      } catch {
        throw new EngineError(DAMAGED);
      }
      const items = content.items.filter((i) => "str" in i) as PdfTextItem[];
      const image = await png(canvas);
      const layout =
        pdfTextLayout(page.pageNumber, items, content.styles as Record<string, PdfTextStyle>, {
          transform: viewport.transform,
          width: canvas.width,
          height: canvas.height,
        }, measure) ?? (await ocrPage(page.pageNumber, image, canvas.width, canvas.height));
      out.push({ layout, image });
      page.cleanup();
    }
    return out;
  } finally {
    void close();
  }
}

async function readImage(file: Blob): Promise<ReadPage[]> {
  const head = new Uint8Array(await file.slice(0, 4).arrayBuffer());
  const tiff = (head[0] === 0x49 && head[1] === 0x49) || (head[0] === 0x4d && head[1] === 0x4d);
  let bitmap: ImageBitmap;
  try {
    // Upright, as the server's exif_transpose: phone photos store the page sideways with a tag.
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new EngineError(tiff ? TIFF_IN_BROWSER : DAMAGED);
  }
  checkPixels(bitmap.width, bitmap.height);
  const canvas = canvasOf(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#ffffff"; // a transparent PNG reads as white paper, as the server's RGB convert
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  const image = await png(canvas);
  return [{ layout: await ocrPage(1, image, canvas.width, canvas.height), image }];
}

/** Every page of the file, with its layout and PNG. Throws `EngineError` with a message to show. */
export async function readFile(file: Blob, kind: "pdf" | "image"): Promise<ReadPage[]> {
  if (kind === "image") return readImage(file);
  let bytes: ArrayBuffer;
  try {
    bytes = await file.arrayBuffer();
  } catch {
    throw new EngineError("The uploaded file could not be read.");
  }
  return readPdf(bytes);
}
