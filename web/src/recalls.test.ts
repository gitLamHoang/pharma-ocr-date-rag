import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { parseRecalls, filterRecalls } from './recalls.ts';

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
