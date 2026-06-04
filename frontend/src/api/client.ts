import type {
  AnalyticsData,
  Lead,
  LeadDetail,
  PipelineStatus,
  UploadResponse,
  PreviewResponse,
  ReadinessResponse,
  CampaignCheckResult,
  CsvHistoryResponse,
} from "./types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status} ${r.statusText}: ${text}`);
  }
  return r.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status} ${r.statusText}: ${text}`);
  }
  return r.json() as Promise<T>;
}

// ─── Analytics ────────────────────────────────────────────────────────────

export function fetchAnalytics(): Promise<AnalyticsData> {
  return get<AnalyticsData>("/analytics");
}

export function syncSmartleadAnalytics(): Promise<{ ok: boolean; campaigns_synced: number; totals: Record<string, number>; errors: string[] }> {
  return post<{ ok: boolean; campaigns_synced: number; totals: Record<string, number>; errors: string[] }>("/analytics/sync", {});
}

// ─── Leads ────────────────────────────────────────────────────────────────

export function fetchLeads(
  page = 0,
  limit = 50,
  status?: string
): Promise<{ leads: Lead[]; total: number }> {
  const params = new URLSearchParams({
    offset: String(page * limit),
    limit: String(limit),
  });
  if (status) params.set("status", status);
  return get(`/leads?${params}`);
}

export function fetchLead(leadId: string): Promise<LeadDetail> {
  return get<LeadDetail>(`/leads/${encodeURIComponent(leadId)}`);
}

// ─── Pipeline ─────────────────────────────────────────────────────────────

export async function uploadCsv(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const r = await fetch(`${BASE}/pipeline/upload`, {
    method: "POST",
    body: form,
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status} ${r.statusText}: ${text}`);
  }
  return r.json() as Promise<UploadResponse>;
}

export function previewCsv(csv_path: string): Promise<PreviewResponse> {
  return post<PreviewResponse>("/pipeline/preview", { csv_path });
}

export function fetchReadiness(): Promise<ReadinessResponse> {
  return get<ReadinessResponse>("/pipeline/readiness");
}

export function checkCampaign(): Promise<CampaignCheckResult> {
  return get<CampaignCheckResult>("/pipeline/campaign-check");
}

export function startPipeline(opts: {
  csv_path:    string;
  dry_run:     boolean;
  single_lead?: number;
  batch_size?:  number;
}): Promise<{ started: boolean }> {
  return post("/pipeline/run", opts);
}

export function stopPipeline(): Promise<{ stopped: boolean }> {
  return post("/pipeline/stop");
}

export function fetchPipelineStatus(): Promise<PipelineStatus> {
  return get<PipelineStatus>("/pipeline/status");
}

export function fetchCsvHistory(): Promise<CsvHistoryResponse> {
  return get<CsvHistoryResponse>("/pipeline/csv-history");
}

// ─── Bulk lead operations ──────────────────────────────────────────────────

export async function deleteLead(leadId: string): Promise<void> {
  const r = await fetch(`/api/leads/${encodeURIComponent(leadId)}`, { method: "DELETE" });
  if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`); }
}

export async function bulkDeleteLeads(leadIds: string[]): Promise<{ deleted: number }> {
  const r = await fetch("/api/leads/bulk-delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lead_ids: leadIds }),
  });
  if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`); }
  return r.json();
}

export async function deleteEmailOnlyLeads(): Promise<{ deleted: number }> {
  const r = await fetch("/api/leads/email-only", { method: "DELETE" });
  if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`); }
  return r.json();
}
