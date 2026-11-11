import { useState } from "react";

export const THEME_KEY = "pharma-dates:theme";

type Choice = "system" | "light" | "dark";

const CHOICES: { value: Choice; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

function readChoice(): Choice {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // Storage blocked: follow the system.
  }
  return "system";
}

function applyChoice(choice: Choice): void {
  const root = document.documentElement;
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
  try {
    if (choice === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, choice);
  } catch {
    // Storage blocked: the choice lasts for this page only.
  }
}

/** System / Light / Dark. The pre-paint script in index.html applies the saved choice on load. */
export function ThemeToggle() {
  const [choice, setChoice] = useState<Choice>(readChoice);

  return (
    <fieldset className="segmented">
      <legend className="visually-hidden">Theme</legend>
      {CHOICES.map(({ value, label }) => (
        <label key={value} className="segmented__option">
          <input
            type="radio"
            name="theme"
            value={value}
            checked={choice === value}
            onChange={() => {
              setChoice(value);
              applyChoice(value);
            }}
          />
          <span>{label}</span>
        </label>
      ))}
    </fieldset>
  );
}
