import type { RunStatus } from "../api";

const LABELS: Record<RunStatus, string> = {
  queued: "Queued",
  reading: "Reading",
  classifying: "Classifying",
  validating: "Validating",
  done: "Done",
  failed: "Failed",
};

const TONES: Partial<Record<RunStatus, string>> = { done: "", failed: " pill--danger" };

/** A run's status as a pill: in progress in info, done plain, failed in danger. */
export function StatusBadge({ status }: { status: RunStatus }) {
  return <span className={"pill" + (TONES[status] ?? " pill--info")}>{LABELS[status]}</span>;
}
