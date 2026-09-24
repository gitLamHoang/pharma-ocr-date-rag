import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
  csvText,
  filteredFields,
  fold,
  latestEvent,
  makeEvent,
  parseWorkspace,
  sourceSlice,
  validateEvent,
} from './data.ts';

const fixture = () =>
  parseWorkspace(
    JSON.parse(readFileSync(new URL('../public/data/workspace.json', import.meta.url), 'utf8')),
  );
const filters = { language: '', label: '', status: '', query: '' };

test('published workspace has exact source spans and five languages', () => {
  const data = fixture();
  assert.equal(data.documents.length, 8);
  assert.equal(new Set(data.documents.map((doc) => doc.language)).size, 5);
  assert.equal(filteredFields(data, [], filters).length, 42);
  for (const doc of data.documents)
    for (const field of doc.fields) {
      assert.equal(sourceSlice(doc, field), field.raw_text);
      assert.ok(field.box[0] + field.box[2] <= 1);
      assert.ok(field.box[1] + field.box[3] <= 1);
    }
});
test('corrupted source offsets and duplicate field identities are rejected', () => {
  const data = fixture();
  data.documents[0].fields[0].start += 1;
  assert.throws(() => parseWorkspace(data), /source evidence/);
  const other = fixture();
  other.documents[0].fields.push(other.documents[0].fields[0]);
  assert.throws(() => parseWorkspace(other), /source evidence/);
});
test('Unicode codepoint offsets do not split non-BMP text', () => {
  const doc = fixture().documents[0];
  assert.equal(
    sourceSlice({ ...doc, text: '\u{1f4c4} 2026-10-02' }, { ...doc.fields[0], start: 2, end: 12 }),
    '2026-10-02',
  );
  assert.equal(fold('Phiếu kiểm tra / Đ'), 'phieu kiem tra / d');
});
test('English date vocabulary retrieves French evidence without translating the source', () => {
  const found = filteredFields(fixture(), [], {
    ...filters,
    language: 'fr',
    label: 'expiry',
    query: 'expiry',
  });
  assert.ok(found.length > 0);
  assert.ok(found.every((row) => row.field.label === 'expiry' && row.doc.language === 'fr'));
});
test('no-match searches and language filters return no unrelated fields', () => {
  assert.deepEqual(filteredFields(fixture(), [], { ...filters, query: 'unfindableevidence' }), []);
  assert.equal(filteredFields(fixture(), [], { ...filters, language: 'vi' }).length, 6);
});
test('ambiguous dates cannot be accepted before choosing an interpretation', () => {
  const data = fixture(),
    doc = data.documents.find((d) => d.id === 'fr_certificat')!;
  const field = doc.fields.find((f) => f.normalized === null)!;
  assert.throws(
    () => makeEvent(data, doc, field, 'accepted', null, 'Reviewer', 'Checked source'),
    /valid date/,
  );
  const event = makeEvent(
    data,
    doc,
    field,
    'accepted',
    field.candidates[0],
    ' Reviewer ',
    ' Synthetic convention confirmed ',
  );
  assert.equal(event.reviewer, 'Reviewer');
  assert.equal(event.resolved, field.candidates[0]);
  assert.ok(validateEvent(event, data));
});
test('unresolved rejection is allowed but reviewer, note and candidates are validated', () => {
  const data = fixture(),
    doc = data.documents[0],
    field = doc.fields[0];
  assert.ok(
    validateEvent(
      makeEvent(data, doc, field, 'rejected', null, 'A', 'Insufficient evidence'),
      data,
    ),
  );
  for (const [reviewer, reason] of [
    ['', 'Reason'],
    ['A', '   '],
    ['A'.repeat(81), 'Reason'],
  ]) {
    assert.throws(() =>
      makeEvent(data, doc, field, 'accepted', field.normalized, reviewer, reason),
    );
  }
  assert.throws(() => makeEvent(data, doc, field, 'accepted', '2099-01-01', 'A', 'Reason'));
});
test('append-only decisions use latest event and cannot leak across source versions', () => {
  const data = fixture(),
    doc = data.documents[0],
    field = doc.fields[0];
  const first = makeEvent(data, doc, field, 'needs_review', field.normalized, 'A', 'Check again');
  const second = makeEvent(data, doc, field, 'rejected', field.normalized, 'B', 'Not sufficient');
  const events = [first, second];
  assert.equal(latestEvent(events, doc, field, data.extractorVersion), second);
  assert.equal(filteredFields(data, events, { ...filters, status: 'rejected' }).length, 1);
  assert.equal(
    latestEvent(events, { ...doc, sha256: '0'.repeat(64) }, field, data.extractorVersion),
    undefined,
  );
  assert.equal(latestEvent(events, doc, field, 'future-version'), undefined);
  assert.equal(validateEvent({ ...first, sourceSha256: '0'.repeat(64) }, data), false);
  assert.equal(validateEvent(null, data), false);
  assert.equal(validateEvent({ decision: 'accepted' }, data), false);
});
test('CSV exports quote multiline evidence and neutralize formula prefixes', () => {
  assert.equal(
    csvText([{ source: 'line, "quoted"\nnext', note: ' =1+1' }]),
    '"source","note"\r\n"line, ""quoted""\nnext","\' =1+1"',
  );
  assert.ok(csvText([]).includes('document,date'));
});
