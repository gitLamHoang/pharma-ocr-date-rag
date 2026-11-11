import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, type DocumentSummary, type Health } from "../api";
import { Documents } from "./Documents";

function summary(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    id: 1,
    name: "coa-lot-4471.pdf",
    pages: 3,
    status: "done",
    error: null,
    n_dates: 12,
    n_flags: 2,
    n_needs_review: 5,
    created_at: "2026-11-11T09:05:00",
    ...overrides,
  };
}

const AI_OFF: Health = { ai_enabled: false, provider: "anthropic", model: null, tesseract_langs_missing: [] };
const AI_ON: Health = { ai_enabled: true, provider: "anthropic", model: "claude-opus-5-5", tesseract_langs_missing: [] };

function renderPage() {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <MemoryRouter>
        <Documents />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/**
 * Let pending fetches land. React Query batches its notifications on a 0 ms timer that fake timers
 * only run once the clock moves, so this advances 1 ms per pass (2 ms in all, far below the 2 s poll).
 */
async function flush() {
  for (let i = 0; i < 2; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
  }
}

/** Move the clock, then let the refetch it triggered land. */
async function tick(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
  await flush();
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(api, "getHealth").mockResolvedValue(AI_ON);
  vi.spyOn(api, "listDocuments").mockResolvedValue([]);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("Documents screen", () => {
  it("names the next step when there are no documents", async () => {
    renderPage();
    await flush();

    expect(screen.getByRole("heading", { level: 1, name: "Documents" })).toBeInTheDocument();
    expect(screen.getByText("No documents yet. Drop a PDF or scan above, or choose a file.")).toBeInTheDocument();
  });

  it("lists the documents with their counts", async () => {
    vi.mocked(api.listDocuments).mockResolvedValue([summary()]);
    renderPage();
    await flush();

    expect(screen.getByRole("link", { name: "coa-lot-4471.pdf" })).toBeInTheDocument();
    expect(screen.getByText("5")).toHaveClass("pill--review");
  });

  it.each(["reading", "classifying", "validating"] as const)(
    "polls every 2 s while a document is %s, and stops once it is done",
    async (status) => {
      const list = vi.mocked(api.listDocuments);
      list
        .mockResolvedValueOnce([summary({ status })])
        .mockResolvedValueOnce([summary({ status })])
        .mockResolvedValue([summary({ status: "done" })]);
      renderPage();
      await flush();
      expect(list).toHaveBeenCalledTimes(1);

      await tick(1900);
      expect(list).toHaveBeenCalledTimes(1);
      await tick(100);
      expect(list).toHaveBeenCalledTimes(2);
      await tick(2000);
      expect(list).toHaveBeenCalledTimes(3);
      expect(screen.getByText("Done")).toBeInTheDocument();

      await tick(10_000);
      expect(list).toHaveBeenCalledTimes(3);
    },
  );

  it("stops polling when a document fails, and shows why", async () => {
    const list = vi.mocked(api.listDocuments);
    list
      .mockResolvedValueOnce([summary({ status: "reading" })])
      .mockResolvedValue([summary({ status: "failed", error: "This file has no pages." })]);
    renderPage();
    await flush();

    await tick(2000);
    expect(screen.getByText("This file has no pages.")).toBeInTheDocument();
    await tick(10_000);
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("does not poll when every document is settled", async () => {
    const list = vi.mocked(api.listDocuments);
    list.mockResolvedValue([summary(), summary({ id: 2, name: "bad.pdf", status: "failed", error: "Broken." })]);
    renderPage();
    await flush();

    await tick(10_000);
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("says when AI classification is off", async () => {
    vi.mocked(api.getHealth).mockResolvedValue(AI_OFF);
    renderPage();
    await flush();

    expect(screen.getByText("AI classification off — rules only")).toBeInTheDocument();
  });

  it("shows no banner when AI is on", async () => {
    renderPage();
    await flush();

    expect(screen.queryByText("AI classification off — rules only")).not.toBeInTheDocument();
  });

  it("uploads a chosen file and refreshes the list", async () => {
    const upload = vi.spyOn(api, "uploadDocument").mockResolvedValue({ document_id: 4, run_id: 9, status: "queued" });
    const list = vi.mocked(api.listDocuments);
    renderPage();
    await flush();
    list.mockResolvedValue([summary({ id: 4, name: "coa.pdf", status: "queued" })]);

    const file = new File(["%PDF"], "coa.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Choose files to upload"), { target: { files: [file] } });
    await flush();

    expect(upload).toHaveBeenCalledWith(file);
    expect(screen.getByRole("link", { name: "coa.pdf" })).toBeInTheDocument();
    expect(screen.getByText("Queued")).toBeInTheDocument();
  });

  it("shows the server's reason when an upload is refused", async () => {
    vi.spyOn(api, "uploadDocument").mockRejectedValue(new ApiError(413, "This file is larger than 50 MB."));
    renderPage();
    await flush();

    const file = new File(["%PDF"], "big.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Choose files to upload"), { target: { files: [file] } });
    await flush();

    expect(screen.getByRole("alert")).toHaveTextContent("big.pdf: This file is larger than 50 MB.");
  });

  it("never uploads a rejected file", async () => {
    const upload = vi.spyOn(api, "uploadDocument");
    renderPage();
    await flush();

    fireEvent.change(screen.getByLabelText("Choose files to upload"), {
      target: { files: [new File(["MZ"], "setup.exe")] },
    });
    await flush();

    expect(upload).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("setup.exe is not a supported file.");
  });

  it("says when the list cannot be loaded and retries", async () => {
    const list = vi.mocked(api.listDocuments);
    list.mockRejectedValueOnce(new ApiError(0, "Could not reach the server. Check that it is running, then try again."));
    renderPage();
    await flush();

    expect(screen.getByRole("alert")).toHaveTextContent("Could not reach the server.");
    list.mockResolvedValue([summary()]);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await flush();

    expect(screen.getByRole("link", { name: "coa-lot-4471.pdf" })).toBeInTheDocument();
  });
});
