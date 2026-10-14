import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { parseRecalls } from './recalls.ts';
import { buildEvidenceIndex, searchEvidence, evidenceExport, tokens } from './search.ts';
const data = parseRecalls(
  JSON.parse(readFileSync(new URL('../public/data/recalls.json', import.meta.url), 'utf8')),
);
const index = buildEvidenceIndex(data);
test('index groups expiry and distribution cells into one cited batch row', () => {
  assert.equal(index.rows.length, 371);
  const result = searchEvidence(index, '0162858 expiry');
  assert.equal(result.hits.length, 1);
  const { evidence, score, matchedTerms } = result.hits[0];
  assert.equal(evidence.batch, '0162858');
  assert.equal(evidence.fields.length, 2);
  assert.deepEqual(matchedTerms, ['0162858', 'expiry']);
  assert.ok(Number.isFinite(score) && score > 0);
  assert.equal(evidence.fields.find((field) => field.role === 'expiry')?.normalized, '2028-05');
});
test('unknown, partial, and contradictory identifiers cannot fall back to medicine-name matches', () => {
  for (const query of [
    'Flutiform batch 9999999',
    'Flutiform 24062FA',
    'Flutiform 0162858',
    'batch 016285',
    'batch 999',
    'Flutiform 0162858 0163605',
  ]) {
    assert.equal(searchEvidence(index, query).hits.length, 0, query);
  }
  assert.equal(searchEvidence(index, 'Flutiform batch 9999999').reason, 'unknown_batch');
});
test('ranking is deterministic and respects all terms rather than returning unrelated results', () => {
  const result = searchEvidence(index, 'Flutiform');
  assert.ok(result.hits.length > 1);
  assert.ok(result.hits.every((hit) => /Flutiform/i.test(hit.evidence.document.title)));
  assert.deepEqual(searchEvidence(index, 'Flutiform'), result);
  assert.ok(result.hits.every((hit, i) => i === 0 || hit.score <= result.hits[i - 1].score));
  assert.equal(searchEvidence(index, 'inventedmedicine expiry').hits.length, 0);
  assert.equal(searchEvidence(index, 'the and for').reason, 'empty');
  assert.equal(searchEvidence(index, '').hits.length, 0);
});
test('batch punctuation and case are retained while natural query stop words are ignored', () => {
  const result = searchEvidence(index, 'What is the expiry for batch 270185-24062fa-30424?');
  assert.equal(result.hits.length, 1);
  assert.equal(result.hits[0].evidence.batch, '270185-24062FA-30424');
  assert.deepEqual(tokens('Flutiform 250 micrograms'), ['flutiform', '250', 'micrograms']);
  assert.ok(searchEvidence(index, 'Flutiform 250 micrograms').hits.length);
});
test('filters change source eligibility without changing semantic values', () => {
  assert.equal(searchEvidence(index, '0162858', { split: 'train', kind: '' }).hits.length, 0);
  assert.equal(searchEvidence(index, '0162858', { split: 'test', kind: 'date' }).hits.length, 1);
  const cutoffs = searchEvidence(index, 'expiry cutoff');
  assert.equal(cutoffs.hits.length, 3);
  for (const hit of cutoffs.hits) {
    const field = hit.evidence.fields.find((field) => field.value_kind === 'cutoff')!;
    assert.equal(field.normalized, null);
    assert.deepEqual(field.candidates, []);
    assert.equal(field.cutoff?.inclusive, true);
  }
});
test('export reproduces query, filters, ranking, original cells and exact citations', () => {
  const filters = { split: 'test', kind: '' };
  const result = searchEvidence(index, '0162858 expiry', filters);
  const exported = evidenceExport(data, result, filters);
  assert.equal(exported.query, '0162858 expiry');
  assert.deepEqual(exported.filters, filters);
  assert.equal(exported.resultCount, 1);
  assert.equal(exported.results[0].rank, 1);
  const citation = exported.results[0].citation;
  assert.equal(citation.indexBase, 0);
  assert.match(citation.url, /^https:\/\/www.gov.uk\/drug-device-alerts\//);
  const doc = data.documents.find((doc) => doc.id === citation.documentId)!;
  const table = doc.tables.find((table) => table.table_index === citation.tableIndex)!;
  assert.equal(citation.sourceSha256, doc.source.sha256);
  assert.deepEqual(
    exported.results[0].cells.map((cell) => cell.value),
    table.rows[citation.rowIndex],
  );
  assert.match(exported.scoreMeaning, /not confidence/);
  assert.match(exported.attribution, /Open Government Licence/);
  assert.equal(
    evidenceExport(data, searchEvidence(index, 'unknownmedicine'), filters).resultCount,
    0,
  );
});
