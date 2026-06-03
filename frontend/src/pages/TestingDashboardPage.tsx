/**
 * Testing Framework Dashboard
 * Based on Morgan's Loom Alchemic Equation:
 *   Offer + (Copy + Leads) + (Script × Delivery) + (Reply + Warm FUP) = Overall ABR
 *
 * Three sequential KPIs:
 *   LVR  — Loom View Rate         target ≥ 15%   (sample: 300 sent)
 *   PRR  — Positive Reply Rate    target ≥ 20% view-to-reply  (sample: 45 views)
 *   ABR  — Appointment Book Rate  target ≥ 50% reply-to-book  (sample: 9 replies)
 */
import { useEffect, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface SampleGate {
  required: number;
  have: number;
  pct: number;
}

interface KPITargets {
  lvr: number;
  prr_overall: number;
  prr_view: number;
  abr_overall: number;
  abr_reply: number;
}

interface VariantRow {
  variant_id: string;
  name: string;
  hook_style: string;
  description: string;
  sent: number;
  views: number;
  replies: number;
  bookings: number;
  lvr: number;
  prr_overall: number;
  prr_view: number;
  abr_overall: number;
  abr_reply: number;
  lvr_status: "pass" | "fail" | "pending";
  prr_status: "pass" | "fail" | "pending";
  abr_status: "pass" | "fail" | "pending";
  lvr_sample_pct: number;
  prr_sample_pct: number;
  abr_sample_pct: number;
  leading: boolean;
}

interface TestingData {
  total_sent: number;
  total_views: number;
  total_replies: number;
  total_booked: number;
  lvr: number;
  prr_overall: number;
  prr_view: number;
  abr_overall: number;
  abr_reply: number;
  kpi: KPITargets;
  sample: { lvr: SampleGate; prr: SampleGate; abr: SampleGate };
  lvr_status: "pass" | "fail" | "pending";
  prr_status: "pass" | "fail" | "pending";
  abr_status: "pass" | "fail" | "pending";
  phase: "LVR" | "PRR" | "ABR" | "SCALE";
  phase_label: string;
  variants: VariantRow[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const pct = (n: number) => `${(n * 100).toFixed(1)}%`;

const statusColor = (s: "pass" | "fail" | "pending") =>
  s === "pass" ? "#22c55e" : s === "fail" ? "#ef4444" : "#94a3b8";

const statusBg = (s: "pass" | "fail" | "pending") =>
  s === "pass" ? "rgba(34,197,94,0.12)" : s === "fail" ? "rgba(239,68,68,0.12)" : "rgba(148,163,184,0.08)";

const statusLabel = (s: "pass" | "fail" | "pending") =>
  s === "pass" ? "IN KPI ✓" : s === "fail" ? "BELOW KPI" : "PENDING DATA";

// ── Sub-components ─────────────────────────────────────────────────────────────

function PhaseBar({ phase }: { phase: string }) {
  const phases = ["LVR", "PRR", "ABR", "SCALE"];
  const idx = phases.indexOf(phase);
  return (
    <div style={{ display: "flex", gap: 0, marginBottom: 28 }}>
      {phases.map((p, i) => {
        const done = i < idx;
        const active = i === idx;
        return (
          <div
            key={p}
            style={{
              flex: 1,
              padding: "10px 0",
              textAlign: "center",
              fontSize: 13,
              fontWeight: active ? 700 : 500,
              color: done ? "#22c55e" : active ? "#fff" : "#64748b",
              background: done ? "rgba(34,197,94,0.15)" : active ? "#3b82f6" : "rgba(255,255,255,0.04)",
              borderTop: `2px solid ${done ? "#22c55e" : active ? "#3b82f6" : "rgba(255,255,255,0.08)"}`,
              transition: "all 0.2s",
            }}
          >
            {done ? `✓ ${p}` : active ? `▶ ${p}` : p}
          </div>
        );
      })}
    </div>
  );
}

function SampleProgress({ gate, label }: { gate: SampleGate; label: string }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#94a3b8", marginBottom: 4 }}>
        <span>{label} sample</span>
        <span>{gate.have} / {gate.required}</span>
      </div>
      <div style={{ height: 4, background: "rgba(255,255,255,0.08)", borderRadius: 2, overflow: "hidden" }}>
        <div
          style={{
            height: "100%",
            width: `${gate.pct * 100}%`,
            background: gate.pct >= 1 ? "#22c55e" : "#3b82f6",
            borderRadius: 2,
            transition: "width 0.6s ease",
          }}
        />
      </div>
    </div>
  );
}

function KPICard({
  title, value, target, status, formula, description,
}: {
  title: string;
  value: number;
  target: number;
  status: "pass" | "fail" | "pending";
  formula: string;
  description: string;
}) {
  const color = statusColor(status);
  return (
    <div
      style={{
        background: statusBg(status),
        border: `1px solid ${color}40`,
        borderRadius: 12,
        padding: "20px 24px",
        flex: 1,
        minWidth: 200,
      }}
    >
      <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>
        {title}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
        <span style={{ fontSize: 32, fontWeight: 700, color }}>{pct(value)}</span>
        <span style={{ fontSize: 13, color: "#64748b" }}>target {pct(target)}</span>
      </div>
      <div
        style={{
          display: "inline-block",
          padding: "2px 8px",
          borderRadius: 4,
          fontSize: 11,
          fontWeight: 600,
          color,
          background: `${color}18`,
          marginBottom: 10,
        }}
      >
        {statusLabel(status)}
      </div>
      <div style={{ fontSize: 11, color: "#64748b", fontFamily: "monospace", marginBottom: 6 }}>{formula}</div>
      <div style={{ fontSize: 12, color: "#94a3b8" }}>{description}</div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function TestingDashboardPage() {
  const [data, setData] = useState<TestingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/video/testing")
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(e.message); setLoading(false); });
  }, []);

  if (loading) return <div style={{ padding: 40, color: "#94a3b8" }}>Loading testing data…</div>;
  if (error || !data) return <div style={{ padding: 40, color: "#ef4444" }}>Error: {error}</div>;

  return (
    <div style={{ padding: "28px 32px", maxWidth: 1200, fontFamily: "system-ui, sans-serif", color: "#e2e8f0" }}>

      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, color: "#f1f5f9" }}>
          Testing Framework
        </h1>
        <p style={{ fontSize: 13, color: "#64748b", margin: "6px 0 0" }}>
          Offer + (Copy + Leads) + (Script × Delivery) + (Reply + Warm FUP) = ABR
        </p>
      </div>

      {/* Phase progress */}
      <PhaseBar phase={data.phase} />

      {/* Current phase banner */}
      <div
        style={{
          background: data.phase === "SCALE" ? "rgba(34,197,94,0.12)" : "rgba(59,130,246,0.12)",
          border: `1px solid ${data.phase === "SCALE" ? "#22c55e40" : "#3b82f640"}`,
          borderRadius: 10,
          padding: "14px 20px",
          marginBottom: 28,
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <span style={{ fontSize: 20 }}>
          {data.phase === "SCALE" ? "🚀" : data.phase === "ABR" ? "📅" : data.phase === "PRR" ? "💬" : "👁️"}
        </span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: data.phase === "SCALE" ? "#22c55e" : "#60a5fa" }}>
            Current Focus: {data.phase}
          </div>
          <div style={{ fontSize: 12, color: "#94a3b8" }}>{data.phase_label}</div>
        </div>
      </div>

      {/* Three KPI cards */}
      <div style={{ display: "flex", gap: 16, marginBottom: 28, flexWrap: "wrap" }}>
        <KPICard
          title="LVR: Loom View Rate"
          value={data.lvr}
          target={data.kpi.lvr}
          status={data.lvr_status}
          formula="views ÷ sent"
          description="Measures offer resonance, copy quality & lead quality. Fix first."
        />
        <KPICard
          title="PRR: Positive Reply Rate"
          value={data.prr_view}
          target={data.kpi.prr_view}
          status={data.prr_status}
          formula="replies ÷ views"
          description="Measures script content & delivery. Fix after LVR is in KPI."
        />
        <KPICard
          title="ABR: Appointment Book Rate"
          value={data.abr_reply}
          target={data.kpi.abr_reply}
          status={data.abr_status}
          formula="bookings ÷ replies"
          description="Measures reply style & warm follow-up. Fix after PRR is in KPI."
        />
      </div>

      {/* Sample size gates */}
      <div
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 12,
          padding: "18px 24px",
          marginBottom: 28,
        }}
      >
        <div style={{ fontSize: 12, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 16 }}>
          Sample Size Gates: data is only meaningful once each gate is reached
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 24 }}>
          <SampleProgress gate={data.sample.lvr} label="LVR (need 300 sent)" />
          <SampleProgress gate={data.sample.prr} label="PRR (need 45 views)" />
          <SampleProgress gate={data.sample.abr} label="ABR (need 9 replies)" />
        </div>
      </div>

      {/* Overall funnel numbers */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 12,
          marginBottom: 32,
        }}
      >
        {[
          { label: "Total Sent",    value: data.total_sent,    icon: "📤" },
          { label: "Total Viewed",  value: data.total_views,   icon: "👁️" },
          { label: "Total Replied", value: data.total_replies, icon: "💬" },
          { label: "Total Booked",  value: data.total_booked,  icon: "📅" },
        ].map(({ label, value, icon }) => (
          <div
            key={label}
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 10,
              padding: "14px 18px",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: 22, marginBottom: 4 }}>{icon}</div>
            <div style={{ fontSize: 26, fontWeight: 700, color: "#f1f5f9" }}>{value}</div>
            <div style={{ fontSize: 11, color: "#64748b" }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Per-variant table */}
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: "#94a3b8", marginBottom: 14, textTransform: "uppercase", letterSpacing: "0.08em" }}>
          Per-Variant Breakdown
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {data.variants.map((v) => (
            <div
              key={v.variant_id}
              style={{
                background: v.leading ? "rgba(59,130,246,0.08)" : "rgba(255,255,255,0.03)",
                border: `1px solid ${v.leading ? "#3b82f640" : "rgba(255,255,255,0.07)"}`,
                borderRadius: 10,
                padding: "16px 20px",
              }}
            >
              {/* Variant header */}
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                <span
                  style={{
                    background: v.leading ? "#3b82f6" : "rgba(255,255,255,0.1)",
                    color: "#fff",
                    padding: "2px 10px",
                    borderRadius: 5,
                    fontSize: 12,
                    fontWeight: 700,
                  }}
                >
                  {v.variant_id}
                </span>
                <span style={{ fontWeight: 600, color: "#e2e8f0", fontSize: 14 }}>{v.name}</span>
                {v.leading && (
                  <span style={{ fontSize: 11, color: "#3b82f6", marginLeft: 4 }}>⭐ LEADING</span>
                )}
                <span style={{ fontSize: 12, color: "#64748b", marginLeft: "auto" }}>{v.hook_style}</span>
              </div>

              {/* Metrics row */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 12 }}>
                {/* Counts */}
                {[
                  { label: "Sent",    val: v.sent },
                  { label: "Views",   val: v.views },
                  { label: "Replies", val: v.replies },
                  { label: "Booked",  val: v.bookings },
                ].map(({ label, val }) => (
                  <div key={label} style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 20, fontWeight: 700, color: "#f1f5f9" }}>{val}</div>
                    <div style={{ fontSize: 11, color: "#64748b" }}>{label}</div>
                  </div>
                ))}

                {/* KPI status pills */}
                {[
                  { label: "LVR", val: v.lvr, target: 0.15, status: v.lvr_status, pctSample: v.lvr_sample_pct },
                  { label: "PRR", val: v.prr_view, target: 0.20, status: v.prr_status, pctSample: v.prr_sample_pct },
                  { label: "ABR", val: v.abr_reply, target: 0.50, status: v.abr_status, pctSample: v.abr_sample_pct },
                ].map(({ label, val, target, status, pctSample }) => (
                  <div key={label} style={{ textAlign: "center" }}>
                    <div
                      style={{
                        fontSize: 18,
                        fontWeight: 700,
                        color: statusColor(status),
                      }}
                    >
                      {pct(val)}
                    </div>
                    <div style={{ fontSize: 10, color: "#64748b", marginBottom: 4 }}>
                      {label} / target {pct(target)}
                    </div>
                    <div
                      style={{
                        display: "inline-block",
                        padding: "1px 6px",
                        borderRadius: 3,
                        fontSize: 10,
                        fontWeight: 600,
                        color: statusColor(status),
                        background: `${statusColor(status)}18`,
                      }}
                    >
                      {statusLabel(status)}
                    </div>
                    {/* Mini progress bar */}
                    <div style={{ height: 2, background: "rgba(255,255,255,0.06)", borderRadius: 1, marginTop: 6, overflow: "hidden" }}>
                      <div
                        style={{
                          height: "100%",
                          width: `${pctSample * 100}%`,
                          background: pctSample >= 1 ? "#22c55e" : "#3b82f6",
                          borderRadius: 1,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer rule */}
      <div style={{ marginTop: 32, padding: "16px 0", borderTop: "1px solid rgba(255,255,255,0.07)", fontSize: 12, color: "#475569" }}>
        <strong style={{ color: "#64748b" }}>Ceteris Paribus:</strong> change ONE variable at a time.
        Once all KPIs are in target, change NOTHING. Just increase volume.
        Use a Petri Dish (duplicate campaign) to test improvements without breaking what works.
      </div>
    </div>
  );
}
