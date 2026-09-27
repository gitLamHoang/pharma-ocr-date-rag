import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { parseRecalls, filterRecalls, cellInterpretation } from './recalls.ts';

const load = () =>
  JSON.parse(readFileSync(new URL('../public/data/recalls.json', import.meta.url), 'utf8'));
test('public records retain original table cells, batches and source URLs', () => {
  const data = parseRecalls(load());
  assert.equal(data.documents.length, 60);
  assert.equal(data.records.length, 742);
  const matches = filterRecalls(data, '0162858', 'expiry', 'test', false);
  assert.equal(matches.length, 1);
  assert.equal(matches[0].normalized, '2028-05');
});
test('public evidence rejects altered cells, URLs and duplicate field IDs', () => {
  for (const kind of ['cell', 'url', 'duplicate', 'batch']) {
    const data = load();
    if (kind === 'cell') data.records[0].raw_text = 'invented';
    if (kind === 'url') data.documents[0].url = 'javascript:alert(1)';
    if (kind === 'duplicate') data.records.push(data.records[0]);
    if (kind === 'batch') data.records[0].batch_column_index = data.records[0].column_index;
    assert.throws(() => parseRecalls(data));
  }
});
test('unresolved and split filters never manufacture a resolved date', () => {
  const data = parseRecalls(load());
  const rows = filterRecalls(data, '', '', 'test', true);
  assert.ok(rows.length);
  assert.ok(rows.every((row) => row.normalized === null && row.split === 'test'));
  assert.equal(filterRecalls(data, 'no-such-source-ever', '', '', false).length, 0);
});

test('cutoffs and distribution statements remain distinct from normalized dates', () => {
  const data = parseRecalls(load());
  const cutoffs = filterRecalls(data, '', '', '', true, 'cutoff');
  const statements = filterRecalls(data, '', '', '', true, 'non_date');
  assert.equal(cutoffs.length, 3);
  assert.equal(statements.length, 39);
  assert.equal(filterRecalls(data, '', '', '', true, 'unparsed').length, 38);
  assert.equal(cellInterpretation(cutoffs[0]), 'Up to 2029-05 (inclusive)');
  assert.equal(cellInterpretation(statements[0]), 'Source states: Not yet distributed');
  assert.ok(
    [...cutoffs, ...statements].every((row) => row.normalized === null && !row.candidates.length),
  );
  assert.equal(filterRecalls(data, '', 'expiry', 'test', false, 'cutoff').length, 1);
});

test('invalid semantic combinations and legacy snapshots fail closed', () => {
  for (const kind of [
    'normalized',
    'candidates',
    'inclusive',
    'precision',
    'missing',
    'statement',
    'unknown',
    'legacy',
  ]) {
    const data = load();
    const row = data.records.find((row: { value_kind: string }) => row.value_kind === 'cutoff');
    if (kind === 'normalized') {
      row.normalized = row.cutoff.upper;
      row.candidates = [row.normalized];
    }
    if (kind === 'candidates') row.candidates = [row.cutoff.upper];
    if (kind === 'inclusive') row.cutoff.inclusive = false;
    if (kind === 'precision') row.cutoff.precision = 'day';
    if (kind === 'missing') row.cutoff = null;
    if (kind === 'statement') row.statement = 'not_distributed';
    if (kind === 'unknown') row.value_kind = 'approved';
    if (kind === 'legacy') data.schemaVersion = 1;
    assert.throws(() => parseRecalls(data), kind);
  }
});

test('a source statement cannot be relabeled as a date or a different statement', () => {
  for (const kind of ['normalized', 'role', 'wording', 'statement']) {
    const data = load();
    const row = data.records.find((row: { value_kind: string }) => row.value_kind === 'non_date');
    if (kind === 'normalized') row.normalized = '2026-09-27';
    if (kind === 'role') row.role = 'expiry';
    if (kind === 'wording') row.statement = 'not_distributed';
    if (kind === 'statement') row.statement = 'unknown_statement';
    assert.throws(() => parseRecalls(data), kind);
  }
});
