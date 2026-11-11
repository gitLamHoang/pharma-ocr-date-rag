import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { api } from "./api";

function renderAt(path: string) {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queries}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "getHealth").mockResolvedValue({
    ai_enabled: false,
    provider: "anthropic",
    model: null,
    tesseract_langs_missing: [],
  });
});

describe("App routes", () => {
  it("shows the Documents screen at /", () => {
    renderAt("/");

    expect(screen.getByRole("heading", { level: 1, name: "Documents" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute("aria-current", "page");
  });

  it("shows the Review screen for /documents/:id", () => {
    renderAt("/documents/3");

    expect(screen.getByRole("heading", { level: 1, name: "Document 3" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Documents" })).not.toHaveAttribute("aria-current");
  });

  it("answers an unknown path with a way back", () => {
    renderAt("/nowhere");

    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to documents" })).toHaveAttribute("href", "/");
  });

  it("says when AI is off", async () => {
    renderAt("/");

    expect(await screen.findByText("Rules only")).toBeInTheDocument();
  });

  it("names the model when AI is on", async () => {
    vi.spyOn(api, "getHealth").mockResolvedValue({
      ai_enabled: true,
      provider: "anthropic",
      model: "claude-opus-5-5",
      tesseract_langs_missing: [],
    });
    renderAt("/");

    expect(await screen.findByText("AI on")).toBeInTheDocument();
    expect(screen.getByText("claude-opus-5-5")).toBeInTheDocument();
  });

  it("says when the server cannot be reached", async () => {
    vi.spyOn(api, "getHealth").mockRejectedValue(new Error("down"));
    renderAt("/");

    expect(await screen.findByText("Server unreachable")).toBeInTheDocument();
  });
});
