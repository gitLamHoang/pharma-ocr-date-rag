/**
 * Build steps for the static GitHub Pages build (`VITE_MODE=static`):
 * - `virtual:pycore` bundles the pure Python core (the files listed in
 *   src/engine/pycore-modules.json, read from ../backend) as strings for Pyodide.
 * - pdf.js's decoder wasm, standard fonts, CMaps and ICC profiles are served from `pdfjs/`, so a
 *   PDF never needs a CDN.
 * - `404.html` repeats `index.html`, so GitHub Pages serves the app for deep links.
 */
import { copyFileSync, createReadStream, existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, resolve } from "node:path";
import type { Plugin } from "vite";

const ROOT = import.meta.dirname;
const BACKEND = resolve(ROOT, "../backend");
const MANIFEST = resolve(ROOT, "src/engine/pycore-modules.json");
const PDFJS = resolve(ROOT, "node_modules/pdfjs-dist");
export const PDFJS_ASSET_DIRS = ["wasm", "standard_fonts", "cmaps", "iccs"];
const VIRTUAL = "virtual:pycore";
const RESOLVED = "\0" + VIRTUAL;

export function pycoreModules(): string[] {
  return (JSON.parse(readFileSync(MANIFEST, "utf-8")) as { modules: string[] }).modules;
}

/** `import files from "virtual:pycore"`: `{ "pharma_dates/models.py": "<source>", ... }`. */
export function pycore(): Plugin {
  return {
    name: "pharma-pycore",
    resolveId: (id) => (id === VIRTUAL ? RESOLVED : null),
    load(id) {
      if (id !== RESOLVED) return null;
      this.addWatchFile(MANIFEST);
      const files: Record<string, string> = {};
      for (const rel of pycoreModules()) {
        const path = resolve(BACKEND, rel);
        this.addWatchFile(path);
        files[rel] = readFileSync(path, "utf-8");
      }
      return `export default ${JSON.stringify(files)};`;
    },
  };
}

function* filesIn(dir: string, prefix = ""): Generator<[string, string]> {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* filesIn(path, `${prefix}${name}/`);
    else yield [`${prefix}${name}`, path];
  }
}

const TYPES: Record<string, string> = { ".wasm": "application/wasm", ".js": "text/javascript" };

/** pdf.js assets under `pdfjs/`, and the GitHub Pages 404 fallback. */
export function pagesAssets(): Plugin {
  let outDir = "dist";
  return {
    name: "pharma-pages-assets",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const base = server.config.base;
        const url = (req.url ?? "").split("?")[0];
        if (!url.startsWith(`${base}pdfjs/`)) return next();
        const rel = url.slice(`${base}pdfjs/`.length);
        const path = resolve(PDFJS, rel);
        if (!path.startsWith(PDFJS) || !PDFJS_ASSET_DIRS.includes(rel.split("/")[0]) || !existsSync(path)) return next();
        res.setHeader("Content-Type", TYPES[extname(path)] ?? "application/octet-stream");
        createReadStream(path).pipe(res);
      });
    },
    generateBundle() {
      for (const dir of PDFJS_ASSET_DIRS) {
        for (const [rel, path] of filesIn(join(PDFJS, dir))) {
          if (rel.startsWith("quickjs")) continue; // PDF scripting, which the reader never runs
          this.emitFile({ type: "asset", fileName: `pdfjs/${dir}/${rel}`, source: readFileSync(path) });
        }
      }
    },
    closeBundle() {
      const index = join(outDir, "index.html");
      if (existsSync(index)) copyFileSync(index, join(outDir, "404.html"));
    },
  };
}
