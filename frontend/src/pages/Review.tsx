import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api, type DateRecord, type Flag, type ReviewBody, type RunStatus, type RunSummary } from "../api";
import { DateList } from "../components/DateList";
import type { Decision } from "../components/DateRow";
import { FlagsPanel } from "../components/FlagsPanel";
import { PageViewer } from "../components/PageViewer";
import { ReviewDialog } from "../components/ReviewDialog";
import { StatusBadge } from "../components/StatusBadge";
import { groupByFamily, makeLabels } from "../dateDisplay";

/** While the run is still moving, the document is re-read this often. */
const POLL_MS = 2000;

const MOVING: Partial<Record<RunStatus, string>> = {
  queued: "Waiting to start.",
  reading: "Reading the pages.",
  classifying: "Classifying the dates.",
  validating: "Checking the dates against each other.",
};

interface Selection {
  ids: number[];
  active: number | null;
  flag: number | null;
}

const NOTHING: Selection = { ids: [], active: null, flag: null };

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "";
}

function moving(run: RunSummary | null | undefined): boolean {
  return !!run && run.status in MOVING;
}

/** True when a key press belongs to a field or the open dialog, not to the screen's shortcuts. */
function typing(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest("input, textarea, select, [contenteditable='true'], dialog") !== null;
}

