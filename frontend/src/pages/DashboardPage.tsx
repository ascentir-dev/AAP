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
import { fetchAnalytics, syncSmartleadAnalytics, fetchSubjectLines } from "../api/client";
import type { AnalyticsData, HeatmapCell, SubjectLineStat } from "../api/types";

function pct(n: number) {
  return (n * 100).toFixed(1) + "%";
}


type IcpMetric = "reply_rate" | "open_rate";

// ── "No data" cell style (0% or missing) ─────────────────────────────────────
const NO_EVENTS_CELL = { bg: "#1e2a3a", text: "#3d5a80" };

// ── Dynamic relative color scale ──────────────────────────────────────────────
// Four tiers mapped to percentile rank within the VISIBLE cells.
// Best 25% → green  |  50–75% → light-green  |  25–50% → amber  |  Bottom 25% → red
// Thresholds are always data-driven so the best cell is always green and the
// worst is always red, regardless of absolute rate values.
const DYNAMIC_TIERS = [
  { bg: "#0d3327", text: "#34d399", label: "best"  },
  { bg: "#134029", text: "#4ade80", label: "good"  },
  { bg: "#2a2a10", text: "#fbbf24", label: "avg"   },
  { bg: "#3b1010", text: "#f87171", label: "low"   },
] as const;

interface DynamicScale { p25: number; p50: number; p75: number; }

/** Compute quartile cutoffs from an array of rates (zeros excluded). */
function computeScale(rates: number[]): DynamicScale | null {
  const nz = rates.filter(r => r > 0).sort((a, b) => a - b);
  if (nz.length < 2) return null;
  const at = (f: number) => nz[Math.min(nz.length - 1, Math.floor(nz.length * f))];
  return { p25: at(0.25), p50: at(0.50), p75: at(0.75) };
}

/** Map a single rate to a background + text color using a pre-computed scale. */
function dynamicColor(rate: number, scale: DynamicScale | null): { bg: string; textColor: string } {
  if (rate <= 0 || !scale) return { bg: NO_EVENTS_CELL.bg, textColor: NO_EVENTS_CELL.text };
  // If all visible rates are identical, show them all as "good" (no ranking)
  if (scale.p75 <= scale.p25) return { bg: DYNAMIC_TIERS[1].bg, textColor: DYNAMIC_TIERS[1].text };
  if (rate >= scale.p75) return { bg: DYNAMIC_TIERS[0].bg, textColor: DYNAMIC_TIERS[0].text };
  if (rate >= scale.p50) return { bg: DYNAMIC_TIERS[1].bg, textColor: DYNAMIC_TIERS[1].text };
  if (rate >= scale.p25) return { bg: DYNAMIC_TIERS[2].bg, textColor: DYNAMIC_TIERS[2].text };
  return { bg: DYNAMIC_TIERS[3].bg, textColor: DYNAMIC_TIERS[3].text };
}

/** Render a legend row for a dynamic scale (shows actual cutoff values). */
function scaleLegendItems(scale: DynamicScale | null) {
  if (!scale) return null;
  return [
    { bg: DYNAMIC_TIERS[0].bg, text: DYNAMIC_TIERS[0].text, label: `≥ ${pct(scale.p75)}  best`  },
    { bg: DYNAMIC_TIERS[1].bg, text: DYNAMIC_TIERS[1].text, label: `≥ ${pct(scale.p50)}  good`  },
    { bg: DYNAMIC_TIERS[2].bg, text: DYNAMIC_TIERS[2].text, label: `≥ ${pct(scale.p25)}  avg`   },
    { bg: DYNAMIC_TIERS[3].bg, text: DYNAMIC_TIERS[3].text, label: `< ${pct(scale.p25)}  low`   },
  ];
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
  "Variant 2": "V2 Compact",
  "Variant 3": "V3 Proof",
  "Variant 4": "V4 AIDA",
  "Variant 5": "V5 3Cs",
  "Variant 6": "V6 QVC",
  "Variant 7": "V7 Flip",
  "Variant 8": "V8 Cost",
  "Variant 9": "V9 PAS",
};

