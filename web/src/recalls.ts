export const valueKinds = {
  date: 'Single date',
  ambiguous_date: 'Ambiguous date',
  cutoff: 'Expiry cutoff',
  non_date: 'Distribution statement',
  unparsed: 'Unsupported value',
};
export const statements = {
  not_yet_distributed: 'Not yet distributed',
  not_distributed: 'Not distributed',
  quarantined_at_wholesaler: 'Quarantined at wholesaler',
};
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
  value_kind: keyof typeof valueKinds;
  cutoff: { upper: string; inclusive: true; precision: 'month' | 'day' } | null;
  statement: keyof typeof statements | null;
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
    data.schemaVersion !== 2 ||
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
      row.candidates.some((candidate) => typeof candidate !== 'string') ||
      !Array.isArray(row.review_reasons) ||
      !validValue(row) ||
      (row.normalized !== null && !row.candidates.includes(row.normalized))
    ) {
      throw new Error('Public date evidence does not match its source table.');
    }
    ids.add(row.id);
  }
  return data;
}
function validValue(row: RecallRecord): boolean {
  if (row.value_kind === 'cutoff') {
    const bound = row.cutoff;
    return (
      row.role === 'expiry' &&
      row.normalized === null &&
      row.candidates.length === 0 &&
      row.statement === null &&
      !!bound &&
      bound.inclusive === true &&
      typeof bound.upper === 'string' &&
      ((bound.precision === 'month' && /^\d{4}-(0[1-9]|1[0-2])$/.test(bound.upper)) ||
        (bound.precision === 'day' &&
          /^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(bound.upper))) &&
      row.review_reasons.includes('inclusive_expiry_cutoff')
    );
  }
  if (row.cutoff !== null) return false;
  if (row.value_kind === 'non_date') {
    return (
      row.role === 'distribution' &&
      row.normalized === null &&
      !row.candidates.length &&
      row.statement !== null &&
      Object.hasOwn(statements, row.statement) &&
      row.raw_text.trim().replace(/\s+/g, ' ').toLowerCase() ===
        statements[row.statement].toLowerCase()
    );
  }
  if (row.statement !== null) return false;
  if (row.value_kind === 'date') return row.normalized !== null && row.candidates.length === 1;
  if (row.value_kind === 'ambiguous_date')
    return row.normalized === null && row.candidates.length > 1;
  return row.value_kind === 'unparsed' && row.normalized === null && row.candidates.length === 0;
}
export function cellInterpretation(row: RecallRecord): string {
  if (row.value_kind === 'cutoff' && row.cutoff) return `Up to ${row.cutoff.upper} (inclusive)`;
  if (row.value_kind === 'non_date' && row.statement)
    return `Source states: ${statements[row.statement]}`;
  if (row.value_kind === 'unparsed') return 'Unsupported value';
  return row.normalized ?? 'Ambiguous date';
}
export function filterRecalls(
  data: RecallData,
  query: string,
  role: string,
  split: string,
  unresolved: boolean,
  kind = '',
): RecallRecord[] {
  const term = query.trim().toLocaleLowerCase();
  return data.records.filter(
    (row) =>
      (!role || row.role === role) &&
      (!split || row.split === split) &&
      (!unresolved || row.normalized === null) &&
      (!kind || row.value_kind === kind) &&
      (!term || `${row.title} ${row.batch} ${row.raw_text}`.toLocaleLowerCase().includes(term)),
  );
}
