import { useEffect, useRef, useState } from "react";
import { api, type DateRecord, type PageInfo } from "../api";

interface Props {
  /** The run shown: its own page images, even while a newer run is reading. */
  runId: number;
  pages: PageInfo[];
  dates: DateRecord[];
  /** The active date: the viewer turns to its page and keeps its box in view. */
  selectedId: number | null;
  /** Changes on every selection, so selecting the active date again turns back to its page. */
  selectionSeq?: number;
  onSelect(id: number): void;
  /** Other dates selected with it (the rest of a clicked flag's dates). */
  linkedIds?: number[];
}

const ZOOM_STEPS = [50, 75, 100, 125, 150, 200, 250, 300];
const FIT = 100;

const percent = (part: number, whole: number) => `${(part / whole) * 100}%`;

function reducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

/** The page image with a box on every date, a thumbnail rail and zoom (100 % fits the width). */
export function PageViewer({ runId, pages, dates, selectedId, selectionSeq = 0, onSelect, linkedIds = [] }: Props) {
  const [pageNo, setPageNo] = useState(pages[0]?.n ?? 1);
  const [zoom, setZoom] = useState(FIT);
  const [failed, setFailed] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const canvas = useRef<HTMLDivElement>(null);

  // Turn to the selected date's page on every selection (during render, not after it), even of
  // the date already active after the reviewer turned pages with the rail.
  const selected = dates.find((d) => d.id === selectedId) ?? null;
  const selection = `${selectedId}:${selectionSeq}`;
  const [shownFor, setShownFor] = useState<string | null>(null);
  if (selection !== shownFor) {
    setShownFor(selection);
    if (selected && selected.page !== pageNo) setPageNo(selected.page);
  }

  // Keep the selected box in view inside the canvas, without scrolling the window.
  useEffect(() => {
    const area = canvas.current;
    const target = area?.querySelector<HTMLElement>(`[data-box-id="${selectedId}"]`);
    if (!area || !target) return;
    const view = area.getBoundingClientRect();
    const rect = target.getBoundingClientRect();
    const inside = rect.top >= view.top && rect.bottom <= view.bottom && rect.left >= view.left && rect.right <= view.right;
    if (inside) return;
    area.scrollTo({
      top: area.scrollTop + rect.top - view.top - (view.height - rect.height) / 2,
      left: area.scrollLeft + rect.left - view.left - (view.width - rect.width) / 2,
      behavior: reducedMotion() ? "auto" : "smooth",
    });
  }, [selectedId, selectionSeq, pageNo, zoom]);

  if (pages.length === 0) {
    return (
      <section className="viewer viewer--empty" aria-label="Page viewer">
        <p className="muted">This run has no page images.</p>
      </section>
    );
  }

  const page = pages.find((p) => p.n === pageNo) ?? pages[0]!;
  const step = ZOOM_STEPS.indexOf(zoom);
  const onPage = dates.filter((d) => d.page === page.n && d.bbox !== null);
  const countOn = (n: number) => dates.filter((d) => d.page === n).length;

  return (
    <section className="viewer" aria-label="Page viewer">
      <header className="viewer__bar">
        <p className="viewer__where">
          Page <span className="viewer__figure">{page.n}</span> of {pages.length}
        </p>
        <div className="viewer__zoom" role="group" aria-label="Zoom">
          <button
            type="button"
            className="button button--quiet viewer__icon"
            aria-label="Zoom out"
            disabled={step <= 0}
            onClick={() => setZoom(ZOOM_STEPS[step - 1]!)}
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3.5 8h9" />
            </svg>
          </button>
          <button
            type="button"
            className="button button--quiet viewer__zoom-value"
            aria-label={`Zoom ${zoom}%, fit to width`}
            title="Fit to width"
            onClick={() => setZoom(FIT)}
          >
            {zoom}%
          </button>
          <button
            type="button"
            className="button button--quiet viewer__icon"
            aria-label="Zoom in"
            disabled={step >= ZOOM_STEPS.length - 1}
            onClick={() => setZoom(ZOOM_STEPS[step + 1]!)}
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3.5 8h9M8 3.5v9" />
            </svg>
          </button>
        </div>
      </header>

      <div className="viewer__body">
        <nav className="viewer__rail" aria-label="Pages">
          {pages.map((p) => {
            const count = countOn(p.n);
            return (
              <button
                key={p.n}
                type="button"
                className="thumb"
                aria-current={p.n === page.n ? "page" : undefined}
                aria-label={`Page ${p.n}, ${count} ${count === 1 ? "date" : "dates"}`}
                onClick={() => setPageNo(p.n)}
              >
                <img
                  className="thumb__image"
                  src={api.pageImageUrl(runId, p.n)}
                  alt=""
                  loading="lazy"
                  style={{ aspectRatio: `${p.width} / ${p.height}` }}
                />
                <span className="thumb__label">
                  <span>{p.n}</span>
                  {count > 0 ? <span className="thumb__count">{count === 1 ? "1 date" : `${count} dates`}</span> : null}
                </span>
              </button>
            );
          })}
        </nav>

        {/* Focusable so the keyboard can scroll a zoomed page; Review leaves ↑/↓ to it. */}
        <div className="viewer__canvas" ref={canvas} tabIndex={0} role="region" aria-label={`Page ${page.n}, scrollable`}>
          <div className="viewer__page" style={{ width: `${zoom}%`, aspectRatio: `${page.width} / ${page.height}` }}>
            {failed === page.n ? (
              <p className="viewer__failed">
                Page {page.n} could not be loaded.{" "}
                <button
                  type="button"
                  className="text-button"
                  onClick={() => {
                    setFailed(null);
                    setAttempt((n) => n + 1);
                  }}
                >
                  Retry
                </button>
              </p>
            ) : (
              <img
                key={`${page.n}-${attempt}`}
                className="viewer__image"
                src={api.pageImageUrl(runId, page.n)}
                alt={`Page ${page.n} of ${pages.length}`}
                onError={() => setFailed(page.n)}
              />
            )}
            {onPage.flatMap((d) => {
              const isSelected = d.id === selectedId || linkedIds.includes(d.id);
              // A date wrapped across lines gets a tight box on each line, not one box over both.
              const boxes = d.line_boxes.length > 0 ? d.line_boxes : [d.bbox!];
              return boxes.map((box, i) => (
                <button
                  key={`${d.id}-${i}`}
                  type="button"
                  tabIndex={-1}
                  className="viewer__box"
                  data-box-id={d.id}
                  data-family={d.current_family}
                  data-active={d.id === selectedId || undefined}
                  aria-pressed={isSelected}
                  aria-label={`${d.raw_text.replace(/\s+/g, " ")}, page ${d.page}`}
                  aria-hidden={i > 0 || undefined}
                  style={{
                    left: percent(box.x0, page.width),
                    top: percent(box.y0, page.height),
                    width: percent(box.x1 - box.x0, page.width),
                    height: percent(box.y1 - box.y0, page.height),
                  }}
                  onClick={() => onSelect(d.id)}
                />
              ));
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
