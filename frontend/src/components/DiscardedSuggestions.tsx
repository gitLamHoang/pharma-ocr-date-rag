import { useQuery } from "@tanstack/react-query";
import { api, type DiscardedSuggestion } from "../api";
import type { Labels } from "../dateDisplay";

interface Props {
  runId: number;
  labels: Labels;
}

/** What the AI suggested, by the classifier's `kind`. */
const KIND: Record<string, string> = {
  transcription: "Transcribed date",
  missed_date: "Missed date",
  label: "Label",
  resolution: "Reading choice",
};

function text(item: DiscardedSuggestion, field: string): string | null {
  const value = item[field];
  return typeof value === "string" && value.trim() ? value : null;
}

/** "Label for p1-c9 · suggested as Approval date": what was suggested, never a date value. */
function describe(item: DiscardedSuggestion, labels: Labels): string {
  const parts = [KIND[item.kind] ?? item.kind];
  const candidate = text(item, "candidate_id");
  if (candidate && item.kind !== "transcription") parts[0] += ` for ${candidate}`;
  const type = text(item, "date_type");
  if (type) parts.push(`suggested as ${labels.type(type)}`);
  return parts.join(" · ");
}

/**
 * AI suggestions that failed verification against the page text: a collapsed debug list, kept
 * apart from the dates. Items show the AI's own words and why they were dropped; no value is
 * derived from them, they get no box on the page and no review actions.
 */
export function DiscardedSuggestions({ runId, labels }: Props) {
  const discarded = useQuery({ queryKey: ["discarded", runId], queryFn: () => api.getDiscarded(runId) });

  if (discarded.isError) {
    return (
      <p className="discarded__failure" role="alert">
        Could not load the discarded AI suggestions. {discarded.error.message}{" "}
        <button type="button" className="text-button" onClick={() => void discarded.refetch()}>
          Retry
        </button>
      </p>
    );
  }
  if (!discarded.data || discarded.data.length === 0) return null;

  return (
    <details className="discarded">
      <summary className="discarded__summary">
        <span className="discarded__title">Discarded AI suggestions</span>
        <span className="date-group__count">{discarded.data.length}</span>
      </summary>
      <p className="discarded__intro muted">
        The AI suggested these, but the page text does not bear them out. They are not dates: they are not
        reviewed, drawn on the page or exported.
      </p>
      <ul className="discarded__list">
        {discarded.data.map((item, i) => {
          const verbatim = text(item, "verbatim_text");
          const evidence = text(item, "evidence");
          return (
            <li key={i} className="discarded__item">
              <p className="discarded__head">
                {verbatim ? <span className="mono discarded__quote">{verbatim}</span> : null}
                <span className="muted">Page {item.page}</span>
              </p>
              <p>{describe(item, labels)}</p>
              {evidence ? <p className="discarded__quote">Evidence “{evidence}”</p> : null}
              <p className="muted">Discarded: {item.reason}</p>
            </li>
          );
        })}
      </ul>
    </details>
  );
}
