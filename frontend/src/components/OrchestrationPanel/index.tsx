import type { OrchestrationResult } from "../../types/api";

interface Props {
  result: OrchestrationResult;
  onApprove?: () => void;
  onReject?: () => void;
  busy?: boolean;
}

function stateClass(state: string): string {
  if (state === "COMPLETED") return "feas-ok";
  if (state === "AWAITING_APPROVAL") return "feas-approve";
  return "feas-no";
}

/** MAF workflow execution trace (per-agent timing/status) plus the answer. */
export function OrchestrationPanel({ result, onApprove, onReject, busy }: Props) {
  const awaiting =
    result.state === "AWAITING_APPROVAL" && !!result.pending_gate;

  return (
    <div className="panel-list">
      <div className="list-item-head">
        <span className={`badge ${stateClass(result.state)}`}>{result.state}</span>
        <span className="list-item-title">
          {result.workflow} · {result.total_duration_ms.toFixed(0)} ms
        </span>
        {result.persisted && <span className="list-item-tag">persisted</span>}
      </div>
      <p className="muted">{result.message}</p>

      {awaiting && (
        <div className="approval-bar">
          <span>
            Awaiting approval after <strong>{result.pending_gate}</strong>.
          </span>
          <div className="approval-actions">
            <button className="primary" onClick={onApprove} disabled={busy}>
              Approve
            </button>
            <button onClick={onReject} disabled={busy}>
              Reject
            </button>
          </div>
        </div>
      )}

      <table className="data-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Agent</th>
            <th>Status</th>
            <th>Attempts</th>
            <th>Duration</th>
          </tr>
        </thead>
        <tbody>
          {result.steps.map((step, i) => (
            <tr key={step.agent}>
              <td>{i + 1}</td>
              <td>{step.agent}</td>
              <td>
                <span
                  className={`badge ${
                    step.status === "SUCCESS" ? "feas-ok" : "feas-no"
                  }`}
                >
                  {step.status}
                </span>
              </td>
              <td>{step.attempts}</td>
              <td>{step.duration_ms.toFixed(0)} ms</td>
            </tr>
          ))}
        </tbody>
      </table>

      {result.answer && (
        <div className="list-item">
          <div className="list-item-head">
            <span className="list-item-title">Assistant answer</span>
            <span className="list-item-tag">explain-only</span>
          </div>
          <div className="chat-text">{result.answer}</div>
        </div>
      )}
    </div>
  );
}
