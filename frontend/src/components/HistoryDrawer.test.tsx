import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { makeLabels } from "../dateDisplay";
import { TAXONOMY, reviewEvent } from "../test-fixtures";
import { HistoryDrawer } from "./HistoryDrawer";

function renderDrawer() {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <HistoryDrawer dateId={1} labels={makeLabels(TAXONOMY)} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("HistoryDrawer", () => {
  it("lists the decisions newest first with reviewer, reason and what changed", async () => {
    vi.spyOn(api, "getHistory").mockResolvedValue([
      reviewEvent({ id: 1, action: "accept", reviewer: "A. First", reason: "Looks right" }),
      reviewEvent({ id: 2, action: "correct", reviewer: "B. Second", reason: "Label says expiry", new_type: "expiry_date", new_value: "2027-03" }),
    ]);
    renderDrawer();

    const items = await screen.findAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Corrected by B. Second");
    expect(items[0]).toHaveTextContent("Label says expiry");
    expect(items[0]).toHaveTextContent("Type Expiry date · value 2027-03");
    expect(items[1]).toHaveTextContent("Accepted by A. First");
  });

  it("says when there are no decisions yet", async () => {
    vi.spyOn(api, "getHistory").mockResolvedValue([]);
    renderDrawer();

    expect(await screen.findByText("No decisions yet.")).toBeInTheDocument();
  });

  it("says when the history could not be loaded", async () => {
    vi.spyOn(api, "getHistory").mockRejectedValue(new Error("Could not reach the server."));
    renderDrawer();

    expect(await screen.findByText(/Could not load the history/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
