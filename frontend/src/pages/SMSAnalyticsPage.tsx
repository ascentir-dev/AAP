import { useEffect, useState, useCallback } from "react";
import {
  Card,
  HTMLTable,
  Tag,
  Spinner,
  NonIdealState,
  Button,
  ProgressBar,
  Tooltip,
} from "@blueprintjs/core";
import { fetchSmsIcpMatrix } from "../api/client";
import type { SmsIcpMatrixCell } from "../api/types";

// ─── API types (local to this page) ──────────────────────────────────────────

interface SMSVariantStat {
  variant_id:    string;
  name:          string;
  framework:     string;
  sent:          number;
  delivered:     number;
  replied:       number;
  opted_out:     number;
  reply_rate:    number;
  opt_out_rate:  number;
}

interface SMSNumberStat {
  number:      string;
  sent:        number;
  delivered:   number;
  replied:     number;
  opted_out:   number;
  reply_rate:  number;
}

interface SMSKPIs {
  total_sent:             number;
  total_generated:        number;  // bodies written (includes ready-but-unsent)
  total_delivered:        number;
  total_replied:          number;
  total_opted_out:        number;
  total_booked:           number;
  blended_reply_rate:     number;
  blended_opt_out_rate:   number;
  // cost fields
  total_ai_cost_usd:      number;
  total_twilio_cost_usd:  number;
  total_cost_usd:         number;
}

interface SMSAnalyticsData {
  kpis:      SMSKPIs;
  variants:  SMSVariantStat[];
  numbers:   SMSNumberStat[];
  test_id:   string;
}

// ─── Dynamic color scale helpers ──────────────────────────────────────────────

const NO_EVENTS_CELL  = { bg: "#1e2a3a", text: "#3d5a80" };

const DYNAMIC_TIERS = [
  { bg: "#0d3327", text: "#34d399" },
  { bg: "#134029", text: "#4ade80" },
  { bg: "#2a2a10", text: "#fbbf24" },
  { bg: "#3b1010", text: "#f87171" },
] as const;

interface DynamicScale { p25: number; p50: number; p75: number; }

function computeScale(rates: number[]): DynamicScale | null {
  const nz = rates.filter(r => r > 0).sort((a, b) => a - b);
  if (nz.length < 2) return null;
  const at = (f: number) => nz[Math.min(nz.length - 1, Math.floor(nz.length * f))];
  return { p25: at(0.25), p50: at(0.50), p75: at(0.75) };
}

function dynamicColor(rate: number, scale: DynamicScale | null): { bg: string; textColor: string } {
  if (rate <= 0 || !scale) return { bg: NO_EVENTS_CELL.bg, textColor: NO_EVENTS_CELL.text };
  if (scale.p75 <= scale.p25) return { bg: DYNAMIC_TIERS[1].bg, textColor: DYNAMIC_TIERS[1].text };
  if (rate >= scale.p75) return { bg: DYNAMIC_TIERS[0].bg, textColor: DYNAMIC_TIERS[0].text };
  if (rate >= scale.p50) return { bg: DYNAMIC_TIERS[1].bg, textColor: DYNAMIC_TIERS[1].text };
  if (rate >= scale.p25) return { bg: DYNAMIC_TIERS[2].bg, textColor: DYNAMIC_TIERS[2].text };
  return { bg: DYNAMIC_TIERS[3].bg, textColor: DYNAMIC_TIERS[3].text };
}

function scaleLegendItems(scale: DynamicScale | null) {
  if (!scale) return null;
  const p = (n: number) => (n * 100).toFixed(1) + "%";
  return [
    { bg: DYNAMIC_TIERS[0].bg, text: DYNAMIC_TIERS[0].text, label: `≥ ${p(scale.p75)}  best` },
    { bg: DYNAMIC_TIERS[1].bg, text: DYNAMIC_TIERS[1].text, label: `≥ ${p(scale.p50)}  good` },
    { bg: DYNAMIC_TIERS[2].bg, text: DYNAMIC_TIERS[2].text, label: `≥ ${p(scale.p25)}  avg`  },
    { bg: DYNAMIC_TIERS[3].bg, text: DYNAMIC_TIERS[3].text, label: `< ${p(scale.p25)}  low`  },
  ];
}

// ─── Misc helpers ─────────────────────────────────────────────────────────────

function pct(n: number) { return (n * 100).toFixed(1) + "%"; }

function maskNumber(num: string) {
  return num.length >= 10 ? num.slice(0, -7) + "***-" + num.slice(-4) : num;
}

