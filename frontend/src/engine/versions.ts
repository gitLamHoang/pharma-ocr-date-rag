/**
 * The pinned assets the static build loads from jsDelivr (exact versions, so the files never
 * change under a published build). Everything else is bundled.
 */
export const PYODIDE_VERSION = "314.0.7";
export const PYODIDE_INDEX_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

export const TESSERACT_CORE_VERSION = "7.0.0";
export const TESSERACT_CORE_PATH = `https://cdn.jsdelivr.net/npm/tesseract.js-core@${TESSERACT_CORE_VERSION}`;
/** English only (LSTM, integer model): the same `eng` pack the server uses. */
export const TESSERACT_LANG_PATH = "https://cdn.jsdelivr.net/npm/@tesseract.js-data/eng@1.0.0/4.0.0_best_int";
