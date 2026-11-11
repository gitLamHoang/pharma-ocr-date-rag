/** The run export as the server writes it (`GET /api/runs/{id}/export`), built in the browser. */
import type { DateRecord, DocumentRecord, ExportFormat, Flag, ReviewEvent } from "../types";

export const CSV_COLUMNS = [
  "document",
  "run_id",
  "date_id",
  "page",
  "raw_text",
  "status",
  "current_type",
  "current_family",
  "current_value",
  "date_type",
  "normalized",
  "candidates",
  "precision",
  "qualifier",
  "resolved_value",
  "evidence",
  "source",
  "confidence",
  "flags",
  "carried_from_run",
  "last_action",
  "last_reviewer",
  "last_reason",
  "last_reviewed_at",
  "context",
] as const;

const FORMULA_START = ["=", "+", "-", "@", "\t", "\r"];

/** A CSV cell a spreadsheet will not run as a formula (leading = + - @ tab or CR get a `'`). */
export function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return FORMULA_START.some((c) => text.startsWith(c)) ? "'" + text : text;
}

/** Python's `csv.writer` quoting (QUOTE_MINIMAL), rows ended with CRLF. */
function csvField(text: string): string {
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** A float as Python prints it (`1.0`, not `1`). */
function pyFloat(value: number): string {
  return Number.isInteger(value) ? value.toFixed(1) : String(value);
}

/** `<stem>-run-<id>.<format>` with the stem made safe, as the server's Content-Disposition. */
export function exportFilename(filename: string, runId: number, format: ExportFormat): string {
  const dot = filename.lastIndexOf(".");
  const stem = dot > 0 ? filename.slice(0, dot) : filename;
  const safe = stem.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._]+|[._]+$/g, "") || "document";
  return `${safe}-run-${runId}.${format}`;
}

export interface ExportInput {
  document: DocumentRecord;
  run: object & { id: number };
  dates: DateRecord[];
  flags: Flag[];
  histories: Map<number, ReviewEvent[]>;
  exportedAt: string;
}

export function exportCsv({ document, run, dates, flags, histories }: ExportInput): string {
  const flagRules = new Map<number, string[]>();
  for (const f of flags) for (const id of f.date_ids) flagRules.set(id, [...(flagRules.get(id) ?? []), f.rule]);
  const lines = [CSV_COLUMNS.join(",")];
  for (const d of dates) {
    const last = histories.get(d.id)?.at(-1) ?? null;
    const row: Record<(typeof CSV_COLUMNS)[number], unknown> = {
      document: document.filename,
      run_id: run.id,
      date_id: d.id,
      page: d.page,
      raw_text: d.raw_text,
      status: d.status,
      current_type: d.current_type,
      current_family: d.current_family,
      current_value: d.current_value,
      date_type: d.date_type,
      normalized: d.normalized,
      candidates: d.candidates.join(" | "),
      precision: d.precision,
      qualifier: d.qualifier,
      resolved_value: d.resolved_value,
      evidence: d.evidence,
      source: d.source,
      confidence: pyFloat(d.confidence),
      flags: (flagRules.get(d.id) ?? []).join(" | "),
      carried_from_run: d.carried_from_run,
      last_action: last?.action,
      last_reviewer: last?.reviewer,
      last_reason: last?.reason,
      last_reviewed_at: last?.at,
      context: d.context,
    };
    lines.push(CSV_COLUMNS.map((c) => csvField(csvCell(row[c]))).join(","));
  }
  // A byte-order mark so spreadsheet programs read the file as UTF-8.
  return "﻿" + lines.map((l) => l + "\r\n").join("");
}

export function exportJson({ document, run, dates, flags, histories, exportedAt }: ExportInput): string {
  const body = {
    exported_at: exportedAt,
    document,
    run,
    dates: dates.map((d) => ({ ...d, history: histories.get(d.id) ?? [] })),
    flags,
  };
  return JSON.stringify(body, null, 2);
}
