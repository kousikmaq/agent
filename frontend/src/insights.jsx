import { useRef, useState } from "react";
import { toPng } from "html-to-image";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell, LabelList,
  PieChart, Pie, Legend, ComposedChart, Line,
} from "recharts";

const PALETTE = ["#5B8DD6", "#3FA99B", "#D9A441", "#8C6FC0", "#CC6677", "#5FA84E", "#E08A5B", "#6FB1C0"];

function ChartCard({ chart }) {
  const { type, title, insight, data, unit } = chart;
  return (
    <div className="ins-chart">
      <div className="ins-chart-title">{title}</div>
      <div className="ins-chart-body">
        <ResponsiveContainer width="100%" height={190}>
          {type === "pie" ? (
            <PieChart>
              <Pie data={data} dataKey="value" nameKey="name" innerRadius={38} outerRadius={68} paddingAngle={2}>
                {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
              </Pie>
              <Tooltip formatter={(v) => `${v}${unit || ""}`} />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          ) : type === "band" ? (
            <ComposedChart data={data} margin={{ top: 6, right: 10, left: -12, bottom: 0 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#5A6675" }} />
              <YAxis tick={{ fontSize: 10, fill: "#5A6675" }} />
              <Tooltip formatter={(v, n) => [Array.isArray(v) ? `${v[0]}–${v[1]}` : v, n === "range" ? "P10–P90" : "forecast"]} />
              <Bar dataKey="range" fill="#cfe0f5" radius={[4, 4, 4, 4]} barSize={20} />
              <Line dataKey="mid" stroke="#5B8DD6" strokeWidth={2} dot={{ r: 3 }} name="forecast" />
            </ComposedChart>
          ) : type === "barh" ? (
            <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 0 }}>
              <XAxis type="number" tick={{ fontSize: 10, fill: "#5A6675" }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: "#5A6675" }} width={64} />
              <Tooltip formatter={(v) => `${v}${unit || ""}`} />
              <Bar dataKey="value" radius={[0, 5, 5, 0]} barSize={16}>
                {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
                <LabelList dataKey="value" position="right" formatter={(v) => `${v}${unit || ""}`} style={{ fontSize: 10, fill: "#5A6675" }} />
              </Bar>
            </BarChart>
          ) : (
            <BarChart data={data} margin={{ top: 8, right: 10, left: -14, bottom: 0 }}>
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#5A6675" }} />
              <YAxis tick={{ fontSize: 10, fill: "#5A6675" }} />
              <Tooltip formatter={(v) => `${v}${unit || ""}`} />
              <Bar dataKey="value" radius={[5, 5, 0, 0]} barSize={26}>
                {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
              </Bar>
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
      <div className="ins-chart-insight">💡 {insight}</div>
    </div>
  );
}

export default function InsightsReport({ report, onEmailImage }) {
  const ref = useRef(null);
  const [busy, setBusy] = useState("");

  async function capture() {
    if (!ref.current) return null;
    return toPng(ref.current, { pixelRatio: 2, backgroundColor: "#ffffff", cacheBust: true });
  }
  async function download() {
    setBusy("download");
    try {
      const url = await capture();
      if (url) {
        const a = document.createElement("a");
        a.href = url; a.download = `production_insights_${Date.now()}.png`;
        document.body.appendChild(a); a.click(); a.remove();
      }
    } finally { setBusy(""); }
  }
  async function email() {
    setBusy("email");
    try {
      const url = await capture();
      if (url) onEmailImage?.(url, report);
    } finally { setBusy(""); }
  }

  return (
    <div className="insights">
      <div className="ins-actions-bar">
        <div>
          <div className="ins-heading">📊 {report.headline}</div>
          <div className="ins-time">Generated {report.generated_at}</div>
        </div>
        <div className="ins-buttons">
          <button className="ins-btn" onClick={download} disabled={busy === "download"}>
            {busy === "download" ? "…" : "⬇ Download"}
          </button>
          <button className="ins-btn primary" onClick={email} disabled={busy === "email"}>
            {busy === "email" ? "…" : "✉️ Email report"}
          </button>
        </div>
      </div>

      <div className="ins-capture" ref={ref}>
        <div className="ins-kpis">
          {report.kpis.map((kpi, i) => (
            <div key={i} className={`ins-kpi ${kpi.tone}`}>
              <div className="ins-kpi-v">{kpi.value}</div>
              <div className="ins-kpi-l">{kpi.label}</div>
            </div>
          ))}
        </div>

        <div className="ins-narrative">
          <div className="ins-narrative-title">Key takeaways</div>
          <ul>{report.narrative.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </div>

        <div className="ins-grid">
          {report.charts.map((c) => <ChartCard key={c.id} chart={c} />)}
        </div>
        <div className="ins-foot">Production &amp; Scheduling Assistant · {report.generated_at}</div>
      </div>
    </div>
  );
}
