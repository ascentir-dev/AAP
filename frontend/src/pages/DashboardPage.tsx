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
  Tooltip,
} from "@blueprintjs/core";
import { fetchAnalytics, syncSmartleadAnalytics } from "../api/client";
import type { AnalyticsData, HeatmapCell } from "../api/types";

function pct(n: number) {
  return (n * 100).toFixed(1) + "%";
}

function heatColor(replyRatePct: number): string {
  if (replyRatePct >= 4.0) return "#1D9E75";
  if (replyRatePct >= 3.0) return "#5DCAA5";
  if (replyRatePct >= 2.0) return "#9FE1CB";
  if (replyRatePct > 0)    return "#E1F5EE";
  return "#2f3640";
}

// Short label for long ICP names in the matrix
function shortICP(icp: string): string {
  return icp
    .replace("Agency", "Agency")
    .replace("Financial Advisory", "Fin. Advisory")
    .replace("Wealth Management", "Wealth Mgmt")
    .replace("Operations Consulting", "Ops Consulting")
    .replace("Professional Training", "Prof. Training")
    .replace("Strategy Consulting", "Strategy Cons.")
    .replace(" / ", "/");
}

// Map variant_id to short framework name for matrix column headers
const VARIANT_SHORT: Record<string, string> = {
  "Variant 1": "V1 PPP",
  "Variant 2": "V2 PPP Compact",
  "Variant 3": "V3 PPP+Proof",
  "Variant 4": "V4 AIDA",
  "Variant 5": "V5 3Cs",
  "Variant 6": "V6 QVC",
  "Variant 7": "V7 Demand Flip",
  "Variant 8": "V8 Inv. Demand",
  "Variant 9": "V9 PAS",
};

