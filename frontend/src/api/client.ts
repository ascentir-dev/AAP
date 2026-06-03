import type {
  AnalyticsData,
  Lead,
  LeadDetail,
  PipelineStatus,
  UploadResponse,
  PreviewResponse,
  ReadinessResponse,
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
