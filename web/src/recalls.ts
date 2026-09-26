export interface RecallDocument {
  id: string;
  title: string;
  url: string;
  split: string;
  source: { sha256: string };
  tables: Array<{ table_index: number; heading: string; headers: string[]; rows: string[][] }>;
}
export interface RecallRecord {
  id: string;
  document_id: string;
  title: string;
  url: string;
  source_sha256: string;
  split: string;
  table_index: number;
  row_index: number;
  column_index: number;
  batch_column_index: number;
  header: string;
  batch: string;
  raw_text: string;
  role: 'expiry' | 'distribution';
  normalized: string | null;
  candidates: string[];
  precision: string;
  review_reasons: string[];
  model_score: number;
  status: 'needs_review';
}
export interface RecallData {
  schemaVersion: number;
  attribution: string;
  licence: string;
  snapshotRetrievedAt: string;
  corpus: { documents: number; columns: number; document_splits: Record<string, number> };
  evaluation: Record<
    string,
    {
      model: { count: number; accuracy: number };
      keywords: { accuracy: number };
      seen_heading_count: number;
      abstention: { classified: number; total: number };
    }
  >;
  documents: RecallDocument[];
  records: RecallRecord[];
}
export function parseRecalls(value: unknown): RecallData {
  const data = value as RecallData;
  if (
    !data ||
    data.schemaVersion !== 1 ||
    !Array.isArray(data.documents) ||
    !Array.isArray(data.records)
  ) {
    throw new Error('Invalid public-notice snapshot.');
  }
  const docs = new Map(data.documents.map((doc) => [doc.id, doc]));
  const ids = new Set<string>();
  if (docs.size !== data.documents.length) throw new Error('Duplicate public source identity.');
  for (const doc of data.documents) {
    const url = new URL(doc.url);
    if (url.origin !== 'https://www.gov.uk' || !url.pathname.startsWith('/drug-device-alerts/')) {
      throw new Error('Unexpected public source URL.');
    }
  }
  for (const row of data.records) {
    const doc = docs.get(row.document_id);
    const table = doc?.tables.find((table) => table.table_index === row.table_index);
    if (
      !doc ||
      !table ||
      ids.has(row.id) ||
      row.url !== doc.url ||
      row.source_sha256 !== doc.source.sha256 ||
      row.split !== doc.split ||
      !Number.isInteger(row.row_index) ||
      !Number.isInteger(row.column_index) ||
      row.row_index < 0 ||
      row.column_index < 0 ||
      table.rows[row.row_index]?.[row.column_index] !== row.raw_text ||
      table.headers[row.column_index] !== row.header ||
      !Number.isInteger(row.batch_column_index) ||
      row.batch_column_index < 0 ||
      table.rows[row.row_index]?.[row.batch_column_index] !== row.batch ||
      !['expiry', 'distribution'].includes(row.role) ||
      row.status !== 'needs_review' ||
      !Array.isArray(row.candidates) ||
      (row.normalized !== null && !row.candidates.includes(row.normalized))
    ) {
      throw new Error('Public date evidence does not match its source table.');
    }
    ids.add(row.id);
  }
  return data;
}
export function filterRecalls(
  data: RecallData,
  query: string,
  role: string,
  split: string,
  unresolved: boolean,
): RecallRecord[] {
  const term = query.trim().toLocaleLowerCase();
  return data.records.filter(
    (row) =>
      (!role || row.role === role) &&
      (!split || row.split === split) &&
      (!unresolved || row.normalized === null) &&
      (!term || `${row.title} ${row.batch} ${row.raw_text}`.toLocaleLowerCase().includes(term)),
  );
}
