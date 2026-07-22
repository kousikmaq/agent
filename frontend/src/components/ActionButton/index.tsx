/**
 * ActionButton — a button that runs an async action and animates through
 * idle → loading (spinner) → success (check + confetti) / error states.
 *
 * Keeps its own transient state so callers only provide the async work and
 * labels. On success it shows a brief confetti burst, then returns to idle.
 */
import { useCallback, useRef, useState } from "react";

type Status = "idle" | "loading" | "success" | "error";

interface Props {
  /** The async work to run when clicked. Reject to show the error state. */
  onAction: () => Promise<void>;
  /** Idle label. */
  label: string;
  /** Label while running. */
  pendingLabel?: string;
  /** Label shown briefly on success. */
  successLabel?: string;
  /** Optional leading icon (emoji or short glyph). */
  icon?: string;
  /** Visual style. */
  variant?: "primary" | "ghost";
  /** Disable the button. */
  disabled?: boolean;
  className?: string;
}

export function ActionButton({
  onAction,
  label,
  pendingLabel = "Sending…",
  successLabel = "Sent",
  icon,
  variant = "primary",
  disabled = false,
  className = "",
}: Props) {
  const [status, setStatus] = useState<Status>("idle");
  const resetTimer = useRef<number | undefined>(undefined);

  const run = useCallback(async () => {
    if (status === "loading") return;
    window.clearTimeout(resetTimer.current);
    setStatus("loading");
    try {
      await onAction();
      setStatus("success");
      resetTimer.current = window.setTimeout(() => setStatus("idle"), 2200);
    } catch {
      setStatus("error");
      resetTimer.current = window.setTimeout(() => setStatus("idle"), 2600);
    }
  }, [onAction, status]);

  const content =
    status === "loading" ? (
      <>
        <span className="ab-spinner" aria-hidden />
        {pendingLabel}
      </>
    ) : status === "success" ? (
      <>
        <span className="ab-check" aria-hidden>
          ✓
        </span>
        {successLabel}
      </>
    ) : status === "error" ? (
      <>
        <span className="ab-error-icon" aria-hidden>
          !
        </span>
        Failed — retry
      </>
    ) : (
      <>
        {icon && (
          <span className="ab-icon" aria-hidden>
            {icon}
          </span>
        )}
        {label}
      </>
    );

  return (
    <button
      type="button"
      className={`action-btn ab-${variant} ab-${status} ${className}`.trim()}
      onClick={run}
      disabled={disabled || status === "loading"}
    >
      {status === "success" && (
        <span className="ab-confetti" aria-hidden>
          {Array.from({ length: 8 }).map((_, i) => (
            <i key={i} style={{ ["--i" as string]: i }} />
          ))}
        </span>
      )}
      {content}
    </button>
  );
}
