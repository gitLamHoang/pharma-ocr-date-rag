import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DateRecord, PageInfo } from "../api";
import { dateRecord } from "../test-fixtures";
import { PageViewer } from "./PageViewer";

const PAGES: PageInfo[] = [
  { n: 1, width: 1000, height: 2000 },
  { n: 2, width: 1000, height: 2000 },
];

function renderViewer(dates: DateRecord[], props: Partial<Parameters<typeof PageViewer>[0]> = {}) {
  const onSelect = vi.fn();
  const view = render(
    <PageViewer documentId={1} pages={PAGES} dates={dates} selectedId={null} onSelect={onSelect} {...props} />,
  );
  return { onSelect, ...view };
}

function box(id: number): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-box-id="${id}"]`);
}

function pageImage(): HTMLImageElement {
  return screen.getByRole("img", { name: /^Page \d of 2$/ }) as HTMLImageElement;
}

describe("PageViewer", () => {
  it("scales each box from page pixels to the rendered page", () => {
    renderViewer([dateRecord({ id: 1, bbox: { x0: 100, y0: 200, x1: 300, y1: 250 } })]);

    const style = box(1)!.style;
    expect(style.left).toBe("10%");
    expect(style.top).toBe("10%");
    expect(style.width).toBe("20%");
    expect(style.height).toBe("2.5%");
  });

  it("draws only the current page's boxes, coloured by family", () => {
    renderViewer([
      dateRecord({ id: 1, page: 1, current_family: "signature" }),
      dateRecord({ id: 2, page: 2 }),
      dateRecord({ id: 3, page: 1, bbox: null }),
    ]);

    expect(box(1)).toHaveAttribute("data-family", "signature");
    expect(box(2)).toBeNull();
    expect(box(3)).toBeNull();
    expect(pageImage().src).toContain("/api/documents/1/pages/1.png");
  });

  it("selects a date when its box is clicked", () => {
    const { onSelect } = renderViewer([dateRecord({ id: 5 })]);

    fireEvent.click(box(5)!);

    expect(onSelect).toHaveBeenCalledWith(5);
  });

  it("marks the selected box and the linked ones", () => {
    renderViewer([dateRecord({ id: 1 }), dateRecord({ id: 2 }), dateRecord({ id: 3 })], { selectedId: 1, linkedIds: [3] });

    expect(box(1)).toHaveAttribute("aria-pressed", "true");
    expect(box(2)).toHaveAttribute("aria-pressed", "false");
    expect(box(3)).toHaveAttribute("aria-pressed", "true");
  });

  it("turns to the selected date's page", () => {
    const dates = [dateRecord({ id: 1, page: 1 }), dateRecord({ id: 2, page: 2 })];
    const { rerender } = renderViewer(dates);
    expect(pageImage()).toHaveAccessibleName("Page 1 of 2");

    rerender(<PageViewer documentId={1} pages={PAGES} dates={dates} selectedId={2} onSelect={() => {}} />);

    expect(pageImage()).toHaveAccessibleName("Page 2 of 2");
    expect(box(2)).toHaveAttribute("aria-pressed", "true");
  });

  it("turns pages from the thumbnail rail", () => {
    renderViewer([]);

    fireEvent.click(screen.getByRole("button", { name: /^Page 2/ }));

    expect(pageImage()).toHaveAccessibleName("Page 2 of 2");
    expect(screen.getByRole("button", { name: /^Page 2/ })).toHaveAttribute("aria-current", "page");
  });

  it("zooms between 50 % and 300 %", () => {
    renderViewer([]);
    const zoomIn = screen.getByRole("button", { name: "Zoom in" });
    const zoomOut = screen.getByRole("button", { name: "Zoom out" });
    const readout = () => screen.getByRole("button", { name: /fit to width/ });
    expect(readout()).toHaveTextContent("100%");

    for (let i = 0; i < 20; i++) fireEvent.click(zoomIn);
    expect(readout()).toHaveTextContent("300%");
    expect(zoomIn).toBeDisabled();
    expect(document.querySelector<HTMLElement>(".viewer__page")!.style.width).toBe("300%");

    for (let i = 0; i < 20; i++) fireEvent.click(zoomOut);
    expect(readout()).toHaveTextContent("50%");
    expect(zoomOut).toBeDisabled();

    fireEvent.click(readout());
    expect(readout()).toHaveTextContent("100%");
  });

  it("says when a page image fails to load, and retries", () => {
    renderViewer([]);

    fireEvent.error(pageImage());
    expect(screen.getByText(/Page 1 could not be loaded/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(pageImage()).toBeInTheDocument();
  });

  it("says when the run has no page images", () => {
    render(<PageViewer documentId={1} pages={[]} dates={[]} selectedId={null} onSelect={() => {}} />);

    expect(screen.getByText("This run has no page images.")).toBeInTheDocument();
  });
});
