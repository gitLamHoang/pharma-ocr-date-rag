import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api";
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
          <Route path="/documents/:id" element={<Review />} />
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

  it("shows a frozen older run read-only", async () => {
    renderAt("/documents/1?run=3");
    await screen.findByRole("heading", { level: 1, name: "coa-lot-4471.pdf" });
    await waitFor(() => expect(row(1)).not.toBeNull());

    expect(api.getDates).toHaveBeenCalledWith(3);
    expect(screen.getByText(/Run 3 is frozen/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the latest run" })).toHaveAttribute("href", "/documents/1");

    fireEvent.click(rowButton(1));
    expect(within(row(1)).queryByRole("button", { name: /^Accept/ })).not.toBeInTheDocument();
    key("a");
    key("e");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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
