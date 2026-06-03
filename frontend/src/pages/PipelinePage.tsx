/**
 * PipelinePage — two-phase launch flow
 *
 * Phase 1 · Personalize
 *   Enriches each lead, scores intent, generates a personalised email and
 *   (for high-intent leads) a 55-second personalised video.  Nothing is sent.
 *   Runs the pipeline with dry_run=true so all assets are cached in the
 *   ledger and can be pushed instantly in Phase 2.
 *
 * Phase 2 · Push to Smartlead
 *   Reads the cached assets (email + video) from the ledger and sends each
 *   lead to their assigned Smartlead campaign.  No re-generation needed —
 *   the pipeline skips completed stages, so this phase is fast (API calls only).
 */
import { useEffect, useRef, useState, useCallback } from "react";
import {
  Card,
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
} from "../api/client";
import type {
  PipelineStatus,
  UploadResponse,
  PreviewResponse,
  ReadinessResponse,
  ActivityItem,
  CampaignCheckResult,
  CsvUpload,
} from "../api/types";

// ─── helpers ─────────────────────────────────────────────────────────────────

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
  dry_run: "✓",   // personalised successfully (dry run)
  skipped: "—",
  failed:  "✗",
};

// ─── sub-components ───────────────────────────────────────────────────────────

function ActivityFeed({ items, running }: { items: ActivityItem[]; running: boolean }) {
  if (items.length === 0) return null;
  return (
    <div
      style={{
        background:   "#1c2127",
        border:       "1px solid #2f363e",
        borderRadius: 10,
        overflow:     "hidden",
        marginTop:    16,
      }}
    >
      <div
        style={{
          padding:      "9px 14px",
          background:   "#252a31",
          borderBottom: "1px solid #2f363e",
          display:      "flex",
          alignItems:   "center",
          gap:          8,
        }}
      >
        {running && <Spinner size={12} />}
        <span style={{ fontSize: 12, fontWeight: 600, color: "#abb3bf" }}>
          Live Feed
        </span>
        <span style={{ fontSize: 11, color: "#5f6b7c", marginLeft: "auto" }}>
          last {items.length} · newest first
        </span>
      </div>
      <div style={{ maxHeight: 320, overflowY: "auto" }}>
        {items.map((item, i) => {
          const color = STATUS_COLOR[item.status] ?? "#738091";
          const glyph = STATUS_GLYPH[item.status] ?? "?";
          return (
            <div
              key={`${item.email}-${i}`}
              style={{
                display:      "flex",
                alignItems:   "center",
                gap:          10,
                padding:      "7px 14px",
                borderBottom: "1px solid #222830",
                animation:    "feedIn 0.2s ease",
              }}
            >
              <span style={{ width: 14, textAlign: "center", fontWeight: 700, color, fontSize: 13 }}>
                {glyph}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <span style={{ color: "#f6f7f9", fontSize: 13 }}>
                  {item.name || item.email}
                </span>
                {item.company && (
                  <span style={{ color: "#5f6b7c", fontSize: 12, marginLeft: 5 }}>
                    @ {item.company}
                  </span>
                )}
                {item.status === "failed" && item.error && (
                  <div style={{ color: "#e63946", fontSize: 11, marginTop: 1 }}>
                    {item.error.slice(0, 90)}
                  </div>
                )}
              </div>
              <span style={{ color: "#5f6b7c", fontSize: 11, flexShrink: 0 }}>{item.time}</span>
              <span
                style={{
                  fontSize: 10, fontWeight: 600, color,
                  background: color + "22",
                  padding: "2px 6px", borderRadius: 4,
                  textTransform: "uppercase", flexShrink: 0,
                }}
              >
                {item.status === "dry_run" ? "personalised" : item.status.replace("_", " ")}
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
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
      {stats.map((s) => (
        <div
          key={s.label}
          style={{
            flex: "1 1 90px",
            background: "#1c2127",
            border: "1px solid #2f363e",
            borderRadius: 8,
            padding: "12px 14px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 26, fontWeight: 700, color: s.color ?? "#f6f7f9", lineHeight: 1 }}>
            {typeof s.value === "number" ? fmt(s.value) : s.value}
          </div>
          <div style={{ fontSize: 10, color: "#5f6b7c", marginTop: 4 }}>{s.label}</div>
          {s.sub && <div style={{ fontSize: 9, color: "#383e47", marginTop: 2 }}>{s.sub}</div>}
        </div>
      ))}
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

  // ── preview (new vs duplicate)
  const [preview,    setPreview]    = useState<PreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [showDups,   setShowDups]   = useState(false);

  // ── readiness (how many personalised & ready to push)
  const [readiness,        setReadiness]        = useState<ReadinessResponse | null>(null);
  const [loadingReadiness, setLoadingReadiness] = useState(false);

  // ── campaign validation (Smartlead campaign health check)
  const [campaignCheck,     setCampaignCheck]     = useState<CampaignCheckResult | null>(null);
  const [campaignChecking,  setCampaignChecking]  = useState(false);
  // true = check ran and threw a network error (show neutral msg, don't block push)
  const [campaignFetchFailed, setCampaignFetchFailed] = useState(false);

  // ── run state
  const [lastMode,   setLastMode]   = useState<RunMode | null>(null);
  const [starting,   setStarting]   = useState(false);
  const [stopping,   setStopping]   = useState(false);
  const [runErr,     setRunErr]     = useState<string | null>(null);
  const [batchSize,  setBatchSize]  = useState<number>(100);

  // ── live pipeline status (polled every 2 s)
  const [status, setStatus] = useState<PipelineStatus | null>(null);

  // ── polling ──────────────────────────────────────────────────────────────
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

  // ── restore last CSV from localStorage on mount
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
  }, []); // runs once on mount

  const runCampaignCheck = useCallback(async () => {
    setCampaignChecking(true);
    setCampaignFetchFailed(false);
    try {
      const result = await checkCampaign();
      setCampaignCheck(result);
    } catch {
      // Network error — flag it so the UI can show a neutral message
      // without blocking the push button
      setCampaignCheck(null);
      setCampaignFetchFailed(true);
    } finally {
      setCampaignChecking(false);
    }
  }, []);

  const pollStatus = useCallback(async () => {
    try { setStatus(await fetchPipelineStatus()); }
    catch { /* ignore */ }
  }, []);

  useEffect(() => {
    pollStatus();
    refreshReadiness();
    runCampaignCheck();
    const id = setInterval(async () => {
      await pollStatus();
    }, 2000);
    return () => clearInterval(id);
  }, [pollStatus, refreshReadiness, runCampaignCheck]);

  // Refresh readiness + campaign check once the pipeline finishes
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && status && !status.running) {
      refreshReadiness();
      runCampaignCheck();
    }
    wasRunning.current = status?.running ?? false;
  }, [status, refreshReadiness, runCampaignCheck]);

  // ── upload ───────────────────────────────────────────────────────────────
  async function handleFile(file: File) {
    if (!file.name.endsWith(".csv")) {
      setUploadErr("Only .csv files are accepted.");
      return;
    }
    setUploading(true);
    setUploadErr(null);
    setPreview(null);
    try {
      const result = await uploadCsv(file);
      setUpload(result);
      localStorage.setItem("aap_last_csv", JSON.stringify(result));
      refreshHistory();
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
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }
  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
    e.target.value = "";
  }

  // ── launch helpers ───────────────────────────────────────────────────────
  async function launch(mode: RunMode) {
    if (!upload) return;
    setStarting(true);
    setRunErr(null);
    setLastMode(mode);
    try {
      await startPipeline({
        csv_path:   upload.csv_path,
        dry_run:    mode === "personalize",
        batch_size: mode === "personalize" ? batchSize : undefined,
      });
      await pollStatus();
    } catch (e: unknown) {
      setRunErr(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  }

  async function handleStop() {
    setStopping(true);
    try { await stopPipeline(); await pollStatus(); }
    finally { setStopping(false); }
  }

  // ── derived ──────────────────────────────────────────────────────────────
  const isRunning   = status?.running ?? false;
  const hasStatus   = (status?.total ?? 0) > 0;
  const progress    = hasStatus ? (status!.processed / status!.total) : 0;
  const newCount    = preview?.new_count       ?? 0;
  const dupCount    = preview?.duplicate_count ?? 0;
  const readyToPush = readiness?.ready_to_push ?? 0;
  const activity    = status?.recent_activity  ?? [];

  // Campaign check blocks push only when we have a definitive "not ok" result.
  // If the check hasn't run yet (null) or had a network error (null), we don't block.
  const campaignBlocked = campaignCheck !== null && !campaignCheck.ok;

  // What is running right now?
  const phaseLabel = isRunning
    ? lastMode === "personalize" ? "Personalising leads…" : "Pushing to Smartlead…"
    : null;

  return (
    <div style={{ maxWidth: 900 }}>
      <style>{`
        @keyframes feedIn {
          from { opacity:0; transform:translateY(-5px) }
          to   { opacity:1; transform:translateY(0) }
        }
        .drop-zone {
          border:2px dashed #383e47; border-radius:12px; padding:32px 24px;
          text-align:center; cursor:pointer;
          transition:border-color .15s, background .15s;
          margin-bottom:20px; background:#1c2127;
        }
        .drop-zone:hover, .drop-zone.drag-over { border-color:#4c90f0; background:#1a2335; }
        .drop-zone.has-file { border-color:#1D9E75; border-style:solid; }
      `}</style>

      <h1 className="page-title" style={{ marginBottom: 4 }}>Pipeline</h1>
      <p style={{ color: "#5f6b7c", fontSize: 13, marginBottom: 24, lineHeight: 1.6 }}>
        Two steps: <strong style={{ color: "#abb3bf" }}>Personalise</strong> — enrich every lead,
        score intent, write the email, record the video.
        Then <strong style={{ color: "#abb3bf" }}>Push</strong> — send the finished assets to
        Smartlead and go live.
      </p>

      {/* ══ UPLOAD ══════════════════════════════════════════════════════════ */}
      <div
        className={`drop-zone${dragOver ? " drag-over" : ""}${upload ? " has-file" : ""}`}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        {uploading ? (
          <><Spinner size={28} style={{ marginBottom: 8 }} />
            <div style={{ color: "#738091", fontSize: 13 }}>Uploading…</div></>
        ) : upload ? (
          <><div style={{ fontSize: 30, marginBottom: 6 }}>📄</div>
            <div style={{ fontWeight: 600, color: "#f6f7f9", fontSize: 15 }}>{upload.filename}</div>
            <div style={{ fontSize: 12, color: "#738091", marginTop: 4 }}>
              {fmt(upload.lead_count)} total · {fmt(upload.new_leads ?? 0)} new · {fmt(upload.duplicate_leads ?? 0)} already processed · click to replace
            </div></>
        ) : (
          <><div style={{ fontSize: 36, marginBottom: 8 }}>📂</div>
            <div style={{ fontWeight: 600, color: "#f6f7f9", marginBottom: 4 }}>
              Drop your leads CSV here
            </div>
            <div style={{ fontSize: 12, color: "#5f6b7c" }}>
              or click to browse · Native format or Apollo / Clay skiptrace
            </div></>
        )}
      </div>
      <input ref={fileRef} type="file" accept=".csv"
        style={{ display: "none" }} onChange={handleInputChange} />

      {uploadErr && (
        <Callout intent="danger" icon="warning-sign" style={{ marginBottom: 16 }}>
          {uploadErr}
        </Callout>
      )}

      {/* ── CSV Upload History ── */}
      {csvHistory.length > 0 && (
        <div style={{ marginTop: 20, marginBottom: 4 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#738091", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>
            CSV Upload History
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {csvHistory.map((u) => (
              <div
                key={u.id}
                style={{
                  background: upload?.csv_path === u.csv_path ? "#1c2e40" : "#1a2433",
                  border: upload?.csv_path === u.csv_path ? "1px solid #1D6FA4" : "1px solid #253545",
                  borderRadius: 6,
                  padding: "8px 12px",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  cursor: "pointer",
                }}
                onClick={() => {
                  const restored = { filename: u.filename, csv_path: u.csv_path, lead_count: u.lead_count, new_leads: u.new_leads, duplicate_leads: u.duplicate_leads };
                  setUpload(restored);
                  localStorage.setItem("aap_last_csv", JSON.stringify(restored));
                  previewCsv(u.csv_path).then(setPreview).catch(() => {});
                }}
              >
                <span style={{ fontSize: 16 }}>📄</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: "#f6f7f9", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {u.filename}
                  </div>
                  <div style={{ fontSize: 11, color: "#5f6b7c", marginTop: 1 }}>
                    {u.lead_count.toLocaleString()} total · <span style={{ color: "#3ddc84" }}>{u.new_leads.toLocaleString()} new</span> · {u.duplicate_leads.toLocaleString()} already processed · {new Date(u.uploaded_at).toLocaleDateString()}
                  </div>
                </div>
                {upload?.csv_path === u.csv_path && (
                  <span style={{ fontSize: 10, color: "#1D6FA4", fontWeight: 600 }}>ACTIVE</span>
                )}
              </div>
            ))}
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: "#738091" }}>
            <span style={{ color: "#3ddc84", fontWeight: 600 }}>{totalNewLeads.toLocaleString()}</span> unique new leads across all uploads
          </div>
        </div>
      )}

      {/* ── Duplicate preview ── */}
      {(previewing || preview) && (
        <Card style={{
          background: "#252a31", border: "1px solid #383e47",
          borderRadius: 10, marginBottom: 20, padding: "14px 18px",
        }}>
          {previewing
            ? <div style={{ display:"flex", alignItems:"center", gap:10,
                            color:"#738091", fontSize:13 }}>
                <Spinner size={14} /> Scanning for duplicates…
              </div>
            : preview && <>
                <div style={{ display:"flex", gap:24, alignItems:"center", flexWrap:"wrap" }}>
                  <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                    <span style={{ fontSize:22, fontWeight:700,
                      color: newCount > 0 ? "#1D9E75" : "#738091" }}>
                      {fmt(newCount)}
                    </span>
                    <div>
                      <div style={{ fontSize:12, color:"#abb3bf" }}>new leads</div>
                      <div style={{ fontSize:10, color:"#5f6b7c" }}>will be processed</div>
                    </div>
                  </div>

                  <Divider style={{ margin:"0 4px" }} />

                  <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                    <span style={{ fontSize:22, fontWeight:700,
                      color: dupCount > 0 ? "#f0b429" : "#383e47" }}>
                      {fmt(dupCount)}
                    </span>
                    <div>
                      <div style={{ fontSize:12, color:"#abb3bf" }}>duplicates</div>
                      <div style={{ fontSize:10, color:"#5f6b7c" }}>already sent · auto-skipped</div>
                    </div>
                    {dupCount > 0 && (
                      <Button minimal small
                        icon={showDups ? "chevron-up" : "chevron-down"}
                        style={{ color:"#5f6b7c" }}
                        onClick={() => setShowDups(v => !v)} />
                    )}
                  </div>

                  {newCount === 0 && (
                    <Callout intent="warning" icon="warning-sign"
                      style={{ marginLeft:"auto", padding:"6px 12px", fontSize:12 }}>
                      All leads already sent — nothing to do.
                    </Callout>
                  )}
                </div>

                {showDups && dupCount > 0 && (
                  <div style={{ marginTop:12, maxHeight:160, overflowY:"auto" }}>
                    <table style={{ width:"100%", fontSize:12, borderCollapse:"collapse" }}>
                      <thead>
                        <tr style={{ color:"#5f6b7c" }}>
                          {["Name","Company","Email","Status"].map(h => (
                            <th key={h} style={{ textAlign:"left", padding:"3px 8px",
                              borderBottom:"1px solid #2f363e" }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.duplicate_leads.slice(0,50).map(l => (
                          <tr key={l.lead_id}>
                            <td style={{ padding:"3px 8px", color:"#abb3bf" }}>
                              {l.first_name} {l.last_name}
                            </td>
                            <td style={{ padding:"3px 8px", color:"#738091" }}>{l.company}</td>
                            <td style={{ padding:"3px 8px", color:"#738091" }}>{l.email}</td>
                            <td style={{ padding:"3px 8px" }}>
                              <span style={{ color:"#1D9E75", fontSize:11 }}>
                                ✓ {l.existing_status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {dupCount > 50 && (
                      <div style={{ color:"#5f6b7c", fontSize:11, padding:"5px 8px" }}>
                        …and {dupCount - 50} more
                      </div>
                    )}
                  </div>
                )}
              </>
          }
        </Card>
      )}

      {/* ══ PHASE 1 — PERSONALISE ═══════════════════════════════════════════ */}
      <Card style={{
        background:   "#1e2329",
        border:       `2px solid ${isRunning && lastMode === "personalize" ? "#4c90f0" : "#2f3640"}`,
        borderRadius: 12,
        marginBottom: 16,
        padding:      "22px 24px",
      }}>
        <div style={{ display:"flex", alignItems:"flex-start", gap:16 }}>
          {/* Step number */}
          <div style={{
            width:36, height:36, borderRadius:"50%", flexShrink:0,
            background: readyToPush > 0 ? "#1D9E75" : "#2f363e",
            display:"flex", alignItems:"center", justifyContent:"center",
            fontSize:15, fontWeight:700,
            color: readyToPush > 0 ? "#fff" : "#5f6b7c",
          }}>
            {readyToPush > 0 ? "✓" : "1"}
          </div>

          <div style={{ flex:1 }}>
            <div style={{ fontWeight:700, color:"#f6f7f9", fontSize:15, marginBottom:4 }}>
              Personalise Leads
            </div>
            <div style={{ fontSize:12, color:"#738091", marginBottom:14, lineHeight:1.6 }}>
              Enriches each lead's website, scores intent with AI, writes a personalised
              email, and records a personalised video for high-intent leads
              (intent ≥ 0.65). Nothing is sent yet — assets are saved and ready to review.
            </div>

            {/* Batch size control */}
            {!isRunning && (
              <div style={{
                display: "flex", alignItems: "center", gap: 10,
                marginBottom: 14,
                background: "#161b22", border: "1px solid #2f363e",
                borderRadius: 8, padding: "10px 14px",
                width: "fit-content",
              }}>
                <span style={{ fontSize: 12, color: "#738091", whiteSpace: "nowrap" }}>
                  Leads to personalise per run:
                </span>
                <input
                  type="number"
                  min={1}
                  max={upload?.lead_count ?? 9999}
                  value={batchSize}
                  onChange={e => {
                    const v = Math.max(1, parseInt(e.target.value) || 1);
                    setBatchSize(v);
                  }}
                  style={{
                    width: 80, padding: "4px 8px",
                    background: "#252a31", border: "1px solid #383e47",
                    borderRadius: 6, color: "#f6f7f9", fontSize: 14,
                    fontWeight: 600, textAlign: "center",
                    outline: "none",
                  }}
                />
                {upload && (
                  <div style={{ display: "flex", gap: 6 }}>
                    {[25, 50, 100, 250].filter(n => n <= (upload?.lead_count ?? 9999)).map(n => (
                      <button
                        key={n}
                        onClick={() => setBatchSize(n)}
                        style={{
                          padding: "3px 8px", borderRadius: 5, fontSize: 11,
                          border: "1px solid " + (batchSize === n ? "#4c90f0" : "#2f363e"),
                          background: batchSize === n ? "#1a2a4a" : "transparent",
                          color: batchSize === n ? "#4c90f0" : "#5f6b7c",
                          cursor: "pointer",
                        }}
                      >{n}</button>
                    ))}
                    {upload && (
                      <button
                        onClick={() => setBatchSize(upload.lead_count)}
                        style={{
                          padding: "3px 8px", borderRadius: 5, fontSize: 11,
                          border: "1px solid " + (batchSize === upload.lead_count ? "#4c90f0" : "#2f363e"),
                          background: batchSize === upload.lead_count ? "#1a2a4a" : "transparent",
                          color: batchSize === upload.lead_count ? "#4c90f0" : "#5f6b7c",
                          cursor: "pointer",
                        }}
                      >All {fmt(upload.lead_count)}</button>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* CTA row */}
            <div style={{ display:"flex", gap:10, alignItems:"center", flexWrap:"wrap" }}>
              {isRunning && lastMode === "personalize" ? (
                <Button intent="danger" icon="stop" large loading={stopping}
                  onClick={handleStop}>
                  Stop Personalising
                </Button>
              ) : (
                <Tooltip
                  content={!upload ? "Upload a CSV first" : newCount === 0 ? "No new leads to personalise" : undefined}
                  disabled={!!upload && newCount > 0}
                >
                  <Button
                    intent="primary" icon="generate" large
                    loading={starting && lastMode === "personalize"}
                    disabled={!upload || newCount === 0 || (isRunning && lastMode !== "personalize")}
                    onClick={() => launch("personalize")}
                    style={{ minWidth: 220 }}
                  >
                    {readyToPush > 0
                      ? `Re-personalise ${fmt(Math.min(batchSize, newCount))} leads`
                      : `✨  Personalise ${upload ? fmt(Math.min(batchSize, newCount)) : ""} leads`}
                  </Button>
                </Tooltip>
              )}
              {isRunning && lastMode === "personalize" && (
                <span style={{ fontSize:12, color:"#4c90f0" }}>
                  {phaseLabel} (batch of {fmt(batchSize)})
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Progress (personalise phase) */}
        {isRunning && lastMode === "personalize" && hasStatus && (
          <div style={{ marginTop:16 }}>
            <ProgressBar value={progress} intent="primary" animate stripes
              style={{ height:7, borderRadius:4, marginBottom:6 }} />
            <div style={{ fontSize:11, color:"#5f6b7c", display:"flex", justifyContent:"space-between" }}>
              <span>{fmt(status!.processed)} / {fmt(status!.total - (status!.duplicate_count ?? 0))} personalised</span>
              {status!.elapsed_seconds != null && <span>{status!.elapsed_seconds}s</span>}
            </div>
          </div>
        )}
      </Card>

      {/* ══ PHASE 2 — PUSH ══════════════════════════════════════════════════ */}
      <Card style={{
        background:   "#1e2329",
        border:       `2px solid ${isRunning && lastMode === "push" ? "#1D9E75" : readyToPush > 0 ? "#2a4a3a" : "#2f3640"}`,
        borderRadius: 12,
        marginBottom: 24,
        padding:      "22px 24px",
        opacity:      readyToPush === 0 && !isRunning ? 0.6 : 1,
        transition:   "opacity .2s, border-color .2s",
      }}>
        <div style={{ display:"flex", alignItems:"flex-start", gap:16 }}>
          {/* Step number */}
          <div style={{
            width:36, height:36, borderRadius:"50%", flexShrink:0,
            background: (status?.sent ?? 0) > 0 ? "#1D9E75" : readyToPush > 0 ? "#2a4a3a" : "#2f363e",
            display:"flex", alignItems:"center", justifyContent:"center",
            fontSize:15, fontWeight:700,
            color: readyToPush > 0 || (status?.sent ?? 0) > 0 ? "#1D9E75" : "#5f6b7c",
            border: readyToPush > 0 ? "2px solid #1D9E75" : "2px solid transparent",
          }}>
            {(status?.sent ?? 0) > 0 ? "✓" : "2"}
          </div>

          <div style={{ flex:1 }}>
            <div style={{ fontWeight:700, color:"#f6f7f9", fontSize:15, marginBottom:4 }}>
              Push to Smartlead
            </div>
            <div style={{ fontSize:12, color:"#738091", marginBottom:14, lineHeight:1.6 }}>
              Sends the personalised emails + video links to the right Smartlead campaign
              for each lead. Stages are cached — this is fast (no re-generation).
            </div>

            {/* Readiness summary */}
            {readyToPush > 0 && (
              <div style={{
                display:"flex", gap:16, flexWrap:"wrap",
                background:"#1a2218", border:"1px solid #2a4a3a",
                borderRadius:8, padding:"10px 14px", marginBottom:8,
              }}>
                <div>
                  <span style={{ fontSize:13, color:"#1D9E75", fontWeight:600 }}>
                    {fmt(readyToPush)} leads ready to push
                  </span>
                  <div style={{ fontSize:10, color:"#5f6b7c", marginTop:2 }}>
                    personalised &amp; awaiting Smartlead — not yet sent
                  </div>
                </div>
                <Divider style={{ margin:"0 4px" }} />
                {(readiness?.video_count ?? 0) > 0 && (
                  <span style={{ fontSize:12, color:"#abb3bf" }}>
                    🎥 {fmt(readiness!.video_count)} with personalised video
                  </span>
                )}
                {(readiness?.email_only_count ?? 0) > 0 && (
                  <span style={{ fontSize:12, color:"#abb3bf" }}>
                    📧 {fmt(readiness!.email_only_count)} email-only
                  </span>
                )}
                {loadingReadiness && <Spinner size={12} />}
              </div>
            )}
            {/* Explain the split between ready-to-push and all-time total */}
            {(readiness?.all_personalised ?? 0) > readyToPush && readyToPush > 0 && (
              <div style={{
                fontSize:11, color:"#5f6b7c",
                background:"#161b22", border:"1px solid #2f363e",
                borderRadius:6, padding:"6px 10px", marginBottom:14,
              }}>
                <strong style={{ color:"#738091" }}>Why is this lower than your all-time total?</strong>
                {" "}
                {fmt(readiness!.all_personalised)} personalised all-time
                — {fmt((readiness?.already_sent ?? 0))} already pushed to Smartlead
                = {fmt(readyToPush)} in queue now.
              </div>
            )}
            {(readiness?.all_personalised ?? 0) > readyToPush && readyToPush === 0 && (readiness?.already_sent ?? 0) > 0 && (
              <div style={{
                fontSize:11, color:"#5f6b7c",
                background:"#161b22", border:"1px solid #2f363e",
                borderRadius:6, padding:"6px 10px", marginBottom:14,
              }}>
                All {fmt(readiness!.all_personalised)} personalised leads have already been pushed to Smartlead.
              </div>
            )}

            {/* Campaign validation banner */}
            {campaignChecking ? (
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                marginBottom: 12, fontSize: 12, color: "#738091",
              }}>
                <Spinner size={12} />
                Checking Smartlead campaign…
              </div>
            ) : campaignFetchFailed ? (
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                marginBottom: 12,
                background: "#252a31", border: "1px solid #383e47",
                borderRadius: 6, padding: "8px 12px",
                fontSize: 12, color: "#738091",
              }}>
                <span>Could not verify campaign — proceeding anyway</span>
                <Button minimal small icon="refresh" style={{ color: "#5f6b7c", marginLeft: "auto" }}
                  onClick={runCampaignCheck}>
                  Re-check
                </Button>
              </div>
            ) : campaignCheck?.ok ? (
              <div style={{
                display: "flex", alignItems: "center", gap: 8,
                marginBottom: 12,
                background: "#1a2218", border: "1px solid #2a4a3a",
                borderRadius: 6, padding: "8px 12px",
                fontSize: 12, color: "#1D9E75",
              }}>
                <span style={{ fontWeight: 600 }}>✓</span>
                <span>
                  Campaign ready — &ldquo;{campaignCheck.name}&rdquo; is ACTIVE with correct Step 1 variables
                </span>
                <Button minimal small icon="refresh" style={{ color: "#5f6b7c", marginLeft: "auto" }}
                  onClick={runCampaignCheck}>
                  Re-check
                </Button>
              </div>
            ) : campaignCheck !== null ? (
              <div style={{ marginBottom: 12 }}>
                <Callout intent="danger" icon="warning-sign" style={{ padding: "10px 14px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 13 }}>
                        Campaign not ready — fix these issues before pushing:
                      </div>
                      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
                        {campaignCheck.issues.map((issue, i) => (
                          <li key={i} style={{ marginBottom: 3 }}>{issue}</li>
                        ))}
                      </ul>
                    </div>
                    <Button minimal small icon="refresh" style={{ flexShrink: 0, marginLeft: 12 }}
                      onClick={runCampaignCheck}>
                      Re-check
                    </Button>
                  </div>
                </Callout>
              </div>
            ) : null}

            {/* CTA row */}
            <div style={{ display:"flex", gap:10, alignItems:"center", flexWrap:"wrap" }}>
              {isRunning && lastMode === "push" ? (
                <Button intent="danger" icon="stop" large loading={stopping}
                  onClick={handleStop}>
                  Stop Push
                </Button>
              ) : (
                <Tooltip
                  content={
                    readyToPush === 0
                      ? "Complete Phase 1 first — no personalised leads yet"
                      : campaignBlocked
                      ? "Fix the campaign issues above before pushing"
                      : undefined
                  }
                  disabled={readyToPush > 0 && !campaignBlocked}
                >
                  <Button
                    intent="success" icon="send-to" large
                    loading={starting && lastMode === "push"}
                    disabled={readyToPush === 0 || campaignBlocked || (isRunning && lastMode !== "push")}
                    onClick={() => launch("push")}
                    style={{ minWidth: 260 }}
                  >
                    🚀&nbsp; Push {fmt(readyToPush)} leads to Smartlead
                  </Button>
                </Tooltip>
              )}
              {isRunning && lastMode === "push" && (
                <span style={{ fontSize:12, color:"#1D9E75" }}>
                  Sending to Smartlead…
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Progress (push phase) */}
        {isRunning && lastMode === "push" && hasStatus && (
          <div style={{ marginTop:16 }}>
            <ProgressBar value={progress} intent="success" animate stripes
              style={{ height:7, borderRadius:4, marginBottom:6 }} />
            <div style={{ fontSize:11, color:"#5f6b7c", display:"flex", justifyContent:"space-between" }}>
              <span>{fmt(status!.sent)} sent to Smartlead</span>
              {status!.elapsed_seconds != null && <span>{status!.elapsed_seconds}s</span>}
            </div>
          </div>
        )}
      </Card>

      {runErr && (
        <Callout intent="danger" icon="warning-sign" style={{ marginBottom:16 }}>
          {runErr}
        </Callout>
      )}

      {/* ══ RUN STATS ════════════════════════════════════════════════════════ */}
      {hasStatus && status && (
        <>
          {/* All-time progress bar against the full CSV */}
          {(() => {
            const csvTotal   = status.csv_total ?? upload?.lead_count ?? 0;
            const allDone    = readiness?.all_personalised ?? 0;
            const allSkipped = readiness?.all_skipped      ?? 0;
            const allFailed  = readiness?.all_failed       ?? 0;
            const allTouched = allDone + allSkipped + allFailed;
            const pct        = csvTotal > 0 ? Math.min(1, allTouched / csvTotal) : 0;
            if (csvTotal === 0) return null;
            return (
              <div style={{
                background:"#1c2127", border:"1px solid #2f363e",
                borderRadius:10, padding:"14px 18px", marginBottom:16,
              }}>
                <div style={{ display:"flex", justifyContent:"space-between",
                              alignItems:"center", marginBottom:8 }}>
                  <span style={{ fontSize:12, fontWeight:600, color:"#abb3bf" }}>
                    Overall Progress
                  </span>
                  <span style={{ fontSize:12, color:"#5f6b7c" }}>
                    {fmt(allTouched)} of {fmt(csvTotal)} leads processed
                  </span>
                </div>
                <ProgressBar value={pct} intent="primary"
                  style={{ height:8, borderRadius:4, marginBottom:10 }} />
                <div style={{ display:"flex", gap:20, flexWrap:"wrap" }}>
                  <Tooltip
                    content="All-time total personalised — includes leads already pushed to Smartlead"
                    placement="top"
                  >
                    <span style={{ fontSize:12, color:"#4c90f0", cursor:"default" }}>
                      ✓ {fmt(allDone)} personalised all-time
                    </span>
                  </Tooltip>
                  <span style={{ fontSize:12, color:"#738091" }}>
                    — {fmt(allSkipped)} skipped (not a fit)
                  </span>
                  <span style={{ fontSize:12, color: allFailed > 0 ? "#e63946" : "#383e47" }}>
                    ✗ {fmt(allFailed)} failed
                  </span>
                  <span style={{ fontSize:12, color:"#5f6b7c", marginLeft:"auto" }}>
                    {fmt(csvTotal - allTouched)} remaining
                  </span>
                </div>
              </div>
            );
          })()}

          <BigStatRow stats={[
            { label:"THIS BATCH",               value:status.total,
              color:"#abb3bf", sub:"leads in current run" },
            { label:"PERSONALISED THIS BATCH",  value:status.processed,
              color:"#4c90f0",
              sub: lastMode === "push" ? "sent to Smartlead this run" : "awaiting push to Smartlead" },
            { label:"SENT TO SMARTLEAD",        value: lastMode === "push" ? status.sent : (readiness?.already_sent ?? 0),
              color:"#1D9E75", sub:"all-time across all runs" },
            { label:"DUPLICATES SKIPPED",       value:status.duplicate_count,
              color:"#f0b429" },
            { label:"SKIPPED (NOT A FIT)",      value:status.skipped,
              color:"#738091" },
            { label:"FAILED",                   value:status.failed,
              color: status.failed > 0 ? "#e63946" : "#383e47" },
            ...(status.cost_usd != null
              ? [{ label:"COST", value:`$${status.cost_usd.toFixed(3)}`, color:"#abb3bf" }]
              : []),
          ]} />

          {/* Completion callout */}
          {!isRunning && status.total > 0 && (
            <Callout
              intent={status.failed > 0 ? "warning" : lastMode === "push" ? "success" : "primary"}
              icon={status.failed > 0 ? "warning-sign" : lastMode === "push" ? "tick-circle" : "tick"}
              style={{ marginBottom:16 }}
            >
              {lastMode === "push"
                ? status.failed > 0
                  ? `Push finished with ${status.failed} failure${status.failed !== 1 ? "s" : ""}. ${status.sent} sent to Smartlead.`
                  : `All ${status.sent} leads sent to Smartlead. Campaign is live.`
                : status.failed > 0
                  ? `Personalisation finished with ${status.failed} failure${status.failed !== 1 ? "s" : ""}. ${readyToPush} leads ready to push.`
                  : `Personalisation complete — ${readyToPush} leads ready. Click "Push to Smartlead" when ready.`
              }
            </Callout>
          )}

          <ActivityFeed items={activity} running={isRunning} />
        </>
      )}

      {/* ── empty state ── */}
      {!hasStatus && !isRunning && !upload && (
        <div style={{ textAlign:"center", padding:"56px 24px", color:"#383e47" }}>
          <div style={{ fontSize:52, marginBottom:12 }}>✨</div>
          <div style={{ fontSize:14, color:"#5f6b7c" }}>
            Upload a CSV above to begin.
          </div>
        </div>
      )}
    </div>
  );
}