export function DashboardPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [icpMetric, setIcpMetric] = useState<IcpMetric>("reply_rate");
  const [subjectLines, setSubjectLines] = useState<SubjectLineStat[]>([]);

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
    fetchSubjectLines(3).then((r) => setSubjectLines(r.subject_lines ?? [])).catch(() => {});
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
          <strong>ICP × Variant rates are showing 0%</strong> — the Variant Performance table
          above uses campaign-level totals (always correct), but the ICP matrix needs
          per-lead engagement data to show different rates per ICP.{" "}
          Click <strong>Sync from SmartLead</strong> to pull individual lead opens &amp; replies.
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
          <div className="kpi-label">Delivered</div>
          <div className="kpi-value">{data.total_sent.toLocaleString()}</div>
          <div className="kpi-sub">
            {data.total_in_queue != null && data.total_in_queue > data.total_sent
              ? `${data.total_in_queue.toLocaleString()} in SmartLead queue`
              : "emails sent by SmartLead"}
          </div>
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
              <th>Delivered</th>
              <th style={{ color: "#5f6b7c", fontSize: 11 }}>In Queue</th>
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
                  <td style={{ color: "#5f6b7c", fontSize: 12 }}>{(v.in_queue ?? 0).toLocaleString()}</td>
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
          <div className="section-header" style={{ alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
            <div>
              <h2 className="section-title" style={{ marginBottom: 2 }}>ICP × Variant Performance</h2>
              <span style={{ fontSize: 12, color: "#738091" }}>
                top 8 ICPs by volume · color = {icpMetric === "reply_rate" ? "reply rate" : "open rate"}
              </span>
            </div>
            {/* Metric toggle */}
            <div style={{ display: "flex", gap: 0, marginLeft: "auto", border: "1px solid #383e47", borderRadius: 6, overflow: "hidden" }}>
              {(["reply_rate", "open_rate"] as IcpMetric[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setIcpMetric(m)}
                  style={{
                    padding: "5px 14px", fontSize: 12, fontWeight: 600,
                    border: "none", cursor: "pointer",
                    background: icpMetric === m ? "#215db0" : "#1c2127",
                    color: icpMetric === m ? "#fff" : "#738091",
                    transition: "background 0.15s",
                  }}
                >
                  {m === "reply_rate" ? "Reply Rate" : "Open Rate"}
                </button>
              ))}
            </div>
          </div>

          {/* ── Dynamic legend — computed from actual visible cell rates ─── */}
          {(() => {
            const allRates = topICPs.flatMap(icp =>
              variants.map(v => {
                const c = icpMap.get(icp)?.get(v);
                return c ? (icpMetric === "reply_rate" ? c.reply_rate : c.open_rate) : 0;
              })
            );
            const icpScale = computeScale(allRates);
            const legendItems = scaleLegendItems(icpScale);
            return (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 12, fontSize: 11, color: "#738091", flexWrap: "wrap" }}>
                  {legendItems
                    ? legendItems.map((t) => (
                        <span key={t.label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                          <span style={{ display: "inline-block", width: 11, height: 11, borderRadius: 2, background: t.bg, border: `1px solid ${t.text}33` }} />
                          {t.label}
                        </span>
                      ))
                    : <span style={{ color: "#f0b429" }}>⚠ No rate data yet — click Sync from SmartLead</span>
                  }
                  <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ display: "inline-block", width: 11, height: 11, borderRadius: 2, background: NO_EVENTS_CELL.bg, border: "1px solid #2f363e" }} />
                    0%
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ display: "inline-block", width: 11, height: 11, borderRadius: 2, background: "#161b22", border: "1px solid #2f363e" }} />
                    no leads
                  </span>
                  <span style={{ marginLeft: "auto", fontSize: 10, color: "#4a5568", fontStyle: "italic" }}>
                    colors ranked relative to visible cells
                  </span>
                </div>

                {/* ICP rates banner — shown whenever per-lead events aren't loaded */}
                {!data.events_synced && (
                  <div style={{
                    display: "flex", alignItems: "center", gap: 10,
                    background: "#171e2e", border: "1px solid #2d4068",
                    borderRadius: 6, padding: "8px 14px", marginBottom: 10,
                    fontSize: 12, color: "#7eb3f0",
                  }}>
                    <span style={{ fontSize: 15 }}>📊</span>
                    <span>
                      <strong style={{ color: "#93c5fd" }}>ICP reply rates not yet available.</strong>{" "}
                      The matrix shows accurate <em>sent counts</em> per ICP, but per-ICP open/reply rates
                      require per-lead sync data.{" "}
                      Click <strong style={{ color: "#fff" }}>Sync from SmartLead</strong> above to pull
                      individual lead engagement — each ICP will then show its own measured rate.
                    </span>
                  </div>
                )}
              </>
            );
          })()}

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
                      border: "1px solid #2f363e", minWidth: 80,
                      fontWeight: 600, fontSize: 11,
                    }}>
                      {VARIANT_SHORT[v] ?? v}
                    </th>
                  ))}
                  <th style={{
                    padding: "6px 8px", textAlign: "center",
                    background: "#1c2127", color: "#738091",
                    border: "1px solid #2f363e", minWidth: 60, fontSize: 11,
                  }}>Total</th>
                </tr>
              </thead>
              <tbody>
                {(() => {
                  // Compute scale once per render from ALL visible cells for this metric
                  const allRates = topICPs.flatMap(icp =>
                    variants.map(v => {
                      const c = icpMap.get(icp)?.get(v);
                      return c ? (icpMetric === "reply_rate" ? c.reply_rate : c.open_rate) : 0;
                    })
                  );
                  const icpScale = computeScale(allRates);

                  return topICPs.map((icp, ri) => {
                    const rowTotal = variants.reduce((sum, v) => sum + (icpMap.get(icp)?.get(v)?.sent ?? 0), 0);
                    return (
                      <tr key={icp} style={{ background: ri % 2 === 0 ? "#161b22" : "#1a1f27" }}>
                        <td style={{
                          padding: "8px 12px", fontWeight: 600,
                          color: "#f6f7f9", border: "1px solid #2f363e", fontSize: 12,
                        }}>
                          <Tooltip content={icp} placement="right">
                            <span>{shortICP(icp)}</span>
                          </Tooltip>
                        </td>
                        {variants.map((v) => {
                          const cell = icpMap.get(icp)?.get(v);
                          const n    = cell?.sent ?? 0;
                          const rate = cell
                            ? (icpMetric === "reply_rate" ? cell.reply_rate : cell.open_rate)
                            : 0;
                          const { bg, textColor } = n > 0
                            ? dynamicColor(rate, icpScale)
                            : { bg: "#161b22", textColor: "#2f363e" };
                          return (
                            <td key={v} style={{
                              padding: "6px 8px", textAlign: "center",
                              border: "1px solid #2f363e", background: bg,
                              transition: "background 0.2s",
                            }}>
                              {n > 0 ? (
                                <div style={{ lineHeight: 1.5 }}>
                                  <div style={{ fontWeight: 700, color: textColor, fontSize: 13 }}>
                                    {(rate * 100).toFixed(1)}%
                                  </div>
                                  <div style={{ fontSize: 10, color: "#6b7280", marginTop: 1 }}>
                                    {icpMetric === "reply_rate"
                                      ? `${cell?.replied ?? 0} repl`
                                      : `${cell?.opened ?? 0} open`}
                                  </div>
                                </div>
                              ) : (
                                <span style={{ color: "#2f363e" }}>—</span>
                              )}
                            </td>
                          );
                        })}
                        <td style={{
                          padding: "6px 8px", textAlign: "center",
                          border: "1px solid #2f363e",
                          fontWeight: 700, color: "#738091", fontSize: 12,
                        }}>
                          {rowTotal}
                        </td>
                      </tr>
                    );
                  });
                })()}
                {/* Column totals row */}
                <tr style={{ background: "#1c2127", borderTop: "2px solid #383e47" }}>
                  <td style={{ padding: "8px 12px", fontWeight: 700, color: "#738091", border: "1px solid #2f363e", fontSize: 11 }}>
                    Variant Total
                  </td>
                  {variants.map((v) => {
                    const colTotal = topICPs.reduce((sum, icp) => sum + (icpMap.get(icp)?.get(v)?.sent ?? 0), 0);
                    return (
                      <td key={v} style={{
                        padding: "6px 8px", textAlign: "center",
                        border: "1px solid #2f363e",
                        fontWeight: 700, color: "#5f6b7c", fontSize: 11,
                      }}>
                        {colTotal}
                      </td>
                    );
                  })}
                  <td style={{ border: "1px solid #2f363e" }} />
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ══ Subject Line Open-Rate Matrix ════════════════════════════════════ */}
      {subjectLines.length > 0 && (() => {
        // open_rate from the API is already a percentage (0–100), not a fraction
        const slScale = computeScale(subjectLines.map(s => s.open_rate));
        const slLegend = scaleLegendItems(slScale);
        return (
          <>
            <div className="section-header" style={{ alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
              <div>
                <h2 className="section-title" style={{ marginBottom: 2 }}>Subject Line Open Rates</h2>
                <span style={{ fontSize: 12, color: "#738091" }}>
                  ranked by open rate · color = relative performance · {subjectLines.length} subject lines
                </span>
              </div>
            </div>

            {/* Dynamic legend */}
            <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 12, fontSize: 11, color: "#738091", flexWrap: "wrap" }}>
              {slLegend
                ? slLegend.map((t) => (
                    <span key={t.label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <span style={{ display: "inline-block", width: 11, height: 11, borderRadius: 2, background: t.bg, border: `1px solid ${t.text}33` }} />
                      {t.label}
                    </span>
                  ))
                : null}
              <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ display: "inline-block", width: 11, height: 11, borderRadius: 2, background: NO_EVENTS_CELL.bg, border: "1px solid #2f363e" }} />
                0%
              </span>
              <span style={{ marginLeft: "auto", fontSize: 10, color: "#4a5568", fontStyle: "italic" }}>
                colors ranked relative to visible rows
              </span>
            </div>

            <div style={{ overflowX: "auto", marginBottom: 32 }}>
              <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12, background: "#161b22" }}>
                <thead>
                  <tr>
                    <th style={{ padding: "6px 10px", textAlign: "center", background: "#1c2127", color: "#738091", border: "1px solid #2f363e", width: 32, fontSize: 11 }}>#</th>
                    <th style={{ textAlign: "left", padding: "8px 12px", background: "#1c2127", color: "#738091", border: "1px solid #2f363e" }}>
                      Subject Line
                    </th>
                    <th style={{ padding: "6px 10px", textAlign: "center", background: "#1c2127", color: "#738091", border: "1px solid #2f363e", minWidth: 90, fontSize: 11 }}>
                      Variant
                    </th>
                    <th style={{ padding: "6px 10px", textAlign: "center", background: "#1c2127", color: "#738091", border: "1px solid #2f363e", minWidth: 70, fontSize: 11 }}>
                      Delivered
                    </th>
                    <th style={{ padding: "6px 10px", textAlign: "center", background: "#1c2127", color: "#4c90f0", border: "1px solid #2f363e", minWidth: 90, fontSize: 11, fontWeight: 700 }}>
                      Open Rate
                    </th>
                    <th style={{ padding: "6px 10px", textAlign: "center", background: "#1c2127", color: "#4c90f0", border: "1px solid #2f363e", minWidth: 70, fontSize: 11 }}>
                      Opens
                    </th>
                    <th style={{ padding: "6px 10px", textAlign: "center", background: "#1c2127", color: "#738091", border: "1px solid #2f363e", minWidth: 90, fontSize: 11 }}>
                      Reply Rate
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {subjectLines.map((sl, idx) => {
                    const { bg, textColor } = sl.open_rate > 0
                      ? dynamicColor(sl.open_rate, slScale)
                      : { bg: NO_EVENTS_CELL.bg, textColor: NO_EVENTS_CELL.text };
                    const rowBg = idx % 2 === 0 ? "#161b22" : "#1a1f27";
                    // Highlight [bracket] placeholders in template rows
                    const subjectDisplay = sl.is_grouped
                      ? sl.subject_line.replace(/\[([^\]]+)\]/g, '[$1]')
                      : sl.subject_line;
                    return (
                      <tr key={`${sl.subject_line}-${sl.variant_id}`} style={{ background: rowBg }}>
                        <td style={{ padding: "6px 10px", textAlign: "center", color: "#4a5568", border: "1px solid #2f363e", fontSize: 11 }}>
                          {idx + 1}
                        </td>
                        <td style={{ padding: "8px 12px", border: "1px solid #2f363e", maxWidth: 380 }}>
                          {sl.is_grouped ? (
                            <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {sl.subject_line.split(/(\[[^\]]+\])/).map((part, i) =>
                                /^\[[^\]]+\]$/.test(part)
                                  ? <span key={i} style={{ color: "#4c90f0", fontWeight: 600 }}>{part}</span>
                                  : <span key={i} style={{ color: "#f6f7f9" }}>{part}</span>
                              )}
                            </span>
                          ) : (
                            <Tooltip content={sl.subject_line} placement="right">
                              <span style={{ display: "block", color: "#f6f7f9", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {subjectDisplay}
                              </span>
                            </Tooltip>
                          )}
                        </td>
                        <td style={{ padding: "6px 10px", textAlign: "center", border: "1px solid #2f363e", color: "#abb3bf", fontSize: 11 }}>
                          {VARIANT_SHORT[sl.variant_id] ?? sl.variant_id}
                        </td>
                        <td style={{ padding: "6px 10px", textAlign: "center", border: "1px solid #2f363e", color: "#738091", fontSize: 12 }}>
                          {sl.sent}
                        </td>
                        {/* Open Rate — color-coded cell */}
                        <td style={{ padding: "6px 10px", textAlign: "center", border: "1px solid #2f363e", background: bg, transition: "background 0.2s" }}>
                          <span style={{ fontWeight: 700, color: textColor, fontSize: 13 }}>
                            {sl.open_rate.toFixed(1)}%
                          </span>
                        </td>
                        <td style={{ padding: "6px 10px", textAlign: "center", border: "1px solid #2f363e", color: "#4c90f0", fontSize: 12, fontWeight: 600 }}>
                          {sl.opened}
                        </td>
                        <td style={{ padding: "6px 10px", textAlign: "center", border: "1px solid #2f363e", color: sl.reply_rate > 2 ? "#34d399" : "#738091", fontSize: 12 }}>
                          {sl.reply_rate.toFixed(1)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        );
      })()}

    </div>
  );
}
