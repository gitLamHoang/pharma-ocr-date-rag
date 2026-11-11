import { useEffect, useId, useRef, useState } from "react";
import { api } from "../api";

interface Props {
  documentId: number;
  /** The run the new one replaces; it stays as a frozen record. */
  latestRunId: number;
  pages: number;
  /** A run is still moving: a new one cannot start yet. */
  busy?: boolean;
  /** The new run exists; the screen switches to it. */
  onStarted(runId: number): Promise<void> | void;
}

/** Read the document again in a new run, after the reviewer confirms. */
export function ReprocessButton({ documentId, latestRunId, pages, busy = false, onStarted }: Props) {
  const [confirming, setConfirming] = useState(false);
  const busyId = useId();

  return (
    <>
      <button
        type="button"
        className="button"
        disabled={busy}
        aria-describedby={busy ? busyId : undefined}
        onClick={() => setConfirming(true)}
      >
        Reprocess
      </button>
      {busy ? (
        <span id={busyId} className="visually-hidden">
          A run is in progress.
        </span>
      ) : null}
      {confirming ? (
        <ConfirmDialog
          documentId={documentId}
          latestRunId={latestRunId}
          pages={pages}
          onStarted={async (runId) => {
            await onStarted(runId);
            setConfirming(false);
          }}
          onClose={() => setConfirming(false)}
        />
      ) : null}
    </>
  );
}

interface DialogProps {
  documentId: number;
  latestRunId: number;
  pages: number;
  onStarted(runId: number): Promise<void>;
  onClose(): void;
}

function ConfirmDialog({ documentId, latestRunId, pages, onStarted, onClose }: DialogProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [starting, setStarting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);

  async function start() {
    setStarting(true);
    setFailure(null);
    try {
      const { run_id } = await api.reprocess(documentId);
      await onStarted(run_id);
    } catch (error) {
      setFailure(error instanceof Error && error.message ? error.message : "The new run could not start. Try again.");
      setStarting(false);
    }
  }

  return (
    <dialog
      ref={dialog}
      className="review-dialog"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="review-dialog__form">
        <header className="review-dialog__head">
          <h2 id={titleId}>Reprocess this document?</h2>
        </header>
        <div className="reprocess__body">
          <p>
            A new run reads {pages > 1 ? `all ${pages} pages` : pages === 1 ? "the page" : "the document"} again with the current pipeline and
            replaces run {latestRunId} as the one you review.
          </p>
          <p>
            Decisions carry over to a date when its page, printed text and value match exactly. Every other date
            starts as needs review.
          </p>
          <p className="muted">Run {latestRunId} stays as a read-only record, with its decisions and exports.</p>
        </div>
        {failure ? (
          <p className="review-dialog__failure" role="alert">
            {failure}
          </p>
        ) : null}
        <footer className="review-dialog__actions">
          <button type="button" className="button" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="button button--primary" disabled={starting} onClick={() => void start()}>
            {starting ? "Starting" : "Reprocess document"}
          </button>
        </footer>
      </div>
    </dialog>
  );
}
