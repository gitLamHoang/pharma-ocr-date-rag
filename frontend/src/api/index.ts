import { httpDataSource } from "./client";
import type { DataSource } from "./dataSource";

/**
 * The data source the app uses. Today this is always the HTTP client; the static build
 * (`VITE_MODE=static`, GitHub Pages) will select an in-browser implementation here.
 */
export const api: DataSource = httpDataSource;

export { ApiError } from "./client";
export type { DataSource } from "./dataSource";
export type * from "./types";
