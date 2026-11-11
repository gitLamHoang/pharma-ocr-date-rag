/** The HTTP `DataSource`: one function per backend endpoint. Every error body is `{detail: string}`. */
import type { DataSource } from "./dataSource";
import type {
  DateRecord,
  DiscardedSuggestion,
  DocumentDetail,
  DocumentSummary,
  ExportFormat,
  Flag,
  Health,
  PageInfo,
  ReprocessResult,
  ReviewBody,
  ReviewEvent,
  Taxonomy,
  UploadResult,
} from "./types";

const BASE = "/api";

/** A failed request. `status` is the HTTP status, or 0 when the server could not be reached. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(BASE + path, init);
  } catch {
    throw new ApiError(0, "Could not reach the server. Check that it is running, then try again.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response));
  }
  return (await response.json()) as T;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string" && body.detail) return body.detail;
  } catch {
    // Not JSON (a proxy error page, for example).
  }
  return `The server answered ${response.status} ${response.statusText}`.trim() + ".";
}

function post<T>(path: string, body?: unknown): Promise<T> {
  if (body === undefined) return request<T>(path, { method: "POST" });
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const getHealth = (): Promise<Health> => request("/health");

export const getTaxonomy = (): Promise<Taxonomy> => request("/taxonomy");

export const listDocuments = (): Promise<DocumentSummary[]> => request("/documents");

export function uploadDocument(file: File): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  return request("/documents", { method: "POST", body: form });
}

export const getDocument = (id: number): Promise<DocumentDetail> => request(`/documents/${id}`);

export const getPages = (runId: number): Promise<PageInfo[]> => request(`/runs/${runId}/pages`);

export const pageImageUrl = (runId: number, n: number): string => `${BASE}/runs/${runId}/pages/${n}.png`;

export const getDates = (runId: number): Promise<DateRecord[]> => request(`/runs/${runId}/dates`);

export const getFlags = (runId: number): Promise<Flag[]> => request(`/runs/${runId}/flags`);

export const getDiscarded = (runId: number): Promise<DiscardedSuggestion[]> => request(`/runs/${runId}/discarded`);

export const reviewDate = (id: number, body: ReviewBody): Promise<ReviewEvent> => post(`/dates/${id}/review`, body);

export const getHistory = (id: number): Promise<ReviewEvent[]> => request(`/dates/${id}/history`);

export const reprocess = (id: number): Promise<ReprocessResult> => post(`/documents/${id}/reprocess`);

export const exportUrl = (runId: number, fmt: ExportFormat): string => `${BASE}/runs/${runId}/export?format=${fmt}`;

export const httpDataSource: DataSource = {
  getHealth,
  getTaxonomy,
  listDocuments,
  uploadDocument,
  getDocument,
  getPages,
  pageImageUrl,
  getDates,
  getFlags,
  getDiscarded,
  reviewDate,
  getHistory,
  reprocess,
  exportUrl,
};
