// ─── API response types ────────────────────────────────────────────────────

export interface VariantStat {
  variant_id: string;
  framework: string;
  sent: number;       // emails actually delivered (from SmartLead analytics)
  in_queue: number;   // leads added to SmartLead campaign
  opened: number;
  clicked: number;
  replied: number;
  bounced: number;
  booked: number;
  open_rate: number;
  reply_rate: number;
  click_rate: number;
  book_rate: number;
  bounce_rate: number;
}

export interface FrameworkStat {
  framework: string;
  sent: number;
  opened: number;
  replied: number;
  booked: number;
  variant_ids: string[];
  open_rate: number;
  reply_rate: number;
  book_rate: number;
}

export interface HeatmapCell {
  row_key: string;
  col_key: string;
  sent: number;
  opened: number;
  replied: number;
  booked: number;
  open_rate: number;
  reply_rate: number;
  book_rate: number;
}

export interface SignificanceStatus {
  ready: boolean;
  leader_variant_id: string | null;
  leader_framework?: string;
  significant_winners: string[];
  min_sent: number;
  min_required: number;
}

export interface CostSummary {
  total_cost_usd: number;
  booked: number;
  cost_per_booked: number | null;
}

export interface AnalyticsData {
  test_id: string;
  primary_metric: string;
  min_per_variant: number;
  variants: VariantStat[];
  frameworks: FrameworkStat[];
  heatmap: HeatmapCell[];
  icp_heatmap: HeatmapCell[];
  significance: SignificanceStatus;
  cost: CostSummary;
  total_sent: number;       // emails delivered
  total_in_queue?: number;  // leads added to SmartLead
  total_replied: number;
  total_booked: number;
  blended_reply_rate: number;
  events_synced: boolean;
}

export interface Lead {
  lead_id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  company?: string;
  website?: string;
  role?: string;
  vertical?: string;
  motion?: string;
  intent_confidence?: number;
  variant_id?: string;
  framework?: string;
  status?: string;
  email_type?: string;
  created_at?: string;
  completed_at?: string;
}

export interface LeadDetail extends Lead {
  stages: Record<string, unknown>;
}

export interface ActivityItem {
  name:    string;
  company: string;
  email:   string;
  status:  string;   // "sent" | "dry_run" | "skipped" | "failed"
  error:   string;
  time:    string;   // "HH:MM:SS" UTC
}

export interface PipelineStatus {
  running:          boolean;
  total:            number;   // leads in the current batch
  csv_total?:       number;   // total leads in the full CSV file
  processed:        number;
  sent:             number;
  skipped:          number;
  failed:           number;
  duplicate_count:  number;
  recent_activity:  ActivityItem[];
  start_time?:      string;
  elapsed_seconds?: number;
  cost_usd?:        number;
  run_sent?:         number;
  run_personalised?: number;
  run_failed?:       number;
  db_sent?:          number;
  dry_run_count?:    number;   // personalised & awaiting push (status='dry_run')
}

export interface SmsPipelineStatus {
  running:          boolean;
  total:            number;
  run_generated:    number;   // Phase 1: bodies generated this run
  run_sent:         number;   // Phase 2: messages sent this run
  run_failed:       number;
  run_skipped:      number;
  tcpa_deferred?:   number;   // Phase 2: held back for TCPA window compliance
  db_generated:     number;   // all-time ready-to-send
  db_sent:          number;   // all-time sent
  recent_activity:  SmsActivityItem[];
  start_time?:      string;
  elapsed_seconds?: number;
  cost_usd?:        number;
  last_error?:      string;
}

export interface SmsActivityItem {
  name:    string;
  company: string;
  phone:   string;
  status:  string;
  time:    string;
  error?:  string;
}

export interface SmsReadinessResponse {
  ready_to_send: number;
  already_sent:  number;
  replied:       number;
  total:         number;
  error?:        string;
}

export interface UploadResponse {
  filename:        string;
  lead_count:      number;
  new_leads:       number;       // leads NOT already in DB
  duplicate_leads: number;       // leads already processed
  csv_path:        string;
}

export interface CsvUpload {
  id:              number;
  filename:        string;
  csv_path:        string;
  uploaded_at:     string;
  lead_count:      number;
  new_leads:       number;
  duplicate_leads: number;
  sent_count?:     number;   // live: leads from this CSV already sent to SmartLead
  pending_count?:  number;   // live: leads from this CSV personalised but not yet pushed
  failed_count?:   number;   // live: leads from this CSV that failed Phase 1
}

export interface CsvHistoryResponse {
  uploads:         CsvUpload[];
  total_new_leads: number;
}

