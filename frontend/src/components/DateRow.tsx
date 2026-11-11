import { useState } from "react";
import type { DateRecord, DateStatus, ReviewAction } from "../api";
import { isAmbiguous, monthLabel, snippet, type Labels } from "../dateDisplay";
import { HistoryDrawer } from "./HistoryDrawer";

export type Decision = Exclude<ReviewAction, "reopen">;

interface Props {
  date: DateRecord;
  labels: Labels;
  /** Part of the selection (the clicked date, or every date of the clicked flag). */
  selected: boolean;
  /** The one date the actions and the keyboard work on. */
  active: boolean;
  readOnly: boolean;
  onSelect(id: number): void;
  onAction(date: DateRecord, action: Decision): void;
}

const STATUS: Record<DateStatus, { label: string; tone: string }> = {
  needs_review: { label: "Needs review", tone: "pill" },
  accepted: { label: "Accepted", tone: "pill pill--positive" },
  corrected: { label: "Corrected", tone: "pill pill--positive" },
  rejected: { label: "Rejected", tone: "pill pill--danger" },
};

/** The value as the reviewer must read it: one ISO value, a month, or the readings to choose from. */
export function DateValue({ date }: { date: DateRecord }) {
  let body;
  if (isAmbiguous(date)) {
    body = date.candidates.map((reading, i) => (
      <span key={reading}>
        {i > 0 ? <span className="muted"> or </span> : null}
        <span className="mono">{reading}</span>
      </span>
    ));
  } else if (date.current_value === null) {
    body = (
      <>
        <span className="muted" aria-hidden="true">
          —
        </span>
        <span className="visually-hidden">No value</span>
      </>
    );
  } else {
    const month = monthLabel(date.current_value);
    body = (
      <>
        <span className="mono">{date.current_value}</span>
        {month ? <span className="date-value__month">{month}</span> : null}
      </>
    );
  }
  return (
    <span className="date-value" data-testid="date-value">
      {body}
    </span>
  );
}

function Source({ source }: { source: DateRecord["source"] }) {
  if (source === "ai_only") return <span className="pill pill--info">AI-only · verify</span>;
  return <span>{source === "rules" ? "Rules" : "Rules + AI"}</span>;
}

/** The page's words around the date, with the date itself in ink. */
function Context({ context, raw, wide }: { context: string; raw: string; wide: boolean }) {
  const { before, match, after } = snippet(context, raw, wide ? 120 : 40);
  return (
    <span className="date-row__context">
      {before}
      {match ? <span className="date-row__match">{match}</span> : null}
      {after}
    </span>
  );
}

/** One date: value and type, the page's own words, where it is, where it came from, its status. */
export function DateRow({ date, labels, selected, active, readOnly, onSelect, onAction }: Props) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const status = STATUS[date.status];

  return (
    <li className="date-row" data-date-id={date.id} data-selected={selected || undefined} data-active={active || undefined}>
      <button
        type="button"
        className="date-row__select"
        aria-pressed={selected}
        aria-current={active || undefined}
        onClick={() => onSelect(date.id)}
      >
        <span className="date-row__head">
          <DateValue date={date} />
          <span className={status.tone}>{status.label}</span>
        </span>
        <span className="date-row__type">
          {labels.type(date.current_type)}
          {date.qualifier ? <span className="muted"> · {date.qualifier}</span> : null}
        </span>
        <span className="date-row__meta">
          <span className="mono date-row__raw">{date.raw_text}</span>
          <span>Page {date.page}</span>
          <Source source={date.source} />
          <span>
            Confidence <span className="mono">{date.confidence.toFixed(2)}</span>
          </span>
        </span>
        {date.context ? <Context context={date.context} raw={date.raw_text} wide={active} /> : null}
        {!isAmbiguous(date) && date.candidates.length > 1 ? (
          <span className="date-row__note">
            Also readable as{" "}
            {date.candidates
              .filter((c) => c !== date.current_value)
              .map((c, i) => (
                <span key={c}>
                  {i > 0 ? " or " : null}
                  <span className="mono">{c}</span>
                </span>
              ))}
            {date.evidence ? <> · evidence “{date.evidence}”</> : null}
          </span>
        ) : null}
        {date.carried_from_run !== null ? (
          <span className="date-row__note">Carried over from run {date.carried_from_run}</span>
        ) : null}
        {date.bbox === null ? <span className="date-row__note">No box on the page for this date</span> : null}
      </button>

      {active ? (
        <div className="date-row__actions">
          {readOnly ? null : (
            <>
              <button type="button" className="button" onClick={() => onAction(date, "accept")}>
                Accept <kbd>A</kbd>
              </button>
              <button type="button" className="button" onClick={() => onAction(date, "correct")}>
                Edit <kbd>E</kbd>
              </button>
              <button type="button" className="button button--danger" onClick={() => onAction(date, "reject")}>
                Reject
              </button>
            </>
          )}
          <button
            type="button"
            className="button button--quiet date-row__history"
            aria-expanded={historyOpen}
            onClick={() => setHistoryOpen((open) => !open)}
          >
            History
          </button>
        </div>
      ) : null}
      {active && historyOpen ? <HistoryDrawer dateId={date.id} labels={labels} /> : null}
    </li>
  );
}
