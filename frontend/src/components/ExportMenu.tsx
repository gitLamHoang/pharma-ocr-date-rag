import { useEffect, useId, useRef, useState } from "react";
import { api, type ExportFormat } from "../api";

interface Props {
  /** The run on screen; a frozen run exports its own dates. */
  runId: number;
}

const FORMATS: { format: ExportFormat; label: string; hint: string }[] = [
  { format: "csv", label: "Export CSV", hint: "One row per date, for a spreadsheet" },
  { format: "json", label: "Export JSON", hint: "Dates, flags and every review decision" },
];

/** Download the run's dates, with their full review history, as CSV or JSON. */
export function ExportMenu({ runId }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  function close() {
    setOpen(false);
    button.current?.focus();
  }

  return (
    <div
      ref={root}
      className="export-menu"
      onKeyDown={(event) => {
        if (open && event.key === "Escape") {
          event.stopPropagation();
          close();
        }
      }}
    >
      <button
        ref={button}
        type="button"
        className="button"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((was) => !was)}
      >
        Export
        <svg className="export-menu__chevron" viewBox="0 0 16 16" aria-hidden="true">
          <path d="M4 6l4 4 4-4" />
        </svg>
      </button>
      {open ? (
        <ul id={menuId} className="export-menu__list">
          {FORMATS.map(({ format, label, hint }) => (
            <li key={format}>
              <a className="export-menu__item" href={api.exportUrl(runId, format)} download={api.exportFilename?.(runId, format) ?? ""} onClick={() => setOpen(false)}>
                <span className="export-menu__label">{label}</span>
                <span className="export-menu__hint">{hint}</span>
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
