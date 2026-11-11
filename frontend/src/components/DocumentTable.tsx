import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { DocumentSummary } from "../api";
import { StatusBadge } from "./StatusBadge";

interface Props {
  /** The rows; `undefined` while the first load is in flight. */
  documents: DocumentSummary[] | undefined;
  /** Replaces the rows with one sentence (an error with its retry, for example). */
  notice?: ReactNode;
}

const COLUMNS = 7;
const SKELETON_ROWS = 3;

/** `2026-11-11 09:05` in the reader's local time. */
function formatUploaded(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())} ${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

function Missing() {
  return (
    <>
      <span className="muted" aria-hidden="true">
        —
      </span>
      <span className="visually-hidden">No value yet</span>
    </>
  );
}

function plural(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

/** The figures a phone moves under the name: "3 pages · 12 dates · 2 flags". */
function phoneFigures(doc: DocumentSummary): string {
  const parts = doc.pages > 0 ? [plural(doc.pages, "page")] : [];
  if (doc.status === "done") parts.push(plural(doc.n_dates, "date"), plural(doc.n_flags, "flag"));
  return parts.join(" · ");
}

/** Counts only mean something once the run is done; until then they print as a dash. */
function Count({ value, known }: { value: number; known: boolean }) {
  return <td className="num doc-table__minor">{known ? value : <Missing />}</td>;
}

/** The documents, newest first: name, pages, status, dates, flags, needs review, uploaded at. */
export function DocumentTable({ documents, notice }: Props) {
  let body: ReactNode;
  if (notice) body = <MessageRow>{notice}</MessageRow>;
  else if (documents === undefined) body = <SkeletonRows />;
  else if (documents.length === 0) {
    body = <MessageRow>No documents yet. Drop a PDF or scan above, or choose a file.</MessageRow>;
  } else body = documents.map((doc) => <Row key={doc.id} doc={doc} />);

  return (
    <table className="doc-table" aria-label="Documents" aria-busy={documents === undefined && !notice}>
      <thead>
        <tr>
          <th scope="col" className="doc-table__name">
            Name
          </th>
          <th scope="col" className="doc-table__pages num doc-table__minor">
            Pages
          </th>
          <th scope="col" className="doc-table__status">
            Status
          </th>
          <th scope="col" className="doc-table__count num doc-table__minor">
            Dates
          </th>
          <th scope="col" className="doc-table__count num doc-table__minor">
            Flags
          </th>
          <th scope="col" className="doc-table__review num">
            Needs review
          </th>
          <th scope="col" className="doc-table__uploaded">
            Uploaded
          </th>
        </tr>
      </thead>
      <tbody>{body}</tbody>
    </table>
  );
}

function Row({ doc }: { doc: DocumentSummary }) {
  const done = doc.status === "done";
  const uploaded = formatUploaded(doc.created_at);
  return (
    <tr>
      <td className="doc-table__name">
        <Link to={`/documents/${doc.id}`} className="doc-table__link" title={doc.name}>
          {doc.name}
        </Link>
        {doc.status === "failed" && doc.error ? <p className="doc-table__error">{doc.error}</p> : null}
        {/* Shown only where the matching cells are hidden (CSS), so each fact is read once. */}
        <p className="doc-table__subline doc-table__subline--phone">{phoneFigures(doc)}</p>
        <time className="doc-table__subline" dateTime={doc.created_at}>
          {uploaded}
        </time>
      </td>
      <td className="num doc-table__minor">{doc.pages > 0 ? doc.pages : <Missing />}</td>
      <td className="doc-table__status">
        <StatusBadge status={doc.status} />
      </td>
      <Count value={doc.n_dates} known={done} />
      <Count value={doc.n_flags} known={done} />
      <td className="num">
        {!done ? (
          <Missing />
        ) : doc.n_needs_review > 0 ? (
          <span className="pill pill--review">{doc.n_needs_review}</span>
        ) : (
          0
        )}
      </td>
      <td className="doc-table__uploaded">
        <time dateTime={doc.created_at}>{uploaded}</time>
      </td>
    </tr>
  );
}

function MessageRow({ children }: { children: ReactNode }) {
  return (
    <tr className="doc-table__message">
      <td colSpan={COLUMNS}>{children}</td>
    </tr>
  );
}

function SkeletonRows() {
  return Array.from({ length: SKELETON_ROWS }, (_, i) => (
    <tr key={i} className="doc-table__skeleton" aria-hidden="true">
      <td>
        <span className="bar" style={{ width: `${48 - i * 8}%` }} />
      </td>
      <td className="num doc-table__minor">
        <span className="bar bar--num" />
      </td>
      <td>
        <span className="bar bar--pill" />
      </td>
      <td className="num doc-table__minor">
        <span className="bar bar--num" />
      </td>
      <td className="num doc-table__minor">
        <span className="bar bar--num" />
      </td>
      <td className="num">
        <span className="bar bar--num" />
      </td>
      <td className="doc-table__uploaded">
        <span className="bar bar--time" />
      </td>
    </tr>
  ));
}
