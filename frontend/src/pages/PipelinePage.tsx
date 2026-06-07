/**
 * PipelinePage — two-channel pipeline dashboard
 *
 * ┌─────────────────────────────────────────────────────┐
 * │  Lead Source  (shared CSV upload + history)         │
 * └─────────────────────────────────────────────────────┘
 * ┌──────────────────────┐  ┌──────────────────────────┐
 * │  📧 Cold Email        │  │  📱 SMS                  │
 * │  Phase 1 Personalise  │  │  Phase 1 Generate        │
 * │  Phase 2 Push         │  │  Phase 2 Send            │
 * │  Stats + Activity     │  │  Stats + Activity        │
 * └──────────────────────┘  └──────────────────────────┘
 */
import { useEffect, useRef, useState, useCallback } from "react";
import {
  Button,
  ProgressBar,
  Callout,
  Spinner,
  Divider,
  Tooltip,
} from "@blueprintjs/core";
import {
  uploadCsv,
  previewCsv,
  startPipeline,
  stopPipeline,
  fetchPipelineStatus,
  fetchReadiness,
  checkCampaign,
  fetchCsvHistory,
  applyDailyLimits,
  startSmsPipeline,
  stopSmsPipeline,
  fetchSmsPipelineStatus,
  fetchSmsReadiness,
  fetchEmailMasterStats,
  fetchSmsMasterStats,
} from "../api/client";
import type {
  PipelineStatus,
  SmsPipelineStatus,
  SmsReadinessResponse,
  UploadResponse,
  PreviewResponse,
  ReadinessResponse,
  ActivityItem,
  CampaignCheckResult,
  CsvUpload,
  EmailMasterStats,
  SmsMasterStats,
} from "../api/types";

// ─── helpers ──────────────────────────────────────────────────────────────────

function fmt(n: number | undefined | null) {
  return (n ?? 0).toLocaleString();
}

const STATUS_COLOR: Record<string, string> = {
  sent:    "#1D9E75",
  dry_run: "#4c90f0",
  skipped: "#9aa5b4",
  failed:  "#e63946",
};
const STATUS_GLYPH: Record<string, string> = {
  sent:    "✓",
  dry_run: "✓",
  skipped: "—",
  failed:  "✗",
};

// ─── sub-components ───────────────────────────────────────────────────────────

function ActivityFeed({ items, running }: { items: ActivityItem[]; running: boolean }) {
  if (items.length === 0) return null;
  return (
    <div style={{ background: "#1c2127", border: "1px solid #2f363e", borderRadius: 10, overflow: "hidden", marginTop: 12 }}>
      <div style={{ padding: "8px 14px", background: "#252a31", borderBottom: "1px solid #2f363e", display: "flex", alignItems: "center", gap: 8 }}>
        {running && <Spinner size={12} />}
        <span style={{ fontSize: 11, fontWeight: 600, color: "#abb3bf" }}>Live Feed</span>
        <span style={{ fontSize: 10, color: "#5f6b7c", marginLeft: "auto" }}>
          last {items.length} · newest first
        </span>
      </div>
      <div style={{ maxHeight: 260, overflowY: "auto" }}>
        {items.map((item, i) => {
          const color = STATUS_COLOR[item.status] ?? "#738091";
          const glyph = STATUS_GLYPH[item.status] ?? "?";
          return (
            <div
              key={`${item.email}-${i}`}
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 14px", borderBottom: "1px solid #222830", animation: "feedIn 0.2s ease" }}
            >
              <span style={{ width: 14, textAlign: "center", fontWeight: 700, color, fontSize: 12 }}>{glyph}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <span style={{ color: "#f6f7f9", fontSize: 12 }}>{item.name || item.email}</span>
                {item.company && (
                  <span style={{ color: "#5f6b7c", fontSize: 11, marginLeft: 5 }}>@ {item.company}</span>
                )}
                {item.status === "failed" && item.error && (
                  <div style={{ color: "#e63946", fontSize: 11, marginTop: 1 }}>{item.error.slice(0, 80)}</div>
                )}
              </div>
              <span style={{ color: "#5f6b7c", fontSize: 10, flexShrink: 0 }}>{item.time}</span>
              <span style={{ fontSize: 9, fontWeight: 600, color, background: color + "22", padding: "2px 5px", borderRadius: 4, textTransform: "uppercase", flexShrink: 0 }}>
                {item.status === "dry_run" ? "done" : item.status.replace("_", " ")}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function BigStatRow({ stats }: {
  stats: { label: string; value: number | string; color?: string; sub?: string }[]
}) {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
      {stats.map((s) => (
        <div key={s.label} style={{ flex: "1 1 80px", background: "#1c2127", border: "1px solid #2f363e", borderRadius: 8, padding: "10px 12px", textAlign: "center" }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: s.color ?? "#f6f7f9", lineHeight: 1 }}>
            {typeof s.value === "number" ? fmt(s.value) : s.value}
          </div>
          <div style={{ fontSize: 9, color: "#5f6b7c", marginTop: 3, textTransform: "uppercase", letterSpacing: "0.04em" }}>{s.label}</div>
          {s.sub && <div style={{ fontSize: 9, color: "#383e47", marginTop: 2 }}>{s.sub}</div>}
        </div>
      ))}
    </div>
  );
}

// ─── master stats panels ──────────────────────────────────────────────────────

function MasterLeadDB({ stats }: { stats: EmailMasterStats | null }) {
  if (!stats || stats.total_leads === 0) return null;

  const processed  = stats.total_sent + stats.total_personalised;
  const pct        = stats.total_leads > 0 ? Math.round((processed / stats.total_leads) * 100) : 0;
  const sentPct    = stats.total_leads > 0 ? Math.round((stats.total_sent / stats.total_leads) * 100) : 0;
  const readyPct   = stats.total_leads > 0 ? Math.round((stats.total_personalised / stats.total_leads) * 100) : 0;

  return (
    <div style={{
      background: "linear-gradient(135deg, #141a23 0%, #151c26 100%)",
      borderBottom: "1px solid #2f363e",
      padding: "14px 16px",
    }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "#738091", textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Master Lead Database
          </span>
          <span style={{ fontSize: 10, color: "#5f6b7c" }}>· {stats.uploads_count} upload{stats.uploads_count !== 1 ? "s" : ""} combined</span>
        </div>
        <Tooltip
          content="Same email in two CSVs = one lead_id. It's personalised once and never re-sent."
          placement="top"
        >
          <span style={{
            fontSize: 10, color: "#4c90f0", fontWeight: 600,
            background: "#4c90f015", border: "1px solid #4c90f030",
            padding: "2px 7px", borderRadius: 20, cursor: "default",
          }}>
            🔒 dedup-protected
          </span>
        </Tooltip>
      </div>

      {/* KPI row */}
      <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
        {[
          { label: "Total Leads",  value: stats.total_leads,        color: "#abb3bf" },
          { label: "Sent",         value: stats.total_sent,         color: "#1D9E75" },
          { label: "Ready",        value: stats.total_personalised, color: "#4c90f0" },
          { label: "Failed",       value: stats.total_failed,       color: stats.total_failed > 0 ? "#e63946" : "#383e47" },
          { label: "Untouched",    value: stats.total_remaining,    color: "#5f6b7c" },
        ].map(k => (
          <div key={k.label} style={{
            flex: "1 1 60px", textAlign: "center",
            background: "#1c2127", border: "1px solid #2a3140",
            borderRadius: 7, padding: "8px 6px",
          }}>
            <div style={{ fontSize: 18, fontWeight: 700, color: k.color, lineHeight: 1 }}>
              {fmt(k.value)}
            </div>
            <div style={{ fontSize: 9, color: "#5f6b7c", marginTop: 3, textTransform: "uppercase", letterSpacing: "0.04em" }}>
              {k.label}
            </div>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontSize: 10, color: "#5f6b7c" }}>
            <span style={{ color: "#1D9E75" }}>{sentPct}% sent</span>
            {readyPct > 0 && <span style={{ color: "#4c90f0" }}> · {readyPct}% ready</span>}
          </span>
          <span style={{ fontSize: 10, color: "#5f6b7c" }}>{pct}% processed total</span>
        </div>
        {/* Stacked bar: sent (green) + personalised/ready (blue) + remaining (dark) */}
        <div style={{ height: 6, borderRadius: 4, background: "#2a3140", overflow: "hidden", display: "flex" }}>
          <div style={{ width: `${sentPct}%`, background: "#1D9E75", transition: "width .4s" }} />
          <div style={{ width: `${readyPct}%`, background: "#4c90f0", transition: "width .4s" }} />
        </div>
      </div>
    </div>
  );
}

function SmsMasterPool({ stats }: { stats: SmsMasterStats | null }) {
  if (!stats || stats.total_leads === 0) return null;

  const sentPct      = stats.leads_with_phone > 0 ? Math.round((stats.sms_sent / stats.leads_with_phone) * 100) : 0;
  const phoneReach   = stats.total_leads > 0 ? Math.round((stats.leads_with_phone / stats.total_leads) * 100) : 0;

  return (
    <div style={{
      background: "linear-gradient(135deg, #141a23 0%, #15141f 100%)",
      borderBottom: "1px solid #2f363e",
      padding: "14px 16px",
    }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "#738091", textTransform: "uppercase", letterSpacing: "0.07em" }}>
            SMS Master Pool
          </span>
          <span style={{ fontSize: 10, color: "#5f6b7c" }}>· {stats.uploads_count} upload{stats.uploads_count !== 1 ? "s" : ""} combined</span>
        </div>
        <Tooltip
          content="DNC flags and opt-outs are checked before every send. Same phone across CSVs is only contacted once."
          placement="top"
        >
          <span style={{
            fontSize: 10, color: "#8b5cf6", fontWeight: 600,
            background: "#8b5cf615", border: "1px solid #8b5cf630",
            padding: "2px 7px", borderRadius: 20, cursor: "default",
          }}>
            🔒 DNC-filtered
          </span>
        </Tooltip>
      </div>

      {/* KPI row */}
      <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
        {[
          { label: "Total Leads",   value: stats.total_leads,        color: "#abb3bf",
            tip: "All leads across every uploaded CSV" },
          { label: "With Phone",    value: stats.leads_with_phone,   color: "#8b5cf6",
            tip: `${phoneReach}% of total have a valid, non-DNC wireless number` },
          { label: "DNC Excluded",  value: stats.dnc_excluded,       color: "#f0b429",
            tip: "Leads where every phone number is flagged DNC in the source data" },
          { label: "SMS Sent",      value: stats.sms_sent,           color: "#1D9E75",
            tip: "Successfully sent via Twilio all-time" },
          { label: "Sendable",      value: stats.net_sendable,       color: "#8b5cf6",
            tip: "With phone − sent − opted-out" },
        ].map(k => (
          <Tooltip key={k.label} content={k.tip} placement="top">
            <div style={{
              flex: "1 1 60px", textAlign: "center",
              background: "#1c2127", border: "1px solid #2a3140",
              borderRadius: 7, padding: "8px 6px", cursor: "default",
            }}>
              <div style={{ fontSize: 18, fontWeight: 700, color: k.color, lineHeight: 1 }}>
                {fmt(k.value)}
              </div>
              <div style={{ fontSize: 9, color: "#5f6b7c", marginTop: 3, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                {k.label}
              </div>
            </div>
          </Tooltip>
        ))}
      </div>

      {/* Progress bar + labels */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontSize: 10, color: "#5f6b7c" }}>
            <span style={{ color: "#8b5cf6" }}>{phoneReach}% of leads have valid phone</span>
            {stats.dnc_excluded > 0 && <span style={{ color: "#f0b429" }}> · {fmt(stats.dnc_excluded)} DNC excluded</span>}
          </span>
          <span style={{ fontSize: 10, color: "#5f6b7c" }}>{sentPct}% sent</span>
        </div>
        <div style={{ height: 6, borderRadius: 4, background: "#2a3140", overflow: "hidden", display: "flex" }}>
          <div style={{ width: `${sentPct}%`,    background: "#1D9E75",  transition: "width .4s" }} />
          <div style={{ width: `${Math.max(0, phoneReach - sentPct)}%`, background: "#8b5cf640", transition: "width .4s" }} />
        </div>
      </div>

      {stats.sms_opted_out > 0 && (
        <div style={{ marginTop: 8, fontSize: 10, color: "#5f6b7c" }}>
          <span style={{ color: "#f0b429" }}>⚠ {fmt(stats.sms_opted_out)} opted out</span> — permanently excluded from future sends
        </div>
      )}
    </div>
  );
}

// ─── channel section label ─────────────────────────────────────────────────────

function SectionLabel({ icon, title, subtitle, accentColor, running }: {
  icon: string; title: string; subtitle: string; accentColor: string; running?: boolean;
}) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "14px 18px",
      background: "linear-gradient(135deg, #1e2329 0%, #1a2028 100%)",
      borderRadius: "12px 12px 0 0",
      borderBottom: `2px solid ${accentColor}33`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 38, height: 38, borderRadius: 10, flexShrink: 0,
          background: accentColor + "18", border: `1px solid ${accentColor}33`,
          display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
        }}>
          {icon}
        </div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15, color: "#f6f7f9", lineHeight: 1.2 }}>{title}</div>
          <div style={{ fontSize: 11, color: "#5f6b7c", marginTop: 2 }}>{subtitle}</div>
        </div>
      </div>
      {running && (
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="live-dot" style={{ background: accentColor }} />
          <span style={{ fontSize: 10, fontWeight: 700, color: accentColor, letterSpacing: "0.08em" }}>RUNNING</span>
        </div>
      )}
    </div>
  );
}

