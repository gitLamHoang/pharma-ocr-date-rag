import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { api } from "./api";

vi.mock("./api", async (importOriginal) => ({ ...(await importOriginal<typeof import("./api")>()), STATIC_MODE: true }));

const BANNER = "Runs in your browser · rules only (no AI) · documents are not uploaded anywhere · every date needs review";

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getHealth").mockResolvedValue({ ai_enabled: false, provider: "browser", model: null, tesseract_langs_missing: [] });
  vi.spyOn(api, "listDocuments").mockResolvedValue([]);
});

describe("static (GitHub Pages) mode", () => {
  it("states where documents are processed, on every screen", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const banner = screen.getByRole("note");
    expect(banner).toHaveTextContent(BANNER, { normalizeWhitespace: false });
    expect(banner.textContent).toBe(BANNER);
    expect(await screen.findByText("Rules only")).toBeInTheDocument();
    // The banner already says rules only; the Documents screen does not repeat it.
    expect(screen.queryByText("AI classification off — rules only")).not.toBeInTheDocument();
  });
});
