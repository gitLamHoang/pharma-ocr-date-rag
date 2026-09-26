# Product and Engineering Decisions

## User and Outcome

**Customer hypothesis:** a supplier-quality reviewer who receives vendor documents with many date fields. The initial workflow is to inspect a batch of documents, locate uncertain fields, and export a register with evidence.

The prototype does not yet establish demand. A discovery interview should test whether date review is frequent enough to matter, what mistakes are costly, what formats arrive, and how reviewers record decisions today. Procurement requirements, willingness to pay and time savings are unknown.

A useful pilot measure would be median time to prepare a correct date register, paired with critical date error rate and the percentage of fields requiring review. None of those customer outcomes has been measured here.

## Why These Choices

| Decision | Reason | Trade-off |
| --- | --- | --- |
| Transparent rules first | Date formats are inspectable; a failing example can become a small regression case | Limited vocabulary and layout coverage |
| Separate language from date order | Language does not prove the document's numeric convention | Reviewers must confirm ambiguous dates |
| Null plus candidates | A guessed expiry date can look falsely authoritative | Downstream consumers must handle unresolved values |
| Preserve original source positions | The reviewer can inspect the exact input span even after OCR repair | Browser boxes are rendered-fixture geometry, not measured OCR coordinates |
| Small shared field dictionary | An English expiry query can find French expiry evidence locally | This is terminology matching, not general multilingual semantic search |
| Bounded overlapping word chunks | Chunk-size experiments now use actual word budgets | A field can still split at a boundary |
| One extractor for CLI and both UIs | Exports and displayed results share parser semantics | The browser uses a generated snapshot, not a live Python service |
| Separate local review stores | Static browser demo is easy to try; SQL provides persistent local indexing | Browser localStorage and SQLite do not synchronize |
| Synthetic public corpus | Reproducible examples can be shared and inspected | Scores do not estimate real vendor-document accuracy |
| Separate real public notice corpus | Batch/date tables give a concrete source-linked search problem without private data | One English agency's templates do not represent multilingual suppliers |
| Rules versus learned column classifier | A frozen grouped split makes the comparison reproducible | Both score 80/80 test roles, with repeated headings; no model advantage demonstrated |

The public-notice workflow is now the default browser view. It has its own table-cell evidence contract, documented in the [dataset/model card](public-data.md). It does not mix public candidates with synthetic approval demonstrations. Original-PDF OCR is separately measured; native extraction performs equally well on the limited selected date-coverage task.

## Data Contract

Each date record contains document identity, the SHA-256 of decoded source text, OCR/text engine, selected language and date order, source line and character span, raw text, normalized value, alternatives, precision, contextual field label, label heuristic and review reasons.

The hash identifies the text processed, not the original image bytes or a signed audit record. Offsets address the original decoded Python string. OCR corrections preserve string length; the raw text remains unchanged in the result.

An unresolved date is represented with a null normalized value and two ISO candidates. Month precision produces YYYY-MM, never an invented day. CSV flattens lists; JSON is the lossless structured export.

## Review Policy

- Ambiguous numeric date: inspect the source and confirm DMY/MDY.
- Month precision: keep the month and confirm how the consuming workflow treats it.
- OCR repaired: inspect the original characters.
- Unknown label: inspect the context before assigning a field type.

The confidence value belongs to context classification. It is not a probability of the date being correct, and does not override review reasons. Streamlit offers per-document overrides for sample collections, with the workspace convention as the fallback. CLI folder commands accept an explicit filename-to-order map. Policies are supplied by the caller, never inferred from language or filenames; an explicit unconfirmed setting can override the workspace default. See the [convention contract](date-conventions.md).

The browser supports a per-field interpretation as a separate review decision without changing the original extraction. It does not apply folder policy maps or synchronize with the local extraction sandbox.

Both local stores require a reviewer label and reason. Browser decisions are associated with a source hash, field span and extractor version. SQL versions also include language/date-order settings. SQL history is protected against update/delete by triggers, but anyone with filesystem access can replace the database. Browser storage is editable and can be cleared. Neither store authenticates the reviewer or provides regulatory audit guarantees.

## Evaluation Contract

The original metric counts unique (document, normalized date, label) records. Duplicate occurrences are collapsed. It uses MDY because that was the declared authoring convention of those English fixtures.

The multilingual benchmark checks the entire expected list for each input, including null values, alternatives, precision and review reasons. An extra prediction or missing flag fails that case. It runs with all vocabularies enabled and with each fixture's language selected explicitly.

The corpus contains 30 multilingual field examples and 12 additional English edge cases. It was written during implementation. It is a development regression corpus, not a held-out test. A larger independently annotated set, especially actual rendered/scanned images, is needed to estimate generalization.

## Next Decision Gates

1. Validate date review as a user problem before calling this a viable product.
2. Extend the measured synthetic image and original-PDF experiments with independent annotations and harder layouts before generalizing the results.
3. Expand retrieval questions with distractors and no-answer cases before selecting a retriever.
4. Run optional model comparisons under the same schema and record hardware, model version, latency, cost and accuracy before making model recommendations.
5. Evaluate review-cycle, identity, synchronization and per-document settings before describing a shared operational workflow.
