import type { DateRecord } from "../api";
import { groupByFamily, type Labels } from "../dateDisplay";
import { DateRow, type Decision } from "./DateRow";

interface Props {
  dates: DateRecord[];
  labels: Labels;
  selectedIds: number[];
  activeId: number | null;
  readOnly: boolean;
  onSelect(id: number): void;
  onAction(date: DateRecord, action: Decision): void;
}

/** The run's dates grouped by family (taxonomy order), each family a heading with its count. */
export function DateList({ dates, labels, selectedIds, activeId, readOnly, onSelect, onAction }: Props) {
  if (dates.length === 0) {
    return <p className="date-list__empty muted">No dates found in this document.</p>;
  }
  return (
    <div className="date-list">
      {groupByFamily(dates).map((group) => (
        <section key={group.family} className="date-group" data-family={group.family} aria-labelledby={`family-${group.family}`}>
          <h2 id={`family-${group.family}`} className="date-group__title">
            <span className="date-group__name">{labels.family(group.family)}</span>
            <span className="date-group__count">{group.dates.length}</span>
          </h2>
          <ul className="date-group__rows">
            {group.dates.map((date) => (
              <DateRow
                key={date.id}
                date={date}
                labels={labels}
                selected={selectedIds.includes(date.id)}
                active={date.id === activeId}
                readOnly={readOnly}
                onSelect={onSelect}
                onAction={onAction}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
