/** The page's side of the Pyodide worker (`worker.ts`): one worker, requests matched by id. */
import type { Request, Response } from "./worker";

type Pending = { resolve: (value: string) => void; reject: (error: Error) => void };
type Payload = Request extends infer R ? (R extends Request ? Omit<R, "id"> : never) : never;

let worker: Worker | null = null;
let nextId = 1;
const pending = new Map<number, Pending>();

function call(payload: Payload): Promise<string> {
  if (!worker) {
    worker = new Worker(new URL("./worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (event: MessageEvent<Response>) => {
      const reply = event.data;
      const waiting = pending.get(reply.id);
      pending.delete(reply.id);
      if (!waiting) return;
      if (reply.ok) waiting.resolve(reply.result);
      else waiting.reject(new Error(`Python core failed (${reply.error})`));
    };
    worker.onerror = () => {
      for (const waiting of pending.values()) waiting.reject(new Error("Python core failed to load"));
      pending.clear();
      worker?.terminate();
      worker = null;
    };
  }
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker!.postMessage({ ...payload, id });
  });
}

export const python = {
  /** Start loading Python now, so it is ready when the pages have been read. */
  warm: () => call({ op: "warm" }).catch(() => ""),
  process: (layouts: string, today: string) => call({ op: "process", layouts, today }),
  taxonomy: () => call({ op: "taxonomy" }),
};