// ─── step badge ───────────────────────────────────────────────────────────────

function StepBadge({ step, done, accentColor }: { step: number; done: boolean; accentColor: string }) {
  return (
    <div style={{
      width: 30, height: 30, borderRadius: "50%", flexShrink: 0,
      background: done ? accentColor : "#2f363e",
      border: `2px solid ${done ? accentColor : "#383e47"}`,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 12, fontWeight: 700,
      color: done ? "#fff" : "#5f6b7c",
    }}>
      {done ? "✓" : step}
    </div>
  );
}

// ─── main page ────────────────────────────────────────────────────────────────

type RunMode = "personalize" | "push";

export function PipelinePage() {
  // ── upload
  const [upload,      setUpload]      = useState<UploadResponse | null>(null);
  const [uploading,   setUploading]   = useState(false);
  const [uploadErr,   setUploadErr]   = useState<string | null>(null);
  const [dragOver,    setDragOver]    = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // ── CSV history
  const [csvHistory,    setCsvHistory]    = useState<CsvUpload[]>([]);
  const [totalNewLeads, setTotalNewLeads] = useState(0);

  // ── preview
  const [preview,    setPreview]    = useState<PreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [showDups,   setShowDups]   = useState(false);

  // ── readiness
  const [readiness,        setReadiness]        = useState<ReadinessResponse | null>(null);
  const [loadingReadiness, setLoadingReadiness] = useState(false);

  // ── campaign validation
  const [campaignCheck,        setCampaignCheck]        = useState<CampaignCheckResult | null>(null);
  const [campaignChecking,     setCampaignChecking]     = useState(false);
  const [campaignFetchFailed,  setCampaignFetchFailed]  = useState(false);

  // ── daily limits
  const [limitsApplying, setLimitsApplying] = useState(false);
  const [limitsResult,   setLimitsResult]   = useState<{ ok: boolean; msg: string } | null>(null);

  // ── run state
  const [lastMode,  setLastMode]  = useState<RunMode | null>(null);
  const [starting,  setStarting]  = useState(false);
  const [stopping,  setStopping]  = useState(false);
  const [runErr,    setRunErr]    = useState<string | null>(null);
  const [batchSize, setBatchSize] = useState<number>(100);

  // ── live pipeline status
  const [status, setStatus] = useState<PipelineStatus | null>(null);

  // ── master stats
  const [emailMaster, setEmailMaster] = useState<EmailMasterStats | null>(null);
  const [smsMaster,   setSmsMaster]   = useState<SmsMasterStats | null>(null);

  const refreshMasterStats = useCallback(async () => {
    try { setEmailMaster(await fetchEmailMasterStats()); } catch { /* ignore */ }
    try { setSmsMaster(await fetchSmsMasterStats()); }   catch { /* ignore */ }
  }, []);

  // ── SMS state
  const [smsStatus,    setSmsStatus]    = useState<SmsPipelineStatus | null>(null);
  const [smsReadiness, setSmsReadiness] = useState<SmsReadinessResponse | null>(null);
  const [smsLastMode,  setSmsLastMode]  = useState<"generate" | "send" | null>(null);
  const [smsStarting,  setSmsStarting]  = useState(false);
  const [smsStopping,  setSmsStopping]  = useState(false);
  const [smsErr,       setSmsErr]       = useState<string | null>(null);
  const [smsBatchSize, setSmsBatchSize] = useState<number>(100);

  // ── polling & callbacks ──────────────────────────────────────────────────

  const refreshReadiness = useCallback(async () => {
    setLoadingReadiness(true);
    try { setReadiness(await fetchReadiness()); }
    catch { /* ignore */ }
    finally { setLoadingReadiness(false); }
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      const h = await fetchCsvHistory();
      setCsvHistory(h.uploads);
      setTotalNewLeads(h.total_new_leads);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { refreshHistory(); }, [refreshHistory]);

  useEffect(() => {
    const saved = localStorage.getItem("aap_last_csv");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.csv_path && parsed.filename) {
          setUpload(parsed);
          previewCsv(parsed.csv_path).then(setPreview).catch(() => {});
        }
      } catch { /* ignore */ }
    }
  }, []);

  const runCampaignCheck = useCallback(async () => {
    setCampaignChecking(true);
    setCampaignFetchFailed(false);
    try {
      const result = await checkCampaign();
      setCampaignCheck(result);
    } catch {
      setCampaignCheck(null);
      setCampaignFetchFailed(true);
    } finally {
      setCampaignChecking(false);
    }
  }, []);

  const handleApplyDailyLimits = useCallback(async () => {
    setLimitsApplying(true);
    setLimitsResult(null);
    try {
      const r = await applyDailyLimits(900);
      if (r.ok) {
        setLimitsResult({ ok: true, msg: `Set: ${r.results.map((x: { variant: string; limit: number }) => `${x.variant} → ${x.limit}/day`).join(", ")}` });
      } else {
        setLimitsResult({ ok: false, msg: r.errors.join("; ") || "Failed to apply limits" });
      }
    } catch (e: unknown) {
      setLimitsResult({ ok: false, msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setLimitsApplying(false);
    }
  }, []);

  const pollStatus = useCallback(async () => {
    try {
      const s = await fetchPipelineStatus();
      setStatus(s);
      if (s.running) {
        setLastMode((prev) => {
          if (prev !== null) return prev;
          if ((s.run_personalised ?? 0) > 0) return "personalize";
          if ((s.run_sent ?? 0) > 0) return "push";
          return "personalize";
        });
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    pollStatus();
    refreshReadiness();
    runCampaignCheck();
    refreshMasterStats();
    const id = setInterval(async () => { await pollStatus(); }, 2000);
    return () => clearInterval(id);
  }, [pollStatus, refreshReadiness, runCampaignCheck, refreshMasterStats]);

  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && status && !status.running) {
      refreshReadiness();
      runCampaignCheck();
      refreshMasterStats();
    }
    wasRunning.current = status?.running ?? false;
  }, [status, refreshReadiness, runCampaignCheck, refreshMasterStats]);

  // ── upload handlers ──────────────────────────────────────────────────────

  async function handleFile(file: File) {
    if (!file.name.endsWith(".csv")) { setUploadErr("Only .csv files are accepted."); return; }
    setUploading(true);
    setUploadErr(null);
    setPreview(null);
    try {
      const result = await uploadCsv(file);
      setUpload(result);
      localStorage.setItem("aap_last_csv", JSON.stringify(result));
      refreshHistory();
      refreshMasterStats();
      setPreviewing(true);
      try { setPreview(await previewCsv(result.csv_path)); }
      finally { setPreviewing(false); }
    } catch (e: unknown) {
      setUploadErr(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }
  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
    e.target.value = "";
  }

  // ── email pipeline handlers ──────────────────────────────────────────────

  async function launch(mode: RunMode) {
    if (!upload) return;
    setStarting(true); setRunErr(null); setLastMode(mode);
    try {
      await startPipeline({ csv_path: upload.csv_path, dry_run: mode === "personalize", batch_size: mode === "personalize" ? batchSize : undefined });
      await pollStatus();
    } catch (e: unknown) {
      setRunErr(e instanceof Error ? e.message : String(e));
    } finally { setStarting(false); }
  }

  async function handleStop() {
    setStopping(true);
    try { await stopPipeline(); await pollStatus(); }
    finally { setStopping(false); }
  }

  // ── SMS pipeline handlers ────────────────────────────────────────────────

  const pollSmsStatus = useCallback(async () => {
    try {
      const s = await fetchSmsPipelineStatus();
      setSmsStatus(s);
      if (s.running) {
        setSmsLastMode((prev) => {
          if (prev !== null) return prev;
          if ((s.run_generated ?? 0) > 0) return "generate";
          if ((s.run_sent ?? 0) > 0) return "send";
          return "generate";
        });
      }
    } catch { /* ignore */ }
  }, []);

  const refreshSmsReadiness = useCallback(async () => {
    try { setSmsReadiness(await fetchSmsReadiness()); }
    catch { /* ignore */ }
  }, []);

  useEffect(() => {
    pollSmsStatus();
    refreshSmsReadiness();
    const id = setInterval(() => { pollSmsStatus(); }, 2000);
    return () => clearInterval(id);
  }, [pollSmsStatus, refreshSmsReadiness]);

  const smsWasRunning = useRef(false);
  useEffect(() => {
    if (smsWasRunning.current && smsStatus && !smsStatus.running) {
      refreshSmsReadiness();
    }
    smsWasRunning.current = smsStatus?.running ?? false;
  }, [smsStatus, refreshSmsReadiness]);

  async function launchSms(mode: "generate" | "send") {
    setSmsStarting(true); setSmsErr(null); setSmsLastMode(mode);
    try {
      await startSmsPipeline({ csv_path: mode === "generate" ? upload?.csv_path : undefined, dry_run: mode === "generate", batch_size: mode === "generate" ? smsBatchSize : 0 });
      await pollSmsStatus();
    } catch (e: unknown) {
      setSmsErr(e instanceof Error ? e.message : String(e));
    } finally { setSmsStarting(false); }
  }

  async function handleSmsStop() {
    setSmsStopping(true);
    try { await stopSmsPipeline(); await pollSmsStatus(); }
    finally { setSmsStopping(false); }
  }

  // ── derived ──────────────────────────────────────────────────────────────

  // Email
  const isRunning      = status?.running ?? false;
  const hasStatus      = (status?.total ?? 0) > 0;
  const runDone        = lastMode === "push" ? (status?.run_sent ?? 0) : (status?.run_personalised ?? 0);
  const progress       = hasStatus && (status?.total ?? 0) > 0 ? Math.min(1, runDone / status!.total) : 0;
  const newCount       = preview?.new_count       ?? 0;
  const dupCount       = preview?.duplicate_count ?? 0;
  const readyToPush    = readiness?.ready_to_push ?? 0;
  const activity       = status?.recent_activity  ?? [];
  const campaignBlocked = campaignCheck !== null && !campaignCheck.ok;

  // SMS
  const smsIsRunning   = smsStatus?.running ?? false;
  const smsHasStatus   = (smsStatus?.total ?? 0) > 0;
  const smsRunDone     = smsLastMode === "send" ? (smsStatus?.run_sent ?? 0) : (smsStatus?.run_generated ?? 0);
  const smsProgress    = smsHasStatus && (smsStatus?.total ?? 0) > 0 ? Math.min(1, smsRunDone / smsStatus!.total) : 0;
  const smsReadyToSend = smsReadiness?.ready_to_send ?? 0;

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div style={{ maxWidth: 1200, width: "100%" }}>

      {/* ── Global styles ── */}
      <style>{`
        @keyframes feedIn {
          from { opacity:0; transform:translateY(-4px) }
          to   { opacity:1; transform:translateY(0) }
        }
        @keyframes livePulse {
          0%, 100% { opacity:1; transform:scale(1); box-shadow:0 0 0 0 currentColor; }
          50%       { opacity:.7; transform:scale(1.3); box-shadow:0 0 0 3px transparent; }
        }
        .drop-zone {
          border:2px dashed #383e47; border-radius:10px; padding:24px;
          text-align:center; cursor:pointer;
          transition:border-color .15s, background .15s; background:#1c2127;
        }
        .drop-zone:hover,.drop-zone.drag-over { border-color:#4c90f0; background:#1a2335; }
        .drop-zone.has-file { border-color:#1D9E75; border-style:solid; }
        .live-dot {
          width:7px; height:7px; border-radius:50%; display:inline-block;
          animation:livePulse 1.4s ease-in-out infinite;
        }
        .batch-chip {
          padding:3px 9px; border-radius:5px; font-size:11px; cursor:pointer;
          transition:background .1s, border-color .1s;
        }
        .channel-panel {
          border:1px solid #2f363e; border-radius:12px;
          overflow:hidden; background:#191e24;
        }
        .phase-card {
          background:#1e2329; border-radius:10px; padding:18px 20px;
          border:2px solid #2a3140; margin-bottom:10px;
          transition:border-color .2s, opacity .2s;
        }
      `}</style>

      {/* ══ PAGE HEADER ══════════════════════════════════════════════════════ */}
      <div style={{ marginBottom: 22 }}>
        <h1 className="page-title" style={{ marginBottom: 3 }}>Pipeline</h1>
        <p style={{ color: "#5f6b7c", fontSize: 13, margin: 0, lineHeight: 1.6 }}>
          Upload leads once — both channels read from the same CSV. Run Cold Email and SMS independently.
        </p>
      </div>

      {/* ══ LEAD SOURCE ══════════════════════════════════════════════════════ */}
      <div style={{ background: "#191e24", border: "1px solid #2f363e", borderRadius: 12, marginBottom: 24, overflow: "hidden" }}>

        {/* Section header */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "11px 18px", background: "#1e2329",
          borderBottom: "1px solid #2f363e",
        }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: upload ? "#1D9E75" : "#383e47" }} />
          <span style={{ fontSize: 11, fontWeight: 700, color: "#738091", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Lead Source
          </span>
          {upload && (
            <span style={{ fontSize: 11, color: "#1D9E75", marginLeft: 4 }}>
              · {upload.filename}
            </span>
          )}
          {totalNewLeads > 0 && (
            <span style={{ fontSize: 11, color: "#5f6b7c", marginLeft: "auto" }}>
              <span style={{ color: "#3ddc84", fontWeight: 600 }}>{totalNewLeads.toLocaleString()}</span> unique new leads total
            </span>
          )}
        </div>

        <div style={{ padding: "16px 18px" }}>

          {/* Drop zone */}
          <div
            className={`drop-zone${dragOver ? " drag-over" : ""}${upload ? " has-file" : ""}`}
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            style={{ marginBottom: 0 }}
          >
            {uploading ? (
              <><Spinner size={24} style={{ marginBottom: 6 }} />
                <div style={{ color: "#738091", fontSize: 13 }}>Uploading…</div></>
            ) : upload ? (
              <div style={{ display: "flex", alignItems: "center", gap: 14, textAlign: "left" }}>
                <div style={{ fontSize: 28, flexShrink: 0 }}>📄</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, color: "#f6f7f9", fontSize: 14 }}>{upload.filename}</div>
                  <div style={{ fontSize: 12, color: "#738091", marginTop: 2 }}>
                    {fmt(upload.lead_count)} total · {fmt(upload.new_leads ?? 0)} new · click to replace
                  </div>
                </div>
                <div style={{ fontSize: 11, color: "#383e47" }}>↑ drop new file</div>
              </div>
            ) : (
              <><div style={{ fontSize: 32, marginBottom: 8 }}>📂</div>
                <div style={{ fontWeight: 600, color: "#f6f7f9", marginBottom: 4 }}>Drop your leads CSV here</div>
                <div style={{ fontSize: 12, color: "#5f6b7c" }}>or click to browse · Native format or Apollo / Clay skiptrace</div></>
            )}
          </div>
          <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }} onChange={handleInputChange} />

          {uploadErr && (
            <Callout intent="danger" icon="warning-sign" style={{ marginTop: 12 }}>
              {uploadErr}
            </Callout>
          )}

          {/* CSV History */}
          {csvHistory.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#5f6b7c", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 7 }}>
                Previous uploads
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {csvHistory.map((u) => {
                  const isActive = upload?.csv_path === u.csv_path;
                  return (
                    <div
                      key={u.id}
                      style={{
                        background: isActive ? "#1c2e40" : "#1a2433",
                        border: isActive ? "1px solid #1D6FA4" : "1px solid #253545",
                        borderRadius: 7, padding: "7px 12px",
                        display: "flex", alignItems: "center", gap: 10, cursor: "pointer",
                      }}
                      onClick={() => {
                        const restored = { filename: u.filename, csv_path: u.csv_path, lead_count: u.lead_count, new_leads: u.new_leads, duplicate_leads: u.duplicate_leads };
                        setUpload(restored);
                        localStorage.setItem("aap_last_csv", JSON.stringify(restored));
                        previewCsv(u.csv_path).then(setPreview).catch(() => {});
                      }}
                    >
                      <span style={{ fontSize: 14 }}>📄</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 12, color: "#f6f7f9", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {u.filename}
                        </div>
                        <div style={{ fontSize: 11, color: "#5f6b7c", marginTop: 1 }}>
                          {u.lead_count.toLocaleString()} total
                          {" · "}<span style={{ color: "#1D9E75" }}>{(u.sent_count ?? 0).toLocaleString()} sent</span>
                          {(u.pending_count ?? 0) > 0 && <span style={{ color: "#4c90f0" }}> · {u.pending_count!.toLocaleString()} ready</span>}
                          {(u.failed_count ?? 0) > 0 && <span style={{ color: "#e63946" }}> · {u.failed_count!.toLocaleString()} failed</span>}
                          {" · "}{new Date(u.uploaded_at).toLocaleDateString()}
                        </div>
                      </div>
                      {isActive && <span style={{ fontSize: 10, color: "#4c90f0", fontWeight: 700, flexShrink: 0 }}>ACTIVE</span>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Duplicate preview */}
          {(previewing || preview) && (
            <div style={{
              marginTop: 14, background: "#252a31", border: "1px solid #383e47",
              borderRadius: 9, padding: "12px 16px",
            }}>
              {previewing
                ? <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#738091", fontSize: 13 }}>
                    <Spinner size={14} /> Scanning for duplicates…
                  </div>
                : preview && (
                  <>
                    <div style={{ display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 20, fontWeight: 700, color: newCount > 0 ? "#1D9E75" : "#738091" }}>{fmt(newCount)}</span>
                        <div>
                          <div style={{ fontSize: 12, color: "#abb3bf" }}>new leads</div>
                          <div style={{ fontSize: 10, color: "#5f6b7c" }}>will be processed</div>
                        </div>
                      </div>
                      <Divider style={{ margin: "0 4px" }} />
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 20, fontWeight: 700, color: dupCount > 0 ? "#f0b429" : "#383e47" }}>{fmt(dupCount)}</span>
                        <div>
                          <div style={{ fontSize: 12, color: "#abb3bf" }}>duplicates</div>
                          <div style={{ fontSize: 10, color: "#5f6b7c" }}>auto-skipped</div>
                        </div>
                        {dupCount > 0 && (
                          <Button minimal small icon={showDups ? "chevron-up" : "chevron-down"}
                            style={{ color: "#5f6b7c" }} onClick={() => setShowDups(v => !v)} />
                        )}
                      </div>
                      {newCount === 0 && (
                        <Callout intent="warning" icon="warning-sign" style={{ marginLeft: "auto", padding: "5px 10px", fontSize: 12 }}>
                          All leads already sent.
                        </Callout>
                      )}
                    </div>
                    {showDups && dupCount > 0 && (
                      <div style={{ marginTop: 10, maxHeight: 150, overflowY: "auto" }}>
                        <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
                          <thead>
                            <tr style={{ color: "#5f6b7c" }}>
                              {["Name", "Company", "Email", "Status"].map(h => (
                                <th key={h} style={{ textAlign: "left", padding: "3px 8px", borderBottom: "1px solid #2f363e" }}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {preview.duplicate_leads.slice(0, 50).map(l => (
                              <tr key={l.lead_id}>
                                <td style={{ padding: "3px 8px", color: "#abb3bf" }}>{l.first_name} {l.last_name}</td>
                                <td style={{ padding: "3px 8px", color: "#738091" }}>{l.company}</td>
                                <td style={{ padding: "3px 8px", color: "#738091" }}>{l.email}</td>
                                <td style={{ padding: "3px 8px" }}><span style={{ color: "#1D9E75", fontSize: 10 }}>✓ {l.existing_status}</span></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {dupCount > 50 && <div style={{ color: "#5f6b7c", fontSize: 10, padding: "4px 8px" }}>…and {dupCount - 50} more</div>}
                      </div>
                    )}
                  </>
                )
              }
            </div>
          )}
        </div>
      </div>

      {/* Empty state — only when no CSV loaded and no runs have happened */}
      {!upload && !hasStatus && !smsHasStatus && (
        <div style={{ textAlign: "center", padding: "48px 24px", color: "#383e47" }}>
          <div style={{ fontSize: 48, marginBottom: 10 }}>✨</div>
          <div style={{ fontSize: 14, color: "#5f6b7c" }}>Upload a CSV above to begin.</div>
        </div>
      )}

      {/* ══ TWO-CHANNEL COLUMNS ══════════════════════════════════════════════ */}
      <div style={{ display: "flex", gap: 18, alignItems: "flex-start", flexWrap: "wrap" }}>

        {/* ╔══════════════════════════════════════╗
            ║  📧  COLD EMAIL  COLUMN              ║
            ╚══════════════════════════════════════╝ */}
        <div style={{ flex: "1 1 440px", minWidth: 0 }} className="channel-col">
          <div className="channel-panel">

            {/* Channel header */}
            <SectionLabel
              icon="📧"
              title="Cold Email"
              subtitle="Smartlead · AI personalised video + email"
              accentColor="#4c90f0"
              running={isRunning}
            />

            {/* Master Lead Database panel */}
            <MasterLeadDB stats={emailMaster} />

            {/* Per-run KPI strip (only shown when a run has happened) */}
            {(hasStatus || readyToPush > 0 || (readiness?.already_sent ?? 0) > 0) && (
              <div style={{ display: "flex", gap: 1, borderBottom: "1px solid #2f363e" }}>
                {[
                  { label: "Sent this run", value: fmt(readiness?.already_sent ?? status?.db_sent ?? 0), color: "#1D9E75" },
                  { label: "Ready to push", value: fmt(readyToPush), color: readyToPush > 0 ? "#4c90f0" : "#383e47" },
                  { label: "Failed",        value: fmt(status?.failed ?? 0), color: (status?.failed ?? 0) > 0 ? "#e63946" : "#383e47" },
                ].map((k) => (
                  <div key={k.label} style={{ flex: 1, padding: "10px 14px", background: "#1c2127", textAlign: "center" }}>
                    <div style={{ fontSize: 20, fontWeight: 700, color: k.color, lineHeight: 1 }}>{k.value}</div>
                    <div style={{ fontSize: 9, color: "#5f6b7c", marginTop: 3, textTransform: "uppercase", letterSpacing: "0.05em" }}>{k.label}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Phase cards */}
            <div style={{ padding: "14px 14px 6px" }}>

              {/* ── Phase 1: Personalise ── */}
              <div className="phase-card" style={{
                borderColor: isRunning && lastMode === "personalize" ? "#4c90f080" : readyToPush > 0 ? "#1D9E7540" : "#2a3140",
              }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
                  <StepBadge step={1} done={readyToPush > 0} accentColor="#4c90f0" />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, color: "#f6f7f9", fontSize: 14, marginBottom: 3 }}>
                      Personalise Leads
                    </div>
                    <div style={{ fontSize: 12, color: "#5f6b7c", marginBottom: 12, lineHeight: 1.55 }}>
                      Enrich each lead, score intent, write a personalised email, record a personalised video for high-intent leads (≥ 0.65). Nothing is sent yet.
                    </div>

                    {/* Batch size */}
                    {!isRunning && (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 11, color: "#738091", whiteSpace: "nowrap" }}>Batch:</span>
                        <input
                          type="number" min={1} max={upload?.lead_count ?? 9999} value={batchSize}
                          onChange={e => setBatchSize(Math.max(1, parseInt(e.target.value) || 1))}
                          style={{
                            width: 70, padding: "3px 8px", background: "#252a31",
                            border: "1px solid #383e47", borderRadius: 6, color: "#f6f7f9",
                            fontSize: 13, fontWeight: 600, textAlign: "center", outline: "none",
                          }}
                        />
                        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                          {[25, 50, 100, 250].filter(n => n <= (upload?.lead_count ?? 9999)).map(n => (
                            <button key={n} className="batch-chip" onClick={() => setBatchSize(n)} style={{
                              border: "1px solid " + (batchSize === n ? "#4c90f0" : "#2f363e"),
                              background: batchSize === n ? "#1a2a4a" : "transparent",
                              color: batchSize === n ? "#4c90f0" : "#5f6b7c",
                            }}>{n}</button>
                          ))}
                          {upload && (
                            <button className="batch-chip" onClick={() => setBatchSize(upload.lead_count)} style={{
                              border: "1px solid " + (batchSize === upload.lead_count ? "#4c90f0" : "#2f363e"),
                              background: batchSize === upload.lead_count ? "#1a2a4a" : "transparent",
                              color: batchSize === upload.lead_count ? "#4c90f0" : "#5f6b7c",
                            }}>All {fmt(upload.lead_count)}</button>
                          )}
                        </div>
                      </div>
                    )}

                    {/* CTA */}
                    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                      {isRunning && lastMode === "personalize" ? (
                        <Button intent="danger" icon="stop" loading={stopping} onClick={handleStop}>
                          Stop Personalising
                        </Button>
                      ) : (
                        <Tooltip
                          content={!upload ? "Upload a CSV first" : newCount === 0 ? "No new leads to personalise" : undefined}
                          disabled={!!upload && newCount > 0}
                        >
                          <Button
                            intent="primary" icon="generate"
                            loading={starting && lastMode === "personalize"}
                            disabled={!upload || newCount === 0 || (isRunning && lastMode !== "personalize")}
                            onClick={() => launch("personalize")}
                          >
                            {readyToPush > 0
                              ? `Re-personalise ${fmt(Math.min(batchSize, newCount))} leads`
                              : `✨  Personalise ${upload ? fmt(Math.min(batchSize, newCount)) : ""} leads`}
                          </Button>
                        </Tooltip>
                      )}
                      {isRunning && lastMode === "personalize" && (
                        <span style={{ fontSize: 11, color: "#4c90f0" }}>Personalising… batch of {fmt(batchSize)}</span>
                      )}
                    </div>
                  </div>
                </div>

                {isRunning && lastMode === "personalize" && hasStatus && (
                  <div style={{ marginTop: 14 }}>
                    <ProgressBar value={progress} intent="primary" animate stripes style={{ height: 6, borderRadius: 4, marginBottom: 5 }} />
                    <div style={{ fontSize: 11, color: "#5f6b7c", display: "flex", justifyContent: "space-between" }}>
                      <span>{fmt(status!.run_personalised ?? 0)} / {fmt(status!.total)} personalised</span>
                      {status!.elapsed_seconds != null && <span>{status!.elapsed_seconds}s</span>}
                    </div>
                  </div>
                )}
              </div>

              {/* ── Phase 2: Push to Smartlead ── */}
              <div className="phase-card" style={{
                borderColor: isRunning && lastMode === "push" ? "#1D9E7580" : readyToPush > 0 ? "#1D9E7540" : "#2a3140",
                opacity: readyToPush === 0 && !isRunning ? 0.55 : 1,
              }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
                  <StepBadge step={2} done={(status?.db_sent ?? 0) > 0} accentColor="#1D9E75" />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, color: "#f6f7f9", fontSize: 14, marginBottom: 3 }}>
                      Push to Smartlead
                    </div>
                    <div style={{ fontSize: 12, color: "#5f6b7c", marginBottom: 12, lineHeight: 1.55 }}>
                      Sends personalised emails + video links to the right Smartlead campaign. Assets are cached — fast (no re-generation).
                    </div>

                    {/* Readiness summary */}
                    {readyToPush > 0 && (
                      <div style={{
                        background: "#1a2218", border: "1px solid #2a4a3a", borderRadius: 8,
                        padding: "9px 13px", marginBottom: 10,
                        display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center",
                      }}>
                        <div>
                          <span style={{ fontSize: 13, color: "#1D9E75", fontWeight: 600 }}>{fmt(readyToPush)} leads ready to push</span>
                          <div style={{ fontSize: 10, color: "#5f6b7c", marginTop: 1 }}>personalised · awaiting Smartlead</div>
                        </div>
                        {(readiness?.video_count ?? 0) > 0 && (
                          <span style={{ fontSize: 11, color: "#abb3bf" }}>🎥 {fmt(readiness!.video_count)} with video</span>
                        )}
                        {(readiness?.email_only_count ?? 0) > 0 && (
                          <span style={{ fontSize: 11, color: "#abb3bf" }}>📧 {fmt(readiness!.email_only_count)} email-only</span>
                        )}
                        {loadingReadiness && <Spinner size={11} />}
                      </div>
                    )}
                    {(readiness?.all_personalised ?? 0) > readyToPush && readyToPush > 0 && (
                      <div style={{ fontSize: 11, color: "#5f6b7c", background: "#161b22", border: "1px solid #2f363e", borderRadius: 6, padding: "5px 10px", marginBottom: 10 }}>
                        {fmt(readiness!.all_personalised)} personalised all-time — {fmt(readiness?.already_sent ?? 0)} already pushed = {fmt(readyToPush)} in queue.
                      </div>
                    )}
                    {(readiness?.all_personalised ?? 0) > readyToPush && readyToPush === 0 && (readiness?.already_sent ?? 0) > 0 && (
                      <div style={{ fontSize: 11, color: "#5f6b7c", background: "#161b22", border: "1px solid #2f363e", borderRadius: 6, padding: "5px 10px", marginBottom: 10 }}>
                        All {fmt(readiness!.all_personalised)} personalised leads have already been pushed.
                      </div>
                    )}

                    {/* Campaign check */}
                    {campaignChecking ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10, fontSize: 12, color: "#738091" }}>
                        <Spinner size={11} /> Checking Smartlead campaign…
                      </div>
                    ) : campaignFetchFailed ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, background: "#252a31", border: "1px solid #383e47", borderRadius: 6, padding: "7px 11px", fontSize: 12, color: "#738091" }}>
                        <span>Could not verify campaign — proceeding anyway</span>
                        <Button minimal small icon="refresh" style={{ color: "#5f6b7c", marginLeft: "auto" }} onClick={runCampaignCheck}>Re-check</Button>
                      </div>
                    ) : campaignCheck?.ok ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10, background: "#1a2218", border: "1px solid #2a4a3a", borderRadius: 6, padding: "7px 11px", fontSize: 12, color: "#1D9E75" }}>
                        <span style={{ fontWeight: 600 }}>✓</span>
                        <span>Campaign ready — "{campaignCheck.name}" is ACTIVE</span>
                        <Button minimal small icon="refresh" style={{ color: "#5f6b7c", marginLeft: "auto" }} onClick={runCampaignCheck}>Re-check</Button>
                      </div>
                    ) : campaignCheck !== null ? (
                      <div style={{ marginBottom: 10 }}>
                        <Callout intent="danger" icon="warning-sign" style={{ padding: "9px 13px" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                            <div>
                              <div style={{ fontWeight: 600, marginBottom: 5, fontSize: 12 }}>Fix before pushing:</div>
                              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11 }}>
                                {campaignCheck.issues.map((issue, i) => (
                                  <li key={i} style={{ marginBottom: 2 }}>{issue}</li>
                                ))}
                              </ul>
                            </div>
                            <Button minimal small icon="refresh" style={{ flexShrink: 0, marginLeft: 10 }} onClick={runCampaignCheck}>Re-check</Button>
                          </div>
                        </Callout>
                      </div>
                    ) : null}

                    {/* Daily limits */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, padding: "7px 11px", background: "#1c2127", border: "1px solid #2f363e", borderRadius: 6, flexWrap: "wrap" }}>
                      <span style={{ fontSize: 11, color: "#738091", flex: 1 }}>
                        Daily limit: <strong style={{ color: "#abb3bf" }}>18 accounts × 50/day = 900</strong>
                      </span>
                      <Button small icon="time" loading={limitsApplying} style={{ fontSize: 11 }} onClick={handleApplyDailyLimits}>
                        Apply to SmartLead
                      </Button>
                    </div>
                    {limitsResult && (
                      <Callout intent={limitsResult.ok ? "success" : "danger"} icon={limitsResult.ok ? "tick-circle" : "warning-sign"}
                        style={{ marginBottom: 10, fontSize: 11, padding: "7px 11px" }}>
                        {limitsResult.msg}
                      </Callout>
                    )}

                    {/* Push CTA */}
                    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                      {isRunning && lastMode === "push" ? (
                        <Button intent="danger" icon="stop" loading={stopping} onClick={handleStop}>Stop Push</Button>
                      ) : (
                        <Tooltip
                          content={
                            readyToPush === 0 ? "Complete Phase 1 first" :
                            campaignBlocked ? "Fix campaign issues above" : undefined
                          }
                          disabled={readyToPush > 0 && !campaignBlocked}
                        >
                          <Button
                            intent="success" icon="send-to"
                            loading={starting && lastMode === "push"}
                            disabled={readyToPush === 0 || campaignBlocked || (isRunning && lastMode !== "push")}
                            onClick={() => launch("push")}
                          >
                            🚀 Push {fmt(readyToPush)} leads to Smartlead
                          </Button>
                        </Tooltip>
                      )}
                      {isRunning && lastMode === "push" && (
                        <span style={{ fontSize: 11, color: "#1D9E75" }}>Sending to Smartlead…</span>
                      )}
                    </div>
                  </div>
                </div>

                {isRunning && lastMode === "push" && hasStatus && (
                  <div style={{ marginTop: 14 }}>
                    <ProgressBar value={progress} intent="success" animate stripes style={{ height: 6, borderRadius: 4, marginBottom: 5 }} />
                    <div style={{ fontSize: 11, color: "#5f6b7c", display: "flex", justifyContent: "space-between" }}>
                      <span>{fmt(status!.run_sent ?? 0)} / {fmt(status!.total)} pushed</span>
                      {status!.elapsed_seconds != null && <span>{status!.elapsed_seconds}s</span>}
                    </div>
                  </div>
                )}
              </div>

              {/* Run error */}
              {runErr && <Callout intent="danger" icon="warning-sign" style={{ marginBottom: 10 }}>{runErr}</Callout>}

              {/* Overall progress + stats */}
              {hasStatus && status && (
                <>
                  {(() => {
                    const csvTotal   = status.csv_total ?? upload?.lead_count ?? 0;
                    const allDone    = readiness?.all_personalised ?? 0;
                    const allSkipped = readiness?.all_skipped      ?? 0;
                    const allFailed  = readiness?.all_failed       ?? 0;
                    const allTouched = allDone + allSkipped + allFailed;
                    const pct        = csvTotal > 0 ? Math.min(1, allTouched / csvTotal) : 0;
                    if (csvTotal === 0) return null;
                    return (
                      <div style={{ background: "#1c2127", border: "1px solid #2f363e", borderRadius: 9, padding: "12px 14px", marginBottom: 10 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 7 }}>
                          <span style={{ fontSize: 11, fontWeight: 600, color: "#738091" }}>Overall Progress</span>
                          <span style={{ fontSize: 11, color: "#5f6b7c" }}>{fmt(allTouched)} / {fmt(csvTotal)}</span>
                        </div>
                        <ProgressBar value={pct} intent="primary" style={{ height: 7, borderRadius: 4, marginBottom: 8 }} />
                        <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                          <Tooltip content="All-time personalised — includes already pushed" placement="top">
                            <span style={{ fontSize: 11, color: "#4c90f0", cursor: "default" }}>✓ {fmt(allDone)} personalised</span>
                          </Tooltip>
                          <span style={{ fontSize: 11, color: "#738091" }}>— {fmt(allSkipped)} skipped</span>
                          <span style={{ fontSize: 11, color: allFailed > 0 ? "#e63946" : "#383e47" }}>✗ {fmt(allFailed)} failed</span>
                          <span style={{ fontSize: 11, color: "#5f6b7c", marginLeft: "auto" }}>{fmt(csvTotal - allTouched)} remaining</span>
                        </div>
                      </div>
                    );
                  })()}

                  <BigStatRow stats={[
                    { label: "This Batch",     value: status.total, color: "#abb3bf", sub: "queued this run" },
                    { label: lastMode === "push" ? "Pushed This Run" : "Personalised",
                      value: lastMode === "push" ? (status.run_sent ?? 0) : (status.run_personalised ?? 0), color: "#4c90f0" },
                    { label: "Sent All-Time",  value: status.db_sent ?? readiness?.already_sent ?? 0, color: "#1D9E75" },
                    { label: "Dupes Skipped",  value: status.duplicate_count, color: "#f0b429" },
                    { label: "Not a Fit",      value: status.skipped, color: "#738091" },
                    { label: "Failed",         value: status.failed, color: status.failed > 0 ? "#e63946" : "#383e47" },
                    ...(status.cost_usd != null
                      ? [{ label: "Cost", value: `$${status.cost_usd.toFixed(3)}`, color: "#abb3bf" }]
                      : []),
                  ]} />

                  {!isRunning && status.total > 0 && (
                    <Callout
                      intent={status.failed > 0 ? "warning" : lastMode === "push" ? "success" : "primary"}
                      icon={status.failed > 0 ? "warning-sign" : lastMode === "push" ? "tick-circle" : "tick"}
                      style={{ marginBottom: 10, fontSize: 12 }}
                    >
                      {lastMode === "push"
                        ? status.failed > 0
                          ? `Push finished with ${status.failed} failure${status.failed !== 1 ? "s" : ""}. ${fmt(status.run_sent ?? 0)} sent (${fmt(status.db_sent ?? 0)} all-time).`
                          : `${fmt(status.run_sent ?? 0)} leads pushed. ${fmt(status.db_sent ?? 0)} sent all-time. Campaign is live.`
                        : status.failed > 0
                          ? `Personalisation finished with ${status.failed} failure${status.failed !== 1 ? "s" : ""}. ${readyToPush} leads ready to push.`
                          : `Personalisation complete — ${fmt(status.run_personalised ?? 0)} done, ${readyToPush} total ready to push.`
                      }
                    </Callout>
                  )}

                  <ActivityFeed items={activity} running={isRunning} />
                </>
              )}
            </div>
          </div>{/* end channel-panel */}
        </div>{/* end email col */}


        {/* ╔══════════════════════════════════════╗
            ║  📱  SMS  COLUMN                     ║
            ╚══════════════════════════════════════╝ */}
        <div style={{ flex: "1 1 440px", minWidth: 0 }} className="channel-col">
          <div className="channel-panel">

            {/* Channel header */}
            <SectionLabel
              icon="📱"
              title="SMS"
              subtitle="Twilio · 6-variant A/B · 3-number rotation"
              accentColor="#8b5cf6"
              running={smsIsRunning}
            />

            {/* SMS Master Pool panel */}
            <SmsMasterPool stats={smsMaster} />

            {/* Per-run SMS KPI strip + Export */}
            <div style={{ display: "flex", gap: 1, borderBottom: "1px solid #2f363e" }}>
              {[
                { label: "Ready to send",  value: fmt(smsReadyToSend), color: smsReadyToSend > 0 ? "#8b5cf6" : "#383e47" },
                { label: "Sent all-time",  value: fmt(smsReadiness?.already_sent ?? 0), color: "#1D9E75" },
                { label: "Replied",        value: fmt(smsReadiness?.replied ?? 0), color: "#f0b429" },
              ].map((k) => (
                <div key={k.label} style={{ flex: 1, padding: "10px 14px", background: "#1c2127", textAlign: "center" }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: k.color, lineHeight: 1 }}>{k.value}</div>
                  <div style={{ fontSize: 9, color: "#5f6b7c", marginTop: 3, textTransform: "uppercase", letterSpacing: "0.05em" }}>{k.label}</div>
                </div>
              ))}
              {upload && (
                <div style={{ padding: "8px 10px", background: "#1c2127", display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <Tooltip content="Export SMS tracking sheet — all leads" placement="top">
                    <Button icon="download" small minimal style={{ color: "#738091" }}
                      onClick={() => {
                        const url = `/api/export/sms-leads?csv_path=${encodeURIComponent(upload.csv_path)}`;
                        const a = document.createElement("a");
                        a.href = url; a.download = ""; a.click();
                      }}
                    >Export</Button>
                  </Tooltip>
                </div>
              )}
            </div>

            {/* Phase cards */}
            <div style={{ padding: "14px 14px 6px" }}>

              {/* ── SMS Phase 1: Generate ── */}
              <div className="phase-card" style={{
                borderColor: smsIsRunning && smsLastMode === "generate" ? "#8b5cf680" : smsReadyToSend > 0 ? "#8b5cf640" : "#2a3140",
              }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
                  <StepBadge step={1} done={smsReadyToSend > 0} accentColor="#8b5cf6" />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, color: "#f6f7f9", fontSize: 14, marginBottom: 3 }}>
                      Generate SMS
                    </div>
                    <div style={{ fontSize: 12, color: "#5f6b7c", marginBottom: 12, lineHeight: 1.55 }}>
                      Reads the CSV, assigns each lead an ICP-matched variant (V1–V6 A/B), pulls their enrichment from the email ledger, and writes a personalised message. Nothing is sent via Twilio yet.
                    </div>

                    {/* Batch size */}
                    {!smsIsRunning && (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 11, color: "#738091", whiteSpace: "nowrap" }}>Batch:</span>
                        <input
                          type="number" min={1} value={smsBatchSize}
                          onChange={e => setSmsBatchSize(Math.max(1, parseInt(e.target.value) || 1))}
                          style={{
                            width: 70, padding: "3px 8px", background: "#252a31",
                            border: "1px solid #383e47", borderRadius: 6, color: "#f6f7f9",
                            fontSize: 13, fontWeight: 600, textAlign: "center", outline: "none",
                          }}
                        />
                        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                          {[50, 100, 250].map(n => (
                            <button key={n} className="batch-chip" onClick={() => setSmsBatchSize(n)} style={{
                              border: "1px solid " + (smsBatchSize === n ? "#8b5cf6" : "#2f363e"),
                              background: smsBatchSize === n ? "#251a45" : "transparent",
                              color: smsBatchSize === n ? "#8b5cf6" : "#5f6b7c",
                            }}>{n}</button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Generate CTA */}
                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                      {smsIsRunning && smsLastMode === "generate" ? (
                        <Button intent="danger" icon="stop" loading={smsStopping} onClick={handleSmsStop}>Stop Generating</Button>
                      ) : (
                        <Tooltip content={!upload ? "Upload a CSV first" : undefined} disabled={!!upload}>
                          <Button
                            intent="primary" icon="mobile-phone"
                            loading={smsStarting && smsLastMode === "generate"}
                            disabled={!upload || (smsIsRunning && smsLastMode !== "generate")}
                            onClick={() => launchSms("generate")}
                          >
                            {smsReadyToSend > 0
                              ? `Re-generate ${fmt(smsBatchSize)} SMS`
                              : `✨  Generate ${upload ? fmt(smsBatchSize) : ""} SMS`}
                          </Button>
                        </Tooltip>
                      )}
                    </div>
                  </div>
                </div>

                {smsIsRunning && smsLastMode === "generate" && smsHasStatus && (
                  <div style={{ marginTop: 14 }}>
                    <ProgressBar value={smsProgress} intent="primary" animate stripes style={{ height: 6, borderRadius: 4, marginBottom: 5 }} />
                    <div style={{ fontSize: 11, color: "#5f6b7c", display: "flex", justifyContent: "space-between" }}>
                      <span>{fmt(smsStatus!.run_generated)} / {fmt(smsStatus!.total)} generated</span>
                      {smsStatus!.elapsed_seconds != null && <span>{smsStatus!.elapsed_seconds}s</span>}
                    </div>
                  </div>
                )}
              </div>

              {/* ── SMS Phase 2: Send via Twilio ── */}
              <div className="phase-card" style={{
                borderColor: smsIsRunning && smsLastMode === "send" ? "#1D9E7580" : smsReadyToSend > 0 ? "#1D9E7540" : "#2a3140",
                opacity: smsReadyToSend === 0 && !smsIsRunning ? 0.55 : 1,
              }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
                  <StepBadge step={2} done={(smsReadiness?.already_sent ?? 0) > 0} accentColor="#1D9E75" />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, color: "#f6f7f9", fontSize: 14, marginBottom: 3 }}>
                      Send via Twilio
                    </div>
                    <div style={{ fontSize: 12, color: "#5f6b7c", marginBottom: 12, lineHeight: 1.55 }}>
                      Fires all generated messages through your 3 Twilio numbers. 100/day per number · 500 ms between sends · opt-outs handled automatically.
                    </div>

                    {smsReadyToSend > 0 && (
                      <div style={{ background: "#1a2218", border: "1px solid #2a4a3a", borderRadius: 8, padding: "9px 13px", marginBottom: 12, display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
                        <div>
                          <span style={{ fontSize: 13, color: "#1D9E75", fontWeight: 600 }}>{fmt(smsReadyToSend)} SMS ready to send</span>
                          <div style={{ fontSize: 10, color: "#5f6b7c", marginTop: 1 }}>generated · awaiting Twilio</div>
                        </div>
                        <Divider style={{ margin: "0 4px" }} />
                        <span style={{ fontSize: 11, color: "#abb3bf" }}>📡 3 Twilio numbers · ~300/day max</span>
                      </div>
                    )}

                    {/* Send CTA */}
                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                      {smsIsRunning && smsLastMode === "send" ? (
                        <Button intent="danger" icon="stop" loading={smsStopping} onClick={handleSmsStop}>Stop Sending</Button>
                      ) : (
                        <Tooltip content={smsReadyToSend === 0 ? "Generate SMS first" : undefined} disabled={smsReadyToSend > 0}>
                          <Button
                            intent="success" icon="mobile-phone"
                            loading={smsStarting && smsLastMode === "send"}
                            disabled={smsReadyToSend === 0 || (smsIsRunning && smsLastMode !== "send")}
                            onClick={() => launchSms("send")}
                          >
                            🚀 Send {fmt(smsReadyToSend)} SMS via Twilio
                          </Button>
                        </Tooltip>
                      )}
                    </div>
                  </div>
                </div>

                {smsIsRunning && smsLastMode === "send" && smsHasStatus && (
                  <div style={{ marginTop: 14 }}>
                    <ProgressBar value={smsProgress} intent="success" animate stripes style={{ height: 6, borderRadius: 4, marginBottom: 5 }} />
                    <div style={{ fontSize: 11, color: "#5f6b7c", display: "flex", justifyContent: "space-between" }}>
                      <span>{fmt(smsStatus!.run_sent)} / {fmt(smsStatus!.total)} sent</span>
                      {smsStatus!.elapsed_seconds != null && <span>{smsStatus!.elapsed_seconds}s</span>}
                    </div>
                  </div>
                )}
              </div>

              {/* SMS errors */}
              {smsErr && <Callout intent="danger" icon="warning-sign" style={{ marginBottom: 10 }}>{smsErr}</Callout>}

              {/* SMS stats after run */}
              {smsHasStatus && smsStatus && (
                <>
                  <BigStatRow stats={[
                    { label: "This Batch",    value: smsStatus.total,                color: "#abb3bf", sub: "processed" },
                    { label: smsLastMode === "send" ? "Sent This Run" : "Generated", value: smsLastMode === "send" ? (smsStatus.run_sent ?? 0) : (smsStatus.run_generated ?? 0), color: "#8b5cf6" },
                    { label: "Sent All-Time", value: smsStatus.db_sent ?? 0,         color: "#1D9E75" },
                    { label: "Ready to Send", value: smsStatus.db_generated ?? 0,    color: "#738091" },
                    { label: "Failed",        value: smsStatus.run_failed ?? 0,      color: smsStatus.run_failed ? "#e63946" : "#383e47" },
                    ...((smsStatus.tcpa_deferred ?? 0) > 0
                      ? [{ label: "TCPA Deferred", value: smsStatus.tcpa_deferred!, color: "#f0b429", sub: "outside send window" }]
                      : []),
                    ...(smsStatus.cost_usd != null
                      ? [{ label: "SMS Cost", value: `$${smsStatus.cost_usd.toFixed(3)}`, color: "#abb3bf" }]
                      : []),
                  ]} />
                  {(smsStatus.tcpa_deferred ?? 0) > 0 && (
                    <div style={{
                      display: "flex", alignItems: "center", gap: 8,
                      background: "#1a1a0f", border: "1px solid #f0b42940",
                      borderRadius: 7, padding: "7px 11px", marginBottom: 10,
                      fontSize: 11, color: "#f0b429",
                    }}>
                      <span style={{ fontSize: 14 }}>⏰</span>
                      <span>
                        <strong>{smsStatus.tcpa_deferred}</strong> message{smsStatus.tcpa_deferred !== 1 ? "s" : ""} held
                        back — recipient local time is outside the 8 AM–9 PM TCPA window.
                        They remain <em>ready</em> and will send on the next pipeline run
                        when the window opens.
                      </span>
                    </div>
                  )}

                  {!smsIsRunning && smsStatus.total > 0 && (
                    <Callout
                      intent={smsStatus.run_failed ? "warning" : smsLastMode === "send" ? "success" : "primary"}
                      icon={smsStatus.run_failed ? "warning-sign" : "tick"}
                      style={{ marginBottom: 10, fontSize: 12 }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                        <span>
                          {smsLastMode === "send"
                            ? `${fmt(smsStatus.run_sent ?? 0)} SMS sent via Twilio this run. ${fmt(smsStatus.db_sent ?? 0)} sent all-time.`
                            : `Generation complete — ${fmt(smsStatus.run_generated ?? 0)} messages ready. Click "Send via Twilio" when ready.`
                          }
                        </span>
                        {(smsStatus.run_failed ?? 0) > 0 && (
                          <Button
                            small
                            intent="warning"
                            icon="refresh"
                            onClick={async () => {
                              try {
                                const r = await fetch("/api/sms/reset-failed", { method: "POST" });
                                const d = await r.json();
                                alert(`Reset ${d.reset} failed lead(s) to pending. Re-run Generate to retry them.`);
                              } catch {
                                alert("Reset failed — check server logs.");
                              }
                            }}
                          >
                            Reset {smsStatus.run_failed} Failed
                          </Button>
                        )}
                      </div>
                    </Callout>
                  )}

                  <ActivityFeed
                    items={(smsStatus.recent_activity ?? []).map((a) => ({
                      email:   a.phone,
                      name:    a.name,
                      company: a.company,
                      status:  a.status === "sms_sent" ? "sent" : a.status === "sms_ready" ? "dry_run" : "failed",
                      time:    a.time,
                      error:   a.error ?? "",
                    }))}
                    running={smsIsRunning}
                  />
                </>
              )}
            </div>
          </div>{/* end channel-panel */}
        </div>{/* end SMS col */}

      </div>{/* end two-column container */}
    </div>
  );
}
