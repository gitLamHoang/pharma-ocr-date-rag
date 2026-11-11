import "fake-indexeddb/auto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TAXONOMY } from "../../test-fixtures";
import { httpDataSource } from "../client";
import type { DataSource } from "../dataSource";
import { EngineError, type CoreDate, type CoreFlag, type Engine } from "../../engine/types";
import type { PageLayout } from "../../engine/layout";
import { createStaticDataSource, type StaticDataSource } from "./staticDataSource";
import { memoryStorage, openStorage } from "./storage";

const PDF_BYTES = "%PDF-1.4\nnative";
const PNG_BYTES = "\x89PNG\r\n\x1a\nscan";

function file(content: string, name = "coa.pdf"): File {
  return new File([Uint8Array.from(content, (c) => c.charCodeAt(0))], name);
}

function layout(n: number, text: string): PageLayout {
  return { n, width: 1700, height: 2200, text, text_source: "pdf", words: [], transcription: null };
}

function coreDate(overrides: Partial<CoreDate> = {}): CoreDate {
  return {
    id: "p1-c1",
    page: 1,
    raw_text: "31/03/2027",
    normalized: "2027-03-31",
    candidates: ["2027-03-31"],
    precision: "day",
    char_start: 13,
    char_end: 23,
    bbox: { x0: 10, y0: 20, x1: 110, y1: 40 },
    line_boxes: [],
    context: "Expiry date: 31/03/2027",
    rule_label: "expiry",
    source: "rules",
    date_type: "expiry_date",
    family: "product",
    qualifier: null,
    resolved_value: null,
    evidence: null,
    confidence: 0.5,
    rationale: "Rule-based label from nearby words (no AI label for this date).",
    ...overrides,
  };
}

/** Reads one page and finds the dates `dates()` returns; counts its calls. */
function fakeEngine(dates: () => CoreDate[] = () => [coreDate()], flags: () => CoreFlag[] = () => []) {
  const engine = {
    reads: 0,
    analyses: [] as PageLayout[][],
    readError: null as Error | null,
    async read(_file: Blob, kind: "pdf" | "image") {
      engine.reads += 1;
      if (engine.readError) throw engine.readError;
      return [
        {
          layout: { ...layout(1, "Expiry date: 31/03/2027"), text_source: kind === "pdf" ? "pdf" : "ocr" } as PageLayout,
          image: new Blob(["png"], { type: "image/png" }),
        },
      ];
    },
    async analyze(layouts: PageLayout[], today: string) {
      expect(today).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      engine.analyses.push(layouts);
      return { dates: dates(), flags: flags() };
    },
    async taxonomy() {
      return TAXONOMY;
    },
  };
  return engine satisfies Engine;
}

const urls: Blob[] = [];
beforeEach(() => {
  urls.length = 0;
  vi.stubGlobal("URL", Object.assign(Object.create(URL), URL, {
    createObjectURL: (blob: Blob) => {
      urls.push(blob);
      return `blob:test/${urls.length}`;
    },
    revokeObjectURL: () => {},
  }));
});
afterEach(() => vi.unstubAllGlobals());

async function uploaded(source: StaticDataSource, f = file(PDF_BYTES)) {
  const result = await source.uploadDocument(f);
  await source.idle();
  return result;
}

const REVIEW = { reviewer: "Ada", reason: "Matches the page" } as const;

