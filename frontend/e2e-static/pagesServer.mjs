// Serves dist/ the way GitHub Pages serves a project site: mounted at /pharma-ocr-date-rag/, files
// only (no single-page-app fallback), and 404.html with status 404 for any other path.
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";

const DIST = resolve(import.meta.dirname, "../dist");
const BASE = "/pharma-ocr-date-rag/";
const PORT = Number(process.argv[2] ?? 4175);
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".mjs": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".wasm": "application/wasm",
  ".json": "application/json",
  ".ttf": "font/ttf",
};

function send(res, status, path) {
  res.writeHead(status, { "Content-Type": TYPES[extname(path)] ?? "application/octet-stream" });
  createReadStream(path).pipe(res);
}

createServer((req, res) => {
  const path = decodeURIComponent((req.url ?? "/").split("?")[0]);
  if (path.startsWith(BASE)) {
    let file = normalize(join(DIST, path.slice(BASE.length)));
    if (file.startsWith(DIST) && existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
    if (file.startsWith(DIST) && existsSync(file) && statSync(file).isFile()) return send(res, 200, file);
  }
  send(res, 404, join(DIST, "404.html"));
}).listen(PORT, "127.0.0.1");
