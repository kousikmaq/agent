/**
 * Minimal global toast system.
 *
 * A module-level store lets any component fire a toast without threading a
 * context through the tree. Mount a single <Toaster /> near the app root.
 */
import { useEffect, useState } from "react";

export type ToastKind = "success" | "error" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

type Listener = (toasts: Toast[]) => void;

let toasts: Toast[] = [];
const listeners = new Set<Listener>();
let nextId = 1;

function emit() {
  for (const listener of listeners) listener(toasts);
}

/** Show a toast. Auto-dismisses after `duration` ms (default 4000). */
export function toast(message: string, kind: ToastKind = "info", duration = 4000) {
  const id = nextId++;
  toasts = [...toasts, { id, kind, message }];
  emit();
  window.setTimeout(() => dismiss(id), duration);
  return id;
}

export function dismiss(id: number) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

/** Renders active toasts. Mount once at the app root. */
export function Toaster() {
  const [items, setItems] = useState<Toast[]>(toasts);
  useEffect(() => {
    listeners.add(setItems);
    return () => {
      listeners.delete(setItems);
    };
  }, []);

  const icon = (kind: ToastKind) =>
    kind === "success" ? "✓" : kind === "error" ? "!" : "i";

  return (
    <div className="toaster" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`}>
          <span className="toast-icon" aria-hidden>
            {icon(t.kind)}
          </span>
          <span className="toast-msg">{t.message}</span>
          <button
            className="toast-close"
            aria-label="Dismiss"
            onClick={() => dismiss(t.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