describe("StaticDataSource", () => {
  it("implements every DataSource method, and nothing that edits or deletes", () => {
    const source = createStaticDataSource({ storage: memoryStorage(), engine: fakeEngine() });
    const required = Object.keys(httpDataSource) as (keyof DataSource)[];
    for (const name of required) expect(typeof source[name], name).toBe("function");
    const extra = Object.keys(source).filter((k) => !required.includes(k as keyof DataSource));
    expect(extra.sort()).toEqual(["exportFilename", "idle"]);
    expect(Object.keys(source).some((k) => /delete|remove|update|edit|clear/i.test(k))).toBe(false);
  });

  it("reports a rules-only engine in the browser", async () => {
    const source = createStaticDataSource({ storage: memoryStorage(), engine: fakeEngine() });
    expect(await source.getHealth()).toEqual({
      ai_enabled: false,
      provider: "browser",
      model: null,
      tesseract_langs_missing: [],
    });
    expect(await source.getTaxonomy()).toEqual(TAXONOMY);
  });

  it("processes an upload in the browser: run done, pages, dates with boxes, counts", async () => {
    const engine = fakeEngine();
    const source = createStaticDataSource({ storage: memoryStorage(), engine });
    const result = await source.uploadDocument(file(PDF_BYTES));
    expect(result).toEqual({ document_id: 1, run_id: 1, status: "queued" });
    await source.idle();

    const [summary] = await source.listDocuments();
    expect(summary).toMatchObject({ id: 1, name: "coa.pdf", pages: 1, status: "done", error: null });
    expect(summary).toMatchObject({ n_dates: 1, n_flags: 0, n_needs_review: 1 });

    const detail = await source.getDocument(1);
    expect(source.pageImageUrl(1, 1)).toMatch(/^blob:/); // the Review screen reads pages from the detail
    expect(detail.run).toEqual({ id: 1, status: "done", error: null, ai_used: false, ai_model: null });
    expect(detail.pages).toEqual([{ n: 1, width: 1700, height: 2200 }]);
    expect(detail.document).toMatchObject({ filename: "coa.pdf", pages: 1, status: "done", ai_model: null });
    expect(detail.document.sha256).toMatch(/^[0-9a-f]{64}$/);

    expect(await source.getPages(1)).toEqual([{ n: 1, width: 1700, height: 2200 }]);
    expect(source.pageImageUrl(1, 1)).toMatch(/^blob:/);
    const [date] = await source.getDates(1);
    expect(date).toMatchObject({
      id: 1,
      candidate_id: "p1-c1",
      run_id: 1,
      document_id: 1,
      bbox: { x0: 10, y0: 20, x1: 110, y1: 40 },
      status: "needs_review",
      current_type: "expiry_date",
      current_family: "product",
      current_value: "2027-03-31",
      carried_from_run: null,
    });
    expect(await source.getFlags(1)).toEqual([]);
    expect(await source.getDiscarded(1)).toEqual([]);
  });

  it("maps flags' candidate ids to date ids", async () => {
    const engine = fakeEngine(
      () => [coreDate(), coreDate({ id: "p1-c2", char_start: 30, char_end: 40 })],
      () => [{ rule: "R1", severity: "error", message: "Expired", date_ids: ["p1-c2"] }],
    );
    const source = createStaticDataSource({ storage: memoryStorage(), engine });
    await uploaded(source);
    expect(await source.getFlags(1)).toEqual([{ id: 1, rule: "R1", severity: "error", message: "Expired", date_ids: [2] }]);
  });

  it("fails the run with the reader's message for an unreadable file", async () => {
    const engine = fakeEngine();
    engine.readError = new EngineError("This PDF is password-protected. Remove the password and upload it again.");
    const source = createStaticDataSource({ storage: memoryStorage(), engine });
    await uploaded(source);
    const [summary] = await source.listDocuments();
    expect(summary).toMatchObject({ status: "failed", error: "This PDF is password-protected. Remove the password and upload it again." });

    engine.readError = new TypeError("secret page text in a stack");
    await uploaded(source, file(PDF_BYTES + "2", "other.pdf"));
    expect((await source.listDocuments())[0]).toMatchObject({ name: "other.pdf", status: "failed", error: "Processing error" });
  });

  it("refuses an unsupported type and a file over 50 MB before reading it", async () => {
    const engine = fakeEngine();
    const source = createStaticDataSource({ storage: memoryStorage(), engine });
    await expect(source.uploadDocument(file("hello", "notes.txt"))).rejects.toMatchObject({
      status: 415,
      message: "This file type is not supported. Upload a PDF, PNG, JPG or TIFF file.",
    });
    const big = file(PDF_BYTES);
    Object.defineProperty(big, "size", { value: 50 * 1024 * 1024 + 1 });
    await expect(source.uploadDocument(big)).rejects.toMatchObject({ status: 413, message: "This file is larger than 50 MB." });
    expect(engine.reads).toBe(0);
    expect(await source.listDocuments()).toEqual([]);
  });

  it("reads a scanned image through the OCR path", async () => {
    const engine = fakeEngine();
    const source = createStaticDataSource({ storage: memoryStorage(), engine });
    await uploaded(source, file(PNG_BYTES, "scan.png"));
    expect(engine.analyses[0][0].text_source).toBe("ocr");
  });

  it("returns the existing run for an identical re-upload", async () => {
    const engine = fakeEngine();
    const source = createStaticDataSource({ storage: memoryStorage(), engine });
    await uploaded(source);
    expect(await uploaded(source, file(PDF_BYTES, "copy.pdf"))).toEqual({ document_id: 1, run_id: 1, status: "done" });
    expect(engine.reads).toBe(1);
  });

  it("validates reviews with the server's rules and messages", async () => {
    const source = createStaticDataSource({ storage: memoryStorage(), engine: fakeEngine() });
    await uploaded(source);
    const cases: [object, number, string][] = [
      [{ action: "accept", reviewer: " ", reason: "x" }, 422, "a reviewer name is required"],
      [{ action: "accept", reviewer: "Ada", reason: "" }, 422, "a reason is required"],
      [{ action: "approve", ...REVIEW }, 422, "unknown review action 'approve'"],
      [{ action: "correct", ...REVIEW }, 422, "a correction needs a new type or a new value"],
      [{ action: "accept", ...REVIEW, new_type: "expiry_date" }, 422, "only a correction can change the type or value"],
      [{ action: "correct", ...REVIEW, new_type: "nope" }, 422, "date type 'nope' is not in the taxonomy"],
      [
        { action: "correct", ...REVIEW, new_value: "2027-02-30" },
        422,
        "a value must be a date written YYYY-MM-DD, or YYYY-MM for month precision",
      ],
    ];
    for (const [body, status, message] of cases) {
      await expect(source.reviewDate(1, body as never)).rejects.toMatchObject({ status, message });
    }
    await expect(source.reviewDate(99, { action: "accept", ...REVIEW })).rejects.toMatchObject({
      status: 404,
      message: "Date 99 not found.",
    });
    expect(await source.getHistory(1)).toEqual([]);
  });

  it("refuses a day for a month-only date", async () => {
    const engine = fakeEngine(() => [coreDate({ raw_text: "03/2027", normalized: "2027-03", precision: "month" })]);
    const source = createStaticDataSource({ storage: memoryStorage(), engine });
    await uploaded(source);
    await expect(source.reviewDate(1, { action: "correct", ...REVIEW, new_value: "2027-03-31" })).rejects.toMatchObject({
      status: 422,
      message: "the page gives a month only; write the value as YYYY-MM, never with a day",
    });
  });

  it("appends review events; history and status follow them and cannot be edited through the API", async () => {
    const source = createStaticDataSource({ storage: memoryStorage(), engine: fakeEngine() });
    await uploaded(source);
    const accepted = await source.reviewDate(1, { action: "accept", ...REVIEW });
    expect(accepted).toMatchObject({ id: 1, date_id: 1, action: "accept", reviewer: "Ada", carried_from_run: null });
    expect(accepted.at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$/);
    await source.reviewDate(1, { action: "correct", reviewer: "Ada", reason: "Typo", new_type: "manufacture_date" });

    const history = await source.getHistory(1);
    expect(history.map((e) => e.action)).toEqual(["accept", "correct"]);
    history[0].action = "reject";
    history.pop();
    expect((await source.getHistory(1)).map((e) => e.action)).toEqual(["accept", "correct"]);

    const [date] = await source.getDates(1);
    expect(date).toMatchObject({ status: "corrected", current_type: "manufacture_date", date_type: "expiry_date" });
    expect((await source.listDocuments())[0].n_needs_review).toBe(0);
  });

  it("reprocesses locally, freezes the old run and carries exact matches over", async () => {
    let second = false;
    const engine = fakeEngine(() =>
      second ? [coreDate(), coreDate({ id: "p1-c2", raw_text: "01/01/2026", normalized: "2026-01-01" })] : [coreDate()],
    );
    const source = createStaticDataSource({ storage: memoryStorage(), engine });
    await uploaded(source);
    await source.reviewDate(1, { action: "accept", ...REVIEW });
    second = true;
    expect(await source.reprocess(1)).toEqual({ run_id: 2 });
    await source.idle();

    expect(engine.reads).toBe(2);
    const dates = await source.getDates(2);
    expect(dates.map((d) => [d.id, d.status, d.carried_from_run])).toEqual([
      [2, "accepted", 1],
      [3, "needs_review", null],
    ]);
    expect((await source.getHistory(2))[0]).toMatchObject({ reason: "carried over from run 1", carried_from_run: 1 });
    await expect(source.reviewDate(1, { action: "reject", ...REVIEW })).rejects.toMatchObject({
      status: 409,
      message: "run 1 is frozen; review the document's latest run 2",
    });
    await expect(source.reprocess(42)).rejects.toMatchObject({ status: 404, message: "Document 42 not found." });
  });

  it("exports CSV and JSON in the browser, with review decisions", async () => {
    const source = createStaticDataSource({ storage: memoryStorage(), engine: fakeEngine() });
    await uploaded(source);
    await source.reviewDate(1, { action: "accept", reviewer: "Ada", reason: "=SUM(A1)" });

    expect(source.exportUrl(1, "csv")).toMatch(/^blob:/);
    const csv = await urls.at(-1)!.text();
    const [header, row] = csv.replace(/^﻿/, "").trim().split("\r\n");
    expect(header.split(",").slice(0, 6)).toEqual(["document", "run_id", "date_id", "page", "raw_text", "status"]);
    expect(row).toContain(",accepted,");
    expect(row).toContain(",'=SUM(A1),"); // a reason is never run as a formula
    expect(source.exportFilename(1, "csv")).toBe("coa-run-1.csv");

    source.exportUrl(1, "json");
    const body = JSON.parse(await urls.at(-1)!.text());
    expect(body.document.filename).toBe("coa.pdf");
    expect(body.dates[0].history[0].action).toBe("accept");
    expect(body.flags).toEqual([]);
  });

  it("works in memory when IndexedDB is unavailable", async () => {
    const storage = await openStorage("blocked", null);
    expect(storage.persistent).toBe(false);
    const throwing = { open: () => { throw new DOMException("blocked", "SecurityError"); } } as unknown as IDBFactory;
    expect((await openStorage("blocked", throwing)).persistent).toBe(false);

    const source = createStaticDataSource({ storage, engine: fakeEngine() });
    await uploaded(source);
    await source.reviewDate(1, { action: "accept", ...REVIEW });
    expect((await source.getDates(1))[0].status).toBe("accepted");
  });

  it("keeps documents, dates and decisions in IndexedDB across page loads", async () => {
    const name = `test-${Math.random()}`;
    const first = createStaticDataSource({ storage: openStorage(name), engine: fakeEngine() });
    await uploaded(first);
    await first.reviewDate(1, { action: "accept", ...REVIEW });

    const storage = await openStorage(name);
    expect(storage.persistent).toBe(true);
    const engine = fakeEngine();
    const reloaded = createStaticDataSource({ storage, engine });
    expect((await reloaded.listDocuments())[0]).toMatchObject({ name: "coa.pdf", status: "done", n_needs_review: 0 });
    expect(reloaded.pageImageUrl(1, 1)).toBe("");
    await reloaded.getDocument(1);
    expect(reloaded.pageImageUrl(1, 1)).toMatch(/^blob:/);
    expect((await reloaded.getDates(1))[0].status).toBe("accepted");
    expect(await reloaded.getPages(1)).toHaveLength(1);
    expect(reloaded.pageImageUrl(1, 1)).toMatch(/^blob:/);
    expect(await reloaded.reprocess(1)).toEqual({ run_id: 2 });
    await reloaded.idle();
    expect(engine.reads).toBe(1); // reread from the stored original
    expect((await reloaded.getDates(2))[0].status).toBe("accepted");
  });

  it("refuses to overwrite a stored review event", async () => {
    const storage = await openStorage(`test-${Math.random()}`);
    const event = { id: 1, date_id: 1, action: "accept" };
    await storage.append("events", event);
    await expect(storage.append("events", { ...event, action: "reject" })).rejects.toThrow();
    expect((await storage.load()).events).toEqual([event]);

    const memory = memoryStorage();
    await memory.append("events", event);
    await expect(memory.append("events", { ...event, action: "reject" })).rejects.toThrow();
  });

  it("marks a run a closed tab left unfinished as failed", async () => {
    const storage = memoryStorage();
    await storage.put("documents", { id: 1, filename: "a.pdf", sha256: "x", pages: 0, status: "reading", created_at: "2026-11-11T00:00:00+00:00", ai_model: null, pipeline_version: "1.0.0" });
    await storage.put("runs", { id: 1, document_id: 1, status: "reading", error: null });
    const source = createStaticDataSource({ storage, engine: fakeEngine() });
    expect((await source.listDocuments())[0]).toMatchObject({
      status: "failed",
      error: "Processing was interrupted. Reprocess the document.",
    });
  });
});
