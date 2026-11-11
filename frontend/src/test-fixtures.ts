/** Builders for the API's records, shared by the Review tests. */
import type { DateRecord, DocumentDetail, Flag, ReviewEvent, Taxonomy } from "./api";

export function dateRecord(overrides: Partial<DateRecord> = {}): DateRecord {
  return {
    id: 1,
    candidate_id: "p1-c1",
    run_id: 4,
    document_id: 1,
    page: 1,
    raw_text: "14/03/2026",
    normalized: "2026-03-14",
    candidates: ["2026-03-14"],
    precision: "day",
    char_start: 0,
    char_end: 10,
    bbox: { x0: 100, y0: 200, x1: 300, y1: 250 },
    context: "Date of manufacture: 14/03/2026",
    rule_label: "manufacture_date",
    source: "rules",
    date_type: "manufacture_date",
    family: "product",
    qualifier: null,
    resolved_value: null,
    evidence: null,
    confidence: 0.92,
    rationale: null,
    status: "needs_review",
    current_type: "manufacture_date",
    current_family: "product",
    current_value: "2026-03-14",
    carried_from_run: null,
    ...overrides,
  };
}

/** `09/10/2026` with no evidence: two readings, no value. */
export function ambiguousDate(overrides: Partial<DateRecord> = {}): DateRecord {
  return dateRecord({
    raw_text: "09/10/2026",
    normalized: null,
    candidates: ["2026-09-10", "2026-10-09"],
    current_value: null,
    context: "Approved on 09/10/2026",
    date_type: "approval_date",
    current_type: "approval_date",
    family: "document",
    current_family: "document",
    ...overrides,
  });
}

/** `EXP 03/2027`: month precision. */
export function monthDate(overrides: Partial<DateRecord> = {}): DateRecord {
  return dateRecord({
    raw_text: "EXP 03/2027",
    normalized: "2027-03",
    candidates: ["2027-03"],
    precision: "month",
    current_value: "2027-03",
    date_type: "expiry_date",
    current_type: "expiry_date",
    context: "Lot 4471 EXP 03/2027",
    ...overrides,
  });
}

export function flag(overrides: Partial<Flag> = {}): Flag {
  return { id: 1, rule: "ambiguous_unresolved", severity: "info", message: "09/10/2026 could be 2026-09-10 or 2026-10-09; choose the reading.", date_ids: [1], ...overrides };
}

export function reviewEvent(overrides: Partial<ReviewEvent> = {}): ReviewEvent {
  return {
    id: 1,
    date_id: 1,
    action: "accept",
    new_type: null,
    new_value: null,
    reviewer: "J. Doe",
    reason: "Matches the page",
    at: "2026-11-11T09:05:00",
    carried_from_run: null,
    ...overrides,
  };
}

export function documentDetail(overrides: Partial<DocumentDetail> = {}): DocumentDetail {
  return {
    document: {
      id: 1,
      filename: "coa-lot-4471.pdf",
      sha256: "0".repeat(64),
      pages: 2,
      status: "done",
      created_at: "2026-11-11T09:00:00",
      ai_model: null,
      pipeline_version: "2.0.0",
    },
    run: { id: 4, status: "done", error: null, ai_used: false, ai_model: null },
    pages: [
      { n: 1, width: 1000, height: 2000 },
      { n: 2, width: 1000, height: 2000 },
    ],
    ...overrides,
  };
}

export const TAXONOMY: Taxonomy = [
  {
    family: "product",
    label: "Product / batch",
    types: [
      { id: "manufacture_date", label: "Manufacture date" },
      { id: "expiry_date", label: "Expiry date" },
    ],
  },
  {
    family: "document",
    label: "Document control",
    types: [
      { id: "effective_date", label: "Effective date" },
      { id: "approval_date", label: "Approval date" },
    ],
  },
  { family: "signature", label: "Signature", types: [{ id: "signature_date", label: "Signature date" }] },
  {
    family: "other",
    label: "Other",
    types: [
      { id: "other_date", label: "Other date" },
      { id: "unknown", label: "Unknown" },
    ],
  },
];
