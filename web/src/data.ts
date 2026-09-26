export type Decision = 'accepted' | 'rejected' | 'needs_review';
export type View = 'recalls' | 'workspace' | 'register' | 'benchmarks' | 'history';
export interface Field {
  id: string;
  raw_text: string;
  normalized: string | null;
  label: string;
  candidates: string[];
  precision: string;
  review_reasons: string[];
  context: string;
  start: number;
  end: number;
  confidence: number;
  line: number;
  box: [number, number, number, number];
  source_sha256: string;
}
export interface Document {
  id: string;
  filename: string;
  title: string;
  vendor: string;
  language: string;
  text: string;
  sha256: string;
  image: string;
  imageSha256: string;
  page: { width: number; height: number };
  fields: Field[];
}
export interface Case {
  id: string;
  language: string;
  text: string;
  date_order: string;
  expected: Array<{
    normalized: string | null;
    label: string;
    candidates: string[];
    review_reasons: string[];
  }>;
}
export interface Benchmark {
  passed: number;
  total: number;
  by_language: Record<string, { passed: number; total: number }>;
  failures: unknown[];
}
export interface Workspace {
  schemaVersion: number;
  extractorVersion: string;
  scope: string;
  documents: Document[];
  benchmark: { sha256: string; results: Record<string, Benchmark> };
  cases: Case[];
  fieldVocabulary: Record<string, Record<string, string[]>>;
  sourceSha256: Record<string, string>;
}
export interface ReviewEvent {
  id: string;
  fieldId: string;
  documentId: string;
  sourceSha256: string;
  extractorVersion: string;
  decision: Decision;
  resolved: string | null;
  reviewer: string;
  reason: string;
  createdAt: string;
}