export function DashboardPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);

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

  async function handleSync() {
    setSyncing(true);
    setSyncResult(null);
    try {
      const r = await syncSmartleadAnalytics();
      const total = Object.values(r.totals).reduce((a, b) => a + b, 0);
      setSyncResult(
        r.ok
          ? `Synced ${r.campaigns_synced} campaigns — ${total} new engagement events imported.`
          : `Sync completed with errors: ${r.errors.join("; ")}`
      );
      await load();
    } catch (e: unknown) {
      setSyncResult(`Sync failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSyncing(false);
    }
  }

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
        action={<Button intent="primary" onClick={load}>Retry</Button>}
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

  // Framework×motion heatmap
  const frameworks = [...new Set(data.heatmap.map((c) => c.row_key))].sort();
  const heatGrid = (fw: string, motion: string) =>
    data.heatmap.find((c) => c.row_key === fw && c.col_key === motion);

  // ICP×Variant matrix — get top ICPs by total sent, all variants sorted
  const icpMap = new Map<string, Map<string, HeatmapCell>>();
  const icpSentTotal = new Map<string, number>();
  for (const cell of (data.icp_heatmap ?? [])) {
    if (!icpMap.has(cell.col_key)) icpMap.set(cell.col_key, new Map());
    icpMap.get(cell.col_key)!.set(cell.row_key, cell);
    icpSentTotal.set(cell.col_key, (icpSentTotal.get(cell.col_key) ?? 0) + cell.sent);
  }
  const topICPs = [...icpSentTotal.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([icp]) => icp);
  const variants = [...new Set((data.icp_heatmap ?? []).map((c) => c.row_key))].sort();

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <h1 className="page-title" style={{ margin: 0 }}>Campaign Dashboard</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {!data.events_synced && (
            <span style={{ fontSize: 12, color: "#f0b429" }}>
              ⚠ Open/reply rates need a sync
            </span>
          )}
          <Button
            icon="refresh"
            intent={data.events_synced ? "none" : "warning"}
            loading={syncing}
            onClick={handleSync}
            minimal={data.events_synced}
          >
            Sync from SmartLead
          </Button>
        </div>
      </div>

      {syncResult && (
        <Callout
          intent={syncResult.startsWith("Sync failed") ? "danger" : "success"}
          icon={syncResult.startsWith("Sync failed") ? "error" : "tick"}
          style={{ marginBottom: 16 }}
        >
          {syncResult}
        </Callout>
      )}

      {!data.events_synced && !syncResult && (
        <Callout intent="warning" icon="info-sign" style={{ marginBottom: 16 }}>
          <strong>Open/reply rates are showing 0%</strong> — SmartLead webhooks require a
          public URL and can't reach localhost. Click <strong>Sync from SmartLead</strong> to
          pull engagement data directly from the API. Sent counts are always accurate.
        </Callout>
      )}

      {/* ── Significance banner ── */}
      {sig.ready && sig.significant_winners.length > 0 && (
        <Callout className="sig-banner" intent="success" icon="trophy"
          title={`Winner found: ${sig.leader_variant_id}`}>
          {sig.leader_variant_id} ({sig.leader_framework}) is statistically beating{" "}
          {sig.significant_winners.join(", ")} at p&lt;0.05 on {data.primary_metric}.
        </Callout>
      )}
      {!sig.ready && (
        <Callout className="sig-banner" intent="primary" icon="time">
          <strong>Gathering data…</strong> {sig.min_sent.toLocaleString()} /{" "}
          {sig.min_required.toLocaleString()} minimum leads per variant.
          <ProgressBar
            value={sig.min_sent / Math.max(sig.min_required, 1)}
            intent="primary" animate={false} stripes={false}
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
          <div className="kpi-value">${data.cost.total_cost_usd.toFixed(2)}</div>
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
              <th>Click %</th>
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
                  <td><strong>{v.variant_id}</strong></td>
                  <td style={{ fontSize: 12 }}>{v.framework}</td>
                  <td>{v.sent.toLocaleString()}</td>
                  <td style={{ color: v.open_rate > 0.25 ? "#4c90f0" : undefined }}>
                    {pct(v.open_rate)}
                  </td>
                  <td><strong style={{ color: v.reply_rate > 0.03 ? "#1D9E75" : undefined }}>
                    {pct(v.reply_rate)}
                  </strong></td>
                  <td>{pct(v.click_rate)}</td>
                  <td>{pct(v.book_rate)}</td>
                  <td style={{ color: v.bounce_rate > 0.05 ? "#e63946" : undefined }}>
                    {pct(v.bounce_rate)}
                  </td>
                  <td>
                    {isLeader && sig.ready ? (
                      <Tag intent="success" minimal icon="trophy">Winner</Tag>
                    ) : isLeader ? (
                      <Tag intent="primary" minimal>Leader</Tag>
                    ) : sig.significant_winners.includes(v.variant_id) ? (
                      <Tag intent="warning" minimal>Losing</Tag>
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

      {/* ── ICP × Variant Performance Matrix ── */}
      {topICPs.length > 0 && (
        <>
          <div className="section-header">
            <h2 className="section-title">ICP × Variant Performance</h2>
            <span style={{ fontSize: 12, color: "#738091" }}>
              sent · open% · reply% — top 8 ICPs by volume
            </span>
          </div>
          <Callout intent="none" icon="info-sign"
            style={{ marginBottom: 12, fontSize: 12, background: "#1c2127", border: "1px solid #2f363e" }}>
            Cells show: <strong style={{ color: "#abb3bf" }}>sent</strong> ·{" "}
            <strong style={{ color: "#4c90f0" }}>open%</strong> ·{" "}
            <strong style={{ color: "#1D9E75" }}>reply%</strong>. Grey = &lt;5 sent (insufficient data).
            Use this to reallocate volume toward the ICP+variant combos with the highest reply rates.
          </Callout>
          <div style={{ overflowX: "auto", marginBottom: 32 }}>
            <table style={{
              borderCollapse: "collapse", width: "100%",
              fontSize: 12, background: "#161b22",
            }}>
              <thead>
                <tr>
                  <th style={{
                    textAlign: "left", padding: "8px 12px",
                    background: "#1c2127", color: "#738091",
                    border: "1px solid #2f363e", minWidth: 160,
                  }}>
                    ICP (Vertical)
                  </th>
                  {variants.map((v) => (
                    <th key={v} style={{
                      padding: "6px 8px", textAlign: "center",
                      background: "#1c2127", color: "#abb3bf",
                      border: "1px solid #2f363e", minWidth: 90,
                      fontWeight: 600,
                    }}>
                      <div>{VARIANT_SHORT[v] ?? v}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {topICPs.map((icp, ri) => (
                  <tr key={icp} style={{ background: ri % 2 === 0 ? "#161b22" : "#1a1f27" }}>
                    <td style={{
                      padding: "8px 12px", fontWeight: 600,
                      color: "#f6f7f9", border: "1px solid #2f363e",
                      fontSize: 12,
                    }}>
                      <Tooltip content={icp} placement="right">
                        <span>{shortICP(icp)}</span>
                      </Tooltip>
                    </td>
                    {variants.map((v) => {
                      const cell = icpMap.get(icp)?.get(v);
                      const openPct  = cell && cell.sent >= 5 ? (cell as any).opened / cell.sent * 100 : null;
                      const replyPct = cell && cell.sent >= 5 ? cell.reply_rate * 100 : null;
                      const bg = replyPct != null ? heatColor(replyPct) : "#2f3640";
                      const darkCell = replyPct == null || replyPct < 2;
                      return (
                        <td key={v} style={{
                          padding: "6px 8px", textAlign: "center",
                          border: "1px solid #2f363e",
                          background: bg,
                        }}>
                          {cell && cell.sent >= 5 ? (
                            <div style={{ lineHeight: 1.6 }}>
                              <div style={{ color: darkCell ? "#738091" : "#1a3a2e", fontWeight: 600 }}>
                                {cell.sent}
                              </div>
                              <div style={{ color: darkCell ? "#4c90f0" : "#1a4a8a", fontSize: 11 }}>
                                {openPct != null ? openPct.toFixed(0) + "% open" : "—"}
                              </div>
                              <div style={{
                                color: darkCell ? "#1D9E75" : "#0d4a30",
                                fontWeight: 700, fontSize: 11,
                              }}>
                                {replyPct != null ? replyPct.toFixed(1) + "% reply" : "—"}
                              </div>
                            </div>
                          ) : (
                            <span style={{ color: "#5f6b7c" }}>
                              {cell ? cell.sent : "—"}
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

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
                          style={{ background: color, color: rate >= 2.0 ? "#1a3a2e" : "#738091" }}
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
                <td><strong>{f.framework}</strong></td>
                <td>
                  {f.variant_ids.map((v) => (
                    <Tag key={v} minimal style={{ marginRight: 4 }}>{v}</Tag>
                  ))}
                </td>
                <td>{f.sent.toLocaleString()}</td>
                <td>{pct(f.open_rate)}</td>
                <td><strong>{pct(f.reply_rate)}</strong></td>
                <td>{pct(f.book_rate)}</td>
              </tr>
            ))}
          </tbody>
        </HTMLTable>
      </div>
    </div>
  );
}
