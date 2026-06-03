// ─── API response types ────────────────────────────────────────────────────

export interface VariantStat {
  variant_id: string;
  framework: string;
  sent: number;
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
  replied: number;
  booked: number;
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
  significance: SignificanceStatus;
  cost: CostSummary;
  total_sent: number;
  total_replied: number;
  total_booked: number;
  blended_reply_rate: number;
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
}

export interface UploadResponse {
  filename:   string;
  lead_count: number;
  csv_path:   string;
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

export interface CampaignCheckResult {
  ok:          boolean;
  campaign_id: string | null;
  name:        string | null;
  status:      string | null;
  issues:      string[];
}
