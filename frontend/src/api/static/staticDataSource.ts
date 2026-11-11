/**
 * The static build's `DataSource` (`VITE_MODE=static`, GitHub Pages): every document is read and
 * checked in this browser and kept in its IndexedDB (or memory). Nothing is sent anywhere.
 *
 * It follows the server's rules (backend `store.py`, `pipeline.py`, `api.py`): one run per
 * processing, only the latest run takes reviews (409 otherwise), append-only review events from
 * which status and current type/value are read, the same validation messages, the same
 * exact-match carry-over on reprocess, the same upload limits and export columns.
 */
import { ApiError } from "../client";
import type { DataSource } from "../dataSource";
import type {
  DateRecord,
  DocumentDetail,
  DocumentRecord,
  DocumentSummary,
  ExportFormat,
  Flag,
  Health,
  PageInfo,
  ReviewAction,
  ReviewBody,
  ReviewEvent,
  RunStatus,
  Taxonomy,
} from "../types";
import type { PageLayout } from "../../engine/layout";
import { EngineError, type CoreDate, type Engine } from "../../engine/types";
import { exportCsv, exportFilename, exportJson } from "./export";
import type { Storage } from "./storage";

export const MAX_UPLOAD_MB = 50;
export const PIPELINE_VERSION = "1.0.0";
export const UNSUPPORTED = "This file type is not supported. Upload a PDF, PNG, JPG or TIFF file.";
const PROCESSING_ERROR = "Processing error";
const INTERRUPTED = "Processing was interrupted. Reprocess the document.";
const UNREADABLE = "The uploaded file could not be read.";
const ACTIONS: ReviewAction[] = ["accept", "correct", "reject", "reopen"];
const STATUS_OF = { accept: "accepted", correct: "corrected", reject: "rejected", reopen: "needs_review" } as const;

interface RunRecord {
  id: number;
  document_id: number;
  pipeline_version: string;
  ai_model: null;
  ai_used: false;
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  error: string | null;
}

interface PageRecord extends PageLayout {
  id: string;
  run_id: number;
}

type DateRow = Omit<CoreDate, "id"> & { id: number; candidate_id: string; run_id: number; document_id: number };

interface FlagRecord extends Flag {
  run_id: number;
}

export interface StaticDataSource extends DataSource {
  /** The download name for `exportUrl` (a blob URL carries none). */
  exportFilename(runId: number, fmt: ExportFormat): string;
  /** Resolves once every queued run has finished. */
  idle(): Promise<void>;
}

interface Options {
  storage: Storage | Promise<Storage>;
  engine: Engine;
}

/** The server's timestamp format: UTC, seconds, `+00:00`. */
function now(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00");
}

