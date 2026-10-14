import type { RecallData, RecallDocument, RecallRecord } from './recalls.ts';

/** Lexical retrieval only. Scores rank source rows; they are not probabilities. */
export const retrievalMethod = { name: 'BM25', version: 1, k1: 1.2, b: 0.75 } as const;
const stopWords = new Set(
  'a an the and or of to in on at for from with is are was were what which when how can could please show find me tell about batch batches number numbers'.split(
    ' ',
  ),
);
export function tokens(text: string): string[] {
  return (
    text
      .normalize('NFKC')
      .toLowerCase()
      .match(/[\p{L}\p{N}]+(?:[-/][\p{L}\p{N}]+)*/gu) ?? []
  ).filter((term) => !stopWords.has(term));
}
const batchKey = (text: string) => text.normalize('NFKC').trim().toLowerCase().replace(/\s+/g, ' ');
export interface EvidenceRow {
  id: string;
  document: RecallDocument;
  tableIndex: number;
  rowIndex: number;
  batch: string;
  fields: RecallRecord[];
  cells: Array<{ header: string; value: string }>;
}
interface IndexedRow {
  evidence: EvidenceRow;
  frequencies: Map<string, number>;
  length: number;
}
export interface EvidenceIndex {
  rows: IndexedRow[];
  documentFrequency: Map<string, number>;
  averageLength: number;
  batches: Set<string>;
}
export interface SearchFilters {
  split: string;
  kind: string;
}
export interface SearchHit {
  evidence: EvidenceRow;
  score: number;
  matchedTerms: string[];
}
export interface SearchResult {
  query: string;
  terms: string[];
  requiredBatches: string[];
  hits: SearchHit[];
  reason: 'empty' | 'unknown_batch' | 'no_match' | 'matched';
}
export function buildEvidenceIndex(data: RecallData): EvidenceIndex {
  const docs = new Map(data.documents.map((doc) => [doc.id, doc]));
  const grouped = new Map<string, EvidenceRow>();
  for (const field of data.records) {
    const id = `${field.document_id}:${field.table_index}:${field.row_index}`;
    const existing = grouped.get(id);
    if (existing) {
      existing.fields.push(field);
      continue;
    }
    const document = docs.get(field.document_id)!;
    const table = document.tables.find((table) => table.table_index === field.table_index)!;
    grouped.set(id, {
      id,
      document,
      tableIndex: field.table_index,
      rowIndex: field.row_index,
      batch: field.batch,
      fields: [field],
      cells: table.headers.map((header, index) => ({
        header,
        value: table.rows[field.row_index][index] ?? '',
      })),
    });
  }
  const documentFrequency = new Map<string, number>();
  const rows = [...grouped.values()].map((evidence) => {
    const frequencies = new Map<string, number>();
    const table = evidence.document.tables.find(
      (table) => table.table_index === evidence.tableIndex,
    )!;
    const text = [
      evidence.document.title,
      table.heading,
      evidence.batch,
      ...evidence.cells.flatMap(({ header, value }) => [header, value]),
      ...evidence.fields.flatMap((field) => [
        field.role,
        field.normalized ?? '',
        ...field.candidates,
        field.role === 'expiry' ? 'expiry expiration' : 'distribution distributed',
        field.value_kind.replaceAll('_', ' '),
      ]),
    ].join(' ');
    const terms = tokens(text);
    for (const term of terms) frequencies.set(term, (frequencies.get(term) ?? 0) + 1);
    for (const term of frequencies.keys())
      documentFrequency.set(term, (documentFrequency.get(term) ?? 0) + 1);
    return { evidence, frequencies, length: terms.length };
  });
  return {
    rows,
    documentFrequency,
    averageLength: rows.reduce((n, row) => n + row.length, 0) / Math.max(1, rows.length),
    batches: new Set(rows.map((row) => batchKey(row.evidence.batch))),
  };
}
/** Exact identifiers are never fuzzed. Every non-stop query term must occur. */
export function searchEvidence(
  index: EvidenceIndex,
  query: string,
  filters: SearchFilters = { split: '', kind: '' },
): SearchResult {
  const terms = [...new Set(tokens(query))];
  const explicit = [
    ...query.matchAll(
      /\bbatch(?:\s+(?:no\.?|number))?\s*[:#]?\s+([\p{L}\p{N}]+(?:[-/][\p{L}\p{N}]+)*)/giu,
    ),
  ].map((match) => batchKey(match[1]));
  const identifiers = terms.filter(
    (term) =>
      index.batches.has(term) ||
      (/\d/.test(term) &&
        /\p{L}/u.test(term) &&
        !/^\d+(?:mg|ml|mcg|g|l|iu|micrograms?)$/i.test(term)) ||
      /^\d{5,}$/.test(term),
  );
  const requiredBatches = [...new Set([...explicit, ...identifiers])];
  const result: SearchResult = {
    query: query.trim(),
    terms,
    requiredBatches,
    hits: [],
    reason: 'empty',
  };
  if (!terms.length) return result;
  if (requiredBatches.some((batch) => !index.batches.has(batch)))
    return { ...result, reason: 'unknown_batch' };
  const { k1, b } = retrievalMethod;
  for (const row of index.rows) {
    if (filters.split && row.evidence.document.split !== filters.split) continue;
    if (filters.kind && !row.evidence.fields.some((field) => field.value_kind === filters.kind))
      continue;
    if (requiredBatches.some((batch) => batchKey(row.evidence.batch) !== batch)) continue;
    if (!terms.every((term) => row.frequencies.has(term))) continue;
    const score = terms.reduce((sum, term) => {
      const df = index.documentFrequency.get(term) ?? 0;
      const frequency = row.frequencies.get(term) ?? 0;
      const idf = Math.log(1 + (index.rows.length - df + 0.5) / (df + 0.5));
      return (
        sum +
        (idf * frequency * (k1 + 1)) /
          (frequency + k1 * (1 - b + (b * row.length) / index.averageLength))
      );
    }, 0);
    result.hits.push({ evidence: row.evidence, score, matchedTerms: terms });
  }
  result.hits.sort((a, b) => b.score - a.score || a.evidence.id.localeCompare(b.evidence.id));
  result.reason = result.hits.length ? 'matched' : 'no_match';
  return result;
}
export function evidenceExport(data: RecallData, result: SearchResult, filters: SearchFilters) {
  return {
    schemaVersion: 1,
    query: result.query,
    filters: { ...filters },
    method: retrievalMethod,
    matching: 'All non-stop query terms required; exact batch identifiers only',
    scoreMeaning: 'Lexical ranking score, not confidence or clinical validity',
    scope: 'Frozen English MHRA research corpus; not current recall advice; no generated answer',
    snapshotRetrievedAt: data.snapshotRetrievedAt,
    attribution: data.attribution,
    licence: data.licence,
    resultCount: result.hits.length,
    reason: result.reason,
    results: result.hits.map(({ evidence, score, matchedTerms }, rank) => ({
      rank: rank + 1,
      score,
      matchedTerms,
      id: evidence.id,
      batch: evidence.batch,
      citation: {
        documentId: evidence.document.id,
        title: evidence.document.title,
        url: evidence.document.url,
        sourceSha256: evidence.document.source.sha256,
        tableIndex: evidence.tableIndex,
        rowIndex: evidence.rowIndex,
        indexBase: 0,
      },
      cells: evidence.cells,
      fields: evidence.fields,
    })),
  };
}