export interface ReadinessResponse {
  personalized:     number;   // dry-run complete, not yet pushed
  video_count:      number;   // of those, have a personalized video
  email_only_count: number;   // of those, email-only (below intent threshold)
  ready_to_push:    number;   // same as personalized — semantic alias
  already_sent:     number;   // already live in Smartlead
  // All-time cumulative totals (across every batch ever run)
  all_personalised: number;
  all_skipped:      number;
  all_failed:       number;
  all_total:        number;
}

export interface PreviewLead {
  lead_id:         string;
  email:           string;
  first_name:      string;
  last_name:       string;
  company:         string;
  existing_status: string | null;
}

export interface PreviewResponse {
  total:           number;
  new_count:       number;
  duplicate_count: number;
  new_leads:       PreviewLead[];
  duplicate_leads: PreviewLead[];
}

export interface EmailMasterStats {
  total_leads:        number;   // sum of lead_count across ALL csv_uploads
  total_sent:         number;   // status IN ('sent','success') across all CSVs
  total_personalised: number;   // status = 'dry_run' — ready to push
  total_failed:       number;
  total_skipped:      number;
  total_remaining:    number;   // untouched leads (not yet in any pipeline run)
  uploads_count:      number;
  error?:             string;
}

export interface SmsMasterStats {
  total_leads:      number;   // sum of lead_count across ALL csv_uploads
  leads_with_phone: number;   // leads that have ≥1 valid, non-DNC wireless number
  dnc_excluded:     number;   // leads where every phone is DNC-flagged
  sms_sent:         number;   // sms_leads.status = 'sent' all-time
  sms_ready:        number;   // sms_leads.status = 'ready'
  sms_opted_out:    number;   // sms_leads.status = 'opted_out'
  sms_failed:       number;
  net_sendable:     number;   // leads_with_phone − sms_sent − sms_opted_out
  uploads_count:    number;
  scan_complete:    boolean;
  error?:           string;
}

export interface SmsIcpMatrixCell {
  col_key:    string;   // ICP vertical (row in the UI matrix)
  row_key:    string;   // SMS variant_id (column in the UI matrix)
  sent:       number;
  replied:    number;
  reply_rate: number;   // fraction 0–1
}

export interface SmsIcpMatrixResponse {
  cells:  SmsIcpMatrixCell[];
  error?: string;
}

export interface CampaignCheckResult {
  ok:          boolean;
  campaign_id: string | null;
  name:        string | null;
  status:      string | null;
  issues:      string[];
}

export interface SubjectLineStat {
  subject_line: string;
  variant_id:   string;
  sent:         number;
  opened:       number;
  replied:      number;
  booked:       number;
  open_rate:    number;   // already a percentage (0–100), NOT a fraction
  reply_rate:   number;   // already a percentage (0–100)
  book_rate:    number;
  is_grouped:   boolean;  // true = aggregate row for personalized/unique subjects
}

export interface SubjectLineResponse {
  min_sent:             number;
  total_subject_lines:  number;
  subject_lines:        SubjectLineStat[];
}

// ─── Audience (AudienceLab imports) ──────────────────────────────────────────

export interface AudienceImport {
  id:             number;
  name:           string;
  filename:       string | null;
  created_at:     number;    // unix timestamp
  last_refreshed: number;    // unix timestamp
  refresh_count:  number;
  row_count:      number;
  new_count:      number;
  dup_count:      number;
  webhook_url:    string | null;
}

export interface AudienceLead {
  id:                          number;
  first_name:                  string | null;
  last_name:                   string | null;
  business_email:              string | null;
  business_phone:              string | null;
  company:                     string | null;
  company_domain:              string | null;
  job_title:                   string | null;
  seniority:                   string | null;
  department:                  string | null;
  personal_phone:              string | null;
  wireless_phone:              string | null;
  personal_email:              string | null;
  linkedin_url:                string | null;
  city:                        string | null;
  state:                       string | null;
  country:                     string | null;
  industry:                    string | null;
  employee_count:              string | null;
  revenue:                     string | null;
  has_verified_business_email: number;
  has_verified_personal_email: number;
  has_valid_phone:             number;
  has_wireless_phone:          number;
  created_at:                  number;
}

export interface AudienceLeadsResponse {
  leads:  AudienceLead[];
  total:  number;
  offset: number;
  limit:  number;
}

export interface AudienceStats {
  total_leads:   number;
  total_imports: number;
  with_phone:    number;
  with_email:    number;
  with_wireless: number;
}

export interface AudienceUploadResponse {
  import_id:            number;
  filename:             string;
  total_rows:           number;
  inserted:             number;
  duplicates:           number;
  pipeline_new:         number;   // leads added to pipeline ledger (ready to personalise)
  pipeline_duplicates:  number;   // leads already in pipeline, left untouched
  csv_path:             string;   // saved path in data/input/ — pass to pipeline run
}
