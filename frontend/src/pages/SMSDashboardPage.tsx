import { useEffect, useState, useCallback } from "react";
import {
  Card,
  HTMLTable,
  Tag,
  Spinner,
  NonIdealState,
  Button,
  ProgressBar,
} from "@blueprintjs/core";

// ─── API Types ────────────────────────────────────────────────────────────────

interface SMSVariantStat {
  variant_id: string;
  name: string;
  framework: string;
  sent: number;
  delivered: number;
  replied: number;
  opted_out: number;
  reply_rate: number;
  opt_out_rate: number;
}

interface SMSNumberStat {
  number: string;
  sent: number;
  delivered: number;
  replied: number;
  opted_out: number;
  reply_rate: number;
}

interface SMSKPIs {
  total_sent: number;
  total_delivered: number;
  total_replied: number;
  total_opted_out: number;
  total_booked: number;
  blended_reply_rate: number;
  blended_opt_out_rate: number;
}

interface SMSAnalytics {
  kpis: SMSKPIs;
  variants: SMSVariantStat[];
  numbers: SMSNumberStat[];
  test_id: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function pct(n: number) {
  return (n * 100).toFixed(1) + "%";
}

function maskNumber(num: string) {
  // Show +1 (XXX) XXX-XXXX → +1 (XXX) ***-XXXX for privacy
  if (num.length >= 10) {
    return num.slice(0, -7) + "***-" + num.slice(-4);
  }
  return num;
}

function replyColor(rate: number): string {
  if (rate >= 0.08) return "#1D9E75";
  if (rate >= 0.05) return "#5DCAA5";
  if (rate >= 0.02) return "#9FE1CB";
  if (rate > 0) return "#E1F5EE";
  return "transparent";
}

// ─── Component ────────────────────────────────────────────────────────────────

export function SMSDashboardPage() {
  const [data, setData] = useState<SMSAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const r = await fetch("/api/sms/analytics");
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const d: SMSAnalytics = await r.json();
      setData(d);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <Spinner size={40} />
        <p style={{ color: "#738091", marginTop: 16 }}>Loading SMS analytics…</p>
      </div>
    );
  }

  if (error) {
    return (
      <NonIdealState
        icon="error"
        title="Could not load SMS analytics"
        description={error}
        action={<Button intent="primary" onClick={load}>Retry</Button>}
      />
    );
  }

  if (!data || data.kpis.total_sent === 0) {
    return (
      <NonIdealState
        className="empty-state"
        icon="mobile-phone"
        title="No SMS data yet"
        description="Add Twilio credentials to .env, then run the SMS pipeline to see analytics here."
      />
    );
  }

  const kpis = data.kpis;

  return (
    <div>
      <h1 className="page-title">SMS Outreach Dashboard</h1>

      {/* ── KPI cards ── */}
      <div className="kpi-grid">
        <Card className="kpi-card">
          <div className="kpi-label">Total Sent</div>
          <div className="kpi-value">{kpis.total_sent.toLocaleString()}</div>
          <div className="kpi-sub">SMS messages delivered</div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Reply Rate</div>
          <div className="kpi-value">{(kpis.blended_reply_rate * 100).toFixed(1)}%</div>
          <div className="kpi-sub">{kpis.total_replied.toLocaleString()} replies</div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Calls Booked</div>
          <div className="kpi-value">{kpis.total_booked.toLocaleString()}</div>
          <div className="kpi-sub">
            {kpis.total_sent > 0
              ? ((kpis.total_booked / kpis.total_sent) * 100).toFixed(2) + "% book rate"
              : "—"}
          </div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Opt-Out Rate</div>
          <div className="kpi-value" style={{ color: kpis.blended_opt_out_rate > 0.03 ? "#e06060" : undefined }}>
            {(kpis.blended_opt_out_rate * 100).toFixed(1)}%
          </div>
          <div className="kpi-sub">{kpis.total_opted_out.toLocaleString()} opted out</div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Variants Running</div>
          <div className="kpi-value">{data.variants.length}</div>
          <div className="kpi-sub">Test: {data.test_id}</div>
        </Card>
      </div>

      {/* ── A/B Variant table ── */}
      <div className="section-header" style={{ marginTop: 32 }}>
        <h2 className="section-title">SMS Variant A/B Test</h2>
        <Tag minimal>Primary metric: reply_rate</Tag>
      </div>
      <div className="variant-table-wrap" style={{ marginBottom: 24 }}>
        <HTMLTable interactive style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>Variant</th>
              <th>Name</th>
              <th>Framework</th>
              <th>Sent</th>
              <th>Delivered</th>
              <th>Reply %</th>
              <th>Opt-Out %</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.variants.map((v) => {
              const color = replyColor(v.reply_rate);
              const isLeader =
                data.variants.length > 0 &&
                v.variant_id ===
                  [...data.variants].sort((a, b) => b.reply_rate - a.reply_rate)[0]
                    .variant_id;
              return (
                <tr key={v.variant_id}>
                  <td><strong>{v.variant_id}</strong></td>
                  <td>{v.name}</td>
                  <td>{v.framework}</td>
                  <td>{v.sent.toLocaleString()}</td>
                  <td>{v.delivered.toLocaleString()}</td>
                  <td>
                    <span
                      style={{
                        background: color,
                        color: v.reply_rate >= 0.02 ? "#1a3a2e" : undefined,
                        padding: "2px 8px",
                        borderRadius: 4,
                        fontWeight: 600,
                      }}
                    >
                      {pct(v.reply_rate)}
                    </span>
                  </td>
                  <td
                    style={{
                      color: v.opt_out_rate > 0.03 ? "#e06060" : undefined,
                    }}
                  >
                    {pct(v.opt_out_rate)}
                  </td>
                  <td>
                    {v.sent < 500 ? (
                      <Tag minimal>Gathering data</Tag>
                    ) : isLeader ? (
                      <Tag intent="primary" minimal>Leader</Tag>
                    ) : (
                      <Tag minimal>Testing</Tag>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </HTMLTable>
        {data.variants.length > 0 && (
          <div style={{ padding: "8px 12px", color: "#738091", fontSize: 12 }}>
            Minimum 500 sends per variant required for significance.
            {(() => {
              const minSent = Math.min(...data.variants.map((v) => v.sent));
              const progress = Math.min(minSent / 500, 1);
              return (
                <ProgressBar
                  value={progress}
                  intent="primary"
                  animate={false}
                  stripes={false}
                  style={{ marginTop: 6 }}
                />
              );
            })()}
          </div>
        )}
      </div>

      {/* ── Per-number performance ── */}
      <div className="section-header">
        <h2 className="section-title">Phone Number Performance</h2>
        <span style={{ fontSize: 12, color: "#738091" }}>
          3-number rotation. Leads are deterministically assigned
        </span>
      </div>
      <div className="variant-table-wrap">
        <HTMLTable interactive style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>Number</th>
              <th>Sent</th>
              <th>Delivered</th>
              <th>Replies</th>
              <th>Reply %</th>
              <th>Opt-Outs</th>
              <th>Health</th>
            </tr>
          </thead>
          <tbody>
            {data.numbers.map((n) => (
              <tr key={n.number}>
                <td>
                  <code style={{ color: "#9FA8DA" }}>{maskNumber(n.number)}</code>
                </td>
                <td>{n.sent.toLocaleString()}</td>
                <td>{n.delivered.toLocaleString()}</td>
                <td>{n.replied.toLocaleString()}</td>
                <td><strong>{pct(n.reply_rate)}</strong></td>
                <td style={{ color: n.opted_out > 5 ? "#e06060" : undefined }}>
                  {n.opted_out}
                </td>
                <td>
                  {n.opted_out > 10 ? (
                    <Tag intent="danger" minimal>At risk</Tag>
                  ) : n.replied > 0 ? (
                    <Tag intent="success" minimal>Active</Tag>
                  ) : (
                    <Tag minimal>Warming</Tag>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </HTMLTable>
      </div>
    </div>
  );
}