export const languages: Record<string, string> = {
  en: 'English',
  fr: 'French',
  de: 'German',
  es: 'Spanish',
  vi: 'Vietnamese',
};
export const labels: Record<string, string> = {
  expiry: 'Expiry',
  manufacture: 'Manufacture',
  qa_check: 'Quality check',
  audit: 'Audit',
  received: 'Received',
  document: 'Document date',
  unknown: 'Unclassified',
};
export function fold(text: string): string {
  return text.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '').replace(/đ/g, 'd');
}
export function sourceSlice(doc: Document, field: Field): string {
  return Array.from(doc.text).slice(field.start, field.end).join('');
}
export function parseWorkspace(value: unknown): Workspace {
  const data = value as Workspace;
  if (
    !data ||
    data.schemaVersion !== 1 ||
    !Array.isArray(data.documents) ||
    !data.documents.length ||
    typeof data.extractorVersion !== 'string' ||
    !data.benchmark?.results ||
    !Array.isArray(data.cases) ||
    !data.fieldVocabulary
  )
    throw new Error('Unsupported workspace snapshot.');
  const ids = new Set<string>();
  const fieldIds = new Set<string>();
  for (const doc of data.documents) {
    if (
      !doc ||
      typeof doc.id !== 'string' ||
      ids.has(doc.id) ||
      typeof doc.text !== 'string' ||
      typeof doc.title !== 'string' ||
      typeof doc.vendor !== 'string' ||
      !/^[a-f0-9]{64}$/.test(doc.sha256) ||
      !/^[a-f0-9]{64}$/.test(doc.imageSha256) ||
      !/^documents\/[a-z0-9_-]+\.png$/.test(doc.image) ||
      !languages[doc.language] ||
      !Array.isArray(doc.fields) ||
      !doc.page ||
      doc.page.width <= 0 ||
      doc.page.height <= 0
    ) {
      throw new Error('Invalid document evidence.');
    }
    ids.add(doc.id);
    for (const field of doc.fields) {
      if (
        fieldIds.has(field.id) ||
        !Number.isInteger(field.start) ||
        !Number.isInteger(field.end) ||
        field.start < 0 ||
        field.end <= field.start ||
        field.end > Array.from(doc.text).length ||
        sourceSlice(doc, field) !== field.raw_text ||
        !labels[field.label] ||
        !Array.isArray(field.candidates) ||
        !field.candidates.length ||
        field.candidates.some((c) => typeof c !== 'string') ||
        (field.normalized !== null && !field.candidates.includes(field.normalized)) ||
        !Array.isArray(field.review_reasons) ||
        field.source_sha256 !== doc.sha256 ||
        !Array.isArray(field.box) ||
        field.box.length !== 4 ||
        field.box.some((n) => !Number.isFinite(n) || n < 0 || n > 1)
      ) {
        throw new Error('A date field does not match its source evidence.');
      }
      fieldIds.add(field.id);
    }
  }
  return data;
}
export function latestEvent(
  events: ReviewEvent[],
  doc: Document,
  field: Field,
  version: string,
): ReviewEvent | undefined {
  return events.findLast(
    (event) =>
      event.fieldId === field.id &&
      event.sourceSha256 === doc.sha256 &&
      event.extractorVersion === version,
  );
}
export function validateEvent(value: unknown, data: Workspace): value is ReviewEvent {
  if (!value || typeof value !== 'object') return false;
  const event = value as ReviewEvent;
  const doc = data.documents.find((d) => d.id === event.documentId);
  const field = doc?.fields.find((f) => f.id === event.fieldId);
  return !!(
    doc &&
    field &&
    event.sourceSha256 === doc.sha256 &&
    event.extractorVersion === data.extractorVersion &&
    ['accepted', 'rejected', 'needs_review'].includes(event.decision) &&
    typeof event.reviewer === 'string' &&
    event.reviewer.trim() &&
    event.reviewer.length <= 80 &&
    typeof event.reason === 'string' &&
    event.reason.trim() &&
    event.reason.length <= 600 &&
    typeof event.id === 'string' &&
    typeof event.createdAt === 'string' &&
    Number.isFinite(Date.parse(event.createdAt)) &&
    (event.resolved === null || field.candidates.includes(event.resolved)) &&
    (event.decision !== 'accepted' || event.resolved !== null)
  );
}
export function makeEvent(
  data: Workspace,
  doc: Document,
  field: Field,
  decision: Decision,
  resolved: string | null,
  reviewer: string,
  reason: string,
): ReviewEvent {
  const event: ReviewEvent = {
    id: crypto.randomUUID(),
    fieldId: field.id,
    documentId: doc.id,
    sourceSha256: doc.sha256,
    extractorVersion: data.extractorVersion,
    decision,
    resolved,
    reviewer: reviewer.trim(),
    reason: reason.trim(),
    createdAt: new Date().toISOString(),
  };
  if (!validateEvent(event, data))
    throw new Error('Choose a valid date and enter a reviewer and reason.');
  return event;
}
export function matches(data: Workspace, doc: Document, field: Field, query: string): boolean {
  const terms = fold(query).trim().split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const aliases = Object.values(data.fieldVocabulary).flatMap((v) => v[field.label] ?? []);
  const haystack = fold(
    [
      doc.title,
      doc.vendor,
      doc.filename,
      field.raw_text,
      field.normalized ?? '',
      field.context,
      ...aliases,
    ].join(' '),
  );
  return terms.every((term) => haystack.includes(term));
}
export function filteredFields(
  data: Workspace,
  events: ReviewEvent[],
  filters: { language: string; label: string; status: string; query: string },
): Array<{ doc: Document; field: Field; event?: ReviewEvent }> {
  return data.documents
    .flatMap((doc) =>
      doc.fields.map((field) => ({
        doc,
        field,
        event: latestEvent(events, doc, field, data.extractorVersion),
      })),
    )
    .filter(
      ({ doc, field, event }) =>
        (!filters.language || doc.language === filters.language) &&
        (!filters.label || field.label === filters.label) &&
        (!filters.status ||
          (filters.status === 'flagged'
            ? field.review_reasons.length > 0
            : (event?.decision ?? 'pending') === filters.status)) &&
        matches(data, doc, field, filters.query),
    );
}
export function csvText(rows: Record<string, unknown>[]): string {
  if (!rows.length) return 'document,date,type,status,source\n';
  const keys = Object.keys(rows[0]);
  const cell = (value: unknown) => {
    let text = String(value ?? '');
    if (/^[\s]*[=+\-@]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  };
  return [
    keys.map(cell).join(','),
    ...rows.map((row) => keys.map((key) => cell(row[key])).join(',')),
  ].join('\r\n');
}
