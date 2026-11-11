/** What the static build's in-browser engine reads and returns. */
import type { DateRecord, Severity, Taxonomy } from "../api/types";
import type { PageLayout } from "./layout";

/** A file cannot be processed; the message is safe to show (the server's ingest messages). */
export class EngineError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EngineError";
  }
}

/** One page as read in the browser: its layout and its image (PNG). */
export interface ReadPage {
  layout: PageLayout;
  image: Blob;
}

/** A `LabeledDate` from the Python core: `id` is the candidate id ("p1-c2"). */
export type CoreDate = Omit<
  DateRecord,
  "id" | "candidate_id" | "run_id" | "document_id" | "status" | "current_type" | "current_family" | "current_value" | "carried_from_run"
> & { id: string };

/** A `Flag` from the Python core: `date_ids` are candidate ids. */
export interface CoreFlag {
  rule: string;
  severity: Severity;
  message: string;
  date_ids: string[];
}

export interface Engine {
  /** Every page of a PDF or image: text layer or OCR, and the page image. Throws `EngineError`. */
  read(file: Blob, kind: "pdf" | "image"): Promise<ReadPage[]>;
  /** The rules-only pipeline (Python core in Pyodide) over the document's layouts. */
  analyze(layouts: PageLayout[], today: string): Promise<{ dates: CoreDate[]; flags: CoreFlag[] }>;
  taxonomy(): Promise<Taxonomy>;
}
