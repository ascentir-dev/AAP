import type {
  AnalyticsData,
  Lead,
  LeadDetail,
  PipelineStatus,
  SmsPipelineStatus,
  SmsReadinessResponse,
  UploadResponse,
  PreviewResponse,
  ReadinessResponse,
  CampaignCheckResult,
  CsvHistoryResponse,
  EmailMasterStats,
  SmsMasterStats,
  SmsIcpMatrixResponse,
  SubjectLineResponse,
  AudienceImport,
  AudienceLead,
  AudienceLeadsResponse,
  AudienceStats,
  AudienceUploadResponse,
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

export function fetchSubjectLines(minSent = 3): Promise<SubjectLineResponse> {
  return get<SubjectLineResponse>(`/analytics/subject-lines?min_sent=${minSent}`);
}

export function syncSmartleadAnalytics(): Promise<{ ok: boolean; campaigns_synced: number; totals: Record<string, number>; errors: string[] }> {
  return post<{ ok: boolean; campaigns_synced: number; totals: Record<string, number>; errors: string[] }>("/analytics/sync", {});
}

export function applyDailyLimits(totalDaily = 900): Promise<{
  ok: boolean;
  total_daily: number;
  campaigns_configured: number;
  results: { variant: string; campaign_id: string; limit: number; status: string }[];
  errors: string[];
}> {
  return post("/campaigns/daily-limits", { total_daily: totalDaily });
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

export function fetchEmailMasterStats(): Promise<EmailMasterStats> {
  return get<EmailMasterStats>("/pipeline/master-stats");
}

export function fetchSmsMasterStats(): Promise<SmsMasterStats> {
  return get<SmsMasterStats>("/sms/master-stats");
}

export function fetchSmsIcpMatrix(): Promise<SmsIcpMatrixResponse> {
  return get<SmsIcpMatrixResponse>("/sms/icp-matrix");
}

// ─── SMS Pipeline ─────────────────────────────────────────────────────────

export function startSmsPipeline(opts: {
  csv_path?: string;
  dry_run:   boolean;
  batch_size?: number;
}): Promise<{ started: boolean; dry_run: boolean }> {
  return post("/sms/pipeline/run", opts);
}

export function stopSmsPipeline(): Promise<{ stopped: boolean }> {
  return post("/sms/pipeline/stop");
}

export function fetchSmsPipelineStatus(): Promise<SmsPipelineStatus> {
  return get<SmsPipelineStatus>("/sms/pipeline/status");
}

export function fetchSmsReadiness(): Promise<SmsReadinessResponse> {
  return get<SmsReadinessResponse>("/sms/readiness");
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

// ─── Audience ─────────────────────────────────────────────────────────────

export async function uploadAudienceCsv(file: File): Promise<AudienceUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const r = await fetch("/api/audience/upload", { method: "POST", body: form });
  if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`); }
  return r.json();
}

export function fetchAudienceImports(): Promise<{ imports: AudienceImport[] }> {
  return get("/audience/imports");
}

export function fetchAudienceLeads(params: {
  offset?: number;
  limit?: number;
  search?: string;
  has_phone?: boolean;
  has_email?: boolean;
  has_wireless?: boolean;
  has_personal_email?: boolean;
  import_id?: number;
  // Business filters
  job_titles?: string[];
  seniority?: string[];
  departments?: string[];
  company_names?: string[];
  company_domains?: string[];
  industries?: string[];
}): Promise<AudienceLeadsResponse> {
  const p = new URLSearchParams();
  if (params.offset    !== undefined) p.set("offset",             String(params.offset));
  if (params.limit     !== undefined) p.set("limit",              String(params.limit));
  if (params.search)                  p.set("search",             params.search);
  if (params.has_phone)               p.set("has_phone",          "true");
  if (params.has_email)               p.set("has_email",          "true");
  if (params.has_wireless)            p.set("has_wireless",       "true");
  if (params.has_personal_email)      p.set("has_personal_email", "true");
  if (params.import_id !== undefined) p.set("import_id",          String(params.import_id));
  if (params.job_titles?.length)      p.set("job_titles",     params.job_titles.join(","));
  if (params.seniority?.length)       p.set("seniority",      params.seniority.join(","));
  if (params.departments?.length)     p.set("departments",    params.departments.join(","));
  if (params.company_names?.length)   p.set("company_names",  params.company_names.join(","));
  if (params.company_domains?.length) p.set("company_domains",params.company_domains.join(","));
  if (params.industries?.length)      p.set("industries",     params.industries.join(","));
  return get(`/audience/leads?${p}`);
}

export async function setAudienceWebhook(importId: number, url: string): Promise<void> {
  const r = await fetch(`/api/audience/imports/${importId}/webhook`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`); }
}

export function fetchAudienceStats(): Promise<AudienceStats> {
  return get("/audience/stats");
}

export async function deleteAudienceImport(importId: number): Promise<void> {
  const r = await fetch(`/api/audience/imports/${importId}`, { method: "DELETE" });
  if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`); }
}

export async function renameAudienceImport(importId: number, name: string): Promise<void> {
  const r = await fetch(`/api/audience/imports/${importId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t}`); }
}

// Unused import shim — satisfies TypeScript's "imported but never used" check.
export type { AudienceLead };
