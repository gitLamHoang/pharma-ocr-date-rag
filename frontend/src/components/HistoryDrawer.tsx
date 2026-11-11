import { useQuery } from "@tanstack/react-query";
import { api, type ReviewAction, type ReviewEvent } from "../api";
import { formatTimestamp, type Labels } from "../dateDisplay";

interface Props {
  dateId: number;
  labels: Labels;
}

const DONE: Record<ReviewAction, string> = {
  accept: "Accepted",
  correct: "Corrected",
  reject: "Rejected",
  reopen: "Reopened",
};

function Changes({ event, labels }: { event: ReviewEvent; labels: Labels }) {
  if (!event.new_type && !event.new_value) return null;
  return (
    <p className="history__change">
      {event.new_type ? `Type ${labels.type(event.new_type)}` : null}
      {event.new_type && event.new_value ? " · " : null}
      {event.new_value ? (
        <>
          value <span className="mono">{event.new_value}</span>
        </>
      ) : null}
    </p>
  );
}

function HistoryEvent({ event, labels }: { event: ReviewEvent; labels: Labels }) {
  const carried = event.carried_from_run !== null ? `Carried over from run ${event.carried_from_run}` : null;
  // A carried decision's stored reason is usually just that sentence: say it once.
  const reason = carried && event.reason.trim().toLowerCase() === carried.toLowerCase() ? null : event.reason;
  return (
    <li className="history__event">
      <p>
        <span className="history__action">
          {DONE[event.action]} by {event.reviewer}
        </span>
        <span className="muted">
          {" · "}
          <time dateTime={event.at}>{formatTimestamp(event.at)}</time>
        </span>
      </p>
      <Changes event={event} labels={labels} />
      {reason ? <p className="muted">{reason}</p> : null}
      {carried ? <p className="muted">{carried}</p> : null}
    </li>
  );
}

/** A date's review decisions, newest first. Append-only: nothing here can be edited. */
export function HistoryDrawer({ dateId, labels }: Props) {
  const history = useQuery({ queryKey: ["history", dateId], queryFn: () => api.getHistory(dateId) });

  let body;
  if (history.isPending) {
    body = (
      <p className="history__line">
        <span className="bar bar--time" />
      </p>
    );
  } else if (history.isError) {
    body = (
      <p className="history__line history__failure" role="alert">
        Could not load the history. {history.error.message}{" "}
        <button type="button" className="text-button" onClick={() => void history.refetch()}>
          Retry
        </button>
      </p>
    );
  } else if (history.data.length === 0) {
    body = <p className="history__line muted">No decisions yet.</p>;
  } else {
    body = (
      <ol className="history__list">
        {/* Events are append-only, so a higher id is always a later decision. */}
        {[...history.data]
          .sort((a, b) => b.id - a.id)
          .map((event) => (
            <HistoryEvent key={event.id} event={event} labels={labels} />
          ))}
      </ol>
    );
  }

  return (
    <section className="history" aria-label="Review history">
      {body}
    </section>
  );
}