function shortICP(icp: string): string {
  return icp
    .replace("Financial Advisory", "Fin. Advisory")
    .replace("Wealth Management",  "Wealth Mgmt")
    .replace("Operations Consulting", "Ops Consulting")
    .replace("Professional Training", "Prof. Training")
    .replace("Strategy Consulting",   "Strategy Cons.")
    .replace(" / ", "/");
}

const SMS_VARIANT_SHORT: Record<string, string> = {
  "SMS-V1": "V1 Direct",
  "SMS-V2": "V2 Result",
  "SMS-V3": "V3 Show",
  "SMS-V4": "V4 Curiosity",
  "SMS-V5": "V5 Guarantee",
  "SMS-V6": "V6 Scarcity",
};

// ─── Component ────────────────────────────────────────────────────────────────

export function SMSAnalyticsPage() {
  const [analytics, setAnalytics] = useState<SMSAnalyticsData | null>(null);
  const [smsCells,  setSmsCells]  = useState<SmsIcpMatrixCell[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [smsRes, matrixRes] = await Promise.all([
        fetch("/api/sms/analytics").then(r => {
          if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
          return r.json() as Promise<SMSAnalyticsData>;
        }),
        fetchSmsIcpMatrix().catch(() => ({ cells: [] as SmsIcpMatrixCell[] })),
      ]);
      setAnalytics(smsRes);
      setSmsCells(matrixRes.cells ?? []);
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

  // ── Loading / error states ───────────────────────────────────────────────────

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

  if (!analytics || analytics.kpis.total_sent === 0) {
    return (
      <div style={{ padding: 32 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <h1 className="page-title" style={{ margin: 0, color: "#8b5cf6" }}>SMS Analytics</h1>
        </div>
        <NonIdealState
          className="empty-state"
          icon="mobile-phone"
          title="No SMS data yet"
          description="Add Twilio credentials to .env, then run the SMS pipeline to see analytics here."
        />
      </div>
    );
  }

  const kpis     = analytics.kpis;
  const variants = analytics.variants;

  // ICP matrix data
  const smsIcpMap  = new Map<string, Map<string, SmsIcpMatrixCell>>();
  const smsSentTot = new Map<string, number>();
  for (const c of smsCells) {
    if (!smsIcpMap.has(c.col_key)) smsIcpMap.set(c.col_key, new Map());
    smsIcpMap.get(c.col_key)!.set(c.row_key, c);
    smsSentTot.set(c.col_key, (smsSentTot.get(c.col_key) ?? 0) + c.sent);
  }
  const smsTopICPs  = [...smsSentTot.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([k]) => k);
  const smsVariants = [...new Set(smsCells.map(c => c.row_key))].sort();
  const allRates    = smsTopICPs.flatMap(icp => smsVariants.map(v => smsIcpMap.get(icp)?.get(v)?.reply_rate ?? 0));
  const smsScale    = computeScale(allRates);
  const legendItems = scaleLegendItems(smsScale);

  // Leader variant (highest reply rate)
  const leaderVariant = [...variants].sort((a, b) => b.reply_rate - a.reply_rate)[0];

  return (
    <div>
      {/* ── Page header ─────────────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <h1 className="page-title" style={{ margin: 0, color: "#8b5cf6" }}>SMS Analytics</h1>
        <Button icon="refresh" minimal onClick={load} style={{ color: "#8b5cf6" }}>
          Refresh
        </Button>
      </div>
      <p style={{ color: "#738091", fontSize: 12, marginBottom: 24, marginTop: 0 }}>
        Test: {analytics.test_id}
      </p>

      {/* ── KPI cards ───────────────────────────────────────────────────────── */}
      <div className="kpi-grid">
        <Card className="kpi-card">
          <div className="kpi-label">Total Sent</div>
          <div className="kpi-value">{kpis.total_sent.toLocaleString()}</div>
          <div className="kpi-sub">SMS messages delivered</div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Blended Reply Rate</div>
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
          <div className="kpi-value">{variants.length}</div>
          <div className="kpi-sub">
            {leaderVariant ? `Leader: ${leaderVariant.variant_id}` : "Gathering data"}
          </div>
        </Card>
      </div>

      {/* ── Cost breakdown row ───────────────────────────────────────────── */}
      <div className="kpi-grid" style={{ marginTop: 12 }}>
        <Card className="kpi-card">
          <div className="kpi-label">AI Personalization Cost</div>
          <div className="kpi-value" style={{ fontSize: 22 }}>
            ${(kpis.total_ai_cost_usd ?? 0).toFixed(4)}
          </div>
          <div className="kpi-sub">Claude API — per-lead generation</div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Twilio Send Cost</div>
          <div className="kpi-value" style={{ fontSize: 22 }}>
            ${(kpis.total_twilio_cost_usd ?? 0).toFixed(4)}
          </div>
          <div className="kpi-sub">
            {kpis.total_twilio_cost_usd === 0
              ? "Run Reconcile Costs to populate"
              : `$${((kpis.total_twilio_cost_usd ?? 0) / Math.max(kpis.total_sent, 1)).toFixed(5)}/msg avg`}
          </div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Total Cost</div>
          <div className="kpi-value" style={{ fontSize: 22 }}>
            ${(kpis.total_cost_usd ?? 0).toFixed(4)}
          </div>
          <div className="kpi-sub">
            {kpis.total_sent > 0
              ? `$${((kpis.total_cost_usd ?? 0) / kpis.total_sent).toFixed(5)} per send`
              : "AI + Twilio combined"}
          </div>
        </Card>
        <Card className="kpi-card">
          <div className="kpi-label">Generated vs Sent</div>
          <div className="kpi-value" style={{ fontSize: 22 }}>
            {(kpis.total_generated ?? kpis.total_sent).toLocaleString()}
          </div>
          <div className="kpi-sub">
            {kpis.total_sent.toLocaleString()} sent via Twilio
            {(kpis.total_generated ?? 0) > kpis.total_sent
              ? ` · ${((kpis.total_generated ?? 0) - kpis.total_sent).toLocaleString()} queued`
              : ""}
          </div>
        </Card>
      </div>

      {/* ── SMS Variant A/B Performance table ───────────────────────────────── */}
      <div className="section-header" style={{ marginTop: 32 }}>
        <h2 className="section-title">SMS Variant Performance</h2>
        <Tag minimal>Primary metric: reply rate</Tag>
      </div>
      <div className="variant-table-wrap" style={{ marginBottom: 8 }}>
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
            {variants.map((v) => {
              const isLeader = v.variant_id === leaderVariant?.variant_id;
              const replyBg =
                v.reply_rate >= 0.08 ? "#1D9E75" :
                v.reply_rate >= 0.05 ? "#5DCAA5" :
                v.reply_rate >= 0.02 ? "#9FE1CB" :
                v.reply_rate > 0     ? "#E1F5EE" : "transparent";
              return (
                <tr key={v.variant_id}>
                  <td><strong>{v.variant_id}</strong></td>
                  <td>{v.name}</td>
                  <td style={{ fontSize: 12 }}>{v.framework}</td>
                  <td>{v.sent.toLocaleString()}</td>
                  <td>{v.delivered.toLocaleString()}</td>
                  <td>
                    <span style={{
                      background: replyBg,
                      color: v.reply_rate >= 0.02 ? "#1a3a2e" : undefined,
                      padding: "2px 8px", borderRadius: 4, fontWeight: 600,
                    }}>
                      {pct(v.reply_rate)}
                    </span>
                  </td>
                  <td style={{ color: v.opt_out_rate > 0.03 ? "#e06060" : undefined }}>
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
        {variants.length > 0 && (
          <div style={{ padding: "8px 12px", color: "#738091", fontSize: 12 }}>
            500 sends per variant required for significance.
            {(() => {
              const minSent   = Math.min(...variants.map(v => v.sent));
              const progress  = Math.min(minSent / 500, 1);
              return (
                <ProgressBar
                  value={progress} intent="primary"
                  animate={false} stripes={false}
                  style={{ marginTop: 6 }}
                />
              );
            })()}
          </div>
        )}
      </div>

      {/* ── ICP × Variant Reply-Rate Matrix ─────────────────────────────────── */}
      {smsCells.length > 0 && (
        <>
          <div className="section-header" style={{ alignItems: "flex-start", flexWrap: "wrap", gap: 8, marginTop: 32 }}>
            <div>
              <h2 className="section-title" style={{ marginBottom: 2 }}>ICP × Variant Reply Rates</h2>
              <span style={{ fontSize: 12, color: "#738091" }}>
                top 8 ICPs by volume · reply rate only · colors ranked relative to visible cells
              </span>
            </div>
          </div>

          {/* Legend */}
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 12, fontSize: 11, color: "#738091", flexWrap: "wrap" }}>
            {legendItems
              ? legendItems.map(t => (
                  <span key={t.label} style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ display: "inline-block", width: 11, height: 11, borderRadius: 2, background: t.bg, border: `1px solid ${t.text}33` }} />
                    {t.label}
                  </span>
                ))
              : <span>No reply data yet</span>
            }
            <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ display: "inline-block", width: 11, height: 11, borderRadius: 2, background: NO_EVENTS_CELL.bg, border: "1px solid #2f363e" }} />
              0%
            </span>
            <span style={{ marginLeft: "auto", fontSize: 10, color: "#4a5568", fontStyle: "italic" }}>
              colors ranked relative to visible cells
            </span>
          </div>

          {/* Matrix table */}
          <div style={{ overflowX: "auto", marginBottom: 32 }}>
            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12, background: "#161b22" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "8px 12px", background: "#1c2127", color: "#738091", border: "1px solid #2f363e", minWidth: 160 }}>
                    ICP (Vertical)
                  </th>
                  {smsVariants.map(v => (
                    <th key={v} style={{ padding: "6px 8px", textAlign: "center", background: "#1c2127", color: "#8b5cf6", border: "1px solid #2f363e", minWidth: 80, fontWeight: 600, fontSize: 11 }}>
                      {SMS_VARIANT_SHORT[v] ?? v}
                    </th>
                  ))}
                  <th style={{ padding: "6px 8px", textAlign: "center", background: "#1c2127", color: "#738091", border: "1px solid #2f363e", minWidth: 60, fontSize: 11 }}>Total</th>
                </tr>
              </thead>
              <tbody>
                {smsTopICPs.map((icp, ri) => {
                  const rowTotal = smsVariants.reduce((s, v) => s + (smsIcpMap.get(icp)?.get(v)?.sent ?? 0), 0);
                  return (
                    <tr key={icp} style={{ background: ri % 2 === 0 ? "#161b22" : "#1a1f27" }}>
                      <td style={{ padding: "8px 12px", fontWeight: 600, color: "#f6f7f9", border: "1px solid #2f363e", fontSize: 12 }}>
                        <Tooltip content={icp} placement="right">
                          <span>{shortICP(icp)}</span>
                        </Tooltip>
                      </td>
                      {smsVariants.map(v => {
                        const cell = smsIcpMap.get(icp)?.get(v);
                        const n    = cell?.sent ?? 0;
                        const rate = cell?.reply_rate ?? 0;
                        const { bg, textColor } = n > 0
                          ? dynamicColor(rate, smsScale)
                          : { bg: "#161b22", textColor: "#2f363e" };
                        return (
                          <td key={v} style={{ padding: "6px 8px", textAlign: "center", border: "1px solid #2f363e", background: bg, transition: "background 0.2s" }}>
                            {n > 0 ? (
                              <div style={{ lineHeight: 1.5 }}>
                                <div style={{ fontWeight: 700, color: textColor, fontSize: 13 }}>{(rate * 100).toFixed(1)}%</div>
                                <div style={{ fontSize: 10, color: "#6b7280", marginTop: 1 }}>{n} sent</div>
                              </div>
                            ) : (
                              <span style={{ color: "#2f363e" }}>—</span>
                            )}
                          </td>
                        );
                      })}
                      <td style={{ padding: "6px 8px", textAlign: "center", border: "1px solid #2f363e", fontWeight: 700, color: "#738091", fontSize: 12 }}>
                        {rowTotal}
                      </td>
                    </tr>
                  );
                })}
                <tr style={{ background: "#1c2127", borderTop: "2px solid #383e47" }}>
                  <td style={{ padding: "8px 12px", fontWeight: 700, color: "#738091", border: "1px solid #2f363e", fontSize: 11 }}>Variant Total</td>
                  {smsVariants.map(v => {
                    const colTotal = smsTopICPs.reduce((s, icp) => s + (smsIcpMap.get(icp)?.get(v)?.sent ?? 0), 0);
                    return (
                      <td key={v} style={{ padding: "6px 8px", textAlign: "center", border: "1px solid #2f363e", fontWeight: 700, color: "#5f6b7c", fontSize: 11 }}>
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

      {/* ── Phone Number Performance ─────────────────────────────────────────── */}
      {analytics.numbers.length > 0 && (
        <>
          <div className="section-header">
            <h2 className="section-title">Phone Number Performance</h2>
            <span style={{ fontSize: 12, color: "#738091" }}>
              3-number rotation · leads deterministically assigned
            </span>
          </div>
          <div className="variant-table-wrap" style={{ marginBottom: 32 }}>
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
                {analytics.numbers.map(n => (
                  <tr key={n.number}>
                    <td><code style={{ color: "#9FA8DA" }}>{maskNumber(n.number)}</code></td>
                    <td>{n.sent.toLocaleString()}</td>
                    <td>{n.delivered.toLocaleString()}</td>
                    <td>{n.replied.toLocaleString()}</td>
                    <td><strong>{pct(n.reply_rate)}</strong></td>
                    <td style={{ color: n.opted_out > 5 ? "#e06060" : undefined }}>{n.opted_out}</td>
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
        </>
      )}
    </div>
  );
}
