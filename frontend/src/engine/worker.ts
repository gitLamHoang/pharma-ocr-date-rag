/// <reference lib="webworker" />
/// <reference path="./pycore.d.ts" />
/**
 * The Pyodide worker: loads Python (pinned, from jsDelivr) with pydantic, writes the bundled pure
 * core into its file system and runs `pharma_dates.browser`. Messages are JSON strings both ways.
 */
import type { PyodideAPI } from "pyodide";
import files from "virtual:pycore";
import { PYODIDE_INDEX_URL } from "./versions";

export type Request = { id: number; op: "warm" | "taxonomy" } | { id: number; op: "process"; layouts: string; today: string };
export type Response = { id: number; ok: true; result: string } | { id: number; ok: false; error: string };

const CORE_DIR = "/home/pyodide/core";
let python: Promise<PyodideAPI> | null = null;

async function boot(): Promise<PyodideAPI> {
  const { loadPyodide } = (await import(/* @vite-ignore */ `${PYODIDE_INDEX_URL}pyodide.mjs`)) as typeof import("pyodide");
  const pyodide = await loadPyodide({ indexURL: PYODIDE_INDEX_URL });
  await pyodide.loadPackage(["micropip", "pydantic"], { messageCallback: () => {} });
  for (const [path, source] of Object.entries(files)) {
    const target = `${CORE_DIR}/${path}`;
    pyodide.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
    pyodide.FS.writeFile(target, source);
  }
  pyodide.runPython(`import sys\nsys.path.insert(0, ${JSON.stringify(CORE_DIR)})\nimport pharma_dates.browser`);
  return pyodide;
}

const scope = self as unknown as DedicatedWorkerGlobalScope;

scope.onmessage = async (event: MessageEvent<Request>) => {
  const request = event.data;
  try {
    python ??= boot();
    const pyodide = await python;
    const core = pyodide.pyimport("pharma_dates.browser");
    let result = "";
    if (request.op === "process") result = core.process(request.layouts, request.today);
    else if (request.op === "taxonomy") result = core.taxonomy_json();
    scope.postMessage({ id: request.id, ok: true, result } satisfies Response);
  } catch (error) {
    // The type only: a Python traceback can quote document text.
    const name = error instanceof Error ? error.name : "Error";
    if (name !== "PythonError") python = null; // a failed load can be retried
    scope.postMessage({ id: request.id, ok: false, error: name } satisfies Response);
  }
};
