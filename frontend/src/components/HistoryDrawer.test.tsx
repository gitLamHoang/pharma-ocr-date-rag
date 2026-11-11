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

  it("says when each decision was made, newest first even when the server sends them out of order", async () => {
    vi.spyOn(api, "getHistory").mockResolvedValue([
      reviewEvent({ id: 3, action: "reject", reviewer: "C. Third", reason: "Not a date", at: "2026-11-11T11:30:00" }),
      reviewEvent({ id: 1, action: "accept", reviewer: "A. First", reason: "Looks right", at: "2026-11-10T08:15:00" }),
      reviewEvent({ id: 2, action: "reopen", reviewer: "B. Second", reason: "Check again", at: "2026-11-11T09:05:00" }),
    ]);
    renderDrawer();

    const items = await screen.findAllByRole("listitem");
    expect(items.map((item) => item.querySelector(".history__action")?.textContent)).toEqual([
      "Rejected by C. Third",
      "Reopened by B. Second",
      "Accepted by A. First",
    ]);
    const time = items[0]!.querySelector("time");
    expect(time).toHaveAttribute("datetime", "2026-11-11T11:30:00");
    expect(time).toHaveTextContent("2026-11-11 11:30");
    expect(items[2]).toHaveTextContent("2026-11-10 08:15");
  });

  it("marks a decision carried over from an earlier run", async () => {
    vi.spyOn(api, "getHistory").mockResolvedValue([reviewEvent({ id: 5, carried_from_run: 3 })]);
    renderDrawer();

    expect(await screen.findByText("Carried over from run 3")).toBeInTheDocument();
    expect(screen.getByText("Matches the page")).toBeInTheDocument();
  });

  it("says a carried decision came from the earlier run once, even when its reason says so too", async () => {
    vi.spyOn(api, "getHistory").mockResolvedValue([reviewEvent({ id: 5, carried_from_run: 3, reason: "carried over from run 3" })]);
    renderDrawer();

    await screen.findByRole("listitem");
    expect(screen.getAllByText(/carried over from run 3/i)).toHaveLength(1);
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
