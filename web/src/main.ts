import './style.css';
import { parseRecalls, filterRecalls, type RecallData } from './recalls.ts';
import {
  createIcons,
  ScanLine,
  Files,
  Rows3,
  ChartNoAxesCombined,
  History,
  ArrowUpRight,
  Search,
  Check,
  X,
  Flag,
  ChevronLeft,
  ChevronRight,
  Download,
  ZoomIn,
  ZoomOut,
  Globe,
  PanelLeftOpen,
  FileText,
  CircleAlert,
  CheckCheck,
  Braces,
  Copy,
} from 'lucide';
import {
  parseWorkspace,
  languages,
  labels,
  latestEvent,
  filteredFields,
  makeEvent,
  validateEvent,
  csvText,
  sourceSlice,
  type Workspace,
  type Document,
  type Field,
  type ReviewEvent,
  type View,
  type Decision,
} from './data.ts';

const icons = {
  ScanLine,
  Files,
  Rows3,
  ChartNoAxesCombined,
  History,
  ArrowUpRight,
  Search,
  Check,
  X,
  Flag,
  ChevronLeft,
  ChevronRight,
  Download,
  ZoomIn,
  ZoomOut,
  Globe,
  PanelLeftOpen,
  FileText,
  CircleAlert,
  CheckCheck,
  Braces,
  Copy,
};
const root = document.querySelector<HTMLDivElement>('#app')!;
const repository = 'https://github.com/gitLamHoang/pharma-ocr-date-rag';
const storeKey = 'pharma-date-review.events.v1';
let data: Workspace;
let publicData: RecallData | null = null;
let publicError = '';
let events: ReviewEvent[] = [];
const state = {
  view: (['recalls', 'workspace', 'register', 'benchmarks', 'history'].includes(
    location.hash.slice(1),
  )
    ? location.hash.slice(1)
    : 'recalls') as View,
  recallQuery: '',
  recallRole: '',
  recallSplit: '',
  recallUnresolved: false,
  recallPage: 0,
  recallSelected: '',
  docId: 'fr_certificat',
  fieldId: '',
  query: '',
  language: '',
  label: '',
  status: '',
  zoom: 100,
  evidence: 'page',
  benchmarkMode: 'all_languages',
  benchmarkLanguage: '',
  reviewer: 'Demo reviewer',
  reason: '',
  resolved: null as string | null,
  message: '',
  error: '',
  sidebar: false,
};
const escape = (value: unknown) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!,
  );
const icon = (name: string) => '<i data-lucide="' + name + '" aria-hidden="true"></i>';
const button = (action: string, glyph: string, title: string, extra = '') =>
  '<button class="icon-button" data-action="' +
  action +
  '" title="' +
  title +
  '" aria-label="' +
  title +
  '" ' +
  extra +
  '>' +
  icon(glyph) +
  '</button>';
const options = (values: Record<string, string>, selected: string, all: string) =>
  '<option value="">' +
  all +
  '</option>' +
  Object.entries(values)
    .map(
      ([value, label]) =>
        '<option value="' +
        value +
        '" ' +
        (selected === value ? 'selected' : '') +
        '>' +
        escape(label) +
        '</option>',
    )
    .join('');
const selectedDoc = () => data.documents.find((doc) => doc.id === state.docId) ?? data.documents[0];
const selectedField = () =>
  selectedDoc().fields.find((field) => field.id === state.fieldId) ?? selectedDoc().fields[0];
function selectField(doc: Document, field: Field) {
  state.docId = doc.id;
  state.fieldId = field.id;
  state.resolved =
    latestEvent(events, doc, field, data.extractorVersion)?.resolved ?? field.normalized;
  state.reason = '';
  state.error = '';
}
function status(field: Field, doc: Document): string {
  return latestEvent(events, doc, field, data.extractorVersion)?.decision ?? 'pending';
}
const statusText: Record<string, string> = {
  pending: 'Pending',
  accepted: 'Accepted',
  rejected: 'Rejected',
  needs_review: 'Needs review',
};
const badge = (value: string) =>
  '<span class="status status-' + value + '">' + escape(statusText[value] ?? value) + '</span>';
