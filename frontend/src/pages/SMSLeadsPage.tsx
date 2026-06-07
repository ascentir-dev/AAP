/**
 * SMS Leads — full table of every lead that has been through the SMS pipeline.
 *
 * Shows: name, company, role, phone, ICP market, variant, status, last message preview.
 * Filter tabs: All | Ready | Sent | Replied | Opted Out | Failed
 * Search: name, company, phone.
 * Download: exports the master SMS tracking sheet.
 */
import { useEffect, useState, useCallback } from "react";
import {
  InputGroup,
  Spinner,
  NonIdealState,
  Button,
} from "@blueprintjs/core";

// ─── Types ────────────────────────────────────────────────────────────────────

interface SMSLead {
  lead_id:        string;
  first_name:     string;
  last_name:      string;
  company:        string;
  role:           string;
  phone:          string;
  vertical:       string;
  variant_id:     string;
  framework:      string;
  status:         string;
  assigned_number: string;
  created_at:     number;
  updated_at:     number;
  has_reply:      boolean;
  inbound_count:  number;
  last_message?:  string;
  last_message_at?: number;
  last_direction?: "outbound" | "inbound";
}

interface StatusCounts {
  all:       number;
  ready:     number;
  sent:      number;
  replied:   number;
  booked:    number;
  opted_out: number;
  failed:    number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined) {
  return (n ?? 0).toLocaleString();
}

function formatTs(ts: number | null | undefined) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  const now = new Date();
  const diffH = (now.getTime() - d.getTime()) / 3_600_000;
  if (diffH < 24)  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (diffH < 168) return d.toLocaleDateString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  ready:     { label: "Ready",     color: "#4c90f0", bg: "rgba(76,144,240,0.12)" },
  sent:      { label: "Sent",      color: "#1D9E75", bg: "rgba(29,158,117,0.12)" },
  replied:   { label: "Replied",   color: "#f0b429", bg: "rgba(240,180,41,0.12)" },
  booked:    { label: "Booked",    color: "#1D9E75", bg: "rgba(29,158,117,0.2)"  },
  opted_out: { label: "Opted Out", color: "#e63946", bg: "rgba(230,57,70,0.12)"  },
  failed:    { label: "Failed",    color: "#e63946", bg: "rgba(230,57,70,0.12)"  },
  pending:   { label: "Pending",   color: "#738091", bg: "rgba(115,128,145,0.1)" },
};

function StatusBadge({ status }: { status: string }) {
  const m = STATUS_META[status] ?? { label: status, color: "#738091", bg: "rgba(115,128,145,0.1)" };
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 8px", borderRadius: 10,
      fontSize: 11, fontWeight: 600,
      color: m.color, background: m.bg,
      whiteSpace: "nowrap",
    }}>
      {m.label}
    </span>
  );
}

const VARIANT_COLOR: Record<string, string> = {
  "SMS-V1": "#4c90f0",
  "SMS-V2": "#a78bfa",
  "SMS-V3": "#34d399",
  "SMS-V4": "#f97316",
  "SMS-V5": "#f59e0b",
  "SMS-V6": "#e63946",
};

const FILTER_TABS = [
  { key: "all",       label: "All" },
  { key: "ready",     label: "Ready to Send" },
  { key: "sent",      label: "Sent" },
  { key: "replied",   label: "Replied" },
  { key: "booked",    label: "Booked" },
  { key: "opted_out", label: "Opted Out" },
  { key: "failed",    label: "Failed" },
];

// ─── Main component ───────────────────────────────────────────────────────────

