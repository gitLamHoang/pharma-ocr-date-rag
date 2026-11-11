import { createEvent, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { UploadDropzone, type UploadDropzoneHandle } from "./UploadDropzone";

function file(name: string, size = 4, type = ""): File {
  const f = new File([new Uint8Array(Math.min(size, 16))], name, { type });
  if (size > 16) Object.defineProperty(f, "size", { value: size });
  return f;
}

function choose(files: File[]) {
  fireEvent.change(screen.getByLabelText("Choose files to upload"), { target: { files } });
}

function drop(files: File[]) {
  const zone = screen.getByTestId("dropzone");
  const event = createEvent.drop(zone);
  Object.defineProperty(event, "dataTransfer", { value: { files, types: ["Files"] } });
  fireEvent(zone, event);
}

describe("UploadDropzone", () => {
  it("rejects an .exe before uploading and says why", () => {
    const onAccept = vi.fn();
    render(<UploadDropzone onAccept={onAccept} />);

    choose([file("setup.exe")]);

    expect(onAccept).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "setup.exe is not a supported file. Upload a PDF, PNG, JPG or TIFF.",
    );
  });

  it("rejects a file over 50 MB", () => {
    const onAccept = vi.fn();
    render(<UploadDropzone onAccept={onAccept} />);

    choose([file("scan.pdf", 50 * 1024 * 1024 + 1)]);

    expect(onAccept).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("scan.pdf is larger than 50 MB.");
  });

  it.each(["coa.pdf", "label.PNG", "photo.jpg", "photo.jpeg", "scan.tif", "scan.TIFF"])(
    "accepts %s",
    (name) => {
      const onAccept = vi.fn();
      render(<UploadDropzone onAccept={onAccept} />);

      choose([file(name)]);

      expect(onAccept).toHaveBeenCalledWith([expect.objectContaining({ name })]);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    },
  );

  it("passes on the valid files of a mixed drop and names the rejected one", () => {
    const onAccept = vi.fn();
    render(<UploadDropzone onAccept={onAccept} />);

    drop([file("coa.pdf"), file("notes.docx")]);

    expect(onAccept).toHaveBeenCalledWith([expect.objectContaining({ name: "coa.pdf" })]);
    expect(screen.getByRole("alert")).toHaveTextContent("notes.docx is not a supported file.");
  });

  it("shows the drop target while a file is dragged over it", () => {
    render(<UploadDropzone onAccept={vi.fn()} />);
    const zone = screen.getByTestId("dropzone");

    const over = createEvent.dragEnter(zone);
    Object.defineProperty(over, "dataTransfer", { value: { types: ["Files"] } });
    fireEvent(zone, over);
    expect(zone).toHaveAttribute("data-dragging", "true");

    fireEvent.dragLeave(zone);
    expect(zone).not.toHaveAttribute("data-dragging");
  });

  it("shows what is uploading", () => {
    render(<UploadDropzone onAccept={vi.fn()} uploading="coa.pdf" />);

    expect(screen.getByRole("status")).toHaveTextContent("Uploading coa.pdf");
  });

  it("shows a server error passed in", () => {
    render(<UploadDropzone onAccept={vi.fn()} error="This file is larger than 50 MB." />);

    expect(screen.getByRole("alert")).toHaveTextContent("This file is larger than 50 MB.");
  });

  it("opens the file picker from outside", () => {
    const ref = createRef<UploadDropzoneHandle>();
    render(<UploadDropzone ref={ref} onAccept={vi.fn()} />);
    const click = vi.spyOn(screen.getByLabelText("Choose files to upload"), "click");

    ref.current!.open();

    expect(click).toHaveBeenCalled();
  });
});
