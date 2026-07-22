import { useState } from "react";
import { api, ApiError } from "../../api/client";
import { toast } from "../Toast";

interface Props {
  businessDate: string;
  onClose?: () => void;
}

interface Message {
  role: "user" | "assistant";
  text: string;
}

/** Starter questions the user can click to ask the explain-only assistant. */
const SUGGESTIONS = [
  "What are the top capacity bottlenecks today?",
  "Why are orders at risk of being late?",
  "Which recommendations are feasible right now?",
  "How does the overtime scenario compare to the baseline?",
  "What is driving the makespan?",
];

const MATERIAL_RE = /\b(RM-\d+)\b/;

interface QuickAction {
  key: string;
  label: string;
  run: () => Promise<void>;
}

/** Derive agentic follow-up actions from an assistant answer. */
function suggestedActions(text: string, date: string): QuickAction[] {
  const actions: QuickAction[] = [];
  if (/\brisk|late|bottleneck|overdue|delay/i.test(text)) {
    actions.push({
      key: "email-risks",
      label: "✉ Email risk summary",
      run: async () => {
        const r = await api.emailReport(date, {
          report_type: "risks",
          preview: false,
        });
        toast(
          `Risk summary emailed to ${"recipient" in r ? r.recipient : "the team"}`,
          "success"
        );
      },
    });
  }
  const mat = text.match(MATERIAL_RE);
  if (mat) {
    const item = mat[1];
    actions.push({
      key: `order-${item}`,
      label: `📦 Place order for ${item}`,
      run: async () => {
        const r = await api.placeOrder({
          item,
          reason: "Requested from the assistant conversation.",
        });
        toast(
          `Purchase order for ${item} emailed to ${
            "recipient" in r ? r.recipient : "the team"
          }`,
          "success"
        );
      },
    });
  }
  return actions;
}

/** Row of agentic action chips shown under an assistant answer. */
function ActionChips({ text, date }: { text: string; date: string }) {
  const [busy, setBusy] = useState<string | null>(null);
  const actions = suggestedActions(text, date);
  if (actions.length === 0) return null;
  return (
    <div className="chat-actions">
      {actions.map((a) => (
        <button
          key={a.key}
          type="button"
          className="chat-action-chip"
          disabled={busy !== null}
          onClick={async () => {
            setBusy(a.key);
            try {
              await a.run();
            } catch (e) {
              toast(
                e instanceof ApiError ? e.message : "Action failed",
                "error"
              );
            } finally {
              setBusy(null);
            }
          }}
        >
          {busy === a.key ? "Working…" : a.label}
        </button>
      ))}
    </div>
  );
}

/**
 * Planner chat assistant. Sends questions to the explain-only Azure OpenAI
 * endpoint, which is grounded solely on the day's explanation context.
 */
export function ChatAssistant({ businessDate, onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(text?: string) {
    const question = (text ?? input).trim();
    if (!question || busy) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setBusy(true);
    try {
      const res = await api.ask(businessDate, question);
      setMessages((m) => [...m, { role: "assistant", text: res.answer }]);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Failed to reach the assistant.";
      setMessages((m) => [...m, { role: "assistant", text: `⚠ ${message}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      {onClose && (
        <div className="chat-header">
          <span className="chat-title">Assistant</span>
          <button
            className="chat-close"
            onClick={onClose}
            aria-label="Close assistant"
            title="Close assistant"
          >
            ×
          </button>
        </div>
      )}
      <div className="chat-log">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <p className="empty">
              Ask about the schedule, KPIs, risks, recommendations, or scenarios.
            </p>
            <div className="chat-suggestions">
              {SUGGESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="chat-chip"
                  onClick={() => send(q)}
                  disabled={busy}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role}`}>
            <span className="chat-role">{m.role === "user" ? "You" : "Assistant"}</span>
            <div className="chat-text">{m.text}</div>
            {m.role === "assistant" && (
              <ActionChips text={m.text} date={businessDate} />
            )}
          </div>
        ))}
        {busy && <div className="chat-msg assistant">Thinking…</div>}
      </div>
      {messages.length > 0 && (
        <div className="chat-suggestions compact">
          {SUGGESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              className="chat-chip"
              onClick={() => send(q)}
              disabled={busy}
            >
              {q}
            </button>
          ))}
        </div>
      )}
      <div className="chat-input">
        <input
          type="text"
          value={input}
          placeholder="e.g. Why is order ORD-0012 late?"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send();
          }}
          disabled={busy}
        />
        <button onClick={() => send()} disabled={busy || input.trim().length === 0}>
          Send
        </button>
      </div>
    </div>
  );
}
