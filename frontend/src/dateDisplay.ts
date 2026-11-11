/** How dates and their labels read on screen. English only. */
import type { DateRecord, FamilyId, Taxonomy } from "./api";

/** The taxonomy's order (backend `taxonomy.FAMILIES`). */
export const FAMILY_ORDER: FamilyId[] = ["product", "document", "signature", "legal", "audit", "logistics", "other"];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Two or more readings and no value yet (`09/10/2026` without evidence). */
export function isAmbiguous(date: DateRecord): boolean {
  return date.current_value === null && date.candidates.length > 1;
}

/** `2027-03` → `Mar 2027`; anything that is not a month value → null. */
export function monthLabel(value: string): string | null {
  const match = /^(\d{4})-(\d{2})$/.exec(value);
  const month = match ? Number(match[2]) : 0;
  return match && month >= 1 && month <= 12 ? `${MONTHS[month - 1]} ${match[1]}` : null;
}

/** `YYYY-MM-DD`, or `YYYY-MM` for a month-only date, and a real calendar date. */
export function isDateValue(value: string): boolean {
  const match = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(value);
  if (!match) return false;
  const [year, month] = [Number(match[1]), Number(match[2])];
  if (month < 1 || month > 12) return false;
  if (match[3] === undefined) return true;
  const day = Number(match[3]);
  return day >= 1 && day <= new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function humanize(id: string): string {
  const words = id.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export interface Labels {
  type(id: string): string;
  family(id: FamilyId): string;
}

/** Labels from `/api/taxonomy`; ids read as words until it has loaded. */
export function makeLabels(taxonomy: Taxonomy | undefined): Labels {
  const types = new Map<string, string>();
  const families = new Map<string, string>();
  for (const family of taxonomy ?? []) {
    families.set(family.family, family.label);
    for (const t of family.types) types.set(t.id, t.label);
  }
  return {
    type: (id) => types.get(id) ?? humanize(id),
    family: (id) => families.get(id) ?? humanize(id),
  };
}

export interface FamilyGroup {
  family: FamilyId;
  dates: DateRecord[];
}

/** Dates grouped by their current family in taxonomy order, each group in reading order. */
export function groupByFamily(dates: DateRecord[]): FamilyGroup[] {
  return FAMILY_ORDER.map((family) => ({ family, dates: dates.filter((d) => d.current_family === family) })).filter(
    (group) => group.dates.length > 0,
  );
}

export interface Snippet {
  before: string;
  match: string;
  after: string;
}

/**
 * The words around the date in its context, cut at word boundaries about `reach` characters each
 * side, with an ellipsis where text was cut. The date itself is `match` (empty if not found).
 */
export function snippet(context: string, raw: string, reach = 48): Snippet {
  const text = context.replace(/\s+/g, " ").trim();
  // Spaced the same way as the context: a date printed across a line break ("March 4,\n1999").
  const needle = raw.replace(/\s+/g, " ").trim();
  const at = needle ? text.indexOf(needle) : -1;
  if (at < 0) return { before: text, match: "", after: "" };
  let start = Math.max(0, at - reach);
  let end = Math.min(text.length, at + needle.length + reach);
  if (start > 0) start = text.indexOf(" ", start) + 1 || start;
  if (end < text.length) end = Math.max(text.lastIndexOf(" ", end), at + needle.length);
  return {
    before: (start > 0 ? "…" : "") + text.slice(start, at),
    match: needle,
    after: text.slice(at + needle.length, end) + (end < text.length ? "…" : ""),
  };
}

/** `2026-11-11 09:05` in the reader's local time. */
export function formatTimestamp(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())} ${pad(at.getHours())}:${pad(at.getMinutes())}`;
}
