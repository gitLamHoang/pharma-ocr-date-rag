import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "./client";
import { ApiError, httpDataSource } from "./client";

const fetchMock = vi.fn<typeof fetch>();

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function lastCall(): { url: string; method: string; init: RequestInit } {
  const [input, init = {}] = fetchMock.mock.calls.at(-1)!;
  return { url: String(input), method: (init.method ?? "GET").toUpperCase(), init };
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(json([]));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("API client requests", () => {
  it.each([
    ["getHealth", () => client.getHealth(), "/api/health"],
    ["getTaxonomy", () => client.getTaxonomy(), "/api/taxonomy"],
    ["listDocuments", () => client.listDocuments(), "/api/documents"],
    ["getDocument", () => client.getDocument(7), "/api/documents/7"],
    ["getPages", () => client.getPages(12), "/api/runs/12/pages"],
    ["getDates", () => client.getDates(12), "/api/runs/12/dates"],
    ["getFlags", () => client.getFlags(12), "/api/runs/12/flags"],
    ["getDiscarded", () => client.getDiscarded(12), "/api/runs/12/discarded"],
    ["getHistory", () => client.getHistory(31), "/api/dates/31/history"],
  ])("%s sends GET %s", async (_name, call, url) => {
    await call();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(lastCall()).toMatchObject({ url, method: "GET" });
  });

  it("uploadDocument posts the file as the multipart field 'file'", async () => {
    fetchMock.mockResolvedValue(json({ document_id: 3, run_id: 5, status: "queued" }, 202));
    const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "coa.pdf", { type: "application/pdf" });

    const result = await client.uploadDocument(file);

    const { url, method, init } = lastCall();
    expect(url).toBe("/api/documents");
    expect(method).toBe("POST");
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("file")).toBe(file);
    // The browser must set the multipart boundary itself.
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
    expect(result).toEqual({ document_id: 3, run_id: 5, status: "queued" });
  });

  it("reviewDate posts the decision as JSON", async () => {
    fetchMock.mockResolvedValue(json({ id: 1, date_id: 31, action: "correct" }, 201));
    const body = { action: "correct", reviewer: "M. Laurent", reason: "Label says retest", new_type: "retest_date" } as const;

    await client.reviewDate(31, body);

    const { url, method, init } = lastCall();
    expect(url).toBe("/api/dates/31/review");
    expect(method).toBe("POST");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init.body))).toEqual(body);
  });

  it("reprocess posts to the document's reprocess endpoint", async () => {
    fetchMock.mockResolvedValue(json({ run_id: 9 }, 202));

    expect(await client.reprocess(4)).toEqual({ run_id: 9 });
    expect(lastCall()).toMatchObject({ url: "/api/documents/4/reprocess", method: "POST" });
  });
});

describe("API client URLs", () => {
  it("pageImageUrl points at the run's page PNG without fetching", () => {
    expect(client.pageImageUrl(7, 2)).toBe("/api/runs/7/pages/2.png");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("exportUrl names the run and the format", () => {
    expect(client.exportUrl(12, "csv")).toBe("/api/runs/12/export?format=csv");
    expect(client.exportUrl(12, "json")).toBe("/api/runs/12/export?format=json");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("API client errors", () => {
  it("throws ApiError with the server's detail and status", async () => {
    fetchMock.mockResolvedValue(json({ detail: "This run is frozen: a newer run exists." }, 409));

    const error = await client.reviewDate(1, { action: "accept", reviewer: "A", reason: "ok" }).catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.message).toBe("This run is frozen: a newer run exists.");
  });

  it("falls back to the status text when the body is not JSON", async () => {
    fetchMock.mockResolvedValue(new Response("<html>Bad gateway</html>", { status: 502, statusText: "Bad Gateway" }));

    const error = await client.listDocuments().catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
    expect(error.message).toBe("The server answered 502 Bad Gateway.");
  });

  it("reports a network failure as status 0", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const error = await client.getHealth().catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(0);
    expect(error.message).toMatch(/could not reach the server/i);
  });
});

describe("httpDataSource", () => {
  it("implements every DataSource method with the HTTP client", () => {
    expect(Object.keys(httpDataSource).sort()).toEqual(
      [
        "exportUrl",
        "getDates",
        "getDiscarded",
        "getDocument",
        "getFlags",
        "getHealth",
        "getHistory",
        "getPages",
        "getTaxonomy",
        "listDocuments",
        "pageImageUrl",
        "reprocess",
        "reviewDate",
        "uploadDocument",
      ].sort(),
    );
    expect(httpDataSource.getDates).toBe(client.getDates);
  });
});
