/**
 * The in-browser engine of the static build. pdf.js, tesseract.js and Pyodide load on first use
 * (separate chunks), so the screens render before any of them is fetched.
 */
import type { PageLayout } from "./layout";
import type { CoreDate, CoreFlag, Engine } from "./types";
import type { Taxonomy } from "../api/types";

export const browserEngine: Engine = {
  async read(file, kind) {
    const { python } = await import("./pyodide");
    void python.warm(); // Python loads while the pages are read
    const { readFile } = await import("./pdf");
    return readFile(file, kind);
  },
  async analyze(layouts: PageLayout[], today: string) {
    const { python } = await import("./pyodide");
    return JSON.parse(await python.process(JSON.stringify(layouts), today)) as { dates: CoreDate[]; flags: CoreFlag[] };
  },
  async taxonomy() {
    const { python } = await import("./pyodide");
    return JSON.parse(await python.taxonomy()) as Taxonomy;
  },
};
