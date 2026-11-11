import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import type { DateRecord, ReviewBody, Taxonomy } from "../api";
import { isAmbiguous, isDateValue, type Labels } from "../dateDisplay";
import { DateValue, type Decision } from "./DateRow";

/** The reviewer's name is remembered per browser under this key. */
export const REVIEWER_KEY = "pharma-dates:reviewer";

interface Props {
  date: DateRecord;
  action: Decision;
  taxonomy: Taxonomy | undefined;
  labels: Labels;
  /** Resolves when the decision is stored; a rejection's message is shown in the dialog. */
  onSubmit(body: ReviewBody): Promise<void>;
  onClose(): void;
}

const COPY: Record<Decision, { title: string; submit: string }> = {
  accept: { title: "Accept date", submit: "Accept date" },
  correct: { title: "Correct date", submit: "Save correction" },
  reject: { title: "Reject date", submit: "Reject date" },
};

function savedReviewer(): string {
  try {
    return localStorage.getItem(REVIEWER_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveReviewer(name: string): void {
  try {
    localStorage.setItem(REVIEWER_KEY, name);
  } catch {
    // Storage blocked: the name is asked for again next time.
  }
}

interface Errors {
  reviewer?: string;
  reason?: string;
  value?: string;
  form?: string;
}

/** Accept, correct or reject one date. Every decision names its reviewer and a reason. */
export function ReviewDialog({ date, action, taxonomy, labels, onSubmit, onClose }: Props) {
  const ids = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const reviewerInput = useRef<HTMLInputElement>(null);
  const reasonInput = useRef<HTMLInputElement>(null);
  const [reviewer, setReviewer] = useState(savedReviewer);
  const [reason, setReason] = useState("");
  const [type, setType] = useState(date.current_type);
  const [value, setValue] = useState(date.current_value ?? "");
  const [reading, setReading] = useState<string | null>(date.candidates.includes(date.current_value ?? "") ? date.current_value : null);
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // A date the page allows two readings of: the reviewer picks one of them, never types a third.
  const readings = date.candidates.length > 1;
  const copy = COPY[action];

  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    (reviewerInput.current!.value ? reasonInput.current! : reviewerInput.current!).focus();
    return () => element.close();
  }, []);

  function validate(): { errors: Errors; body: ReviewBody } {
    const found: Errors = {};
    const body: ReviewBody = { action, reviewer: reviewer.trim(), reason: reason.trim() };
    if (!body.reviewer) found.reviewer = "Enter your name.";
    if (!body.reason) found.reason = "Say why, in a few words.";
    if (action === "correct") {
      const newValue = readings ? reading : value.trim() || null;
      body.new_type = type !== date.current_type ? type : null;
      body.new_value = newValue !== date.current_value ? newValue : null;
      if (!readings && body.new_value !== null && !isDateValue(body.new_value)) {
        found.value = "Write the date as YYYY-MM-DD, or YYYY-MM for a month-only date.";
      } else if (!readings && body.new_value !== null && date.precision === "month" && body.new_value.length !== 7) {
        // Never invent a day for a month-only date.
        found.value = "The page gives a month only. Write YYYY-MM, without a day.";
      } else if (body.new_type === null && body.new_value === null) {
        found.form = "Change the type or the value, or cancel.";
      }
    }
    return { errors: found, body };
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    const { errors: found, body } = validate();
    setErrors(found);
    setFailure(null);
    if (Object.keys(found).length > 0) return;
    saveReviewer(body.reviewer);
    setSaving(true);
    try {
      await onSubmit(body);
    } catch (error) {
      setFailure(error instanceof Error && error.message ? error.message : "The decision was not saved. Try again.");
      setSaving(false);
    }
  }

  const field = (name: string) => `${ids}-${name}`;
  const described = (name: keyof Errors, hint?: string) =>
    [hint, errors[name] ? field(`${name}-error`) : null].filter(Boolean).join(" ") || undefined;

  return (
    <dialog
      ref={dialog}
      className="review-dialog"
      aria-labelledby={field("title")}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <form className="review-dialog__form" onSubmit={submit} noValidate>
        <header className="review-dialog__head">
          <h2 id={field("title")}>{copy.title}</h2>
          <p className="review-dialog__date">
            <DateValue date={date} />
            <span className="muted">
              {labels.type(date.current_type)} · page {date.page} · as written <span className="mono">{date.raw_text}</span>
            </span>
          </p>
        </header>

        {action === "correct" ? (
          <>
            <div className="field">
              <label className="field__label" htmlFor={field("type")}>
                Date type
              </label>
              <select id={field("type")} className="input" value={type} onChange={(e) => setType(e.target.value)}>
                {(taxonomy ?? []).map((family) => (
                  <optgroup key={family.family} label={family.label}>
                    {family.types.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
                {taxonomy ? null : <option value={date.current_type}>{labels.type(date.current_type)}</option>}
              </select>
            </div>

            {readings ? (
              <fieldset className="field review-dialog__readings">
                <legend className="field__label">Reading</legend>
                <p className="field__hint" id={field("reading-hint")}>
                  {isAmbiguous(date)
                    ? "The page allows both. Choose one only if the document says which."
                    : "The page allows both; the current reading is selected."}
                </p>
                {date.candidates.map((candidate) => (
                  <label key={candidate} className="review-dialog__reading">
                    <input
                      type="radio"
                      name={field("reading")}
                      value={candidate}
                      checked={reading === candidate}
                      onChange={() => setReading(candidate)}
                      aria-describedby={field("reading-hint")}
                    />
                    <span className="mono">{candidate}</span>
                  </label>
                ))}
              </fieldset>
            ) : (
              <div className="field">
                <label className="field__label" htmlFor={field("value")}>
                  Value
                </label>
                <input
                  id={field("value")}
                  className="input mono"
                  value={value}
                  inputMode="numeric"
                  autoComplete="off"
                  spellCheck={false}
                  aria-invalid={errors.value ? true : undefined}
                  aria-describedby={described("value", field("value-hint"))}
                  onChange={(e) => setValue(e.target.value)}
                />
                <p className="field__hint" id={field("value-hint")}>
                  {date.precision === "month"
                    ? "The page gives a month only: YYYY-MM."
                    : "YYYY-MM-DD, or YYYY-MM for a month-only date."}
                </p>
                {errors.value ? (
                  <p className="field__error" id={field("value-error")}>
                    {errors.value}
                  </p>
                ) : null}
              </div>
            )}
          </>
        ) : null}

        <div className="field">
          <label className="field__label" htmlFor={field("reviewer")}>
            Reviewer
          </label>
          <input
            ref={reviewerInput}
            id={field("reviewer")}
            className="input"
            value={reviewer}
            autoComplete="name"
            aria-invalid={errors.reviewer ? true : undefined}
            aria-describedby={described("reviewer", field("reviewer-hint"))}
            onChange={(e) => setReviewer(e.target.value)}
          />
          <p className="field__hint" id={field("reviewer-hint")}>
            Remembered in this browser.
          </p>
          {errors.reviewer ? (
            <p className="field__error" id={field("reviewer-error")}>
              {errors.reviewer}
            </p>
          ) : null}
        </div>

        <div className="field">
          <label className="field__label" htmlFor={field("reason")}>
            Reason
          </label>
          <input
            ref={reasonInput}
            id={field("reason")}
            className="input"
            value={reason}
            autoComplete="off"
            aria-invalid={errors.reason ? true : undefined}
            aria-describedby={described("reason")}
            onChange={(e) => setReason(e.target.value)}
          />
          {errors.reason ? (
            <p className="field__error" id={field("reason-error")}>
              {errors.reason}
            </p>
          ) : null}
        </div>

        {errors.form ? <p className="field__error">{errors.form}</p> : null}
        {failure ? (
          <p className="review-dialog__failure" role="alert">
            {failure}
          </p>
        ) : null}

        <footer className="review-dialog__actions">
          <button type="button" className="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="button button--primary" disabled={saving}>
            {saving ? "Saving" : copy.submit}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
