/** Tesseract (tesseract.js, `eng` only) on a page image, in its own worker. */
import { createWorker, PSM, type Worker } from "tesseract.js";
import workerPath from "tesseract.js/dist/worker.min.js?url";
import { ocrLayout, type OcrWord, type PageLayout } from "./layout";
import { TESSERACT_CORE_PATH, TESSERACT_LANG_PATH } from "./versions";

let worker: Promise<Worker> | null = null;

async function start(): Promise<Worker> {
  const w = await createWorker("eng", 1 /* LSTM, as the server's --oem 1 */, {
    workerPath,
    workerBlobURL: false,
    corePath: TESSERACT_CORE_PATH,
    langPath: TESSERACT_LANG_PATH,
  });
  await w.setParameters({ tessedit_pageseg_mode: PSM.AUTO }); // the server's --psm 3
  return w;
}

/** The OCR layout of page `n` from its PNG. */
export async function ocrPage(n: number, image: Blob, width: number, height: number): Promise<PageLayout> {
  worker ??= start().catch((error) => {
    worker = null;
    throw error;
  });
  const { data } = await (await worker).recognize(image, {}, { blocks: true, text: false });
  const lines: OcrWord[][] = [];
  for (const block of data.blocks ?? []) {
    for (const paragraph of block.paragraphs) {
      for (const line of paragraph.lines) {
        lines.push(line.words.map((w) => ({ text: w.text, bbox: w.bbox, confidence: w.confidence })));
      }
    }
  }
  return ocrLayout(n, lines, width, height);
}
