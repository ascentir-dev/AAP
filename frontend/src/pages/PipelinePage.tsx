import { useEffect, useRef, useState, useCallback } from "react";
import {
  Card,
  Button,
  Switch,
  ProgressBar,
  Callout,
  Tag,
  Spinner,
  HTMLTable,
  FormGroup,
  NumericInput,
  Divider,
  Intent,
} from "@blueprintjs/core";
import { uploadCsv, startPipeline, stopPipeline, fetchPipelineStatus } from "../api/client";
import type { PipelineStatus, UploadResponse } from "../api/types";

function fmt(n: number) {
  return n.toLocaleString();
}

export function PipelinePage() {
  const [upload, setUpload] = useState<UploadResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [dryRun, setDryRun] = useState(true);
  const [singleLead, setSingleLead] = useState<number | null>(null);
  const [useSingle, setUseSingle] = useState(false);

  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const pollStatus = useCallback(async () => {
    try {
      const s = await fetchPipelineStatus();
      setStatus(s);
    } catch {
      // silently ignore — server may be unreachable
    }
  }, []);

  useEffect(() => {
    pollStatus();
    const id = setInterval(pollStatus, 3000);
    return () => clearInterval(id);
  }, [pollStatus]);

  // ── CSV upload ─────────────────────────────────────────────────────────────

  async function handleFile(file: File) {
    if (!file.name.endsWith(".csv")) {
      setUploadError("Only .csv files are accepted.");
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const result = await uploadCsv(file);
      setUpload(result);
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  // ── Pipeline controls ──────────────────────────────────────────────────────

  async function handleStart() {
    if (!upload) return;
    setStarting(true);
    setRunError(null);
    try {
      await startPipeline({
        csv_path: upload.csv_path,
        dry_run: dryRun,
        single_lead: useSingle && singleLead !== null ? singleLead : undefined,
      });
      await pollStatus();
    } catch (e: unknown) {
      setRunError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  }

  async function handleStop() {
    setStopping(true);
    try {
      await stopPipeline();
      await pollStatus();
    } finally {
      setStopping(false);
    }
  }

  const progress =
    status && status.total > 0 ? status.processed / status.total : 0;

  const statusIntent: Intent = status?.running
    ? "primary"
    : status?.failed ?? 0 > 0
    ? "danger"
    : "success";

  return (
    <div>
      <h1 className="page-title">Pipeline Control</h1>

      {/* ── Upload drop zone ── */}
      <div
        className={`pipeline-drop-zone${dragOver ? " drag-over" : ""}`}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        {uploading ? (
          <>
            <Spinner size={32} style={{ marginBottom: 8 }} />
            <div style={{ color: "#738091" }}>Uploading…</div>
          </>
        ) : upload ? (
          <>
            <div style={{ fontSize: 36, marginBottom: 8 }}>✅</div>
            <div style={{ fontWeight: 600, color: "#f6f7f9" }}>
              {upload.filename}
            </div>
            <div style={{ fontSize: 13, color: "#738091", marginTop: 4 }}>
              {fmt(upload.lead_count)} leads loaded — click to replace
            </div>
          </>
        ) : (
          <>
            <div className="pipeline-drop-icon">📂</div>
            <div style={{ fontWeight: 600, color: "#f6f7f9", marginBottom: 4 }}>
              Drop your leads CSV here
            </div>
            <div style={{ fontSize: 13, color: "#738091" }}>
              or click to browse — required columns: first_name, email, company,
              website
            </div>
          </>
        )}
      </div>
      <input
        ref={fileRef}
        type="file"
        accept=".csv"
        style={{ display: "none" }}
        onChange={handleInputChange}
      />

      {uploadError && (
        <Callout intent="danger" icon="warning-sign" style={{ marginBottom: 16 }}>
          {uploadError}
        </Callout>
      )}

      {/* ── Run options ── */}
      <Card
        style={{
          background: "#252a31",
          border: "1px solid #383e47",
          marginBottom: 24,
        }}
      >
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: "#f6f7f9",
            marginBottom: 16,
          }}
        >
          Run Options
        </div>

        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <FormGroup label="Mode" inline>
            <Switch
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              label={dryRun ? "Dry Run (no Smartlead push)" : "Live Run"}
              style={{ color: "#abb3bf" }}
            />
          </FormGroup>

          <FormGroup label="Single lead test" inline>
            <Switch
              checked={useSingle}
              onChange={(e) => setUseSingle(e.target.checked)}
              label={useSingle ? "Row index:" : "Off"}
              style={{ color: "#abb3bf" }}
            />
          </FormGroup>

          {useSingle && (
            <FormGroup label="Row index" inline>
              <NumericInput
                value={singleLead ?? 0}
                onValueChange={(v) => setSingleLead(v)}
                min={0}
                style={{ width: 80 }}
              />
            </FormGroup>
          )}
        </div>

        <Divider />

        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Button
            intent="primary"
            icon="play"
            large
            loading={starting}
            disabled={!upload || status?.running}
            onClick={handleStart}
          >
            {dryRun ? "Dry Run" : "Start Live Run"}
          </Button>

          {status?.running && (
            <Button
              intent="danger"
              icon="stop"
              large
              loading={stopping}
              onClick={handleStop}
            >
              Stop
            </Button>
          )}

          {!upload && (
            <span style={{ fontSize: 12, color: "#738091", marginLeft: 8 }}>
              Upload a CSV first
            </span>
          )}
        </div>

        {runError && (
          <Callout
            intent="danger"
            icon="warning-sign"
            style={{ marginTop: 12 }}
          >
            {runError}
          </Callout>
        )}
      </Card>

      {/* ── Live status ── */}
      {status && (
        <Card
          style={{
            background: "#252a31",
            border: "1px solid #383e47",
            marginBottom: 24,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 12,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600, color: "#f6f7f9" }}>
              Pipeline Status
            </div>
            <Tag intent={statusIntent} large>
              {status.running ? "Running" : "Idle"}
            </Tag>
          </div>

          {status.total > 0 && (
            <>
              <ProgressBar
                value={progress}
                intent={statusIntent}
                animate={status.running}
                stripes={status.running}
                style={{ marginBottom: 12 }}
              />
              <div
                style={{
                  fontSize: 12,
                  color: "#738091",
                  textAlign: "right",
                  marginBottom: 16,
                }}
              >
                {fmt(status.processed)} / {fmt(status.total)} processed
                {status.elapsed_seconds != null &&
                  ` · ${Math.round(status.elapsed_seconds)}s elapsed`}
              </div>
            </>
          )}

          <HTMLTable style={{ width: "100%" }}>
            <tbody>
              {(
                [
                  ["Total leads", fmt(status.total)],
                  ["Processed", fmt(status.processed)],
                  ["Sent", fmt(status.sent)],
                  ["Skipped", fmt(status.skipped)],
                  ["Failed", fmt(status.failed)],
                  status.cost_usd != null
                    ? ["Cost so far", `$${status.cost_usd.toFixed(3)}`]
                    : null,
                ].filter(Boolean) as [string, string][]
              ).map(([label, value]) => (
                  <tr key={String(label)}>
                    <td
                      style={{
                        color: "#5f6b7c",
                        fontSize: 12,
                        width: "50%",
                        padding: "4px 8px",
                      }}
                    >
                      {label}
                    </td>
                    <td
                      style={{
                        color: "#abb3bf",
                        fontSize: 13,
                        fontWeight: 600,
                        padding: "4px 8px",
                      }}
                    >
                      {value}
                    </td>
                  </tr>
                ))}
            </tbody>
          </HTMLTable>
        </Card>
      )}
    </div>
  );
}
