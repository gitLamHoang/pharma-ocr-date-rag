# Project roadmap

This roadmap separates shipped behavior from future experiments. The actual commit history records when work was done.

## Implemented

- Date normalization and context labels on synthetic fixtures.
- Optional image OCR adapters; the reproducible path uses plain text.
- Source-chunk retrieval and a three-query chunk-size experiment.
- Per-label extraction evaluation with hashed input/source evidence.
- Local SQLite review queue, versioned document evidence, and persistent decisions.
- Automated tests, linting, formatting, and reproducibility checks in CI.

## Next bounded milestones

1. Define and collect an independently labeled document set with appropriate permission; include ambiguous and failed extractions.
2. Observe a consented reviewer workflow and measure corrections and review time against manual date lookup.
3. Add explicit document retirement and review-cycle semantics so a file reversion can require a fresh review when needed.
4. Exercise real-image OCR adapters on known test scans and record engine/package versions; do not infer OCR accuracy from text fixtures.
5. Add authenticated multi-user service behavior only if reviewer trials justify that scope. See the [scaling boundary](architecture.md#scaling-boundary).

## Not yet measured or implemented

No Mistral/Phi-2 comparison, semantic-model benchmark, user adoption study, production deployment, or compliance validation is claimed. The installed-only LlamaIndex helper is not a retrieval implementation.