/** Today in local time, as the server's `date.today()`. */
function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** (kind) from a file's first bytes, or null for an unsupported type (`ingest.file_kind`). */
export function fileKind(head: Uint8Array): "pdf" | "image" | null {
  const starts = (sig: number[]) => sig.every((b, i) => head[i] === b);
  if (starts([0x25, 0x50, 0x44, 0x46, 0x2d])) return "pdf";
  if (starts([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return "image";
  if (starts([0xff, 0xd8, 0xff])) return "image";
  if (starts([0x49, 0x49, 0x2a, 0x00]) || starts([0x4d, 0x4d, 0x00, 0x2a])) return "image";
  return null;
}

async function sha256(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function validValue(value: string): boolean {
  if (!/^\d{4}-\d{2}(?:-\d{2})?$/.test(value)) return false;
  const [y, m, d = 1] = value.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d && y >= 1;
}

function displayName(name: string): string {
  const base = name.replace(/\\/g, "/").split("/").pop() ?? "";
  // eslint-disable-next-line no-control-regex
  return base.replace(/[\x00-\x1f\x7f]/g, "").trim().slice(0, 200) || "document";
}

const valueOf = (d: { normalized: string | null; resolved_value: string | null }) => d.normalized || d.resolved_value;

export function createStaticDataSource({ storage: storageOption, engine }: Options): StaticDataSource {
  const documents = new Map<number, DocumentRecord>();
  const runs = new Map<number, RunRecord>();
  const pages = new Map<number, PageRecord[]>();
  const dates = new Map<number, DateRow[]>();
  const flags = new Map<number, FlagRecord[]>();
  const events = new Map<number, ReviewEvent[]>(); // by date id
  const dateById = new Map<number, DateRow>();
  const running = new Set<number>();
  const images = new Map<string, Blob>(); // "run:n" -> PNG, this session
  const imageUrls = new Map<string, string>();
  const exportUrls = new Map<string, string>();
  const originals = new Map<number, Blob>();
  const nextId = { documents: 1, runs: 1, dates: 1, flags: 1, events: 1 };
  let taxonomy: Taxonomy | null = null;
  let familyOf = new Map<string, string>();
  let queue: Promise<void> = Promise.resolve();
  let storage: Storage;

  /** Writes go to memory first; a failed write to storage (quota, blocked) keeps the session working. */
  async function persist(write: () => Promise<void>) {
    try {
      await write();
    } catch (error) {
      console.warn("Could not save to browser storage:", (error as Error)?.name);
    }
  }

  const ready = (async () => {
    storage = await storageOption;
    let snapshot;
    try {
      snapshot = await storage.load();
    } catch {
      return;
    }
    for (const d of snapshot.documents as DocumentRecord[]) documents.set(d.id, d);
    for (const r of snapshot.runs as RunRecord[]) runs.set(r.id, r);
    for (const p of snapshot.pages as PageRecord[]) pages.set(p.run_id, [...(pages.get(p.run_id) ?? []), p]);
    for (const d of snapshot.dates as DateRow[]) {
      dates.set(d.run_id, [...(dates.get(d.run_id) ?? []), d]);
      dateById.set(d.id, d);
    }
    for (const f of snapshot.flags as FlagRecord[]) flags.set(f.run_id, [...(flags.get(f.run_id) ?? []), f]);
    for (const e of (snapshot.events as ReviewEvent[]).sort((a, b) => a.id - b.id)) {
      events.set(e.date_id, [...(events.get(e.date_id) ?? []), e]);
    }
    for (const list of pages.values()) list.sort((a, b) => a.n - b.n);
    for (const list of dates.values()) list.sort((a, b) => a.page - b.page || a.char_start - b.char_start || a.id - b.id);
    for (const list of flags.values()) list.sort((a, b) => a.id - b.id);
    const maxId = (ids: Iterable<number>) => Math.max(0, ...ids) + 1;
    nextId.documents = maxId(documents.keys());
    nextId.runs = maxId(runs.keys());
    nextId.dates = maxId(dateById.keys());
    nextId.flags = maxId([...flags.values()].flat().map((f) => f.id));
    nextId.events = maxId([...events.values()].flat().map((e) => e.id));
    // A run cannot still be moving after a page load: the work lived in the closed tab.
    for (const run of runs.values()) {
      if (run.status !== "done" && run.status !== "failed") await setRunStatus(run.id, "failed", INTERRUPTED);
    }
  })();

  // Documents and runs

  function latestRun(documentId: number): RunRecord | null {
    let latest: RunRecord | null = null;
    for (const r of runs.values()) if (r.document_id === documentId && (!latest || r.id > latest.id)) latest = r;
    return latest;
  }

  function latestDoneRun(documentId: number): RunRecord | null {
    let latest: RunRecord | null = null;
    for (const r of runs.values()) {
      if (r.document_id === documentId && r.status === "done" && (!latest || r.id > latest.id)) latest = r;
    }
    return latest;
  }

  async function setRunStatus(runId: number, status: RunStatus, error: string | null = null) {
    const run = runs.get(runId)!;
    Object.assign(run, { status, error, finished_at: status === "done" || status === "failed" ? now() : null });
    await persist(() => storage.put("runs", run));
    const doc = documents.get(run.document_id)!;
    if (latestRun(doc.id)?.id === runId) {
      doc.status = status;
      await persist(() => storage.put("documents", doc));
    }
  }

  async function createRun(documentId: number): Promise<RunRecord> {
    const run: RunRecord = {
      id: nextId.runs++,
      document_id: documentId,
      pipeline_version: PIPELINE_VERSION,
      ai_model: null,
      ai_used: false,
      started_at: now(),
      finished_at: null,
      status: "queued",
      error: null,
    };
    runs.set(run.id, run);
    await persist(() => storage.put("runs", run));
    const doc = documents.get(documentId)!;
    Object.assign(doc, { status: "queued", ai_model: null, pipeline_version: PIPELINE_VERSION });
    await persist(() => storage.put("documents", doc));
    return run;
  }

  function start(run: RunRecord, file: Blob, kind: "pdf" | "image", carryFrom: number | null) {
    running.add(run.id);
    queue = queue.then(() => process(run.id, file, kind, carryFrom)).finally(() => running.delete(run.id));
  }

  async function process(runId: number, file: Blob, kind: "pdf" | "image", carryFrom: number | null) {
    try {
      await setRunStatus(runId, "reading");
      const read = await engine.read(file, kind);
      const run = runs.get(runId)!;
      const doc = documents.get(run.document_id)!;
      doc.pages = Math.max(doc.pages, read.length);
      await persist(() => storage.put("documents", doc));
      await setRunStatus(runId, "classifying");
      const result = await engine.analyze(
        read.map((p) => p.layout),
        today(),
      );
      await setRunStatus(runId, "validating");
      await savePages(runId, read);
      await saveResults(runId, doc.id, result.dates, result.flags);
      if (carryFrom !== null) await carryOver(carryFrom, runId);
      await setRunStatus(runId, "done");
    } catch (error) {
      if (error instanceof EngineError) {
        await setRunStatus(runId, "failed", error.message);
      } else {
        // The type only: messages can quote document text.
        console.error(`run ${runId} failed:`, (error as Error)?.name);
        await setRunStatus(runId, "failed", PROCESSING_ERROR);
      }
    }
  }

  async function savePages(runId: number, read: { layout: PageLayout; image: Blob }[]) {
    const records = read.map(({ layout }) => ({ ...layout, id: `${runId}:${layout.n}`, run_id: runId }));
    pages.set(runId, records);
    for (const [i, { image }] of read.entries()) {
      const key = `${runId}:${records[i].n}`;
      images.set(key, image);
      await persist(() => storage.putBlob(`page:${key}`, image));
      await persist(() => storage.put("pages", records[i]));
    }
  }

  async function saveResults(runId: number, documentId: number, found: CoreDate[], coreFlags: { rule: string; severity: Flag["severity"]; message: string; date_ids: string[] }[]) {
    const ids = new Map<string, number>();
    const rows: DateRow[] = found.map(({ id: candidateId, ...rest }) => {
      const row: DateRow = { ...rest, id: nextId.dates++, candidate_id: candidateId, run_id: runId, document_id: documentId };
      ids.set(candidateId, row.id);
      return row;
    });
    rows.sort((a, b) => a.page - b.page || a.char_start - b.char_start || a.id - b.id);
    const flagRows: FlagRecord[] = coreFlags.map((f) => {
      const unknown = f.date_ids.filter((i) => !ids.has(i));
      if (unknown.length) throw new Error(`flag ${f.rule} refers to unknown dates`);
      return { id: nextId.flags++, run_id: runId, rule: f.rule, severity: f.severity, message: f.message, date_ids: f.date_ids.map((i) => ids.get(i)!) };
    });
    dates.set(runId, rows);
    for (const row of rows) dateById.set(row.id, row);
    flags.set(runId, flagRows);
    for (const row of rows) await persist(() => storage.put("dates", row));
    for (const f of flagRows) await persist(() => storage.put("flags", f));
  }

  // Reviews

  async function insertEvent(
    dateId: number,
    action: ReviewAction,
    newType: string | null,
    newValue: string | null,
    reviewer: string,
    reason: string,
    carriedFromRun: number | null,
  ): Promise<ReviewEvent> {
    const event: ReviewEvent = {
      id: nextId.events++,
      date_id: dateId,
      action,
      new_type: newType,
      new_value: newValue,
      reviewer,
      reason,
      at: now(),
      carried_from_run: carriedFromRun,
    };
    events.set(dateId, [...(events.get(dateId) ?? []), event]);
    await persist(() => storage.append("events", event));
    return { ...event };
  }

  function withStatus(row: DateRow): DateRecord {
    const history = events.get(row.id) ?? [];
    let currentType = row.date_type;
    let currentValue = valueOf(row);
    for (const e of history) {
      // Corrections stay in effect through later accepts and reopens.
      currentType = e.new_type || currentType;
      currentValue = e.new_value || currentValue;
    }
    const last = history.at(-1) ?? null;
    const currentFamily = currentType === row.date_type ? row.family : (familyOf.get(currentType) ?? row.family);
    return structuredClone({
      ...row,
      status: last ? STATUS_OF[last.action] : "needs_review",
      current_type: currentType,
      current_family: currentFamily as DateRecord["family"],
      current_value: currentValue,
      carried_from_run: last ? last.carried_from_run : null,
    });
  }

  async function loadTaxonomy(): Promise<Taxonomy> {
    if (!taxonomy) {
      taxonomy = await engine.taxonomy();
      familyOf = new Map(taxonomy.flatMap((f) => f.types.map((t) => [t.id, f.family] as const)));
    }
    return taxonomy;
  }

  function datesFor(runId: number): DateRecord[] {
    return (dates.get(runId) ?? []).map(withStatus);
  }

  /** Port of `Store.carry_over` (see its docstring): exact (page, raw text, normalized) matches. */
  async function carryOver(oldRunId: number, newRunId: number): Promise<number> {
    const byKey = new Map<string, DateRecord[]>();
    const key = (d: { page: number; raw_text: string; normalized: string | null }) =>
      JSON.stringify([d.page, d.raw_text, d.normalized]);
    for (const d of datesFor(oldRunId)) byKey.set(key(d), [...(byKey.get(key(d)) ?? []), d]);
    let carried = 0;
    for (const d of datesFor(newRunId)) {
      const matches = byKey.get(key(d));
      if (!matches?.length) continue;
      const source = matches.shift()!;
      const last = events.get(source.id)?.at(-1);
      if ((events.get(d.id)?.length ?? 0) > 0 || !last) continue;
      const newType = source.current_type !== d.date_type ? source.current_type : null;
      const unread = source.current_value === null && valueOf(d) !== null;
      const newValue = source.current_value !== valueOf(d) ? source.current_value : null;
      const reason = `carried over from run ${oldRunId}`;
      if (last.action === "reopen") {
        if (newType === null && newValue === null) continue;
        await insertEvent(d.id, "correct", newType, newValue, last.reviewer, reason, oldRunId);
        await insertEvent(d.id, "reopen", null, null, last.reviewer, reason, oldRunId);
      } else if (unread) {
        continue;
      } else {
        await insertEvent(d.id, last.action, newType, newValue, last.reviewer, reason, oldRunId);
      }
      carried += 1;
    }
    return carried;
  }

  async function addReview(dateId: number, body: ReviewBody): Promise<ReviewEvent> {
    const reviewer = (body.reviewer ?? "").trim();
    const reason = (body.reason ?? "").trim();
    const { action } = body;
    const newType = body.new_type ?? null;
    const newValue = body.new_value ?? null;
    const invalid = (message: string) => new ApiError(422, message);
    if (!ACTIONS.includes(action)) throw invalid(`unknown review action '${action}'`);
    if (!reviewer) throw invalid("a reviewer name is required");
    if (!reason) throw invalid("a reason is required");
    if (action === "correct") {
      if (newType === null && newValue === null) throw invalid("a correction needs a new type or a new value");
    } else if (newType !== null || newValue !== null) {
      throw invalid("only a correction can change the type or value");
    }
    if (newType !== null) {
      await loadTaxonomy();
      if (!familyOf.has(newType)) throw invalid(`date type '${newType}' is not in the taxonomy`);
    }
    if (newValue !== null && !validValue(newValue)) {
      throw invalid("a value must be a date written YYYY-MM-DD, or YYYY-MM for month precision");
    }
    const row = dateById.get(dateId);
    if (!row) throw new ApiError(404, `Date ${dateId} not found.`);
    const latest = latestRun(row.document_id)!.id;
    if (row.run_id !== latest) {
      throw new ApiError(409, `run ${row.run_id} is frozen; review the document's latest run ${latest}`);
    }
    if (newValue !== null && row.precision === "month" && newValue.length !== 7) {
      throw invalid("the page gives a month only; write the value as YYYY-MM, never with a day");
    }
    return insertEvent(dateId, action, newType, newValue, reviewer, reason, null);
  }

  // Lookups

  function getRun(runId: number): RunRecord {
    const run = runs.get(runId);
    if (!run) throw new ApiError(404, `Run ${runId} not found.`);
    return run;
  }

  function getDocumentRecord(documentId: number): DocumentRecord {
    const doc = documents.get(documentId);
    if (!doc) throw new ApiError(404, `Document ${documentId} not found.`);
    return doc;
  }

  /** Object URLs for a run's page images, so `pageImageUrl` can answer synchronously. */
  async function prepareImages(runId: number) {
    for (const p of pages.get(runId) ?? []) {
      const key = `${runId}:${p.n}`;
      if (imageUrls.has(key)) continue;
      let blob = images.get(key) ?? null;
      if (!blob) {
        try {
          blob = await storage.getBlob(`page:${key}`);
        } catch {
          blob = null;
        }
      }
      if (blob) imageUrls.set(key, URL.createObjectURL(blob));
    }
  }

  const pageInfo = (runId: number): PageInfo[] =>
    (pages.get(runId) ?? []).map((p) => ({ n: p.n, width: p.width, height: p.height }));

  function exportUrl(runId: number, fmt: ExportFormat): string {
    const run = runs.get(runId);
    if (!run) return "";
    const document = documents.get(run.document_id)!;
    const runDates = datesFor(runId);
    const input = {
      document: structuredClone(document),
      run: structuredClone(run),
      dates: runDates,
      flags: (flags.get(runId) ?? []).map(({ run_id: _, ...f }) => structuredClone(f)),
      histories: new Map(runDates.map((d) => [d.id, structuredClone(events.get(d.id) ?? [])])),
      exportedAt: now(),
    };
    const content = fmt === "csv" ? exportCsv(input) : exportJson(input);
    const type = fmt === "csv" ? "text/csv;charset=utf-8" : "application/json";
    const key = `${runId}:${fmt}`;
    const previous = exportUrls.get(key);
    if (previous) URL.revokeObjectURL(previous);
    const url = URL.createObjectURL(new Blob([content], { type }));
    exportUrls.set(key, url);
    return url;
  }

  const source: StaticDataSource = {
    async getHealth(): Promise<Health> {
      return { ai_enabled: false, provider: "browser", model: null, tesseract_langs_missing: [] };
    },

    getTaxonomy: () => loadTaxonomy(),

    async listDocuments(): Promise<DocumentSummary[]> {
      await ready;
      return [...documents.values()]
        .sort((a, b) => (a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : b.id - a.id))
        .map((d) => {
          const run = latestRun(d.id);
          const runDates = run ? datesFor(run.id) : [];
          return {
            id: d.id,
            name: d.filename,
            pages: d.pages,
            created_at: d.created_at,
            status: run?.status ?? (d.status as RunStatus),
            error: run?.error ?? null,
            n_dates: runDates.length,
            n_flags: run ? (flags.get(run.id)?.length ?? 0) : 0,
            n_needs_review: runDates.filter((x) => x.status === "needs_review").length,
          };
        });
    },

    async uploadDocument(file: File) {
      await ready;
      if (file.size > MAX_UPLOAD_MB * 1024 * 1024) throw new ApiError(413, `This file is larger than ${MAX_UPLOAD_MB} MB.`);
      let bytes: ArrayBuffer;
      try {
        bytes = await file.arrayBuffer();
      } catch {
        throw new ApiError(400, UNREADABLE);
      }
      const kind = fileKind(new Uint8Array(bytes.slice(0, 16)));
      if (kind === null) throw new ApiError(415, UNSUPPORTED);
      const hash = await sha256(bytes);
      let doc = [...documents.values()].find((d) => d.sha256 === hash);
      if (!doc) {
        doc = {
          id: nextId.documents++,
          filename: displayName(file.name),
          sha256: hash,
          pages: 0,
          status: "queued",
          created_at: now(),
          ai_model: null,
          pipeline_version: null,
        };
        documents.set(doc.id, doc);
        const stored = doc;
        await persist(() => storage.put("documents", stored));
      }
      const blob = new Blob([bytes], { type: file.type });
      if (!originals.has(doc.id)) {
        originals.set(doc.id, blob);
        await persist(() => storage.putBlob(`original:${doc.id}`, blob));
      }
      const latest = latestRun(doc.id);
      if (latest && (latest.status === "done" || running.has(latest.id))) {
        return { document_id: doc.id, run_id: latest.id, status: latest.status };
      }
      const carryFrom = latestDoneRun(doc.id)?.id ?? null;
      const run = await createRun(doc.id);
      start(run, blob, kind, carryFrom);
      return { document_id: doc.id, run_id: run.id, status: "queued" as const };
    },

    async getDocument(id: number): Promise<DocumentDetail> {
      await ready;
      const document = structuredClone(getDocumentRecord(id));
      const run = latestRun(id);
      if (run) await prepareImages(run.id);
      return {
        document,
        run: run ? { id: run.id, status: run.status, error: run.error, ai_used: false, ai_model: null } : null,
        pages: run ? pageInfo(run.id) : [],
      };
    },

    async getPages(runId: number): Promise<PageInfo[]> {
      await ready;
      getRun(runId);
      await prepareImages(runId);
      return pageInfo(runId);
    },

    pageImageUrl: (runId: number, n: number) => imageUrls.get(`${runId}:${n}`) ?? "",

    async getDates(runId: number): Promise<DateRecord[]> {
      await ready;
      getRun(runId);
      const corrected = (dates.get(runId) ?? []).some((d) => events.get(d.id)?.some((e) => e.new_type));
      if (corrected) await loadTaxonomy();
      return datesFor(runId);
    },

    async getFlags(runId: number): Promise<Flag[]> {
      await ready;
      getRun(runId);
      return (flags.get(runId) ?? []).map(({ run_id: _, ...f }) => structuredClone(f));
    },

    async getDiscarded(runId: number) {
      await ready;
      getRun(runId);
      return []; // only AI suggestions are discarded, and the static build has no AI
    },

    async reviewDate(id: number, body: ReviewBody): Promise<ReviewEvent> {
      await ready;
      return addReview(id, body);
    },

    async getHistory(id: number): Promise<ReviewEvent[]> {
      await ready;
      return structuredClone(events.get(id) ?? []);
    },

    async reprocess(id: number) {
      await ready;
      const doc = getDocumentRecord(id);
      const latest = latestRun(id);
      if (latest && running.has(latest.id)) return { run_id: latest.id };
      let blob = originals.get(id) ?? null;
      if (!blob) {
        try {
          blob = await storage.getBlob(`original:${id}`);
        } catch {
          blob = null;
        }
      }
      const carryFrom = latestDoneRun(id)?.id ?? null;
      const run = await createRun(doc.id);
      if (!blob) {
        await setRunStatus(run.id, "failed", UNREADABLE);
      } else {
        originals.set(id, blob);
        const kind = fileKind(new Uint8Array(await blob.slice(0, 16).arrayBuffer())) ?? "pdf";
        start(run, blob, kind, carryFrom);
      }
      return { run_id: run.id };
    },

    exportUrl,

    exportFilename(runId: number, fmt: ExportFormat): string {
      const run = runs.get(runId);
      const doc = run ? documents.get(run.document_id) : undefined;
      return exportFilename(doc?.filename ?? "document", runId, fmt);
    },

    async idle() {
      await ready;
      let current: Promise<void>;
      do {
        current = queue;
        await current;
      } while (current !== queue);
    },
  };
  return source;
}
