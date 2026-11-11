/**
 * Where the static build keeps its records: IndexedDB in this browser, or memory when IndexedDB
 * is unavailable or blocked (private windows, blocked site data). Review events are append-only:
 * the storage has no way to replace or delete one.
 */

export type Table = "documents" | "runs" | "pages" | "dates" | "flags" | "events";
export const TABLES: Table[] = ["documents", "runs", "pages", "dates", "flags", "events"];

export interface StoredRecord {
  id: number | string;
}

export type Snapshot = Record<Table, unknown[]>;

export interface Storage {
  /** False when records live only in this page's memory. */
  readonly persistent: boolean;
  load(): Promise<Snapshot>;
  /** Insert or replace a record. Review events go through `append` only. */
  put<T extends StoredRecord>(table: Exclude<Table, "events">, record: T): Promise<void>;
  /** Insert a review event; refuses one whose id is already stored. */
  append<T extends StoredRecord>(table: "events", record: T): Promise<void>;
  putBlob(key: string, blob: Blob): Promise<void>;
  getBlob(key: string): Promise<Blob | null>;
}

export const DB_NAME = "pharma-ocr-date-rag";
const DB_VERSION = 1;
const BLOBS = "blobs";

export function memoryStorage(): Storage {
  const tables = Object.fromEntries(TABLES.map((t) => [t, new Map<number | string, unknown>()])) as Record<
    Table,
    Map<number | string, unknown>
  >;
  const blobs = new Map<string, Blob>();
  return {
    persistent: false,
    async load() {
      return Object.fromEntries(TABLES.map((t) => [t, [...tables[t].values()].map((r) => structuredClone(r))])) as Snapshot;
    },
    async put(table, record) {
      tables[table].set(record.id, structuredClone(record));
    },
    async append(table, record) {
      if (tables[table].has(record.id)) throw new Error(`${table} ${record.id} already exists`);
      tables[table].set(record.id, structuredClone(record));
    },
    async putBlob(key, blob) {
      blobs.set(key, blob);
    },
    async getBlob(key) {
      return blobs.get(key) ?? null;
    },
  };
}

function done<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function committed(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error ?? new Error("transaction aborted"));
  });
}

function indexedDbStorage(db: IDBDatabase): Storage {
  async function write(store: string, op: (s: IDBObjectStore) => IDBRequest) {
    const tx = db.transaction(store, "readwrite");
    const finished = committed(tx);
    op(tx.objectStore(store));
    await finished;
  }
  return {
    persistent: true,
    async load() {
      const tx = db.transaction(TABLES, "readonly");
      const all = await Promise.all(TABLES.map((t) => done(tx.objectStore(t).getAll())));
      return Object.fromEntries(TABLES.map((t, i) => [t, all[i]])) as Snapshot;
    },
    put: (table, record) => write(table, (s) => s.put(record)),
    append: (table, record) => write(table, (s) => s.add(record)),
    // Bytes and type rather than the Blob itself: every engine stores an ArrayBuffer reliably.
    async putBlob(key, blob) {
      const record = { type: blob.type, bytes: await blob.arrayBuffer() };
      await write(BLOBS, (s) => s.put(record, key));
    },
    async getBlob(key) {
      const value = (await done(db.transaction(BLOBS, "readonly").objectStore(BLOBS).get(key))) as
        | { type: string; bytes: ArrayBuffer }
        | undefined;
      return value ? new Blob([value.bytes], { type: value.type }) : null;
    },
  };
}

/** IndexedDB storage, or memory storage when IndexedDB cannot be opened. Never rejects. */
export async function openStorage(
  name: string = DB_NAME,
  factory: IDBFactory | null = globalThis.indexedDB ?? null,
): Promise<Storage> {
  try {
    if (!factory) return memoryStorage();
    const request = factory.open(name, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      for (const t of TABLES) if (!db.objectStoreNames.contains(t)) db.createObjectStore(t, { keyPath: "id" });
      if (!db.objectStoreNames.contains(BLOBS)) db.createObjectStore(BLOBS);
    };
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Error("IndexedDB blocked"));
    });
    return indexedDbStorage(db);
  } catch {
    return memoryStorage();
  }
}
