import { httpDataSource } from "./client";
import type { DataSource } from "./dataSource";
import { createStaticDataSource } from "./static/staticDataSource";
import { openStorage } from "./static/storage";
import { browserEngine } from "../engine";

/** The static build (`VITE_MODE=static`, GitHub Pages): no server, everything in this browser. */
export const STATIC_MODE = import.meta.env.VITE_MODE === "static";

/**
 * The data source the app uses: the HTTP client, or in the static build the in-browser one
 * (documents read, checked and stored in this browser; nothing is uploaded).
 */
export const api: DataSource = STATIC_MODE
  ? createStaticDataSource({ storage: openStorage(), engine: browserEngine })
  : httpDataSource;

export { ApiError } from "./client";
export type { DataSource } from "./dataSource";
export type * from "./types";
