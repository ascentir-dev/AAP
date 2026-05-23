import { useEffect, useState, useCallback } from "react";
import {
  Card,
  Callout,
  HTMLTable,
  Tag,
  Spinner,
  NonIdealState,
  ProgressBar,
  Button,
} from "@blueprintjs/core";
import { fetchAnalytics } from "../api/client";
import type { AnalyticsData } from "../api/types";

function pct(n: number) {
  return (n * 100).toFixed(1) + "%";
}

function heatColor(replyRatePct: number): string {
  if (replyRatePct >= 4.0) return "#1D9E75";
  if (replyRatePct >= 3.0) return "#5DCAA5";
  if (replyRatePct >= 2.0) return "#9FE1CB";
  if (replyRatePct > 0) return "#E1F5EE";
  return "#2f3640";
}

export function DashboardPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const d = await fetchAnalytics();
      setData(d);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load]);

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <Spinner size={40} />
        <p style={{ color: "#738091", marginTop: 16 }}>Loading analytics…</p>
      </div>
    );
  }

  if (error) {
    return (
      <NonIdealState
        icon="error"
        title="Could not load analytics"
        description={error}
        action={
          <Button intent="primary" onClick={load}>
            Retry
          </Button>
        }
      />
    );
  }

  if (!data || data.variants.length === 0) {
    return (
      <NonIdealState
        className="empty-state"
        icon="chart"
        title="No data yet"
        description="Run the pipeline against your lead CSV to start seeing analytics here."
      />
    );
  }

  const sig = data.significance;
  const MOTIONS = ["plg_self_serve", "hybrid_sales_assisted", "sales_led_outbound"];

  // Build heatmap grid from flat cells
  const frameworks = [...new Set(data.heatmap.map((c) => c.row_key))].sort();
  const heatGrid = (fw: string, motion: string) =>
    data.heatmap.find((c) => c.row_key === fw && c.col_key === motion);

  return (
    <div>
      <h1 className="page-title">Campaign Dashboard</h1>

      {/* ── Significance banner ── */}
      {sig.ready && sig.significant_winners.length > 0 && (
        <Callout
          className="sig-banner"
          intent="success"
          icon="trophy"
          title={`Winner found: ${sig.leader_variant_id}`}
        >
          {sig.leader_variant_id} ({sig.leader_framework}) is statistically
          beating {sig.significant_winners.join(", ")} at p&lt;0.05 on{" "}
          {data.primary_metric}.
        </Callout>
      )}

      {!sig.ready && (
        <Callout className="sig-banner" intent="primary" icon="time">
          <strong>Gathering data…</strong> {sig.min_sent.toLocaleString()} /{" "}
          {sig.min_required.toLocaleString()} minimum leads per variant.
          <ProgressBar
            value={sig.min_sent / Math.max(sig.min_required, 1)}
            intent="primary"
            animate={false}
            stripes={false}
            style={{ marginTop: 8 }}
          />
        </Callout>
      )}

      {/* ── KPI cards ── */}
      <div className="kpi-grid">
        <Card className="kpi-card">
          <div className="kpi-label">Total Sent</div>
          <div className="kpi-value">{data.total_sent.toLocaleString()}</div>
          <div className="kpi-sub">emails delivered</div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Blended Reply Rate</div>
          <div className="kpi-value">{data.blended_reply_rate.toFixed(2)}%</div>
          <div className="kpi-sub">{data.total_replied.toLocaleString()} replies</div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Calls Booked</div>
          <div className="kpi-value">{data.total_booked.toLocaleString()}</div>
          <div className="kpi-sub">
            {data.total_sent > 0
              ? ((data.total_booked / data.total_sent) * 100).toFixed(2) + "% book rate"
              : "—"}
          </div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Total Cost</div>
          <div className="kpi-value">
            ${data.cost.total_cost_usd.toFixed(2)}
          </div>
          <div className="kpi-sub">
            {data.cost.cost_per_booked != null
              ? `$${data.cost.cost_per_booked.toFixed(2)} / booked call`
              : "—"}
          </div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Variants Running</div>
          <div className="kpi-value">{data.variants.length}</div>
          <div className="kpi-sub">Test: {data.test_id}</div>
        </Card>
      </div>

      {/* ── Variant performance table ── */}
      <div className="section-header">
        <h2 className="section-title">Variant Performance</h2>
        <Tag minimal>Primary metric: {data.primary_metric}</Tag>
      </div>
      <div className="variant-table-wrap" style={{ marginBottom: 24 }}>
        <HTMLTable interactive style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>Variant</th>
              <th>Framework</th>
              <th>Sent</th>
              <th>Open %</th>
              <th>Reply %</th>
              <th>Book %</th>
              <th>Bounce %</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.variants.map((v) => {
              const isLeader = v.variant_id === sig.leader_variant_id;
              return (
                <tr key={v.variant_id} className={isLeader ? "leader-row" : ""}>
                  <td>
                    <strong>{v.variant_id}</strong>
                  </td>
                  <td>{v.framework}</td>
                  <td>{v.sent.toLocaleString()}</td>
                  <td>{pct(v.open_rate)}</td>
                  <td>
                    <strong>{pct(v.reply_rate)}</strong>
                  </td>
                  <td>{pct(v.book_rate)}</td>
                  <td>{pct(v.bounce_rate)}</td>
                  <td>
                    {isLeader && sig.ready ? (
                      <Tag intent="success" minimal icon="trophy">
                        Winner
                      </Tag>
                    ) : isLeader ? (
                      <Tag intent="primary" minimal>
                        Leader
                      </Tag>
                    ) : sig.significant_winners.includes(v.variant_id) ? (
                      <Tag intent="warning" minimal>
                        Losing
                      </Tag>
                    ) : (
                      <Tag minimal>Testing</Tag>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </HTMLTable>
      </div>

      {/* ── Framework × Motion heatmap ── */}
      <div className="section-header">
        <h2 className="section-title">Framework × Motion Heatmap</h2>
        <span style={{ fontSize: 12, color: "#738091" }}>reply rate %</span>
      </div>
      <div className="heatmap-wrap">
        <table className="heatmap-table">
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>Framework</th>
              {MOTIONS.map((m) => (
                <th key={m}>{m.replace(/_/g, " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {frameworks.map((fw) => (
              <tr key={fw}>
                <td style={{ fontWeight: 600, color: "#f6f7f9", textAlign: "left" }}>
                  {fw}
                </td>
                {MOTIONS.map((motion) => {
                  const cell = heatGrid(fw, motion);
                  const rate = cell ? cell.reply_rate * 100 : 0;
                  const color = heatColor(rate);
                  return (
                    <td key={motion}>
                      {cell && cell.sent >= 10 ? (
                        <span
                          className="heatmap-cell"
                          style={{
                            background: color,
                            color: rate >= 2.0 ? "#1a3a2e" : "#738091",
                          }}
                        >
                          {rate.toFixed(1)}%
                        </span>
                      ) : (
                        <span style={{ color: "#5f6b7c" }}>—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Framework roll-up table ── */}
      <div className="section-header">
        <h2 className="section-title">Framework Roll-up</h2>
      </div>
      <div className="variant-table-wrap">
        <HTMLTable interactive style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>Framework</th>
              <th>Variants</th>
              <th>Sent</th>
              <th>Open %</th>
              <th>Reply %</th>
              <th>Book %</th>
            </tr>
          </thead>
          <tbody>
            {data.frameworks.map((f) => (
              <tr key={f.framework}>
                <td>
                  <strong>{f.framework}</strong>
                </td>
                <td>
                  {f.variant_ids.map((v) => (
                    <Tag key={v} minimal style={{ marginRight: 4 }}>
                      {v}
                    </Tag>
                  ))}
                </td>
                <td>{f.sent.toLocaleString()}</td>
                <td>{pct(f.open_rate)}</td>
                <td>
                  <strong>{pct(f.reply_rate)}</strong>
                </td>
                <td>{pct(f.book_rate)}</td>
              </tr>
            ))}
          </tbody>
        </HTMLTable>
      </div>
    </div>
  );
}
