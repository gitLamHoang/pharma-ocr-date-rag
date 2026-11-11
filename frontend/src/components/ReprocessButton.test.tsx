import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api";
import { ReprocessButton } from "./ReprocessButton";

function renderButton(props: Partial<Parameters<typeof ReprocessButton>[0]> = {}) {
  const onStarted = vi.fn().mockResolvedValue(undefined);
  render(<ReprocessButton documentId={1} latestRunId={4} pages={2} onStarted={onStarted} {...props} />);
  return { onStarted };
}

afterEach(() => vi.restoreAllMocks());

describe("ReprocessButton", () => {
  it("asks for confirmation before starting a new run", async () => {
    const reprocess = vi.spyOn(api, "reprocess").mockResolvedValue({ run_id: 5 });
    const { onStarted } = renderButton();

    fireEvent.click(screen.getByRole("button", { name: "Reprocess" }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Reprocess this document?" })).toBeInTheDocument();
    expect(dialog).toHaveTextContent("Run 4 stays as a read-only record");
    expect(dialog).toHaveTextContent("carry over");
    expect(reprocess).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Reprocess document" }));

    await waitFor(() => expect(onStarted).toHaveBeenCalledWith(5));
    expect(reprocess).toHaveBeenCalledWith(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does nothing when the reviewer cancels", () => {
    const reprocess = vi.spyOn(api, "reprocess");
    const { onStarted } = renderButton();

    fireEvent.click(screen.getByRole("button", { name: "Reprocess" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(reprocess).not.toHaveBeenCalled();
    expect(onStarted).not.toHaveBeenCalled();
  });

  it("keeps the dialog open with the server's message when the run cannot start", async () => {
    vi.spyOn(api, "reprocess").mockRejectedValue(new ApiError(404, "Document 1 not found."));
    const { onStarted } = renderButton();

    fireEvent.click(screen.getByRole("button", { name: "Reprocess" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Reprocess document" }));

    expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("Document 1 not found.");
    expect(onStarted).not.toHaveBeenCalled();
  });

  it("speaks of the document, not of zero pages, when the last run read no pages", () => {
    renderButton({ pages: 0 });

    fireEvent.click(screen.getByRole("button", { name: "Reprocess" }));

    expect(screen.getByRole("dialog")).toHaveTextContent("A new run reads the document again");
    expect(screen.getByRole("dialog")).not.toHaveTextContent("0 pages");
  });

  it("is unavailable while a run is in progress, and says why", () => {
    renderButton({ busy: true });

    const button = screen.getByRole("button", { name: "Reprocess" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("A run is in progress.");
  });
});