export function SMSLeadsPage() {
  const [leads,        setLeads]        = useState<SMSLead[]>([]);
  const [total,        setTotal]        = useState(0);
  const [counts,       setCounts]       = useState<StatusCounts | null>(null);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState<string | null>(null);
  const [filter,       setFilter]       = useState("all");
  const [search,       setSearch]       = useState("");
  const [downloading,  setDownloading]  = useState(false);

  const load = useCallback(async (status: string, q: string) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "500" });
      if (status !== "all") params.set("status", status);
      if (q.trim())         params.set("q", q.trim());
      const r = await fetch(`/api/sms/leads?${params}`);
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const d = await r.json();
      setLeads(d.leads ?? []);
      setTotal(d.total ?? 0);
      if (d.status_counts) setCounts(d.status_counts);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(filter, search);
    const id = setInterval(() => load(filter, search), 15_000);
    return () => clearInterval(id);
  }, [filter, search, load]);

  function handleDownload() {
    setDownloading(true);
    const a = document.createElement("a");
    a.href = "/api/export/sms-leads";
    a.download = "";
    a.click();
    setTimeout(() => setDownloading(false), 1500);
  }

  const replyCount = (counts?.replied ?? 0) + (counts?.booked ?? 0);

  return (
    <div style={{ maxWidth: 1100 }}>

      {/* ── Page header ── */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h1 className="page-title" style={{ marginBottom: 4 }}>SMS Leads</h1>
          <p style={{ color: "#5f6b7c", fontSize: 13, margin: 0 }}>
            Every lead that has been generated or sent through the SMS pipeline.
          </p>
        </div>
        <Button
          icon="download"
          loading={downloading}
          onClick={handleDownload}
          style={{ flexShrink: 0, marginTop: 4 }}
        >
          Export tracking sheet
        </Button>
      </div>

      {/* ── Summary KPI strip ── */}
      {counts && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 20 }}>
          {[
            { label: "Total Generated",  value: counts.all,       color: "#abb3bf" },
            { label: "Ready to Send",    value: counts.ready,     color: "#4c90f0" },
            { label: "Sent",             value: counts.sent,      color: "#1D9E75" },
            { label: "Replied / Booked", value: replyCount,       color: "#f0b429" },
            { label: "Opted Out",        value: counts.opted_out, color: "#e63946" },
            { label: "Failed",           value: counts.failed,    color: counts.failed > 0 ? "#e63946" : "#383e47" },
          ].map(k => (
            <div key={k.label} style={{
              flex: "1 1 80px",
              background: "#1c2127", border: "1px solid #2f363e",
              borderRadius: 8, padding: "10px 12px", textAlign: "center",
            }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: k.color, lineHeight: 1 }}>
                {fmt(k.value)}
              </div>
              <div style={{ fontSize: 10, color: "#5f6b7c", marginTop: 3 }}>{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── Filter tabs + search ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <div style={{ display: "flex", background: "#161b22", borderRadius: 8, overflow: "hidden", border: "1px solid #2f363e" }}>
          {FILTER_TABS.map(tab => {
            const count = tab.key === "all"
              ? (counts?.all ?? 0)
              : tab.key === "replied"
              ? ((counts?.replied ?? 0) + (counts?.booked ?? 0))
              : (counts as Record<string, number> | null)?.[tab.key] ?? 0;
            const active = filter === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setFilter(tab.key)}
                style={{
                  padding: "7px 14px",
                  border: "none",
                  borderRight: "1px solid #2f363e",
                  background: active ? "#253545" : "transparent",
                  color: active ? "#f6f7f9" : "#5f6b7c",
                  cursor: "pointer",
                  fontSize: 12,
                  fontWeight: active ? 600 : 400,
                  display: "flex", alignItems: "center", gap: 5,
                  transition: "background 0.1s",
                }}
              >
                {tab.label}
                {count > 0 && (
                  <span style={{
                    background: active ? "#4c90f0" : "#2f363e",
                    color: active ? "#fff" : "#738091",
                    borderRadius: 10, fontSize: 10, fontWeight: 700,
                    padding: "0 5px", minWidth: 16, textAlign: "center",
                  }}>{fmt(count)}</span>
                )}
              </button>
            );
          })}
        </div>

        <div style={{ flex: 1, minWidth: 200, maxWidth: 300 }}>
          <InputGroup
            placeholder="Search name, company, phone…"
            leftIcon="search"
            value={search}
            onChange={e => setSearch(e.target.value)}
            small
            rightElement={search ? (
              <Button minimal small icon="cross" onClick={() => setSearch("")} />
            ) : undefined}
          />
        </div>

        {loading && <Spinner size={14} />}
        <span style={{ fontSize: 12, color: "#5f6b7c", marginLeft: "auto" }}>
          {fmt(total)} lead{total !== 1 ? "s" : ""}
        </span>
      </div>

      {/* ── Table ── */}
      {error ? (
        <NonIdealState icon="error" title="Could not load SMS leads" description={error}
          action={<Button intent="primary" onClick={() => load(filter, search)}>Retry</Button>} />
      ) : leads.length === 0 && !loading ? (
        <NonIdealState
          icon="mobile-phone"
          title={filter === "all" ? "No SMS leads yet" : `No leads with status "${filter}"`}
          description={
            filter === "all"
              ? "Run the SMS pipeline (Pipeline page → Generate SMS) to personalise leads and they'll appear here."
              : "Try a different filter tab."
          }
        />
      ) : (
        <div style={{
          background: "#1c2127", border: "1px solid #2f363e",
          borderRadius: 10, overflow: "hidden",
        }}>
          {/* Table header */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "2fr 2fr 1.2fr 1.2fr 1fr 1fr 1.6fr",
            gap: 0,
            padding: "8px 16px",
            background: "#161b22",
            borderBottom: "1px solid #2f363e",
            fontSize: 10, fontWeight: 700, color: "#5f6b7c",
            textTransform: "uppercase", letterSpacing: "0.07em",
          }}>
            <span>Lead</span>
            <span>Company</span>
            <span>Phone</span>
            <span>Market / Variant</span>
            <span>Status</span>
            <span>Updated</span>
            <span>Last Message</span>
          </div>

          {/* Rows */}
          {leads.map(lead => {
            const hasReply = lead.has_reply || lead.last_direction === "inbound";
            const varColor = VARIANT_COLOR[lead.variant_id] ?? "#738091";
            return (
              <div
                key={lead.lead_id}
                style={{
                  display: "grid",
                  gridTemplateColumns: "2fr 2fr 1.2fr 1.2fr 1fr 1fr 1.6fr",
                  gap: 0,
                  padding: "10px 16px",
                  borderBottom: "1px solid #222830",
                  alignItems: "center",
                  borderLeft: hasReply ? "3px solid #f0b429" : "3px solid transparent",
                  background: hasReply ? "rgba(240,180,41,0.04)" : "transparent",
                }}
              >
                {/* Name */}
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#f6f7f9", lineHeight: 1.3 }}>
                    {lead.first_name} {lead.last_name}
                    {hasReply && (
                      <span style={{
                        marginLeft: 6, background: "#f0b429", color: "#000",
                        borderRadius: 8, fontSize: 9, fontWeight: 700,
                        padding: "1px 5px", verticalAlign: "middle",
                      }}>
                        {lead.inbound_count > 1 ? `${lead.inbound_count} replies` : "replied"}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: "#5f6b7c", marginTop: 1 }}>{lead.role || "—"}</div>
                </div>

                {/* Company */}
                <div style={{ fontSize: 12, color: "#abb3bf", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", paddingRight: 8 }}>
                  {lead.company || "—"}
                </div>

                {/* Phone */}
                <div style={{ fontSize: 11, color: "#738091", fontFamily: "monospace" }}>
                  {lead.phone || "—"}
                </div>

                {/* Market + Variant */}
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  {lead.vertical && (
                    <span style={{ fontSize: 10, color: "#738091" }}>{lead.vertical}</span>
                  )}
                  {lead.variant_id && (
                    <span style={{
                      fontSize: 10, fontWeight: 700, color: varColor,
                      background: varColor + "1a", borderRadius: 4,
                      padding: "1px 5px", width: "fit-content",
                    }}>
                      {lead.variant_id}
                    </span>
                  )}
                </div>

                {/* Status */}
                <div>
                  <StatusBadge status={lead.status} />
                </div>

                {/* Updated */}
                <div style={{ fontSize: 11, color: "#5f6b7c" }}>
                  {formatTs(lead.updated_at)}
                </div>

                {/* Last message */}
                <div style={{
                  fontSize: 11,
                  color: hasReply ? "#f0b429" : "#5f6b7c",
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  maxWidth: 200,
                }}>
                  {lead.last_message ? (
                    <>
                      {lead.last_direction === "inbound" && (
                        <span style={{ color: "#f0b429", marginRight: 3 }}>←</span>
                      )}
                      {lead.last_message}
                    </>
                  ) : (
                    <span style={{ color: "#383e47" }}>—</span>
                  )}
                </div>
              </div>
            );
          })}

          {/* Load more hint if capped */}
          {total > leads.length && (
            <div style={{ padding: "10px 16px", fontSize: 12, color: "#5f6b7c", textAlign: "center", borderTop: "1px solid #222830" }}>
              Showing {fmt(leads.length)} of {fmt(total)} leads
            </div>
          )}
        </div>
      )}
    </div>
  );
}
