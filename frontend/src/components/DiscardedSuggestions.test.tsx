import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type DiscardedSuggestion } from "../api";
import { makeLabels } from "../dateDisplay";
import { TAXONOMY } from "../test-fixtures";
import { DiscardedSuggestions } from "./DiscardedSuggestions";

const ITEMS: DiscardedSuggestion[] = [
  {
    page: 2,
    kind: "missed_date",
    reason: "could not parse the text as one date",
    verbatim_text: "31 Feb 2027",
    date_type: "expiry_date",
    qualifier: null,
    confidence: 0.7,
    rationale: "Label says expiry",
  },
  { page: 1, kind: "transcription", reason: "not found in the page text", candidate_id: "p1-t0", verbatim_text: "14/03/2026" },
  { page: 1, kind: "label", reason: "unknown candidate id", candidate_id: "p1-c9", date_type: "approval_date", confidence: 0.8, rationale: "" },
  { page: 1, kind: "resolution", reason: "evidence not found on the page", candidate_id: "p1-c4", resolved_value: "2026-09-10", evidence: "US date order" },
];

function renderList(runId = 4) {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <DiscardedSuggestions runId={runId} labels={makeLabels(TAXONOMY)} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("DiscardedSuggestions", () => {
  it("is collapsed and counts the run's discarded suggestions", async () => {
    vi.spyOn(api, "getDiscarded").mockResolvedValue(ITEMS);
    renderList();

    const summary = await screen.findByText("Discarded AI suggestions");
    const section = summary.closest("details")!;
    expect(section).not.toHaveAttribute("open");
    expect(section.querySelector("summary")).toHaveTextContent("4");
    expect(screen.getByText("31 Feb 2027")).not.toBeVisible();
    expect(api.getDiscarded).toHaveBeenCalledWith(4);
  });

  it("lists each suggestion with its page, kind and the reason it was discarded", async () => {
    vi.spyOn(api, "getDiscarded").mockResolvedValue(ITEMS);
    renderList();
    fireEvent.click(await screen.findByText("Discarded AI suggestions"));

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(4);
    expect(items[0]).toHaveTextContent("31 Feb 2027");
    expect(items[0]).toHaveTextContent("Page 2");
    expect(items[0]).toHaveTextContent("Missed date · suggested as Expiry date");
    expect(items[0]).toHaveTextContent("could not parse the text as one date");
    expect(items[1]).toHaveTextContent("Transcribed date");
    expect(items[1]).toHaveTextContent("not found in the page text");
    expect(items[2]).toHaveTextContent("Label for p1-c9 · suggested as Approval date");
    expect(items[3]).toHaveTextContent("Reading choice for p1-c4");
    expect(items[3]).toHaveTextContent("Evidence “US date order”");
    expect(screen.getByText("31 Feb 2027")).toBeVisible();
  });

  it("never shows a suggestion as a date", async () => {
    vi.spyOn(api, "getDiscarded").mockResolvedValue(ITEMS);
    const { container } = renderList();
    fireEvent.click(await screen.findByText("Discarded AI suggestions"));

    expect(container.querySelector("[data-date-id], [data-box-id], [data-testid='date-value']")).toBeNull();
    expect(screen.queryByRole("button", { name: /Accept/ })).not.toBeInTheDocument();
    // The verbatim text stays as the AI wrote it: no ISO value is derived from it.
    expect(container).not.toHaveTextContent("2026-03-14");
    // A rejected reading choice does not show the reading it chose.
    expect(container).not.toHaveTextContent("2026-09-10");
  });

  it("shows nothing when the run discarded nothing", async () => {
    const getDiscarded = vi.spyOn(api, "getDiscarded").mockResolvedValue([]);
    const { container } = renderList();

    await vi.waitFor(() => expect(getDiscarded).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(container).toBeEmptyDOMElement();
  });

  it("says when the list could not be loaded", async () => {
    vi.spyOn(api, "getDiscarded").mockRejectedValue(new Error("Could not reach the server."));
    renderList();

    expect(await screen.findByText(/Could not load the discarded AI suggestions/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
