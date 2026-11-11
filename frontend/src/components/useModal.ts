import { useEffect, type RefObject } from "react";

/**
 * Shows the dialog as a modal while the component is mounted. On unmount it closes it and gives
 * focus back to the element that had it, or to `fallback()` when that element is gone, disabled
 * or was the page itself. The parent removes the dialog before this cleanup runs, so the browser's
 * own focus return never happens.
 */
export function useModal(ref: RefObject<HTMLDialogElement>, fallback?: () => HTMLElement | null) {
  useEffect(() => {
    const element = ref.current!;
    const active = document.activeElement;
    const opener = active instanceof HTMLElement && active !== document.body ? active : null;
    element.showModal();
    return () => {
      element.close();
      const usable = opener?.isConnected && !opener.matches(":disabled") ? opener : null;
      (usable ?? fallback?.())?.focus();
    };
  }, []); // once per mount; `fallback` reads the page when the dialog closes
}
