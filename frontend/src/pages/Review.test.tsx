import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api";
import type { DocumentDetail } from "../api";
import { TAXONOMY, ambiguousDate, dateRecord, documentDetail, flag, monthDate, reviewEvent } from "../test-fixtures";
import { Review } from "./Review";

const DATES = [
  dateRecord({ id: 1, page: 1 }),
  monthDate({ id: 2, page: 1, bbox: { x0: 100, y0: 400, x1: 300, y1: 450 } }),
  ambiguousDate({ id: 3, page: 2 }),
];

function renderAt(path = "/documents/1") {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/documents/:id"
            element={
              <>
                <Link to="/documents/1">First document</Link>
                <Link to="/documents/2">Next document</Link>
                <Review />
              </>
            }
          />
          <Route path="/" element={<p>Documents screen</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function row(id: number): HTMLElement {
  return document.querySelector<HTMLElement>(`[data-date-id="${id}"]`)!;
}

function rowButton(id: number): HTMLElement {
  return row(id).querySelector<HTMLElement>(".date-row__select")!;
}

function box(id: number): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-box-id="${id}"]`);
}

function key(k: string) {
  fireEvent.keyDown(document.body, { key: k });
}

async function loaded() {
  await screen.findByRole("heading", { level: 1, name: "coa-lot-4471.pdf" });
  await waitFor(() => expect(row(1)).not.toBeNull());
}

beforeEach(() => {
  vi.spyOn(api, "getDocument").mockResolvedValue(documentDetail());
  vi.spyOn(api, "getDates").mockResolvedValue(DATES);
  vi.spyOn(api, "getFlags").mockResolvedValue([]);
  vi.spyOn(api, "getTaxonomy").mockResolvedValue(TAXONOMY);
  vi.spyOn(api, "getHistory").mockResolvedValue([]);
  vi.spyOn(api, "reviewDate").mockResolvedValue(reviewEvent());
  vi.spyOn(api, "getDiscarded").mockResolvedValue([]);
  vi.spyOn(api, "getPages").mockImplementation(async () => documentDetail().pages);
  localStorage.setItem("pharma-dates:reviewer", "J. Doe");
});

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("Review screen", () => {
  it("shows the document, its page and its dates for the latest run", async () => {
    renderAt();
    await loaded();

    expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute("href", "/");
    expect(api.getDates).toHaveBeenCalledWith(4);
    expect(screen.getByRole("img", { name: "Page 1 of 2" })).toBeInTheDocument();
    expect(box(1)).not.toBeNull();
  });

  it("selects the box when a row is selected, and the row when a box is clicked", async () => {
    renderAt();
    await loaded();

    fireEvent.click(rowButton(2));
    expect(box(2)).toHaveAttribute("aria-pressed", "true");
    expect(box(1)).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(box(1)!);
    expect(rowButton(1)).toHaveAttribute("aria-current", "true");
    expect(rowButton(2)).toHaveAttribute("aria-pressed", "false");
  });

  it("turns to the page of a date on another page", async () => {
    renderAt();
    await loaded();

    fireEvent.click(rowButton(3));

    expect(screen.getByRole("img", { name: "Page 2 of 2" })).toBeInTheDocument();
    expect(box(3)).toHaveAttribute("aria-pressed", "true");
  });

  it("selects a flag's dates when the flag is clicked", async () => {
    vi.mocked(api.getFlags).mockResolvedValue([
      flag({ id: 7, severity: "error", message: "Expiry 2027-03 is not after manufacture", date_ids: [2, 1] }),
    ]);
    renderAt();
    await loaded();

    fireEvent.click(await screen.findByRole("button", { name: /Expiry 2027-03 is not after manufacture/ }));

    expect(rowButton(1)).toHaveAttribute("aria-pressed", "true");
    expect(rowButton(2)).toHaveAttribute("aria-pressed", "true");
    expect(rowButton(2)).toHaveAttribute("aria-current", "true");
    expect(rowButton(3)).toHaveAttribute("aria-pressed", "false");
    expect(box(1)).toHaveAttribute("aria-pressed", "true");
    expect(box(2)).toHaveAttribute("aria-pressed", "true");
  });

  it("moves with the arrow keys, accepts with A and edits with E", async () => {
    renderAt();
    await loaded();

    key("ArrowDown");
    expect(rowButton(1)).toHaveAttribute("aria-current", "true");
    key("ArrowDown");
    expect(rowButton(2)).toHaveAttribute("aria-current", "true");
    key("ArrowDown");
    key("ArrowDown");
    expect(rowButton(3)).toHaveAttribute("aria-current", "true");
    key("ArrowUp");
    expect(rowButton(2)).toHaveAttribute("aria-current", "true");

    key("a");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Accept date" })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    key("E");
    expect(within(await screen.findByRole("dialog")).getByRole("heading", { name: "Correct date" })).toBeInTheDocument();
  });

  it("ignores the shortcuts while typing in a field", async () => {
    renderAt();
    await loaded();
    key("ArrowDown");
    key("a");
    const reason = within(await screen.findByRole("dialog")).getByLabelText("Reason");

    fireEvent.keyDown(reason, { key: "ArrowDown" });
    fireEvent.keyDown(reason, { key: "e" });

    expect(rowButton(1)).toHaveAttribute("aria-current", "true");
    expect(within(screen.getByRole("dialog")).getByRole("heading", { name: "Accept date" })).toBeInTheDocument();
  });

  it("records a decision and refreshes the dates", async () => {
    renderAt();
    await loaded();
    fireEvent.click(rowButton(1));
    fireEvent.click(within(row(1)).getByRole("button", { name: /^Accept/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: "Matches the page" } });
    vi.mocked(api.getDates).mockResolvedValue([dateRecord({ id: 1, status: "accepted" }), ...DATES.slice(1)]);

    fireEvent.click(within(dialog).getByRole("button", { name: "Accept date" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api.reviewDate).toHaveBeenCalledWith(1, { action: "accept", reviewer: "J. Doe", reason: "Matches the page" });
    expect(await within(row(1)).findByText("Accepted")).toBeInTheDocument();
  });

  it("says the run was replaced when a review gets 409, and goes read-only", async () => {
    vi.mocked(api.reviewDate).mockRejectedValue(new ApiError(409, "run 4 is frozen; review the document's latest run 5"));
    renderAt();
    await loaded();
    fireEvent.click(rowButton(1));
    key("a");
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: "Matches the page" } });

    fireEvent.click(within(dialog).getByRole("button", { name: "Accept date" }));

    expect(await screen.findByText(/This run was replaced — reload/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(within(row(1)).queryByRole("button", { name: /^Accept/ })).not.toBeInTheDocument();

    vi.mocked(api.getDocument).mockResolvedValue(documentDetail({ run: { id: 5, status: "done", error: null, ai_used: false, ai_model: null } }));
    vi.mocked(api.getDates).mockResolvedValue([dateRecord({ id: 11, run_id: 5 })]);
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));

    await waitFor(() => expect(api.getDates).toHaveBeenCalledWith(5));
    await waitFor(() => expect(row(11)).not.toBeNull());
    expect(screen.queryByText(/This run was replaced/)).not.toBeInTheDocument();
  });

  it("shows a frozen run's own pages while a newer run is still reading", async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      documentDetail({ run: { id: 5, status: "reading", error: null, ai_used: false, ai_model: null }, pages: [] }),
    );
    renderAt("/documents/1?run=4");
    await loaded();

    expect(api.getPages).toHaveBeenCalledWith(4);
    expect(screen.queryByText("This run has no page images.")).not.toBeInTheDocument();
    const image = await screen.findByRole("img", { name: "Page 1 of 2" });
    expect(image.getAttribute("src")).toBe("/api/runs/4/pages/1.png");
    expect(box(1)).not.toBeNull();
  });

  it("turns back to the active date's page when it is selected again", async () => {
    renderAt();
    await loaded();
    fireEvent.click(rowButton(3));
    expect(await screen.findByRole("img", { name: "Page 2 of 2" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Page 1, / }));
    expect(screen.getByRole("img", { name: "Page 1 of 2" })).toBeInTheDocument();

    fireEvent.click(rowButton(3));

    expect(screen.getByRole("img", { name: "Page 2 of 2" })).toBeInTheDocument();
    expect(box(3)).not.toBeNull();
  });

  it("moves keyboard focus with the active row on ↑/↓, but not on a click in the viewer", async () => {
    renderAt();
    await loaded();
    rowButton(1).focus();
    key("ArrowDown");
    const active = () => document.querySelector<HTMLElement>("[data-active] .date-row__select");
    await waitFor(() => expect(document.activeElement).toBe(active()));
    const first = active();
    key("ArrowDown");
    await waitFor(() => expect(active()).not.toBe(first));
    expect(document.activeElement).toBe(active());

    const canvas = document.querySelector<HTMLElement>(".viewer__canvas")!;
    canvas.focus();
    fireEvent.click(box(1)!);
    await waitFor(() => expect(row(1)).toHaveAttribute("data-active"));
    expect(document.activeElement).toBe(canvas);
  });

  it("gives focus back to the date's row when the review dialog closes", async () => {
    renderAt();
    await loaded();
    rowButton(1).focus();
    fireEvent.click(rowButton(1));
    key("e");
    let dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(document.activeElement).toBe(rowButton(1));

    // Opened from the shortcut with focus elsewhere: focus still lands on the row it was about.
    (document.activeElement as HTMLElement).blur();
    key("a");
    dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: "Matches the page" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Accept date" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(document.activeElement).toBe(rowButton(1));
  });

  it("shows a frozen older run read-only", async () => {
    renderAt("/documents/1?run=3");
    await screen.findByRole("heading", { level: 1, name: "coa-lot-4471.pdf" });
    await waitFor(() => expect(row(1)).not.toBeNull());

    expect(api.getDates).toHaveBeenCalledWith(3);
    expect(screen.getByText(/Run 3 is frozen/)).toBeInTheDocument();
    // Nothing here can be reviewed, so the count is not the sunflower call to action.
    expect(document.querySelector(".review__summary .pill--review")).toBeNull();
    expect(screen.getByText(/need review in this run/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the latest run" })).toHaveAttribute("href", "/documents/1");

    fireEvent.click(rowButton(1));
    expect(within(row(1)).queryByRole("button", { name: /^Accept/ })).not.toBeInTheDocument();
    key("a");
    key("e");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("ignores a pinned run newer than the latest one", async () => {
    renderAt("/documents/1?run=9");
    await loaded();

    expect(api.getDates).toHaveBeenCalledWith(4);
    expect(api.getDates).not.toHaveBeenCalledWith(9);
    expect(screen.queryByText(/frozen/)).not.toBeInTheDocument();
    fireEvent.click(rowButton(1));
    expect(within(row(1)).getByRole("button", { name: /^Accept/ })).toBeInTheDocument();
  });

  it("refuses a pinned run that belongs to another document", async () => {
    vi.mocked(api.getDates).mockResolvedValue([dateRecord({ id: 21, run_id: 2, document_id: 7 })]);
    renderAt("/documents/1?run=2");

    expect(await screen.findByText("Run 2 is not a run of this document.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the latest run" })).toHaveAttribute("href", "/documents/1");
    expect(row(21)).toBeNull();
    expect(box(21)).toBeNull();
    expect(screen.queryByText(/frozen/)).not.toBeInTheDocument();
  });

  it("refuses a pinned run that does not exist", async () => {
    vi.mocked(api.getDates).mockRejectedValue(new ApiError(404, "Run 2 not found."));
    vi.mocked(api.getFlags).mockRejectedValue(new ApiError(404, "Run 2 not found."));
    renderAt("/documents/1?run=2");

    expect(await screen.findByText("Run 2 is not a run of this document.")).toBeInTheDocument();
    expect(screen.queryByText(/Could not load the dates/)).not.toBeInTheDocument();
  });

  it("starts fresh when another document opens on the same screen", async () => {
    const second = documentDetail({
      document: { ...documentDetail().document, id: 2, filename: "batch-record.pdf" },
      run: { id: 6, status: "done", error: null, ai_used: false, ai_model: null },
    });
    vi.mocked(api.getDocument).mockImplementation(async (id) => (id === 2 ? second : documentDetail()));
    vi.mocked(api.getDates).mockImplementation(async (run) =>
      run === 6 ? [dateRecord({ id: 31, run_id: 6, document_id: 2 })] : DATES,
    );
    renderAt("/documents/2");
    await screen.findByRole("heading", { level: 1, name: "batch-record.pdf" });
    fireEvent.click(screen.getByRole("link", { name: "First document" }));
    await loaded();
    fireEvent.click(rowButton(3));
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByRole("img", { name: "Page 2 of 2" })).toBeInTheDocument();

    // The second document is cached now, so it renders at once: nothing of the first may carry over.
    fireEvent.click(screen.getByRole("link", { name: "Next document" }));

    await screen.findByRole("heading", { level: 1, name: "batch-record.pdf" });
    expect(screen.getByRole("img", { name: "Page 1 of 2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Zoom 100%/ })).toBeInTheDocument();
  });

  it("leaves the arrow keys to the page canvas and the thumbnail rail", async () => {
    renderAt();
    await loaded();
    key("ArrowDown");
    const canvas = document.querySelector<HTMLElement>(".viewer__canvas")!;
    const thumb = screen.getByRole("button", { name: /^Page 2,/ });

    expect(fireEvent.keyDown(canvas, { key: "ArrowDown" })).toBe(true);
    expect(fireEvent.keyDown(thumb, { key: "ArrowUp" })).toBe(true);
    expect(rowButton(1)).toHaveAttribute("aria-current", "true");

    fireEvent.keyDown(box(1)!, { key: "ArrowDown" });
    expect(rowButton(2)).toHaveAttribute("aria-current", "true");
  });

  it("says what the pipeline is doing while the run is in progress", async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      documentDetail({ run: { id: 4, status: "classifying", error: null, ai_used: true, ai_model: "claude-opus-5-5" } }),
    );
    renderAt();

    expect(await screen.findByText(/Classifying the dates/)).toBeInTheDocument();
    expect(api.getDates).not.toHaveBeenCalled();
  });

  it("shows the server's reason when the run failed", async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      documentDetail({ run: { id: 4, status: "failed", error: "The PDF is encrypted.", ai_used: false, ai_model: null }, pages: [] }),
    );
    renderAt();

    expect(await screen.findByText("The PDF is encrypted.")).toBeInTheDocument();
  });

  it("says when the document does not exist", async () => {
    vi.mocked(api.getDocument).mockRejectedValue(new ApiError(404, "Document 9 not found."));
    renderAt("/documents/9");

    expect(await screen.findByText("Document 9 not found.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to documents" })).toHaveAttribute("href", "/");
  });

  it("offers a retry when the dates could not be loaded", async () => {
    vi.mocked(api.getDates).mockRejectedValueOnce(new ApiError(500, "Database is locked."));
    renderAt();

    expect(await screen.findByText(/Could not load the dates\. Database is locked\./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(row(1)).not.toBeNull());
  });
});

describe("Review screen: export, reprocess and discarded suggestions", () => {
  it("exports the run on screen as CSV or JSON", async () => {
    renderAt();
    await loaded();

    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    expect(screen.getByRole("link", { name: /Export CSV/ })).toHaveAttribute("href", api.exportUrl(4, "csv"));
    expect(screen.getByRole("link", { name: /Export JSON/ })).toHaveAttribute("href", api.exportUrl(4, "json"));
  });

  it("exports a frozen run's own dates", async () => {
    renderAt("/documents/1?run=3");
    await waitFor(() => expect(row(1)).not.toBeNull());

    fireEvent.click(screen.getByRole("button", { name: "Export" }));

    expect(screen.getByRole("link", { name: /Export CSV/ })).toHaveAttribute("href", api.exportUrl(3, "csv"));
  });

  it("reprocesses after confirmation, switches to the new run and says how many decisions carried over", async () => {
    let current: DocumentDetail = documentDetail();
    vi.mocked(api.getDocument).mockImplementation(async () => current);
    vi.mocked(api.getDates).mockImplementation(async (run) =>
      run === 5
        ? [
            dateRecord({ id: 11, run_id: 5, status: "accepted", carried_from_run: 4 }),
            monthDate({ id: 12, run_id: 5, status: "rejected", carried_from_run: 4 }),
            ambiguousDate({ id: 13, run_id: 5 }),
          ]
        : DATES,
    );
    const reprocess = vi.spyOn(api, "reprocess").mockImplementation(async () => {
      current = documentDetail({ run: { id: 5, status: "done", error: null, ai_used: false, ai_model: null } });
      return { run_id: 5 };
    });
    renderAt("/documents/1?run=3");
    await waitFor(() => expect(row(1)).not.toBeNull());

    fireEvent.click(screen.getByRole("button", { name: "Reprocess" }));
    const dialog = screen.getByRole("dialog");
    expect(reprocess).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Reprocess document" }));

    expect(await screen.findByText(/2 decisions carried over/)).toBeInTheDocument();
    expect(reprocess).toHaveBeenCalledWith(1);
    expect(api.getDates).toHaveBeenCalledWith(5);
    expect(row(11)).not.toBeNull();
    expect(row(1)).toBeNull();
    expect(screen.getByText(/Run 5 replaced run 4/)).toBeInTheDocument();
    expect(screen.queryByText(/frozen/)).not.toBeInTheDocument();
  });

  it("follows a reprocessed run while it is in progress", async () => {
    let current: DocumentDetail = documentDetail();
    vi.mocked(api.getDocument).mockImplementation(async () => current);
    vi.spyOn(api, "reprocess").mockImplementation(async () => {
      current = documentDetail({ run: { id: 5, status: "reading", error: null, ai_used: false, ai_model: null } });
      return { run_id: 5 };
    });
    renderAt();
    await loaded();

    fireEvent.click(screen.getByRole("button", { name: "Reprocess" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Reprocess document" }));

    expect(await screen.findByText(/Reading the pages/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reprocess" })).toBeDisabled();
  });

  it("offers reprocessing when the run failed", async () => {
    vi.mocked(api.getDocument).mockResolvedValue(
      documentDetail({ run: { id: 4, status: "failed", error: "The PDF is encrypted.", ai_used: false, ai_model: null } }),
    );
    renderAt();

    await screen.findByText("The PDF is encrypted.");
    expect(screen.getByRole("button", { name: "Reprocess" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Export" })).not.toBeInTheDocument();
  });

  it("lists discarded AI suggestions apart from the dates, collapsed", async () => {
    vi.mocked(api.getDiscarded).mockResolvedValue([
      { page: 1, kind: "transcription", reason: "not found in the page text", candidate_id: "p1-t0", verbatim_text: "31 Feb 2027" },
    ]);
    renderAt();
    await loaded();

    const summary = await screen.findByText("Discarded AI suggestions");
    expect(summary.closest("details")).not.toHaveAttribute("open");
    expect(api.getDiscarded).toHaveBeenCalledWith(4);
    expect(document.querySelector(".date-list")).not.toHaveTextContent("31 Feb 2027");
    expect(document.querySelectorAll("[data-date-id]")).toHaveLength(DATES.length);
    expect(document.querySelectorAll("[data-box-id]")).toHaveLength(2);
    expect(screen.getByText(/· 3 dates/)).toBeInTheDocument();
  });
});
