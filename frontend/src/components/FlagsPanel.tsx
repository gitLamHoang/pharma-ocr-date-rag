import { useState } from "react";
import type { Flag, Severity } from "../api";

interface Props {
  flags: Flag[];
  activeFlagId: number | null;
  onSelectFlag(flag: Flag): void;
}

/** Past this many, the list shows the first ones (errors first) and offers the rest. */
const SHOWN = 5;

const RANK: Record<Severity, number> = { error: 0, warning: 1, info: 2 };
const LABEL: Record<Severity, string> = { error: "Error", warning: "Warning", info: "Info" };
const TONE: Record<Severity, string> = { error: "pill--danger", warning: "pill--warning", info: "pill--info" };

/** The run's consistency flags, errors first. Clicking one selects the dates it is about. */
export function FlagsPanel({ flags, activeFlagId, onSelectFlag }: Props) {
  const [all, setAll] = useState(false);
  const ordered = [...flags].sort((a, b) => RANK[a.severity] - RANK[b.severity]);
  const folded = !all && ordered.length > SHOWN + 1;
  const shown = folded ? ordered.slice(0, SHOWN) : ordered;

  return (
    <section className="flags" aria-labelledby="flags-title">
      <h2 id="flags-title" className="date-group__title">
        <span className="date-group__name">Flags</span>
        <span className="date-group__count">{flags.length}</span>
      </h2>
      {ordered.length === 0 ? (
        <p className="flags__empty muted">No consistency flags on this run.</p>
      ) : (
        <ul className="flags__list">
          {shown.map((flag) => (
            <li key={flag.id}>
              <button
                type="button"
                className="flag"
                aria-pressed={flag.id === activeFlagId}
                onClick={() => onSelectFlag(flag)}
              >
                <span className={`pill ${TONE[flag.severity]}`}>{LABEL[flag.severity]}</span>
                <span className="flag__message">{flag.message}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {folded ? (
        <button type="button" className="text-button flags__more" onClick={() => setAll(true)}>
          Show all {ordered.length} flags
        </button>
      ) : null}
    </section>
  );
}
