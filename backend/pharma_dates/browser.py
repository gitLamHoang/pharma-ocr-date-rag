"""The rules-only pipeline over ready-made page layouts, for the static build (Pyodide in a browser).

The browser reads the pages itself (pdf.js text layer or tesseract.js) and hands their layouts here
as JSON; this runs the same steps as the server pipeline with AI off: rule candidates, offline
labels, document-order resolution and validation. JSON in, JSON out.

Standard library and pydantic only (the static build bundles this module with the pure core).
"""

from __future__ import annotations

import json
from datetime import date

from . import taxonomy
from .candidates import apply_document_order, page_candidates, transcription_candidates
from .classify import label_page
from .models import PageLayout
from .validate import validate


def process(layouts_json: str, today: str | None = None) -> str:
    """`{"dates": [LabeledDate...], "flags": [Flag...]}` for a document's page layouts (a JSON list
    of `PageLayout`). `today` (ISO date) is the date the validation rules compare against."""
    layouts = [PageLayout.model_validate(item) for item in json.loads(layouts_json)]
    labeled = []
    for layout in layouts:
        rules = page_candidates(layout)
        cands = rules + transcription_candidates(layout, rules)
        page_dates, _ = label_page(layout, cands, None)
        labeled.extend(page_dates)
    dates = apply_document_order(labeled)
    flags = validate(dates, date.fromisoformat(today) if today else date.today())
    return json.dumps(
        {
            "dates": [d.model_dump(mode="json") for d in dates],
            "flags": [f.model_dump(mode="json") for f in flags],
        },
        ensure_ascii=False,
    )


def taxonomy_json() -> str:
    """The date taxonomy as `GET /api/taxonomy` returns it."""
    return json.dumps(taxonomy.as_json(), ensure_ascii=False)
