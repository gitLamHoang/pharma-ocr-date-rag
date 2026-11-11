/**
 * The API's JSON, field for field (backend/pharma_dates/api.py, store.py, models.py, taxonomy.py).
 * Datetimes arrive as ISO 8601 strings.
 */

export type RunStatus = "queued" | "reading" | "classifying" | "validating" | "done" | "failed";
export type DateStatus = "needs_review" | "accepted" | "corrected" | "rejected";
export type ReviewAction = "accept" | "correct" | "reject" | "reopen";
export type DateSource = "rules" | "ai_only" | "rules+ai";
export type Precision = "day" | "month";
export type Severity = "error" | "warning" | "info";
export type FamilyId = "product" | "document" | "signature" | "legal" | "audit" | "logistics" | "other";
export type ExportFormat = "csv" | "json";

export interface Health {
  ai_enabled: boolean;
  provider: string;
  model: string | null;
  tesseract_langs_missing: string[];
}

export interface DateTypeInfo {
  id: string;
  label: string;
}

export interface Family {
  family: FamilyId;
  label: string;
  types: DateTypeInfo[];
}

export type Taxonomy = Family[];

/** One row of `GET /api/documents`, counts from the document's latest run. */
export interface DocumentSummary {
  id: number;
  name: string;
  pages: number;
  status: RunStatus;
  error: string | null;
  n_dates: number;
  n_flags: number;
  n_needs_review: number;
  created_at: string;
}

export interface UploadResult {
  document_id: number;
  run_id: number;
  status: RunStatus;
}

export interface DocumentRecord {
  id: number;
  filename: string;
  sha256: string;
  pages: number;
  status: string;
  created_at: string;
  ai_model: string | null;
  pipeline_version: string | null;
}

export interface RunSummary {
  id: number;
  status: RunStatus;
  error: string | null;
  ai_used: boolean;
  ai_model: string | null;
}

export interface PageInfo {
  n: number;
  width: number;
  height: number;
}

/** `GET /api/documents/{id}`: the document, its latest run (null before the first run), its pages. */
export interface DocumentDetail {
  document: DocumentRecord;
  run: RunSummary | null;
  pages: PageInfo[];
}

/** A box in page-image pixel coordinates, origin top-left. */
export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** A stored date (`DateWithStatus`). `date_type`/`family` stay the pipeline's label; `current_*` include reviews. */
export interface DateRecord {
  id: number;
  candidate_id: string;
  run_id: number;
  document_id: number;
  page: number;
  raw_text: string;
  normalized: string | null;
  candidates: string[];
  precision: Precision;
  char_start: number;
  char_end: number;
  bbox: BBox | null;
  /** One tight box per printed line when the date wraps across lines; empty on one line (use `bbox`). */
  line_boxes: BBox[];
  context: string;
  rule_label: string;
  source: DateSource;
  date_type: string;
  family: FamilyId;
  qualifier: string | null;
  resolved_value: string | null;
  evidence: string | null;
  confidence: number;
  rationale: string | null;
  status: DateStatus;
  current_type: string;
  current_family: FamilyId;
  current_value: string | null;
  carried_from_run: number | null;
}

export interface Flag {
  id: number;
  rule: string;
  severity: Severity;
  message: string;
  date_ids: number[];
}

/** An AI suggestion that failed verification; shown only in a debug list, never as a date. */
export interface DiscardedSuggestion {
  page: number;
  kind: string;
  reason: string;
  [field: string]: unknown;
}

export interface ReviewBody {
  action: ReviewAction;
  reviewer: string;
  reason: string;
  new_type?: string | null;
  new_value?: string | null;
}

export interface ReviewEvent {
  id: number;
  date_id: number;
  action: ReviewAction;
  new_type: string | null;
  new_value: string | null;
  reviewer: string;
  reason: string;
  at: string;
  carried_from_run: number | null;
}

export interface ReprocessResult {
  run_id: number;
}
