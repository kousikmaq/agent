import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import { toast } from "../Toast";

interface Props {
  businessDate: string;
  onClose?: () => void;
  /** When set (and its nonce changes), the assistant auto-asks this question. */
  seed?: { text: string; nonce: number } | null;
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
  if (/\b(?:risk|late|bottleneck|overdue|delay)/i.test(text)) {
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

/** Animated step-by-step progress shown while the assistant is working. */
const THINKING_STEPS: { label: string; hold: number }[] = [
  { label: "Analysing your question…", hold: 900 },
  { label: "Getting the day's context…", hold: 1200 },
  { label: "Thinking it through…", hold: 1800 },
  { label: "Generating the response…", hold: 4000 },
  // Reached only after ~7.9s, so it flashes briefly right before the answer.
  { label: "Almost done…", hold: 0 },
];

function ThinkingSteps() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const timers: number[] = [];
    let cumulative = 0;
    for (let i = 1; i < THINKING_STEPS.length; i++) {
      cumulative += THINKING_STEPS[i - 1].hold;
      timers.push(window.setTimeout(() => setStep(i), cumulative));
    }
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, []);
  return (
    <div className="chat-msg assistant chat-thinking">
      <span className="ab-spinner" aria-hidden />
      <span className="chat-thinking-text">{THINKING_STEPS[step].label}</span>
    </div>
  );
}

/**
 * Planner chat assistant. Sends questions to the explain-only Azure OpenAI
 * endpoint, which is grounded solely on the day's explanation context.
 */
export function ChatAssistant({ businessDate, onClose, seed }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const lastSeed = useRef<number | null>(null);

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

  // Auto-ask a seeded question (e.g. from an "Ask AI" button on a chart).
  // A new seed starts a fresh conversation before asking.
  useEffect(() => {
    if (seed && seed.nonce !== lastSeed.current) {
      lastSeed.current = seed.nonce;
      setMessages([]);
      setInput("");
      setShowSuggestions(false);
      send(seed.text);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed]);

  const clearChat = () => {
    setMessages([]);
    setInput("");
    setShowSuggestions(false);
  };

  return (
    <div className="chat">
      {onClose && (
        <div className="chat-header">
          <span className="chat-title">Assistant</span>
          <div className="chat-header-actions">
            <button
              className="chat-clear"
              onClick={clearChat}
              disabled={busy || messages.length === 0}
              title="Clear conversation and start fresh"
            >
              Clear
            </button>
            <button
              className="chat-close"
              onClick={onClose}
              aria-label="Close assistant"
              title="Close assistant"
            >
              ×
            </button>
          </div>
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
        {busy && <ThinkingSteps />}
      </div>
      {messages.length > 0 && (
        <div className="chat-suggest-drop">
          <button
            type="button"
            className="chat-suggest-toggle"
            onClick={() => setShowSuggestions((s) => !s)}
          >
            Suggested questions {showSuggestions ? "▴" : "▾"}
          </button>
          {showSuggestions && (
            <div className="chat-suggestions compact">
              {SUGGESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="chat-chip"
                  onClick={() => {
                    send(q);
                    setShowSuggestions(false);
                  }}
                  disabled={busy}
                >
                  {q}
                </button>
              ))}
            </div>
          )}
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