/** One document's dates next to its pages: confirm, correct or reject each. */
export function Review() {
  const params = useParams();
  const documentId = Number(params.id);
  const [search, setSearch] = useSearchParams();
  const pinned = Number(search.get("run")) || null;
  const queryClient = useQueryClient();

  const detail = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api.getDocument(documentId),
    enabled: Number.isInteger(documentId),
    refetchInterval: (query) => (moving(query.state.data?.run) ? POLL_MS : false),
  });
  const latest = detail.data?.run ?? null;
  const runId = pinned ?? latest?.id ?? null;
  const showsLatest = latest !== null && runId === latest.id;
  const ready = runId !== null && detail.data !== undefined && (!showsLatest || latest.status === "done");

  const dates = useQuery({ queryKey: ["dates", runId], queryFn: () => api.getDates(runId!), enabled: ready });
  const flags = useQuery({ queryKey: ["flags", runId], queryFn: () => api.getFlags(runId!), enabled: ready });
  const taxonomy = useQuery({ queryKey: ["taxonomy"], queryFn: () => api.getTaxonomy(), staleTime: Infinity });
  const labels = useMemo(() => makeLabels(taxonomy.data), [taxonomy.data]);

  const [replaced, setReplaced] = useState<number | null>(null);
  const frozen = runId !== null && latest !== null && !showsLatest;
  const readOnly = frozen || replaced === runId;

  const [selection, setSelection] = useState<Selection>(NOTHING);
  const [dialog, setDialog] = useState<{ date: DateRecord; action: Decision } | null>(null);
  const scrollRow = useRef(false);

  const ordered = useMemo(() => groupByFamily(dates.data ?? []).flatMap((g) => g.dates), [dates.data]);
  const active = ordered.find((d) => d.id === selection.active) ?? null;

  // A different run is a different set of dates: drop the old selection.
  const [selectionRun, setSelectionRun] = useState(runId);
  if (selectionRun !== runId) {
    setSelectionRun(runId);
    setSelection(NOTHING);
  }

  function select(id: number, scroll = false) {
    scrollRow.current = scroll;
    setSelection({ ids: [id], active: id, flag: null });
  }

  function selectFlag(flag: Flag) {
    const ids = flag.date_ids.filter((id) => ordered.some((d) => d.id === id));
    scrollRow.current = true;
    setSelection({ ids, active: ids[0] ?? null, flag: flag.id });
  }

  function decide(date: DateRecord, action: Decision) {
    if (!readOnly) setDialog({ date, action });
  }

  useEffect(() => {
    if (!scrollRow.current || selection.active === null) return;
    scrollRow.current = false;
    document.querySelector(`[data-date-id="${selection.active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [selection]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (dialog || event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || typing(event.target)) return;
      if (ordered.length === 0) return;
      const at = active ? ordered.indexOf(active) : -1;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const next = event.key === "ArrowDown" ? Math.min(at + 1, ordered.length - 1) : Math.max(at - 1, 0);
        select(ordered[next]!.id, true);
      } else if (active && (event.key === "a" || event.key === "A")) {
        event.preventDefault();
        decide(active, "accept");
      } else if (active && (event.key === "e" || event.key === "E")) {
        event.preventDefault();
        decide(active, "correct");
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  async function submitReview(body: ReviewBody) {
    const date = dialog!.date;
    try {
      await api.reviewDate(date.id, body);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setDialog(null);
        setReplaced(runId);
        setSearch({ run: String(runId) }, { replace: true });
        void queryClient.invalidateQueries({ queryKey: ["document", documentId] });
        return;
      }
      throw error;
    }
    setDialog(null);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["dates", runId] }),
      queryClient.invalidateQueries({ queryKey: ["history", date.id] }),
      queryClient.invalidateQueries({ queryKey: ["documents"] }),
    ]);
  }

  function reload() {
    setReplaced(null);
    setSearch({}, { replace: true });
    void queryClient.invalidateQueries({ queryKey: ["document", documentId] });
  }

  if (!Number.isInteger(documentId) || (detail.isError && detail.error instanceof ApiError && detail.error.status === 404)) {
    return (
      <div className="screen">
        <TitleRow name="Document not found" />
        <p className="review__message">
          <span>{detail.isError ? detail.error.message : "This address does not name a document."}</span>{" "}
          <Link to="/">Back to documents</Link>
        </p>
      </div>
    );
  }

  if (detail.isError) {
    return (
      <div className="screen">
        <TitleRow name="Document" />
        <p className="review__message review__message--failure" role="alert">
          Could not load the document. {messageOf(detail.error)}{" "}
          <button type="button" className="text-button" onClick={() => void detail.refetch()}>
            Retry
          </button>
        </p>
      </div>
    );
  }

  const doc = detail.data;
  const needReview = dates.data?.filter((d) => d.status === "needs_review").length;

  return (
    <div className="screen review-screen">
      <TitleRow name={doc?.document.filename ?? null}>
        {dates.data ? (
          <p className="review__summary">
            <span className={needReview ? "pill pill--review" : "pill"}>{needReview}</span>
            <span>need review</span>
            <span className="muted">
              · {dates.data.length} {dates.data.length === 1 ? "date" : "dates"}
            </span>
          </p>
        ) : null}
      </TitleRow>

      {replaced !== null && replaced === runId ? (
        <p className="notice notice--alert" role="alert">
          <span>This run was replaced — reload to review the latest run. Nothing was saved.</span>
          <button type="button" className="button" onClick={reload}>
            Reload
          </button>
        </p>
      ) : frozen ? (
        <p className="notice" role="status">
          <span>
            Run {runId} is frozen: run {latest!.id} replaced it, so its dates are read-only.
          </span>
          <Link className="button" to={`/documents/${documentId}`}>
            Open the latest run
          </Link>
        </p>
      ) : null}

      {doc === undefined ? (
        <ReviewSkeleton />
      ) : latest === null ? (
        <p className="review__message">This document has not been processed yet.</p>
      ) : showsLatest && latest.status === "failed" ? (
        <div className="review__message review__message--failure" role="alert">
          <p className="review__failure-title">
            <StatusBadge status="failed" /> The run could not read this document.
          </p>
          <p>{latest.error ?? "No reason was given."}</p>
        </div>
      ) : showsLatest && moving(latest) ? (
        <div className="review__message" role="status">
          <p className="review__failure-title">
            <StatusBadge status={latest.status} /> {MOVING[latest.status]}
          </p>
          <p className="muted">The dates appear here when the run is done. This page updates by itself.</p>
        </div>
      ) : (
        <div className="review">
          <div className="review__viewer">
            <PageViewer
              documentId={documentId}
              pages={doc.pages}
              dates={dates.data ?? []}
              selectedId={selection.active}
              linkedIds={selection.ids}
              onSelect={(id) => select(id, true)}
            />
          </div>
          <aside className="review__panel" aria-label="Dates">
            {dates.isError || flags.isError ? (
              <p className="review__message review__message--failure" role="alert">
                Could not load the dates. {messageOf(dates.error ?? flags.error)}{" "}
                <button
                  type="button"
                  className="text-button"
                  onClick={() => {
                    void dates.refetch();
                    void flags.refetch();
                  }}
                >
                  Retry
                </button>
              </p>
            ) : dates.data && flags.data ? (
              <>
                <FlagsPanel flags={flags.data} activeFlagId={selection.flag} onSelectFlag={selectFlag} />
                <DateList
                  dates={dates.data}
                  labels={labels}
                  selectedIds={selection.ids}
                  activeId={selection.active}
                  readOnly={readOnly}
                  onSelect={(id) => select(id)}
                  onAction={decide}
                />
              </>
            ) : (
              <PanelSkeleton />
            )}
          </aside>
        </div>
      )}

      {dialog ? (
        <ReviewDialog
          key={`${dialog.date.id}-${dialog.action}`}
          date={dialog.date}
          action={dialog.action}
          taxonomy={taxonomy.data}
          labels={labels}
          onSubmit={submitReview}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </div>
  );
}

function TitleRow({ name, children }: { name: string | null; children?: ReactNode }) {
  return (
    <header className="title-row review-title">
      <div className="review-title__name">
        <nav aria-label="Breadcrumb" className="breadcrumb">
          <Link to="/">Documents</Link>
          <span aria-hidden="true"> /</span>
        </nav>
        {name === null ? (
          <h1>
            <span className="bar bar--title" />
            <span className="visually-hidden">Loading document</span>
          </h1>
        ) : (
          <h1 title={name}>{name}</h1>
        )}
      </div>
      {children ? <div className="title-row__actions">{children}</div> : null}
    </header>
  );
}

function PanelSkeleton() {
  return (
    <div className="panel-skeleton" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="panel-skeleton__row">
          <span className="bar bar--time" />
          <span className="bar bar--wide" />
        </div>
      ))}
    </div>
  );
}

function ReviewSkeleton() {
  return (
    <div className="review" aria-hidden="true">
      <div className="review__viewer">
        <div className="viewer viewer--empty" />
      </div>
      <div className="review__panel">
        <PanelSkeleton />
      </div>
    </div>
  );
}
