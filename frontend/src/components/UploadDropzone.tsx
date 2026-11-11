import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type DragEvent } from "react";

/** The server's limits (Settings.max_upload_mb); the page limit is checked server-side. */
const MAX_UPLOAD_MB = 50;
const EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"];
const ACCEPT = [...EXTENSIONS, "application/pdf", "image/png", "image/jpeg", "image/tiff"].join(",");

export interface UploadDropzoneHandle {
  /** Open the system file picker (the title row's upload button uses this). */
  open(): void;
}

interface Props {
  /** Called with the files that passed the client-side checks; never called with an empty list. */
  onAccept(files: File[]): void;
  /** The upload in progress, shown in words ("coa.pdf", "coa.pdf (2 of 3)"). */
  uploading?: string | null;
  /** A server error to show under the zone, as written. */
  error?: string | null;
}

/** Why a file cannot be uploaded, or null when it can. */
function rejection(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return `${file.name} is not a supported file. Upload a PDF, PNG, JPG or TIFF.`;
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `${file.name} is larger than ${MAX_UPLOAD_MB} MB.`;
  return null;
}

function carriesFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes("Files");
}

/** A dashed band across the sheet: drop files on it or choose them. Rejects unsupported files before upload. */
export const UploadDropzone = forwardRef<UploadDropzoneHandle, Props>(function UploadDropzone(
  { onAccept, uploading = null, error = null },
  ref,
) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<string[]>([]);
  const busy = uploading !== null;

  useImperativeHandle(ref, () => ({ open: () => input.current?.click() }), []);

  // A file dropped beside the zone would make the browser open it and leave the app.
  useEffect(() => {
    const stop = (event: globalThis.DragEvent) => {
      if (event.dataTransfer?.types.includes("Files")) event.preventDefault();
    };
    window.addEventListener("dragover", stop);
    window.addEventListener("drop", stop);
    return () => {
      window.removeEventListener("dragover", stop);
      window.removeEventListener("drop", stop);
    };
  }, []);

  function take(list: FileList | File[] | null | undefined) {
    const files = Array.from(list ?? []);
    if (files.length === 0 || busy) return;
    const reasons = files.map(rejection);
    setRejected(reasons.filter((r): r is string => r !== null));
    const accepted = files.filter((_, i) => reasons[i] === null);
    if (accepted.length > 0) onAccept(accepted);
  }

  const messages = [...rejected, ...(error ? [error] : [])];

  return (
    <div className="upload">
      <div
        className="dropzone"
        data-testid="dropzone"
        data-dragging={dragging || undefined}
        aria-busy={busy || undefined}
        onDragEnter={(event) => {
          if (!carriesFiles(event)) return;
          event.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragOver={(event) => {
          if (!carriesFiles(event)) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = busy ? "none" : "copy";
        }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          take(event.dataTransfer?.files);
        }}
      >
        <input
          ref={input}
          className="visually-hidden"
          type="file"
          accept={ACCEPT}
          multiple
          tabIndex={-1}
          aria-label="Choose files to upload"
          onChange={(event) => {
            take(event.currentTarget.files);
            // Let the same file be chosen again after a fix.
            event.currentTarget.value = "";
          }}
        />
        <UploadMark />
        <div className="dropzone__text">
          <p className="dropzone__line">
            {busy ? (
              "Drop more files once this upload finishes"
            ) : (
              <>
                Drop PDFs or scans here, or{" "}
                <button type="button" className="text-button" onClick={() => input.current?.click()}>
                  choose files
                </button>
              </>
            )}
          </p>
          <p className="dropzone__hint">PDF, PNG, JPG or TIFF, up to {MAX_UPLOAD_MB} MB and 100 pages each</p>
        </div>
        <p className="dropzone__status" role="status">
          {busy ? (
            <>
              Uploading <span className="dropzone__file">{uploading}</span>
            </>
          ) : null}
        </p>
        {busy ? <span className="dropzone__progress" aria-hidden="true" /> : null}
      </div>
      {messages.length > 0 ? (
        <ul className="upload__errors" role="alert">
          {messages.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
});

/** A page with an arrow out of it, in the same stroke as the brand mark's box. */
function UploadMark() {
  return (
    <svg className="dropzone__mark" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M12 17v-6m-2.5 2.5L12 11l2.5 2.5" />
    </svg>
  );
}
