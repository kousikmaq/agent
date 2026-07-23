/**
 * Email actions with a preview-before-send modal and a role selector.
 *
 * `ReportEmailButton` renders a role dropdown + an "Email" button. Clicking it
 * opens a modal that previews the professionally formatted email (fetched from
 * the backend without sending), then lets the user send it. Used across tabs.
 */
import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { EmailPreviewResponse, EmailResult } from "../../types/api";
import { ActionButton } from "../ActionButton";
import { toast } from "../Toast";

/** Operational roles a report can be addressed to (mirrors the backend). */
export const ROLES = [
  "Production Planner",
  "Manufacturing Manager",
  "Operations Manager",
  "Plant Scheduler",
] as const;

function isPreview(r: EmailResult): r is EmailPreviewResponse {
  return "html" in r;
}

interface ModalProps {
  title: string;
  role: string | null;
  fetchPreview: () => Promise<EmailResult>;
  send: () => Promise<EmailResult>;
  onClose: () => void;
}

function EmailPreviewModal({ title, role, fetchPreview, send, onClose }: ModalProps) {
  const [preview, setPreview] = useState<EmailPreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchPreview()
      .then((r) => {
        if (!active) return;
        if (isPreview(r)) setPreview(r);
      })
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Could not render preview.")
      );
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const doSend = async () => {
    try {
      const r = await send();
      const recipient = "recipient" in r ? r.recipient : "the team";
      toast(`Email sent to ${recipient}`, "success");
      onClose();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Failed to send email", "error");
      throw e;
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card email-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="email-modal-title">{title}</div>
            {preview && (
              <div className="email-modal-meta">
                To <strong>{preview.recipient}</strong>
                {role && (
                  <>
                    {" "}
                    · as <strong>{role}</strong>
                  </>
                )}
              </div>
            )}
          </div>
          <button className="chat-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="email-modal-body">
          {error ? (
            <p className="login-error">{error}</p>
          ) : !preview ? (
            <div className="email-modal-loading">
              <span className="ab-spinner" aria-hidden /> Rendering preview…
            </div>
          ) : (
            <>
              <div className="email-modal-subject">{preview.subject}</div>
              <iframe
                className="email-preview-frame"
                title="Email preview"
                sandbox=""
                srcDoc={preview.html}
              />
            </>
          )}
        </div>
        <div className="email-modal-foot">
          <button className="rec-dismiss" onClick={onClose}>
            Cancel
          </button>
          <ActionButton
            icon="✉"
            label="Send email"
            pendingLabel="Sending…"
            successLabel="Sent"
            disabled={!preview}
            onAction={doSend}
          />
        </div>
      </div>
    </div>
  );
}

interface Props {
  date: string;
  reportType: string;
  label?: string;
}

/** "Email" button that opens the preview-before-send modal for a tab. */
export function ReportEmailButton({
  date,
  reportType,
  label = "Email report",
}: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="email-cta">
      <button
        type="button"
        className="action-btn ab-primary email-open-btn"
        onClick={() => setOpen(true)}
      >
        <span className="ab-icon" aria-hidden>
          ✉
        </span>
        {label}
      </button>
      {open && (
        <EmailPreviewModal
          title={label}
          role={null}
          fetchPreview={() =>
            api.emailReport(date, {
              report_type: reportType,
              role: null,
              preview: true,
            })
          }
          send={() =>
            api.emailReport(date, {
              report_type: reportType,
              role: null,
              preview: false,
            })
          }
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}