function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function rows() {
  return filteredFields(data, events, {
    language: state.language,
    label: state.label,
    status: state.status,
    query: state.query,
  });
}
function summary() {
  const all = data.documents.flatMap((doc) => doc.fields.map((field) => ({ doc, field })));
  const pending = all.filter(({ doc, field }) => status(field, doc) === 'pending').length;
  const accepted = all.filter(({ doc, field }) => status(field, doc) === 'accepted').length;
  return (
    '<div class="metrics">' +
    '<div><span>Date candidates</span><strong>' +
    all.length +
    '<small> across ' +
    data.documents.length +
    ' documents</small></strong></div>' +
    '<div><span>Pending review</span><strong>' +
    pending +
    '<span class="metric-mark amber"></span></strong></div>' +
    '<div><span>Flagged evidence</span><strong>' +
    all.filter(({ field }) => field.review_reasons.length).length +
    '<small> original extraction</small></strong></div>' +
    '<div><span>Accepted</span><strong>' +
    accepted +
    '<small> in this browser</small></strong></div></div>'
  );
}
function filters() {
  return (
    '<div class="filter-bar"><label class="search">' +
    icon('search') +
    '<input id="query" type="search" placeholder="Search documents or date types" aria-label="Search evidence" value="' +
    escape(state.query) +
    '"></label>' +
    '<label><span class="sr-only">Language</span><select id="language" aria-label="Language">' +
    options(languages, state.language, 'All languages') +
    '</select></label>' +
    '<label><span class="sr-only">Date type</span><select id="label" aria-label="Date type">' +
    options(labels, state.label, 'All date types') +
    '</select></label>' +
    '<label><span class="sr-only">Review status</span><select id="status" aria-label="Review status">' +
    options(
      {
        pending: 'Pending',
        flagged: 'Flagged evidence',
        accepted: 'Accepted',
        needs_review: 'Needs review',
        rejected: 'Rejected',
      },
      state.status,
      'All statuses',
    ) +
    '</select></label></div>'
  );
}
function workspace() {
  const available = rows();
  if (!available.length)
    return (
      filters() +
      '<div class="large-empty">' +
      icon('search') +
      '<h3>No matching evidence</h3><p>There are no source fields for these filters.</p><button data-action="clear-filters">Clear filters</button></div>'
    );
  if (!available.some((row) => row.field.id === state.fieldId))
    selectField(available[0].doc, available[0].field);
  const doc = selectedDoc(),
    field = selectedField();
  const matching = rows();
  const docs = data.documents.filter((d) => matching.some((row) => row.doc.id === d.id));
  const docFields = matching.filter((row) => row.doc.id === doc.id);
  const visibleFields = docFields.map((row) => row.field);
  const allDocumentFields = visibleFields
    .map(
      (hit, index) =>
        '<button class="source-highlight ' +
        (hit.id === field.id ? 'selected' : '') +
        '" data-field="' +
        hit.id +
        '" data-doc="' +
        doc.id +
        '" style="left:' +
        hit.box[0] * 100 +
        '%;top:' +
        hit.box[1] * 100 +
        '%;width:' +
        hit.box[2] * 100 +
        '%;height:' +
        hit.box[3] * 100 +
        '%" title="' +
        escape(labels[hit.label] + ': ' + hit.raw_text) +
        '" aria-label="' +
        escape('Inspect ' + hit.raw_text) +
        '"><span>' +
        (index + 1) +
        '</span></button>',
    )
    .join('');
  const page =
    state.evidence === 'page'
      ? '<div class="paper" style="width:' +
        state.zoom +
        '%"><img src="' +
        doc.image +
        '" alt="Rendered synthetic source: ' +
        escape(doc.title) +
        '" width="' +
        doc.page.width +
        '" height="' +
        doc.page.height +
        '">' +
        allDocumentFields +
        '</div>'
      : '<pre class="source-text">' +
        escape(Array.from(doc.text).slice(0, field.start).join('')) +
        '<mark>' +
        escape(sourceSlice(doc, field)) +
        '</mark>' +
        escape(Array.from(doc.text).slice(field.end).join('')) +
        '</pre>';
  return (
    filters() +
    '<div class="workspace-grid">' +
    '<section class="documents-pane"><div class="pane-heading"><h2>Documents</h2><span>' +
    docs.length +
    '</span></div>' +
    (docs.length
      ? docs
          .map(
            (d) =>
              '<button class="document-item ' +
              (d.id === doc.id ? 'selected' : '') +
              '" data-doc="' +
              d.id +
              '">' +
              '<span class="document-icon">' +
              icon('file-text') +
              '</span><span class="document-copy"><strong>' +
              escape(d.vendor) +
              '</strong><span>' +
              escape(d.title) +
              '</span><small>' +
              languages[d.language] +
              ' · ' +
              d.fields.length +
              ' dates</small></span>' +
              (d.fields.some((f) => f.review_reasons.length)
                ? '<span class="attention-dot" title="Contains flagged evidence"></span>'
                : '') +
              '</button>',
          )
          .join('')
      : '<p class="empty">No matching evidence.</p>') +
    '<div class="collection-note">' +
    icon('globe') +
    '<span>5 languages<br><small>Synthetic sample collection</small></span></div></section>' +
    '<section class="source-pane"><div class="source-toolbar"><div><h2>' +
    escape(doc.title) +
    '</h2><small>' +
    escape(doc.filename) +
    '</small></div>' +
    '<div class="segmented" role="group" aria-label="Source view"><button data-evidence="page" class="' +
    (state.evidence === 'page' ? 'active' : '') +
    '">' +
    icon('file-text') +
    ' Page</button>' +
    '<button data-evidence="text" class="' +
    (state.evidence === 'text' ? 'active' : '') +
    '">' +
    icon('braces') +
    ' Text</button></div></div>' +
    '<div class="page-controls"><span class="source-tag">Synthetic source</span><span>Page 1 of 1</span><div class="zoom">' +
    button('zoom-out', 'zoom-out', 'Zoom out', state.zoom <= 70 ? 'disabled' : '') +
    '<span>' +
    state.zoom +
    '%</span>' +
    button('zoom-in', 'zoom-in', 'Zoom in', state.zoom >= 150 ? 'disabled' : '') +
    '</div></div>' +
    '<div class="page-scroll">' +
    page +
    '</div>' +
    '<div class="source-footer"><span>SHA-256 <code>' +
    doc.sha256.slice(0, 12) +
    '</code></span>' +
    button('copy-hash', 'copy', 'Copy source hash') +
    '<span>Original text preserved</span></div></section>' +
    '<section class="inspector"><div class="pane-heading"><h2>Field inspector</h2>' +
    badge(status(field, doc)) +
    '</div>' +
    '<label class="field-select">Selected field<select id="field" aria-label="Selected field">' +
    visibleFields
      .map(
        (f) =>
          '<option value="' +
          f.id +
          '" ' +
          (f.id === field.id ? 'selected' : '') +
          '>' +
          escape(labels[f.label] + ' · ' + f.raw_text) +
          '</option>',
      )
      .join('') +
    '</select></label>' +
    '<div class="field-value"><span class="type-label">' +
    escape(labels[field.label]) +
    '</span><h3>' +
    escape(state.resolved ?? 'Unresolved date') +
    '</h3><span>' +
    (field.precision === 'month' ? 'Month precision' : 'Day precision') +
    '</span></div>' +
    (field.review_reasons.length
      ? '<div class="review-flags">' +
        field.review_reasons
          .map(
            (reason) =>
              '<div>' +
              icon('circle-alert') +
              '<span>' +
              escape(reason.replaceAll('_', ' ')) +
              '</span></div>',
          )
          .join('') +
        '</div>'
      : '<p class="clear-note">' + icon('check-check') + ' No extraction flags</p>') +
    '<div class="evidence-quote"><span>Source evidence · line ' +
    field.line +
    '</span><blockquote>' +
    escape(field.context) +
    '</blockquote></div>' +
    (field.candidates.length > 1
      ? '<fieldset class="candidates"><legend>Date interpretation</legend>' +
        field.candidates
          .map(
            (candidate) =>
              '<label><input type="radio" name="candidate" value="' +
              candidate +
              '" ' +
              (state.resolved === candidate ? 'checked' : '') +
              '>' +
              candidate +
              '</label>',
          )
          .join('') +
        '</fieldset>'
      : '') +
    '<form id="review-form"><label>Reviewer<input id="reviewer" maxlength="80" value="' +
    escape(state.reviewer) +
    '" required></label>' +
    '<label>Review note<textarea id="reason" rows="2" maxlength="600" placeholder="Reason for this decision" required>' +
    escape(state.reason) +
    '</textarea></label>' +
    (state.error ? '<p class="form-error" role="alert">' + escape(state.error) + '</p>' : '') +
    '<div class="decision-buttons"><button type="submit" class="primary" data-decision="accepted">' +
    icon('check') +
    ' Accept</button>' +
    '<button type="submit" data-decision="needs_review" title="Mark as needing review">' +
    icon('flag') +
    ' Review</button>' +
    '<button type="submit" class="reject" data-decision="rejected" title="Reject this field">' +
    icon('x') +
    ' Reject</button></div></form>' +
    '<div class="inspector-footer"><small>Decision history</small>' +
    historyFor(doc, field) +
    '</div>' +
    '<div class="field-navigation">' +
    button('previous-field', 'chevron-left', 'Previous field') +
    '<span>' +
    (visibleFields.indexOf(field) + 1) +
    ' / ' +
    visibleFields.length +
    ' fields</span>' +
    button('next-field', 'chevron-right', 'Next field') +
    '</div></section></div>' +
    '<div class="workspace-bottom"><span>' +
    matching.length +
    ' matching fields · ' +
    docFields.length +
    ' in selected document</span><span>Review decisions are saved in this browser.</span></div>'
  );
}
function historyFor(doc: Document, field: Field): string {
  const recent = events
    .filter(
      (event) =>
        event.fieldId === field.id &&
        event.sourceSha256 === doc.sha256 &&
        event.extractorVersion === data.extractorVersion,
    )
    .slice(-3)
    .reverse();
  if (!recent.length) return '<p class="muted">No decisions recorded.</p>';
  return recent
    .map(
      (event) =>
        '<div class="mini-event">' +
        badge(event.decision) +
        '<p>' +
        escape(event.reason) +
        '</p><small>' +
        escape(event.reviewer) +
        ' · ' +
        new Date(event.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) +
        '</small></div>',
    )
    .join('');
}
function register() {
  const matches = rows();
  return (
    filters() +
    '<div class="table-toolbar"><h2>Date register <span>' +
    matches.length +
    '</span></h2><button data-action="export-csv">' +
    icon('download') +
    ' Export CSV</button></div>' +
    (matches.length
      ? '<div class="table-scroll"><table><thead><tr><th>Document</th><th>Language</th><th>Type</th><th>Date</th><th>Source text</th><th>Status</th><th>Review flags</th></tr></thead><tbody>' +
        matches
          .map(
            ({ doc, field, event }) =>
              '<tr><td><button class="table-link" data-doc="' +
              doc.id +
              '" data-field="' +
              field.id +
              '">' +
              escape(doc.vendor) +
              '</button><small>' +
              escape(doc.title) +
              '</small></td><td>' +
              languages[doc.language] +
              '</td><td>' +
              labels[field.label] +
              '</td><td class="date-cell">' +
              escape(event?.resolved ?? field.normalized ?? 'Unresolved') +
              '</td><td>' +
              escape(field.raw_text) +
              '</td><td>' +
              badge(event?.decision ?? 'pending') +
              '</td><td>' +
              (field.review_reasons
                .map(
                  (reason) =>
                    '<span class="flag-text">' + escape(reason.replaceAll('_', ' ')) + '</span>',
                )
                .join('') || '<span class="muted">None</span>') +
              '</td></tr>',
          )
          .join('') +
        '</tbody></table></div>'
      : '<div class="large-empty">' +
        icon('search') +
        '<h3>No matching fields</h3><p>There is no evidence for this combination of filters.</p><button data-action="clear-filters">Clear filters</button></div>')
  );
}
function benchmarks() {
  const benchmark = data.benchmark.results[state.benchmarkMode];
  const cases = data.cases.filter(
    (item) => !state.benchmarkLanguage || item.language === state.benchmarkLanguage,
  );
  return (
    '<div class="benchmark-heading"><div><h2>Multilingual extraction</h2><p>Authored synthetic development fixtures · exact-case matching</p></div>' +
    '<div class="segmented" role="group" aria-label="Benchmark mode"><button data-mode="all_languages" class="' +
    (state.benchmarkMode === 'all_languages' ? 'active' : '') +
    '">All vocabularies</button><button data-mode="explicit_language" class="' +
    (state.benchmarkMode === 'explicit_language' ? 'active' : '') +
    '">Explicit language</button></div></div>' +
    '<div class="benchmark-grid"><section class="benchmark-score"><span>Exact case matches</span><strong>' +
    benchmark.passed +
    '<small> / ' +
    benchmark.total +
    '</small></strong><p>Values, labels, alternatives, precision and review flags must all match.</p><a href="' +
    repository +
    '/blob/main/docs/benchmark_results.json" target="_blank" rel="noreferrer">Inspect benchmark report ' +
    icon('arrow-up-right') +
    '</a></section>' +
    '<section class="language-chart"><h3>Coverage by language</h3>' +
    Object.entries(benchmark.by_language)
      .map(
        ([code, value]) =>
          '<div class="bar-row"><span>' +
          languages[code] +
          '</span><div class="bar-track"><div style="width:' +
          (value.total / 18) * 100 +
          '%"></div></div><strong>' +
          value.passed +
          '/' +
          value.total +
          '</strong></div>',
      )
      .join('') +
    '</section></div>' +
    '<div class="benchmark-scope">' +
    icon('circle-alert') +
    '<span>These examples were written during development. The results do not measure real image OCR or held-out vendor-document accuracy.</span></div>' +
    '<div class="table-toolbar"><h2>Test cases <span>' +
    cases.length +
    '</span></h2><select id="benchmark-language" aria-label="Benchmark language">' +
    options(languages, state.benchmarkLanguage, 'All languages') +
    '</select></div>' +
    '<div class="table-scroll"><table><thead><tr><th>Case</th><th>Input</th><th>Expected result</th><th>Convention</th></tr></thead><tbody>' +
    cases
      .map(
        (item) =>
          '<tr><td><code>' +
          item.id +
          '</code><small>' +
          languages[item.language] +
          '</small></td><td>' +
          escape(item.text) +
          '</td><td>' +
          (item.expected.length
            ? item.expected
                .map(
                  (hit) =>
                    escape(hit.normalized ?? hit.candidates.join(' or ')) +
                    '<small>' +
                    escape(labels[hit.label]) +
                    '</small>',
                )
                .join('')
            : '<span class="muted">No date extracted</span>') +
          '</td><td>' +
          (item.date_order === 'auto' ? 'Unconfirmed' : item.date_order.toUpperCase()) +
          '</td></tr>',
      )
      .join('') +
    '</tbody></table></div>'
  );
}
function historyView() {
  const current = events.filter((event) => validateEvent(event, data));
  return (
    '<div class="table-toolbar"><div><h2>Review history <span>' +
    current.length +
    '</span></h2><p class="muted">Local browser decisions for the current source versions.</p></div><button data-action="export-json">' +
    icon('download') +
    ' Export session</button></div>' +
    (current.length
      ? '<div class="history-list">' +
        current
          .toReversed()
          .map((event) => {
            const doc = data.documents.find((d) => d.id === event.documentId)!;
            const field = doc.fields.find((f) => f.id === event.fieldId)!;
            return (
              '<article class="history-event"><span class="event-icon">' +
              icon(event.decision === 'accepted' ? 'check' : 'flag') +
              '</span><div><div class="event-heading">' +
              badge(event.decision) +
              '<button class="table-link" data-doc="' +
              doc.id +
              '" data-field="' +
              field.id +
              '">' +
              escape(doc.vendor + ' · ' + labels[field.label]) +
              '</button><time>' +
              new Date(event.createdAt).toLocaleString() +
              '</time></div><p>' +
              escape(event.reason) +
              '</p><small>' +
              escape(event.reviewer) +
              ' · ' +
              escape(event.resolved ?? 'Unresolved') +
              ' · Source ' +
              event.sourceSha256.slice(0, 12) +
              '</small></div></article>'
            );
          })
          .join('') +
        '</div>'
      : '<div class="large-empty">' +
        icon('history') +
        '<h3>No review decisions yet</h3><p>Current source versions have no recorded decisions in this browser.</p><button data-view="workspace">Open workspace</button></div>')
  );
}
function publicRows() {
  return publicData
    ? filterRecalls(
        publicData,
        state.recallQuery,
        state.recallRole,
        state.recallSplit,
        state.recallUnresolved,
      )
    : [];
}
function publicView() {
  if (!publicData)
    return (
      '<div class="large-empty"><h2>Public notices unavailable</h2><p>' +
      escape(publicError) +
      '</p></div>'
    );
  const matches = publicRows();
  const pageCount = Math.max(1, Math.ceil(matches.length / 25));
  state.recallPage = Math.min(state.recallPage, pageCount - 1);
  const pageRows = matches.slice(state.recallPage * 25, (state.recallPage + 1) * 25);
  const selected = pageRows.find((row) => row.id === state.recallSelected) ?? pageRows[0];
  const doc = publicData.documents.find((doc) => doc.id === selected?.document_id);
  const table = doc?.tables.find((table) => table.table_index === selected?.table_index);
  const evaluation = publicData.evaluation.test;
  return (
    '<div class="metrics"><div><span>Official notices</span><strong>' +
    publicData.corpus.documents +
    '<small>MHRA / GOV.UK</small></strong></div><div><span>Batch/date cells</span><strong>' +
    publicData.records.length +
    '<small>source-linked candidates</small></strong></div><div><span>Training documents</span><strong>' +
    publicData.corpus.document_splits.train +
    '<small>' +
    publicData.corpus.document_splits.validation +
    ' validation / ' +
    publicData.corpus.document_splits.test +
    ' test</small></strong></div><div><span>No single date</span><strong>' +
    publicData.records.filter((row) => row.normalized === null).length +
    '<small>ambiguous or unparsed</small></strong></div></div>' +
    '<div class="public-scope"><span>' +
    icon('circle-alert') +
    'Static research snapshot · ' +
    escape(publicData.snapshotRetrievedAt.slice(0, 10)) +
    ' · Not current recall advice. All values require source review.</span><a href="' +
    repository +
    '/blob/main/docs/public-data.md" target="_blank" rel="noreferrer">Dataset & model card ' +
    icon('arrow-up-right') +
    '</a></div>' +
    '<div class="filter-bar"><label class="search">' +
    icon('search') +
    '<input id="recall-query" type="search" placeholder="Medicine, batch or source date" aria-label="Search public notices" value="' +
    escape(state.recallQuery) +
    '"></label>' +
    '<select id="recall-role" aria-label="Public date type">' +
    options(
      { expiry: 'Expiry', distribution: 'Distribution' },
      state.recallRole,
      'All date types',
    ) +
    '</select>' +
    '<select id="recall-split" aria-label="Dataset split">' +
    options(
      { train: 'Training', validation: 'Validation', test: 'Held-out test' },
      state.recallSplit,
      'All splits',
    ) +
    '</select>' +
    '<label class="public-checkbox"><input type="checkbox" id="recall-unresolved" ' +
    (state.recallUnresolved ? 'checked' : '') +
    '> No single date</label></div>' +
    '<div class="table-toolbar"><h2>Public batch register <span>' +
    matches.length +
    '</span></h2><button data-action="export-public-csv">' +
    icon('download') +
    ' Export CSV</button></div>' +
    (pageRows.length
      ? '<div class="table-scroll public-register"><table><thead><tr><th>Notice / Batch</th><th>Field</th><th>Source value</th><th>Interpretation</th><th>Review flags</th><th>Split</th></tr></thead><tbody>' +
        pageRows
          .map(
            (row) =>
              '<tr class="' +
              (selected?.id === row.id ? 'public-selected' : '') +
              '"><td><button class="table-link" data-public-field="' +
              escape(row.id) +
              '">' +
              escape(row.batch || 'No batch text') +
              '</button><small>' +
              escape(row.title) +
              '</small></td><td>' +
              escape(row.role) +
              '</td><td>' +
              escape(row.raw_text) +
              '</td><td class="date-cell">' +
              escape(row.normalized ?? 'Unresolved') +
              '</td><td>' +
              escape(
                row.review_reasons.join(', ').replaceAll('_', ' ') || 'Source review required',
              ) +
              '</td><td>' +
              escape(row.split) +
              '</td></tr>',
          )
          .join('') +
        '</tbody></table></div>'
      : '<div class="large-empty"><h3>No matching public records</h3></div>') +
    '<div class="public-pagination">' +
    button(
      'recall-prev',
      'chevron-left',
      'Previous public records',
      state.recallPage === 0 ? 'disabled' : '',
    ) +
    '<span>Page ' +
    (state.recallPage + 1) +
    ' / ' +
    pageCount +
    '</span>' +
    button(
      'recall-next',
      'chevron-right',
      'Next public records',
      state.recallPage + 1 >= pageCount ? 'disabled' : '',
    ) +
    '</div>' +
    (doc && table && selected
      ? '<section class="public-source"><div class="table-toolbar"><h2>Source table</h2><a href="' +
        escape(doc.url) +
        '" target="_blank" rel="noreferrer">Original GOV.UK notice ' +
        icon('arrow-up-right') +
        '</a></div><h3>' +
        escape(doc.title) +
        '</h3><p>Table ' +
        (table.table_index + 1) +
        ', row ' +
        (selected.row_index + 1) +
        ' · Classifier score ' +
        selected.model_score.toFixed(3) +
        ' (uncalibrated) · Source SHA-256 <code>' +
        escape(doc.source.sha256) +
        '</code></p>' +
        '<div class="table-scroll"><table><thead><tr>' +
        table.headers.map((header) => '<th>' + escape(header) + '</th>').join('') +
        '</tr></thead><tbody><tr>' +
        table.rows[selected.row_index]
          .map(
            (value, index) =>
              '<td' +
              (index === selected.column_index ? ' class="source-cell-selected"' : '') +
              '>' +
              escape(value) +
              '</td>',
          )
          .join('') +
        '</tr></tbody></table></div>' +
        (selected.candidates.length > 1
          ? '<p>Possible dates: ' + selected.candidates.map(escape).join(' / ') + '</p>'
          : '') +
        '</section>'
      : '') +
    '<section class="public-method"><h2>Measured model comparison</h2><p>Held-out column roles: model ' +
    Math.round(evaluation.model.accuracy * 100) +
    '%; keyword baseline ' +
    Math.round(evaluation.keywords.accuracy * 100) +
    '% on ' +
    evaluation.model.count +
    ' columns. ' +
    evaluation.seen_heading_count +
    ' headings already occur in training. At the review threshold, ' +
    evaluation.abstention.classified +
    '/' +
    evaluation.abstention.total +
    ' receive a role; the rest are unclassified.</p><p>English templates only. This is not date-value accuracy, independently annotated clinical validation, or evidence that the learned model improves on rules.</p><small>' +
    escape(publicData.attribution) +
    '</small></section>'
  );
}
function render() {
  if (location.hash !== '#' + state.view) history.replaceState(null, '', '#' + state.view);
  const titles: Record<View, string> = {
    recalls: 'Public medicine notices',
    workspace: 'Document review',
    register: 'Date register',
    benchmarks: 'Benchmark lab',
    history: 'Review history',
  };
  root.innerHTML =
    '<div class="app-shell ' +
    (state.sidebar ? 'sidebar-open' : '') +
    '">' +
    '<aside class="sidebar"><a class="brand" href="#workspace" data-view="workspace"><span class="brand-mark">' +
    icon('scan-line') +
    '</span><span>Pharma<span>Date Review</span></span></a>' +
    '<span class="nav-label">Workspace</span><nav aria-label="Main navigation">' +
    (
      [
        ['recalls', 'globe', 'Public notices'],
        ['workspace', 'files', 'Document review'],
        ['register', 'rows-3', 'Date register'],
        ['benchmarks', 'chart-no-axes-combined', 'Benchmark lab'],
        ['history', 'history', 'Review history'],
      ] as const
    )
      .map(
        ([view, glyph, label]) =>
          '<button data-view="' +
          view +
          '" class="' +
          (state.view === view ? 'active' : '') +
          '" ' +
          (state.view === view ? 'aria-current="page"' : '') +
          '>' +
          icon(glyph) +
          label +
          (view === 'history' && events.length
            ? '<span class="nav-count">' + events.length + '</span>'
            : '') +
          '</button>',
      )
      .join('') +
    '</nav><div class="sidebar-bottom"><div class="dataset-label"><span class="live-dot"></span>Research workspace</div><p>Public MHRA notices<br>8 synthetic multilingual samples</p>' +
    '<a href="' +
    repository +
    '" target="_blank" rel="noreferrer">Source & methodology ' +
    icon('arrow-up-right') +
    '</a><div class="creator"><span>LP</span><div>Lam Phan<small>Independent portfolio project</small></div></div></div></aside>' +
    '<div class="main-shell"><header class="topbar">' +
    button('sidebar', 'panel-left-open', 'Toggle navigation') +
    '<div class="breadcrumb">Workspace <span>/</span> ' +
    titles[state.view] +
    '</div>' +
    '<div class="top-actions"><span class="environment">' +
    (state.view === 'recalls' ? 'Public source data' : 'Synthetic data') +
    '</span><button data-action="' +
    (state.view === 'recalls' ? 'export-public-json' : 'export-json') +
    '">' +
    icon('download') +
    '<span>Export session</span></button></div></header>' +
    '<main><div class="page-heading"><div><p class="eyebrow">Vendor document intelligence</p><h1>' +
    titles[state.view] +
    '</h1></div><span class="workspace-version">Source-backed candidates <span>v0.3</span></span></div>' +
    (state.view === 'recalls' ? '' : summary()) +
    (state.message
      ? '<div class="notice" role="status">' +
        icon('check-check') +
        escape(state.message) +
        '</div>'
      : '') +
    (state.view === 'recalls'
      ? publicView()
      : state.view === 'workspace'
        ? workspace()
        : state.view === 'register'
          ? register()
          : state.view === 'benchmarks'
            ? benchmarks()
            : historyView()) +
    '</main><footer><span>Research prototype · Source review required</span><a href="' +
    repository +
    '/blob/main/docs/design.md" target="_blank" rel="noreferrer">Methodology ' +
    icon('arrow-up-right') +
    '</a></footer></div></div>';
  createIcons({ icons });
  const pane = root.querySelector<HTMLElement>('.documents-pane');
  const item = pane?.querySelector<HTMLElement>('.document-item.selected');
  if (pane && item && window.innerWidth <= 760) {
    pane.scrollLeft += item.getBoundingClientRect().left - pane.getBoundingClientRect().left;
  }
}
root.addEventListener('click', async (event) => {
  const target = (event.target as Element).closest<HTMLElement>('button,a');
  if (!target) return;
  if (target.dataset.decision) return;
  if (target.dataset.view) {
    state.view = target.dataset.view as View;
    state.sidebar = false;
    state.message = '';
  } else if (target.dataset.publicField) {
    state.recallSelected = target.dataset.publicField;
  } else if (target.dataset.doc) {
    if (state.view === 'history')
      Object.assign(state, { query: '', language: '', label: '', status: '' });
    const doc = data.documents.find((d) => d.id === target.dataset.doc)!;
    selectField(
      doc,
      doc.fields.find((f) => f.id === target.dataset.field) ??
        rows().find((row) => row.doc.id === doc.id)?.field ??
        doc.fields[0],
    );
    state.view = 'workspace';
  } else if (target.dataset.evidence) state.evidence = target.dataset.evidence;
  else if (target.dataset.mode) state.benchmarkMode = target.dataset.mode;
  else if (target.dataset.action) {
    const action = target.dataset.action;
    if (action === 'recall-prev') state.recallPage = Math.max(0, state.recallPage - 1);
    if (action === 'recall-next') state.recallPage++;
    if (action === 'export-public-json' && publicData) {
      download(
        'public-mhra-evidence.json',
        JSON.stringify(
          {
            attribution: publicData.attribution,
            licence: publicData.licence,
            scope: 'Static public-source research snapshot; review required',
            records: publicRows(),
          },
          null,
          2,
        ),
        'application/json',
      );
      return;
    }
    if (action === 'export-public-csv') {
      download(
        'public-mhra-register.csv',
        csvText(
          publicRows().map((row) => ({
            source: row.url,
            batch: row.batch,
            type: row.role,
            raw: row.raw_text,
            normalized: row.normalized,
            candidates: row.candidates.join(' | '),
            table: row.table_index + 1,
            row: row.row_index + 1,
            split: row.split,
            status: row.status,
            source_sha256: row.source_sha256,
            attribution: publicData?.attribution,
            licence: publicData?.licence,
          })),
        ),
        'text/csv',
      );
      return;
    }
    if (action === 'sidebar') state.sidebar = !state.sidebar;
    if (action === 'zoom-in') state.zoom = Math.min(150, state.zoom + 10);
    if (action === 'zoom-out') state.zoom = Math.max(70, state.zoom - 10);
    if (action === 'clear-filters')
      Object.assign(state, { query: '', language: '', label: '', status: '' });
    if (action === 'next-field' || action === 'previous-field') {
      const doc = selectedDoc();
      const fields = rows()
        .filter((row) => row.doc.id === doc.id)
        .map((row) => row.field);
      const index = fields.indexOf(selectedField());
      selectField(
        doc,
        fields[(index + (action === 'next-field' ? 1 : -1) + fields.length) % fields.length],
      );
    }
    if (action === 'copy-hash') {
      try {
        await navigator.clipboard.writeText(selectedDoc().sha256);
        state.message = 'Source hash copied.';
      } catch {
        state.message =
          'Clipboard unavailable. The full source hash is included in the session export.';
      }
    }
    if (action === 'export-json') {
      download(
        'pharma-review-session.json',
        JSON.stringify(
          {
            schemaVersion: 1,
            scope: 'Local browser review of synthetic fixtures',
            extractorVersion: data.extractorVersion,
            documents: data.documents.map((doc) => ({
              id: doc.id,
              sha256: doc.sha256,
              fields: doc.fields,
            })),
            reviews: events,
            exportedAt: new Date().toISOString(),
          },
          null,
          2,
        ),
        'application/json',
      );
      return;
    }
    if (action === 'export-csv') {
      download(
        'pharma-date-register.csv',
        csvText(
          rows().map(({ doc, field, event }) => ({
            document: doc.filename,
            language: doc.language,
            date: event?.resolved ?? field.normalized,
            type: field.label,
            status: event?.decision ?? 'pending',
            source: field.raw_text,
            candidates: field.candidates.join(' | '),
            review_flags: field.review_reasons.join(' | '),
            source_sha256: doc.sha256,
            start: field.start,
            end: field.end,
          })),
        ),
        'text/csv',
      );
      return;
    }
  } else return;
  render();
});
root.addEventListener('change', (event) => {
  const target = event.target as HTMLInputElement;
  if (['recall-role', 'recall-split', 'recall-unresolved'].includes(target.id)) {
    if (target.id === 'recall-role') state.recallRole = target.value;
    if (target.id === 'recall-split') state.recallSplit = target.value;
    if (target.id === 'recall-unresolved') state.recallUnresolved = target.checked;
    state.recallPage = 0;
    state.recallSelected = '';
  } else if (target.id === 'language') state.language = target.value;
  else if (target.id === 'label') state.label = target.value;
  else if (target.id === 'status') state.status = target.value;
  else if (target.id === 'field')
    selectField(
      selectedDoc(),
      selectedDoc().fields.find((f) => f.id === target.value)!,
    );
  else if (target.id === 'benchmark-language') state.benchmarkLanguage = target.value;
  else if (target.name === 'candidate') {
    state.resolved = target.value;
    state.error = '';
  } else return;
  render();
});
root.addEventListener('input', (event) => {
  const target = event.target as HTMLInputElement;
  if (target.id === 'reviewer') state.reviewer = target.value;
  if (target.id === 'reason') state.reason = target.value;
  if (target.id === 'recall-query') {
    const start = target.selectionStart,
      end = target.selectionEnd;
    state.recallQuery = target.value;
    state.recallPage = 0;
    state.recallSelected = '';
    render();
    const input = document.querySelector<HTMLInputElement>('#recall-query')!;
    input.focus();
    input.setSelectionRange(start, end);
  }
  if (target.id === 'query') {
    const start = target.selectionStart,
      end = target.selectionEnd;
    state.query = target.value;
    render();
    const input = document.querySelector<HTMLInputElement>('#query')!;
    input.focus();
    if (input.type !== 'search') input.setSelectionRange(start, end);
  }
});
root.addEventListener('submit', (event) => {
  event.preventDefault();
  const decision = (event as SubmitEvent).submitter?.getAttribute('data-decision') as Decision;
  if (!decision) return;
  try {
    const review = makeEvent(
      data,
      selectedDoc(),
      selectedField(),
      decision,
      state.resolved,
      state.reviewer,
      state.reason,
    );
    const updated = [...events, review];
    localStorage.setItem(storeKey, JSON.stringify(updated));
    events = updated;
    state.reason = '';
    state.error = '';
    state.message = 'Decision recorded in this browser.';
  } catch (error) {
    state.error = error instanceof Error ? error.message : 'Could not save this decision.';
  }
  render();
});
async function start() {
  try {
    const response = await fetch('data/workspace.json');
    if (!response.ok) throw new Error('The evidence snapshot could not be loaded.');
    data = parseWorkspace(await response.json());
    try {
      const publicResponse = await fetch('data/recalls.json');
      if (!publicResponse.ok) throw new Error('Public-source evidence could not be loaded.');
      publicData = parseRecalls(await publicResponse.json());
    } catch (error) {
      publicError = error instanceof Error ? error.message : 'Public notices could not be loaded.';
    }
    try {
      const saved: unknown = JSON.parse(localStorage.getItem(storeKey) ?? '[]');
      if (!Array.isArray(saved)) throw new Error();
      events = saved.filter((event) => validateEvent(event, data));
    } catch {
      state.message =
        'Saved reviews could not be read. New decisions will require browser storage.';
    }
    const doc = selectedDoc();
    selectField(doc, doc.fields.find((f) => f.normalized === null) ?? doc.fields[0]);
    render();
  } catch (error) {
    root.innerHTML =
      '<div class="large-empty"><h1>Workspace unavailable</h1><p>' +
      escape(error instanceof Error ? error.message : error) +
      '</p><button onclick="location.reload()">Reload</button></div>';
  }
}
void start();
