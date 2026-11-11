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

/**
 * Everything the screens read or write. The HTTP client (`client.ts`) is one implementation;
 * a static in-browser one can be swapped in at build time (`VITE_MODE=static`, see `index.ts`).
 * Components get data only through this interface, never through `fetch`.
 */
export interface DataSource {
  getHealth(): Promise<Health>;
  getTaxonomy(): Promise<Taxonomy>;
  listDocuments(): Promise<DocumentSummary[]>;
  uploadDocument(file: File): Promise<UploadResult>;
  getDocument(id: number): Promise<DocumentDetail>;
  /** The pages of one run (a frozen run keeps its own while a newer run is still reading). */
  getPages(runId: number): Promise<PageInfo[]>;
  /** A URL an `<img>` can load for page `n` (1-based) of the run. */
  pageImageUrl(runId: number, n: number): string;
  getDates(runId: number): Promise<DateRecord[]>;
  getFlags(runId: number): Promise<Flag[]>;
  getDiscarded(runId: number): Promise<DiscardedSuggestion[]>;
  reviewDate(id: number, body: ReviewBody): Promise<ReviewEvent>;
  getHistory(id: number): Promise<ReviewEvent[]>;
  reprocess(id: number): Promise<ReprocessResult>;
  /** A URL that downloads the run's export as an attachment. */
  exportUrl(runId: number, fmt: ExportFormat): string;
}
