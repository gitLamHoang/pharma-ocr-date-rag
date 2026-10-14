import { cellInterpretation, valueKinds, type RecallData } from './recalls.ts';
import { searchEvidence, type EvidenceIndex, type SearchHit } from './search.ts';
export interface SearchState {
  searchDraft: string;
  searchQuery: string;
  searchSplit: string;
  searchKind: string;
  searchSelected: string;
  searchLimit: number;
}
const escape = (value: unknown) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!,
  );
const icon = (name: string) => `<i data-lucide="${name}" aria-hidden="true"></i>`;
const selectOptions = (values: Record<string, string>, current: string) =>
  Object.entries(values)
    .map(
      ([value, label]) =>
        `<option value="${value}" ${value === current ? 'selected' : ''}>${label}</option>`,
    )
    .join('');
function detail(hit: SearchHit) {
  const row = hit.evidence;
  return `<section class="search-detail" aria-labelledby="evidence-detail-heading">
    <div class="search-detail-top"><span class="section-kicker">EVIDENCE INSPECTOR</span><span class="evidence-marker">${icon('file-text')}Source linked</span></div>
    <h2 id="evidence-detail-heading" tabindex="-1">Batch <span>${escape(row.batch)}</span></h2>
    <p class="detail-notice-title">${escape(row.document.title)}</p>
    <div class="search-interpretations">${row.fields.map((field) => `<div class="search-interpretation ${field.normalized === null ? 'uncertain' : ''}"><div><span>${escape(field.role)}</span><span class="interpretation-kind">${escape(valueKinds[field.value_kind])}</span></div><strong>${escape(cellInterpretation(field))}</strong><p>Source: <code>${escape(field.raw_text)}</code></p>${field.candidates.length > 1 ? `<p class="candidate-dates">Possible dates: ${field.candidates.map((date) => `<code>${escape(date)}</code>`).join(' or ')}</p>` : ''}${field.review_reasons.length ? `<small>${escape(field.review_reasons.join(' · ').replaceAll('_', ' '))}</small>` : ''}${field.review_reasons.includes('source_footnote') ? '<p class="search-footnote">A footnote qualifies this value. Read the complete source notice.</p>' : ''}</div>`).join('')}</div>
    <div class="source-table-heading"><h3>Original table row</h3><span>Table ${row.tableIndex + 1} · Row ${row.rowIndex + 1}</span></div>
    <dl class="source-record">${row.cells.map((cell) => `<div><dt>${escape(cell.header)}</dt><dd>${escape(cell.value)}</dd></div>`).join('')}</dl>
    <a class="source-link" href="${escape(row.document.url)}" target="_blank" rel="noreferrer">Open original GOV.UK notice ${icon('arrow-up-right')}</a>
    <div class="search-provenance"><span>PAYLOAD SHA-256</span><code>${escape(row.document.source.sha256)}</code><small>Snapshot payload identity · ${escape(row.document.split)} split</small></div>
    <p class="detail-caution">Extracted candidates require source review. Retrieval does not validate a date or establish whether a medicine is safe.</p>
  </section>`;
}
export function searchView(
  data: RecallData | null,
  index: EvidenceIndex | null,
  state: SearchState,
  error: string,
) {
  if (!data || !index)
    return `<div class="large-empty" role="alert">${icon('circle-alert')}<h2>Evidence could not be loaded</h2><p>${escape(error || 'The public snapshot is unavailable.')}</p><button data-action="reload-search">Reload evidence</button></div>`;
  const result = searchEvidence(index, state.searchQuery, {
    split: state.searchSplit,
    kind: state.searchKind,
  });
  const visible = result.hits.slice(0, state.searchLimit);
  const selected =
    result.hits.find((hit) => hit.evidence.id === state.searchSelected) ?? result.hits[0];
  return `<section class="evidence-search ${state.searchQuery ? 'has-query' : ''}" aria-label="Evidence search">
    <div class="search-intro"><span class="search-overline">${icon('scan-line')}THE PUBLIC EVIDENCE WORKBENCH</span><h1>Find the batch.<br><span>See the evidence.</span></h1><p>Search medicine notices. Inspect the original table.<br class="desktop-break"> Keep every interpretation tied to its source.</p></div>
    <div class="evidence-search-box"><form id="evidence-search-form" role="search"><label class="sr-only" for="evidence-query">Search medicine or exact batch</label>${icon('search')}<input id="evidence-query" name="query" type="search" placeholder="Medicine name, exact batch, or date field" value="${escape(state.searchDraft)}" maxlength="200" autocomplete="off" aria-describedby="search-help"><button class="primary" type="submit">Search ${icon('arrow-up-right')}</button></form><p id="search-help">All search terms must match. Batch identifiers are exact. Results are source rows, not generated answers.</p></div>
    <div class="search-examples"><span>EXPLORE A SOURCE</span><button data-search-example="0162858 expiry">Batch 0162858 ${icon('arrow-up-right')}</button><button data-search-example="Flutiform">Flutiform ${icon('arrow-up-right')}</button><button data-search-example="expiry cutoff">Expiry cutoffs ${icon('arrow-up-right')}</button></div>
    <div class="search-corpus-bar"><span>${icon('globe')}<strong>${data.documents.length}</strong> notices</span><span><strong>${index.rows.length}</strong> batch rows</span><span>English · Frozen ${escape(data.snapshotRetrievedAt.slice(0, 10))}</span><a href="#recalls" data-view="recalls">Browse register ${icon('arrow-up-right')}</a></div>
    ${
      state.searchQuery
        ? `<div class="search-results-header"><div><span class="section-kicker">SOURCE MATCHES</span><h2 role="status">${result.hits.length} ${result.hits.length === 1 ? 'batch row' : 'batch rows'} found</h2></div><div class="search-result-filters"><label><span class="sr-only">Evidence split</span><select id="search-split">${selectOptions({ '': 'All splits', train: 'Training', validation: 'Validation', test: 'Held-out test' }, state.searchSplit)}</select></label><label><span class="sr-only">Evidence value kind</span><select id="search-kind">${selectOptions({ '': 'All value kinds', ...valueKinds }, state.searchKind)}</select></label><button data-action="export-search" ${result.hits.length ? '' : 'disabled'}>${icon('download')}Export evidence</button></div></div>
      ${result.hits.length ? `<div class="search-results-layout"><section class="search-results-list" aria-label="Matching batch rows"><p class="ranking-note">Ranked by BM25 lexical relevance. Scores are not confidence.</p>${visible.map((hit, position) => `<button class="search-result ${selected?.evidence.id === hit.evidence.id ? 'is-selected' : ''}" data-search-result="${escape(hit.evidence.id)}" aria-pressed="${selected?.evidence.id === hit.evidence.id}"><span class="result-meta"><span>RESULT ${String(position + 1).padStart(2, '0')}</span><span>BM25 ${hit.score.toFixed(2)}</span></span><strong class="result-batch">${escape(hit.evidence.batch)}${icon('arrow-up-right')}</strong><span class="result-title">${escape(hit.evidence.document.title)}</span><span class="result-fields">${hit.evidence.fields.map((field) => `<span class="${field.normalized === null ? 'needs-attention' : ''}"><b>${escape(field.role)}</b>${escape(cellInterpretation(field))}</span>`).join('')}</span><span class="result-matches">Matched ${hit.matchedTerms.map((term) => `<span>${escape(term)}</span>`).join('')}</span></button>`).join('')}${visible.length < result.hits.length ? `<button class="search-more" data-action="search-more">Show more results <span>${visible.length} of ${result.hits.length}</span></button>` : ''}</section>${selected ? detail(selected) : ''}</div>` : `<div class="search-no-results">${icon('search')}<h3>No matching evidence in this snapshot</h3><p>${result.reason === 'unknown_batch' ? 'This exact batch identifier is not in the corpus. Similar batch numbers have not been substituted.' : 'No row matches every search term and selected filter. Try the medicine name alone or check the exact batch identifier.'}</p><p>A missing result does not establish whether a batch is affected by a recall.</p><button data-action="reset-search">Reset search</button><a href="https://www.gov.uk/drug-device-alerts" target="_blank" rel="noreferrer">Check current MHRA notices ${icon('arrow-up-right')}</a></div>`}`
        : `<div class="search-start-grid"><div><span class="start-number">01 / RETRIEVE</span><h2>One batch. One result.</h2><p>Expiry and distribution evidence stay together. Search the actual notice text with an inspectable lexical ranking.</p></div><div><span class="start-number">02 / VERIFY</span><h2>The source stays visible.</h2><p>Read original table cells, alternative dates, and cutoff qualifiers before drawing a conclusion.</p></div><div><span class="start-number">03 / REPRODUCE</span><h2>Export the evidence.</h2><p>Keep your query, matched terms, source hashes, and table coordinates in one portable JSON file.</p></div></div>`
    }
    <details class="search-method"><summary>Retrieval method & corpus limits ${icon('chevron-right')}</summary><div><p>BM25 with k₁ = 1.2 and b = 0.75 ranks grouped table rows using notice titles, headings, original cells, and field-role aliases. All non-stop query terms must occur. Exact batch identifiers constrain results; there is no fuzzy batch matching or semantic search.</p><p>This is a frozen English MHRA corpus. The browser runs locally over the loaded snapshot, with no online OCR, model endpoint, or generated answer. The benchmark lab covers synthetic date extraction, not retrieval quality. Search rankings are not clinical validation or current recall advice.</p><small>${escape(data.attribution)}</small></div></details>
  </section>`;
}
