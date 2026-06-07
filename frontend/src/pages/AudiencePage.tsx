/**
 * AudiencePage — AudienceLab.io-style contact viewer
 *
 * Two views, each with its own theme:
 *
 *  "Lists"  — dark theme (matches rest of the app)
 *             Shows uploaded CSV batches with metadata + action buttons.
 *             Webhook modal on the chain icon.
 *
 *  "Leads"  — light / white theme (matches AudienceLab screenshot exactly)
 *             "Ascentir Technologies Audience Filters" header with edit icon
 *             Filter tab bar: Intent · Date · Business · Financial · Personal
 *                             · Family · Housing · Location · Contact
 *             Contact table — row numbers, all columns, truncation, pagination
 *             Footer: "X results found" ← left, "1/N  Previous  Next" → right
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { Spinner, Callout } from "@blueprintjs/core";
import {
  uploadAudienceCsv,
  fetchAudienceImports,
  fetchAudienceLeads,
  fetchAudienceStats,
  deleteAudienceImport,
  renameAudienceImport,
  setAudienceWebhook,
} from "../api/client";
import type { AudienceImport, AudienceLead, AudienceStats, AudienceUploadResponse } from "../api/types";

// ─── dark-theme palette (used only on the Lists view) ────────────────────────
const D = {
  bg: "#141b22", card: "#1c2127", cardHover: "#1e2329",
  border: "#2f363e", borderSubtle: "#252a31",
  txt: "#f6f7f9", txtSub: "#abb3bf", txtMuted: "#738091", txtDim: "#5f6b7c",
  green: "#1D9E75", blue: "#4c90f0", yellow: "#f0b429", red: "#e63946", purple: "#8b5cf6",
} as const;

// ─── light-theme palette (used on the Leads / Filters view) ──────────────────
const L = {
  bg: "#ffffff", bg2: "#f8f9fa", border: "#e5e7eb", borderDark: "#d1d5db",
  txt: "#111827", txtSub: "#374151", txtMuted: "#6b7280", txtDim: "#9ca3af",
  blue: "#2563eb", green: "#059669", red: "#dc2626",
  tabActive: "#111827", tabInactive: "#6b7280",
  hdr: "#f9fafb",
} as const;

// ─── helpers ──────────────────────────────────────────────────────────────────
function fmtDate(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}
function fmtNum(n: number | null | undefined) { return (n ?? 0).toLocaleString(); }
function trunc(s: string | null | undefined, max = 26): string {
  if (!s) return "";
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

// ─── filter types ─────────────────────────────────────────────────────────────
interface ContactFilters {
  hasVerifiedPersonalEmail: boolean;
  hasVerifiedBusinessEmail: boolean;
  hasValidPhone: boolean;
  hasWirelessPhone: boolean;
}
const DEF_CONTACT: ContactFilters = {
  hasVerifiedPersonalEmail: false, hasVerifiedBusinessEmail: false,
  hasValidPhone: false, hasWirelessPhone: false,
};

interface BusinessFilters {
  jobTitles: string[]; seniority: string[]; departments: string[];
  companyNames: string[]; companyDomains: string[]; industries: string[];
}
const DEF_BUSINESS: BusinessFilters = {
  jobTitles: [], seniority: [], departments: [],
  companyNames: [], companyDomains: [], industries: [],
};

function countBusiness(f: BusinessFilters): number {
  return f.jobTitles.length + f.seniority.length + f.departments.length +
    f.companyNames.length + f.companyDomains.length + f.industries.length;
}
function countContact(f: ContactFilters): number {
  return Object.values(f).filter(Boolean).length;
}

// ─── small atoms ─────────────────────────────────────────────────────────────

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div role="switch" aria-checked={checked} onClick={() => onChange(!checked)} style={{
      width: 44, height: 24, borderRadius: 12, cursor: "pointer", flexShrink: 0,
      background: checked ? "#111" : "#d8dde6", position: "relative", transition: "background .15s",
    }}>
      <div style={{
        position: "absolute", top: 2, left: checked ? 22 : 2,
        width: 20, height: 20, borderRadius: "50%",
        background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,.35)", transition: "left .15s",
      }} />
    </div>
  );
}

function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "3px 10px", borderRadius: 20, fontSize: 12, fontWeight: 500,
      background: "#e8ecf0", color: "#111", border: "1px solid #d0d7de",
    }}>
      {label}
      <button onClick={onRemove} style={{
        background: "none", border: "none", cursor: "pointer", padding: 0,
        color: "#666", lineHeight: 1, fontSize: 14, display: "flex", alignItems: "center",
      }}>×</button>
    </span>
  );
}

function TagInput({
  placeholder, values, onChange,
}: { placeholder: string; values: string[]; onChange: (v: string[]) => void }) {
  const [draft, setDraft] = useState("");
  function add() {
    const v = draft.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft("");
  }
  return (
    <div style={{
      border: "1px solid #d0d7de", borderRadius: 8, padding: "8px 12px",
      background: "#fff", display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", minHeight: 46,
    }}>
      {values.map((v) => (
        <Chip key={v} label={v} onRemove={() => onChange(values.filter(x => x !== v))} />
      ))}
      <input type="text" placeholder={values.length === 0 ? placeholder : ""}
        value={draft} onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
        onBlur={add}
        style={{ border: "none", outline: "none", fontSize: 13, color: "#111", background: "transparent", flex: 1, minWidth: 80 }} />
    </div>
  );
}

const SENIORITY_OPTIONS = ["C-Suite (CXO)", "Director", "VP", "Manager", "Owner", "Partner", "President", "Founder", "Head of"];
const DEPARTMENT_OPTIONS = ["Sales", "Marketing", "Engineering", "Product", "Finance", "Operations", "Human Resources", "Legal", "Customer Success", "Design", "Data & Analytics"];

function ChipSelect({
  options, selected, onChange, placeholder = "Select…",
}: { options: string[]; selected: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  function toggle(opt: string) {
    onChange(selected.includes(opt) ? selected.filter(x => x !== opt) : [...selected, opt]);
  }
  return (
    <div style={{ position: "relative" }}>
      <div onClick={() => setOpen(o => !o)} style={{
        border: "1px solid #d0d7de", borderRadius: 8, padding: "8px 12px",
        background: "#fff", display: "flex", flexWrap: "wrap", gap: 6,
        alignItems: "center", cursor: "pointer", minHeight: 46,
      }}>
        {selected.length === 0
          ? <span style={{ color: "#aaa", fontSize: 13 }}>{placeholder}</span>
          : selected.map((v) => (
            <Chip key={v} label={v} onRemove={() => toggle(v)} />
          ))}
        <span style={{ marginLeft: "auto", color: "#888", fontSize: 11 }}>⌃⌄</span>
        {selected.length > 0 && (
          <button onClick={(e) => { e.stopPropagation(); onChange([]); }}
            style={{ background: "none", border: "none", cursor: "pointer", color: "#aaa", fontSize: 16 }}>×</button>
        )}
      </div>
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 50,
          background: "#fff", border: "1px solid #d0d7de", borderRadius: 8,
          boxShadow: "0 4px 16px rgba(0,0,0,.12)", overflow: "hidden",
        }}>
          {options.map((opt) => (
            <div key={opt} onClick={() => toggle(opt)} style={{
              padding: "9px 14px", fontSize: 13, cursor: "pointer",
              background: selected.includes(opt) ? "#f0f7ff" : "#fff", color: "#111",
              display: "flex", alignItems: "center", gap: 8,
            }}
              onMouseEnter={(e) => { if (!selected.includes(opt)) (e.currentTarget as HTMLElement).style.background = "#f8fafc"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = selected.includes(opt) ? "#f0f7ff" : "#fff"; }}
            >
              <span style={{
                width: 14, height: 14, border: "1px solid #d0d7de", borderRadius: 3,
                background: selected.includes(opt) ? "#111" : "transparent",
                display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
              }}>
                {selected.includes(opt) && <span style={{ color: "#fff", fontSize: 9, lineHeight: 1 }}>✓</span>}
              </span>
              {opt}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── filter drawer shell ──────────────────────────────────────────────────────
function FilterPanel({
  open, title, subtitle, icon, onClose, children,
}: {
  open: boolean; title: string; subtitle: string; icon?: string;
  onClose: () => void; children: React.ReactNode;
}) {
  return (
    <>
      {open && <div style={{ position: "fixed", inset: 0, zIndex: 200, background: "rgba(0,0,0,.45)" }} onClick={onClose} />}
      <div style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: 440, zIndex: 201,
        background: "#fff", color: "#111",
        transform: open ? "translateX(0)" : "translateX(100%)",
        transition: "transform .22s ease", display: "flex", flexDirection: "column",
        boxShadow: "-4px 0 28px rgba(0,0,0,.18)",
      }}>
        <div style={{ padding: "22px 24px 16px", borderBottom: "1px solid #e8ecf0", flexShrink: 0 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {icon && <span style={{ fontSize: 20 }}>{icon}</span>}
              <div>
                <div style={{ fontSize: 17, fontWeight: 700, color: "#111" }}>{title}</div>
                <div style={{ fontSize: 12, color: "#666", marginTop: 2 }}>{subtitle}</div>
              </div>
            </div>
            <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#888" }}>×</button>
          </div>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px 80px" }}>{children}</div>
      </div>
    </>
  );
}

function FilterFooter({ onReset, onContinue }: { onReset: () => void; onContinue: () => void }) {
  return (
    <div style={{
      position: "absolute", bottom: 0, left: 0, right: 0,
      display: "flex", justifyContent: "flex-end", gap: 10,
      padding: "14px 24px", borderTop: "1px solid #e8ecf0", background: "#fff",
    }}>
      <button onClick={onReset} style={{
        padding: "9px 20px", borderRadius: 6, border: "1px solid #d0d7de",
        background: "#fff", color: "#111", fontSize: 13, fontWeight: 600, cursor: "pointer",
      }}>Reset</button>
      <button onClick={onContinue} style={{
        padding: "9px 20px", borderRadius: 6, border: "none",
        background: "#111", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer",
      }}>Continue</button>
    </div>
  );
}

// ─── Business filter panel ────────────────────────────────────────────────────
function BusinessFilterPanel({
  filters, onChange, onReset, onContinue,
}: { filters: BusinessFilters; onChange: (f: BusinessFilters) => void; onReset: () => void; onContinue: () => void }) {
  function set<K extends keyof BusinessFilters>(key: K, val: BusinessFilters[K]) { onChange({ ...filters, [key]: val }); }
  const Sec = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div style={{ marginBottom: 22 }}>
      <div style={{ fontSize: 14, fontWeight: 700, color: "#111", marginBottom: 8 }}>{label}</div>
      {children}
    </div>
  );
  return (
    <>
      <Sec label="Job Titles"><TagInput placeholder="Type job title and press enter..." values={filters.jobTitles} onChange={(v) => set("jobTitles", v)} /></Sec>
      <Sec label="Seniority"><ChipSelect options={SENIORITY_OPTIONS} selected={filters.seniority} onChange={(v) => set("seniority", v)} placeholder="Select seniority levels..." /></Sec>
      <Sec label="Departments"><ChipSelect options={DEPARTMENT_OPTIONS} selected={filters.departments} onChange={(v) => set("departments", v)} placeholder="Select departments..." /></Sec>
      <Sec label="Company Names"><TagInput placeholder="Type and press enter..." values={filters.companyNames} onChange={(v) => set("companyNames", v)} /></Sec>
      <Sec label="Company Domains"><TagInput placeholder="Type and press enter..." values={filters.companyDomains} onChange={(v) => set("companyDomains", v)} /></Sec>
      <Sec label="Industries"><TagInput placeholder="Type industry and press enter..." values={filters.industries} onChange={(v) => set("industries", v)} /></Sec>
      <FilterFooter onReset={onReset} onContinue={onContinue} />
    </>
  );
}

// ─── Contact filter panel ─────────────────────────────────────────────────────
function ContactFilterPanel({
  filters, onChange, onReset, onContinue,
}: { filters: ContactFilters; onChange: (f: ContactFilters) => void; onReset: () => void; onContinue: () => void }) {
  const rows = [
    { key: "hasVerifiedPersonalEmail" as const, label: "Verified Personal Emails" },
    { key: "hasVerifiedBusinessEmail" as const, label: "Verified Business Emails" },
    { key: "hasValidPhone" as const,            label: "Valid Phones" },
    { key: "hasWirelessPhone" as const,         label: "Skip Traced Wireless Phone Number" },
  ];
  return (
    <>
      {rows.map(({ key, label }) => (
        <div key={key} style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "16px 20px", marginBottom: 8,
          border: "1px solid #e8ecf0", borderRadius: 8, background: "#fff",
        }}>
          <span style={{ fontSize: 14, color: "#111", fontWeight: 500 }}>{label}</span>
          <Toggle checked={filters[key]} onChange={(v) => onChange({ ...filters, [key]: v })} />
        </div>
      ))}
      <FilterFooter onReset={onReset} onContinue={onContinue} />
    </>
  );
}

function PlaceholderPanel({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div style={{ textAlign: "center", padding: "48px 0", color: "#999" }}>
      <div style={{ fontSize: 36, marginBottom: 12 }}>🔧</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: "#555", marginBottom: 6 }}>{title} filters</div>
      <div style={{ fontSize: 12, lineHeight: 1.7 }}>
        Apply {title.toLowerCase()} filters in AudienceLab,<br />
        then export and re-upload the filtered CSV here.
      </div>
      <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, padding: "14px 24px", borderTop: "1px solid #e8ecf0" }}>
        <button onClick={onClose} style={{
          padding: "9px 20px", borderRadius: 6, border: "none",
          background: "#111", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer",
        }}>Close</button>
      </div>
    </div>
  );
}

// ─── Webhook modal ────────────────────────────────────────────────────────────
function WebhookModal({
  open, audienceName, existingUrl, onClose, onSave,
}: {
  open: boolean; audienceName: string; existingUrl: string | null;
  onClose: () => void; onSave: (url: string) => Promise<void>;
}) {
  const [url,       setUrl]       = useState(existingUrl ?? "");
  const [saving,    setSaving]    = useState(false);
  const [testing,   setTesting]   = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  useEffect(() => { if (open) setUrl(existingUrl ?? ""); }, [open, existingUrl]);

  async function handleTest() {
    if (!url) return;
    setTesting(true); setTestResult(null);
    try {
      const r = await fetch(url, { method: "POST", body: JSON.stringify({ test: true }), headers: { "Content-Type": "application/json" } });
      setTestResult(r.ok ? `✓ ${r.status} ${r.statusText}` : `✗ ${r.status} ${r.statusText}`);
    } catch (e: unknown) { setTestResult(`✗ ${e instanceof Error ? e.message : String(e)}`); }
    finally { setTesting(false); }
  }

  async function handleAdd() {
    setSaving(true);
    try { await onSave(url); onClose(); }
    catch (e: unknown) { setTestResult(`✗ ${e instanceof Error ? e.message : String(e)}`); }
    finally { setSaving(false); }
  }

  if (!open) return null;
  return (
    <>
      <div style={{ position: "fixed", inset: 0, zIndex: 300, background: "rgba(0,0,0,.55)" }} onClick={onClose} />
      <div style={{
        position: "fixed", top: "50%", left: "50%", zIndex: 301,
        transform: "translate(-50%, -50%)",
        background: "#fff", color: "#111", borderRadius: 12,
        padding: "32px 32px 24px", width: 520, maxWidth: "95vw",
        boxShadow: "0 8px 48px rgba(0,0,0,.28)",
      }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 8 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Add Webhook {audienceName} Audience</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", fontSize: 20, color: "#888", marginLeft: 8 }}>×</button>
        </div>
        <p style={{ fontSize: 13, color: "#555", margin: "0 0 24px", lineHeight: 1.6 }}>
          Connect your services to receive real-time updates when the audience lists are ready.
        </p>
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#111", marginBottom: 8 }}>Webhook URL</div>
          <div style={{ display: "flex", gap: 8 }}>
            <input type="url" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)}
              style={{ flex: 1, padding: "9px 13px", border: "1.5px solid #111", borderRadius: 7, fontSize: 13, color: "#111", outline: "none" }} />
            <button onClick={handleTest} disabled={!url || testing} style={{
              padding: "9px 16px", borderRadius: 7, border: "none",
              background: url ? "#888" : "#d0d7de", color: "#fff",
              fontSize: 13, fontWeight: 600, cursor: url ? "pointer" : "default", flexShrink: 0,
              display: "flex", alignItems: "center", gap: 5,
            }}>
              {testing ? <Spinner size={12} /> : "Test"}
            </button>
          </div>
          {testResult && (
            <div style={{ marginTop: 6, fontSize: 12, color: testResult.startsWith("✓") ? "#059669" : "#dc2626" }}>{testResult}</div>
          )}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button onClick={onClose} style={{ padding: "10px 22px", borderRadius: 7, border: "1px solid #d0d7de", background: "#fff", color: "#111", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Cancel</button>
          <button onClick={handleAdd} disabled={saving} style={{
            padding: "10px 22px", borderRadius: 7, border: "none",
            background: "#111", color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer",
            display: "flex", alignItems: "center", gap: 6,
          }}>
            {saving ? <Spinner size={12} intent="none" /> : null} Add
          </button>
        </div>
      </div>
    </>
  );
}

// ─── dark action button (Lists view) ─────────────────────────────────────────
function ActionBtn({ children, title, onClick, danger }: {
  children: React.ReactNode; title: string; onClick?: () => void; danger?: boolean;
}) {
  return (
    <button title={title} onClick={onClick} style={{
      background: "none", border: `1px solid ${D.border}`, borderRadius: 5,
      padding: "4px 6px", cursor: "pointer", color: danger ? D.red : D.txtMuted,
      display: "flex", alignItems: "center",
    }}>{children}</button>
  );
}

// ─── FILTER TAB ICONS (SVG inline, matching AudienceLab) ─────────────────────
const TAB_ICONS: Record<string, React.ReactNode> = {
  Intent: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
      <path d="M2 4h12M2 8h8M2 12h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  ),
  Date: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
      <rect x="2" y="3" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M5 2v2M11 2v2M2 7h12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
    </svg>
  ),
  Business: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
      <rect x="2" y="6" width="12" height="8" rx="1" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M5 6V5a3 3 0 0 1 6 0v1" stroke="currentColor" strokeWidth="1.4"/>
    </svg>
  ),
  Financial: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M8 4v1.5M8 10.5V12M6 6.5a2 2 0 1 1 4 0c0 1-1 1.5-2 2s-2 1-2 2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  ),
  Personal: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
      <circle cx="8" cy="5.5" r="2.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M2.5 14c0-3 2.5-5 5.5-5s5.5 2 5.5 5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
    </svg>
  ),
  Family: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
      <circle cx="5.5" cy="4.5" r="2" stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="10.5" cy="4.5" r="2" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M1 14c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4M8.5 14c0-2 1.5-3.5 4-3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  ),
  Housing: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
      <path d="M2 8l6-6 6 6M3.5 7.5V13h9V7.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
      <rect x="6" y="10" width="4" height="3" rx="0.5" stroke="currentColor" strokeWidth="1.2"/>
    </svg>
  ),
  Location: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
      <path d="M8 1.5A4.5 4.5 0 0 1 12.5 6c0 3.5-4.5 8.5-4.5 8.5S3.5 9.5 3.5 6A4.5 4.5 0 0 1 8 1.5z" stroke="currentColor" strokeWidth="1.4"/>
      <circle cx="8" cy="6" r="1.5" stroke="currentColor" strokeWidth="1.2"/>
    </svg>
  ),
  Contact: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
      <rect x="2" y="3.5" width="12" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.4"/>
      <path d="M2 6l6 3.5L14 6" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/>
    </svg>
  ),
};

const FILTER_TABS = ["Intent", "Date", "Business", "Financial", "Personal", "Family", "Housing", "Location", "Contact"] as const;
type FilterTab = typeof FILTER_TABS[number];

// ─── Leads table view (LIGHT THEME — matches AudienceLab exactly) ────────────
function LeadsTableView({
  importRecord, stats, onBack,
}: { importRecord: AudienceImport | null; stats: AudienceStats | null; onBack: () => void }) {
  const [leads,   setLeads]   = useState<AudienceLead[]>([]);
  const [total,   setTotal]   = useState(0);
  const [loading, setLoading] = useState(true);
  const [page,    setPage]    = useState(0);
  const [search]              = useState("");

  const [activePanel,    setActivePanel]    = useState<FilterTab | null>(null);
  const [contactFilters, setContactFilters] = useState<ContactFilters>({ ...DEF_CONTACT });
  const [appliedContact, setAppliedContact] = useState<ContactFilters>({ ...DEF_CONTACT });
  const [bizFilters,     setBizFilters]     = useState<BusinessFilters>({ ...DEF_BUSINESS });
  const [appliedBiz,     setAppliedBiz]     = useState<BusinessFilters>({ ...DEF_BUSINESS });

  const [uploading,  setUploading]  = useState(false);
  const [editTitle,  setEditTitle]  = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const audienceName = importRecord?.name ?? "Ascentir Technologies";
  const LIMIT = 100;

  const load = useCallback(async (p: number, s: string, cf: ContactFilters, bf: BusinessFilters) => {
    setLoading(true);
    try {
      const res = await fetchAudienceLeads({
        offset: p * LIMIT, limit: LIMIT, search: s,
        has_phone: cf.hasValidPhone, has_email: cf.hasVerifiedBusinessEmail,
        has_wireless: cf.hasWirelessPhone, has_personal_email: cf.hasVerifiedPersonalEmail,
        import_id: importRecord?.id,
        job_titles: bf.jobTitles, seniority: bf.seniority, departments: bf.departments,
        company_names: bf.companyNames, company_domains: bf.companyDomains, industries: bf.industries,
      });
      setLeads(res.leads); setTotal(res.total);
    } catch { /* keep stale */ } finally { setLoading(false); }
  }, [importRecord]);

  useEffect(() => { load(page, search, appliedContact, appliedBiz); }, [load, page, search, appliedContact, appliedBiz]);

  const cBadge    = countContact(appliedContact);
  const bBadge    = countBusiness(appliedBiz);
  const totalPages = Math.ceil(total / LIMIT);

  return (
    <div style={{ background: L.bg, minHeight: "100vh", fontFamily: "'Inter', system-ui, sans-serif" }}>

      {/* ── breadcrumb ── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "12px 24px 10px", borderBottom: `1px solid ${L.border}`,
        flexWrap: "wrap", gap: 10,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: L.txtMuted }}>
          {(["Home", "Ascentir Technologies", "Audience"] as const).map((seg, i) => (
            <span key={seg} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              {i > 0 && <span>›</span>}
              <button onClick={onBack} style={{
                background: "none", border: "none", cursor: "pointer", color: L.blue, fontSize: 13, padding: 0,
              }}>{seg}</button>
            </span>
          ))}
          <span>›</span>
          <span style={{ color: L.txt }}>Filters</span>
        </div>

        {/* right side controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          <span style={{ fontSize: 13, color: L.txtMuted, whiteSpace: "nowrap" }}>
            <strong style={{ color: L.txt }}>{fmtNum(stats?.total_leads)}</strong> / 500,000 contacts used this month
          </span>
          <button style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "7px 14px", borderRadius: 6, border: `1px solid ${L.border}`,
            background: L.bg, color: L.txt, fontSize: 13, fontWeight: 500, cursor: "pointer",
          }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2 8A6 6 0 1 1 8 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.3"/></svg>
            Data Dictionary
          </button>
          <button style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "7px 14px", borderRadius: 6, border: `1px solid ${L.borderDark}`,
            background: L.bg, color: L.txt, fontSize: 13, fontWeight: 500, cursor: "pointer",
          }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5"/><path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
            Preview
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "8px 16px", borderRadius: 6, border: "none",
              background: "#111", color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer",
            }}
          >
            {uploading ? <Spinner size={10} intent="none" /> : (
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="2" width="12" height="12" rx="2" stroke="#fff" strokeWidth="1.4"/><path d="M8 5v6M5.5 8.5L8 11l2.5-2.5" stroke="#fff" strokeWidth="1.4" strokeLinecap="round"/></svg>
            )}
            Update Audience
          </button>
          <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }}
            onChange={async (e) => {
              const f = e.target.files?.[0]; if (!f) return; e.target.value = "";
              setUploading(true);
              try { await uploadAudienceCsv(f); await load(page, search, appliedContact, appliedBiz); }
              finally { setUploading(false); }
            }} />
        </div>
      </div>

      {/* ── page title ── */}
      <div style={{ padding: "14px 24px 12px", display: "flex", alignItems: "center", gap: 8 }}>
        {editTitle ? (
          <input autoFocus value={titleDraft}
            onChange={(e) => setTitleDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === "Escape") setEditTitle(false); }}
            onBlur={() => setEditTitle(false)}
            style={{
              fontSize: 20, fontWeight: 700, color: L.txt,
              border: "none", borderBottom: `2px solid ${L.blue}`,
              outline: "none", background: "transparent", width: 400,
            }}
          />
        ) : (
          <>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: L.txt }}>
              {audienceName} Audience Filters
            </h1>
            <button onClick={() => { setTitleDraft(audienceName); setEditTitle(true); }} style={{
              background: "none", border: "none", cursor: "pointer", color: L.txtMuted,
              display: "flex", alignItems: "center", padding: 2,
            }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="M11 2l3 3-8 8H3v-3l8-8z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
              </svg>
            </button>
          </>
        )}
      </div>

      {/* ── filter tab bar ── */}
      <div style={{
        display: "flex", alignItems: "stretch", gap: 0, padding: "0 24px",
        borderBottom: `1px solid ${L.border}`, overflowX: "auto", background: L.bg,
      }}>
        {FILTER_TABS.map((tab) => {
          const active = activePanel === tab;
          const bBadge2 = tab === "Business" ? bBadge : 0;
          const cBadge2 = tab === "Contact" ? cBadge : 0;
          const hasFilter = bBadge2 > 0 || cBadge2 > 0;
          return (
            <button key={tab} onClick={() => setActivePanel(active ? null : tab)} style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "11px 14px", background: "none", border: "none",
              borderBottom: active ? `2px solid ${L.tabActive}` : "2px solid transparent",
              fontSize: 13,
              fontWeight: hasFilter ? 600 : active ? 600 : 400,
              color: active ? L.tabActive : hasFilter ? L.tabActive : L.tabInactive,
              cursor: "pointer", whiteSpace: "nowrap",
            }}>
              <span style={{ color: active ? L.tabActive : hasFilter ? L.tabActive : L.tabInactive }}>
                {TAB_ICONS[tab]}
              </span>
              {tab}
              {(bBadge2 > 0 || cBadge2 > 0) && (
                <span style={{ fontWeight: 400 }}>
                  ({(bBadge2 || cBadge2)} applied)
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* ── table ── */}
      {loading ? (
        <div style={{ textAlign: "center", padding: 60 }}><Spinner size={32} /></div>
      ) : leads.length === 0 ? (
        <div style={{ textAlign: "center", padding: "60px 32px", color: L.txtDim }}>
          <div style={{ fontSize: 36, marginBottom: 10 }}>🔍</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: L.txtSub }}>No contacts match your filters</div>
          <div style={{ fontSize: 13, marginTop: 4 }}>Try adjusting your search or clearing some filters</div>
          <button
            onClick={() => fileRef.current?.click()}
            style={{
              marginTop: 20, padding: "10px 24px", borderRadius: 6, border: "none",
              background: "#111", color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer",
            }}
          >Upload CSV</button>
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: L.bg, borderBottom: `1px solid ${L.border}` }}>
                <th style={{ width: 48, padding: "10px 8px 10px 16px", textAlign: "left", color: L.txtMuted, fontWeight: 500, fontSize: 12 }}></th>
                <TH>First Name</TH>
                <TH>Last Name</TH>
                <TH>Business Email</TH>
                <TH>Business Phone</TH>
                <TH>Company</TH>
                <TH>Company Domain</TH>
                <TH>Job Title</TH>
                <TH>Personal Phone</TH>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead, idx) => (
                <tr key={lead.id}
                  style={{ borderBottom: `1px solid ${L.border}`, cursor: "default" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = L.bg2)}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                  <td style={{ padding: "10px 8px 10px 16px", color: L.txtDim, fontSize: 13, fontWeight: 400, userSelect: "none" }}>
                    {page * LIMIT + idx + 1}
                  </td>
                  <TD>{lead.first_name}</TD>
                  <TD>{lead.last_name}</TD>
                  <TD link={lead.business_email ? `mailto:${lead.business_email}` : undefined} muted>{trunc(lead.business_email, 26)}</TD>
                  <TD muted>{trunc(lead.business_phone, 22)}</TD>
                  <TD bold>{trunc(lead.company, 26)}</TD>
                  <TD muted>{trunc(lead.company_domain, 22)}</TD>
                  <TD>{trunc(lead.job_title, 28)}</TD>
                  <TD muted>{trunc(lead.personal_phone, 20)}</TD>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── footer: results count + pagination ── */}
      {!loading && total > 0 && (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "14px 24px", borderTop: `1px solid ${L.border}`,
          background: L.bg,
        }}>
          <span style={{ fontSize: 13, color: L.txtSub }}>
            <strong style={{ color: L.txt }}>{fmtNum(total)}</strong> results found
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 13, color: L.txtMuted }}>
            <span style={{ fontWeight: 500, color: L.txtSub }}>
              {page + 1} / {Math.max(1, totalPages)}
            </span>
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)} style={{
              padding: "5px 14px", borderRadius: 6,
              border: `1px solid ${L.borderDark}`,
              background: page === 0 ? L.bg2 : L.bg,
              color: page === 0 ? L.txtDim : L.txt,
              fontSize: 13, cursor: page === 0 ? "default" : "pointer",
            }}>Previous</button>
            <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)} style={{
              padding: "5px 14px", borderRadius: 6,
              border: `1px solid ${L.borderDark}`,
              background: page >= totalPages - 1 ? L.bg2 : L.bg,
              color: page >= totalPages - 1 ? L.txtDim : L.txt,
              fontSize: 13, cursor: page >= totalPages - 1 ? "default" : "pointer",
            }}>Next</button>
          </div>
        </div>
      )}

      {/* ── inline search bar (below header, above tabs) ── */}
      <style>{`
        .aud-search-row { display:flex; align-items:center; gap:10px; padding:8px 24px; background:${L.bg}; border-bottom:1px solid ${L.border}; }
      `}</style>

      {/* ── filter drawers ── */}
      <FilterPanel open={activePanel === "Business"} title="Business"
        subtitle="What business characteristics does this audience represent?"
        icon="🏢" onClose={() => setActivePanel(null)}>
        <BusinessFilterPanel
          filters={bizFilters} onChange={setBizFilters}
          onReset={() => setBizFilters({ ...DEF_BUSINESS })}
          onContinue={() => { setAppliedBiz({ ...bizFilters }); setPage(0); setActivePanel(null); }}
        />
      </FilterPanel>

      <FilterPanel open={activePanel === "Contact"} title="Contact"
        subtitle="What contact information should be included?"
        icon="✉️" onClose={() => setActivePanel(null)}>
        <ContactFilterPanel
          filters={contactFilters} onChange={setContactFilters}
          onReset={() => setContactFilters({ ...DEF_CONTACT })}
          onContinue={() => { setAppliedContact({ ...contactFilters }); setPage(0); setActivePanel(null); }}
        />
      </FilterPanel>

      {(["Intent", "Date", "Financial", "Personal", "Family", "Housing", "Location"] as FilterTab[]).map((tab) => (
        <FilterPanel key={tab} open={activePanel === tab}
          title={tab} subtitle={`Filter audience by ${tab.toLowerCase()} criteria`}
          onClose={() => setActivePanel(null)}>
          <PlaceholderPanel title={tab} onClose={() => setActivePanel(null)} />
        </FilterPanel>
      ))}
    </div>
  );
}

// Light-theme table header/cell helpers
function TH({ children }: { children: React.ReactNode }) {
  return (
    <th style={{ padding: "10px 12px", textAlign: "left", color: L.txt, fontWeight: 600, fontSize: 13, whiteSpace: "nowrap" }}>
      {children}
    </th>
  );
}
function TD({ children, muted, bold, link }: {
  children?: React.ReactNode; muted?: boolean; bold?: boolean; link?: string;
}) {
  const style: React.CSSProperties = {
    padding: "10px 12px", color: muted ? L.txtMuted : L.txt,
    fontWeight: bold ? 600 : 400, whiteSpace: "nowrap",
    maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis",
  };
  return (
    <td style={style}>
      {link
        ? <a href={link} style={{ color: L.blue, textDecoration: "none" }}>{children}</a>
        : <>{children ?? <span style={{ color: L.txtDim }}>—</span>}</>
      }
    </td>
  );
}

// ─── Audience Lists view (DARK theme) ────────────────────────────────────────
function AudienceListsView({
  imports, stats, onUpload, onDelete, onRename, onView, uploading, uploadError, uploadResult,
}: {
  imports: AudienceImport[]; stats: AudienceStats | null;
  onUpload: (f: File) => void; onDelete: (id: number) => void;
  onRename: (id: number, name: string) => void; onView: (imp: AudienceImport) => void;
  uploading: boolean; uploadError: string | null;
  uploadResult: AudienceUploadResponse | null;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [search, setSearch] = useState("");
  const [webhookFor, setWebhookFor] = useState<AudienceImport | null>(null);

  const filtered = imports.filter((imp) =>
    !search ||
    imp.name.toLowerCase().includes(search.toLowerCase()) ||
    (imp.filename || "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{ background: D.bg, minHeight: "100vh", color: D.txt, fontFamily: "'Inter', system-ui, sans-serif" }}>
      <div style={{ padding: "12px 28px 0", fontSize: 13, color: D.txtMuted, display: "flex", gap: 6 }}>
        <span style={{ color: D.blue }}>Home</span><span>›</span>
        <span style={{ color: D.blue }}>Ascentir Technologies</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 28px 0" }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: D.txt }}>Audience Lists</h1>
        <button onClick={() => fileRef.current?.click()} style={{
          display: "flex", alignItems: "center", gap: 7,
          padding: "8px 18px", borderRadius: 6, border: "none",
          background: D.txt, color: "#111", fontSize: 13, fontWeight: 700, cursor: "pointer",
        }}>
          {uploading ? <Spinner size={12} /> : null} Create
        </button>
        <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ""; }} />
      </div>

      {uploadError && <div style={{ margin: "12px 28px 0" }}><Callout intent="danger" style={{ fontSize: 12 }}>{uploadError}</Callout></div>}

      {uploadResult && !uploadError && (
        <div style={{ margin: "12px 28px 0", background: "#111d2b", border: "1px solid #2d4068", borderRadius: 8, padding: "12px 16px", display: "flex", alignItems: "flex-start", gap: 12 }}>
          <span style={{ fontSize: 18, lineHeight: 1 }}>✅</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: "#f6f7f9", marginBottom: 4 }}>
              {uploadResult.filename} uploaded — {uploadResult.total_rows.toLocaleString()} rows processed
            </div>
            <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: 12 }}>
              <span><span style={{ color: "#34d399", fontWeight: 700 }}>{uploadResult.pipeline_new.toLocaleString()}</span> <span style={{ color: "#738091" }}>new leads added to pipeline</span></span>
              <span><span style={{ color: "#738091", fontWeight: 600 }}>{uploadResult.pipeline_duplicates.toLocaleString()}</span> <span style={{ color: "#738091" }}>already in system, skipped</span></span>
            </div>
            {uploadResult.pipeline_new > 0 && (
              <div style={{ marginTop: 8, fontSize: 11, color: "#4c90f0" }}>
                Ready to personalise — go to <strong>Dashboard → Personalise</strong> and select <code style={{ background: "#1c2d42", padding: "1px 5px", borderRadius: 3, fontSize: 10 }}>{uploadResult.csv_path.split("/").slice(-1)[0]}</code> when prompted.
              </div>
            )}
          </div>
        </div>
      )}

      {stats && stats.total_leads > 0 && (
        <div style={{ display: "flex", gap: 12, padding: "16px 28px 0", flexWrap: "wrap" }}>
          {[
            { label: "Total contacts",      value: fmtNum(stats.total_leads),   color: D.txt },
            { label: "With business email", value: fmtNum(stats.with_email),    color: D.green },
            { label: "With phone",          value: fmtNum(stats.with_phone),    color: D.blue },
            { label: "Wireless / skiptrace",value: fmtNum(stats.with_wireless), color: D.purple },
          ].map((s) => (
            <div key={s.label} style={{
              background: D.card, border: `1px solid ${D.border}`, borderRadius: 8, padding: "10px 16px", minWidth: 130,
            }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: s.color, lineHeight: 1 }}>{s.value}</div>
              <div style={{ fontSize: 11, color: D.txtDim, marginTop: 3, textTransform: "uppercase", letterSpacing: "0.04em" }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ padding: "16px 28px 0" }}>
        <input type="text" placeholder="Search by name…" value={search} onChange={(e) => setSearch(e.target.value)}
          style={{ width: 280, padding: "8px 13px", border: `1px solid ${D.border}`, borderRadius: 6, fontSize: 13, color: D.txt, outline: "none", background: D.card }} />
      </div>

      <div style={{ padding: "14px 28px 32px", overflowX: "auto" }}>
        {filtered.length === 0 ? (
          <div style={{ textAlign: "center", padding: "72px 32px", border: `2px dashed ${D.border}`, borderRadius: 12, color: D.txtDim }}>
            <div style={{ fontSize: 42, marginBottom: 12 }}>📂</div>
            <div style={{ fontSize: 15, fontWeight: 600, color: D.txtSub, marginBottom: 6 }}>No audience lists yet</div>
            <div style={{ fontSize: 13, marginBottom: 20 }}>Upload a CSV exported from AudienceLab to get started</div>
            <button onClick={() => fileRef.current?.click()} style={{
              padding: "10px 24px", borderRadius: 6, border: "none",
              background: D.txt, color: "#111", fontSize: 13, fontWeight: 700, cursor: "pointer",
            }}>Upload CSV</button>
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${D.border}` }}>
                <th style={{ width: 40, padding: "10px 8px" }} />
                <DTH>Status</DTH>
                <DTH sortable>Created</DTH>
                <DTH>Last Refreshed</DTH>
                <DTH right>Audience Size</DTH>
                <DTH right>Refresh Count</DTH>
                <DTH right>New</DTH>
                <DTH right>Dupes Removed</DTH>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((imp) => (
                <tr key={imp.id} style={{ borderBottom: `1px solid ${D.borderSubtle}`, cursor: "pointer" }}
                  onClick={() => onView(imp)}
                  onMouseEnter={(e) => (e.currentTarget.style.background = D.cardHover)}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                  <td style={{ padding: "14px 8px" }}>
                    <input type="checkbox" style={{ cursor: "pointer", accentColor: D.blue }} onClick={(e) => e.stopPropagation()} />
                  </td>
                  <td style={{ padding: "14px 12px" }}>
                    {editingId === imp.id ? (
                      <input autoFocus value={editName}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => setEditName(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") { onRename(imp.id, editName); setEditingId(null); } if (e.key === "Escape") setEditingId(null); }}
                        onBlur={() => { onRename(imp.id, editName); setEditingId(null); }}
                        style={{ padding: "4px 8px", border: `1px solid ${D.blue}`, borderRadius: 4, fontSize: 13, color: D.txt, outline: "none", background: D.card }} />
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 600, background: "#14532d", color: "#4ade80" }}>Completed</span>
                        <span style={{ color: D.txt, fontWeight: 500 }}>{imp.name}</span>
                      </div>
                    )}
                  </td>
                  <td style={{ padding: "14px 12px", color: D.txtMuted }}>{fmtDate(imp.created_at)}</td>
                  <td style={{ padding: "14px 12px", color: D.txtMuted }}>{fmtDate(imp.last_refreshed)}</td>
                  <td style={{ padding: "14px 12px", textAlign: "right", fontWeight: 600, color: D.txt }}>{fmtNum(imp.row_count)}</td>
                  <td style={{ padding: "14px 12px", textAlign: "right", color: D.txtMuted }}>{fmtNum(imp.refresh_count)}</td>
                  <td style={{ padding: "14px 12px", textAlign: "right", color: D.green, fontWeight: 500 }}>{fmtNum(imp.new_count)}</td>
                  <td style={{ padding: "14px 12px", textAlign: "right", color: D.yellow, fontWeight: 500 }}>{fmtNum(imp.dup_count)}</td>
                  <td style={{ padding: "14px 12px" }}>
                    <div style={{ display: "flex", gap: 4 }} onClick={(e) => e.stopPropagation()}>
                      <ActionBtn title="Refresh" onClick={() => fileRef.current?.click()}>
                        <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M2 8A6 6 0 1 1 8 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><path d="M2 13V8h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      </ActionBtn>
                      <ActionBtn title="Rename" onClick={() => { setEditName(imp.name); setEditingId(imp.id); }}>
                        <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M11 2l3 3-8 8H3v-3l8-8z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/></svg>
                      </ActionBtn>
                      <ActionBtn title="View leads" onClick={() => onView(imp)}>
                        <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.5"/><path d="M1 8s2.5-6 7-6 7 6 7 6-2.5 6-7 6-7-6-7-6z" stroke="currentColor" strokeWidth="1.5"/></svg>
                      </ActionBtn>
                      <ActionBtn title="Download">
                        <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M8 2v8M5 7l3 3 3-3M2 13h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                      </ActionBtn>
                      <ActionBtn title="Configure webhook" onClick={() => setWebhookFor(imp)}>
                        <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                          <path d="M6 4a2 2 0 1 1 0 4 2 2 0 0 1 0-4zM10 8a2 2 0 1 1 0 4 2 2 0 0 1 0-4z" stroke="currentColor" strokeWidth="1.3"/>
                          <path d="M8 6l2 1.5M8 10l2-1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                        </svg>
                      </ActionBtn>
                      <ActionBtn title="Delete" danger onClick={() => {
                        if (confirm(`Delete "${imp.name}" and its orphaned contacts?`)) onDelete(imp.id);
                      }}>
                        <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M2 4h12M5 4V2h6v2M6 7v5M10 7v5M4 4l.5 9h7l.5-9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                      </ActionBtn>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {webhookFor && (
        <WebhookModal
          open={!!webhookFor} audienceName={webhookFor.name}
          existingUrl={webhookFor.webhook_url}
          onClose={() => setWebhookFor(null)}
          onSave={async (url) => { await setAudienceWebhook(webhookFor.id, url); }}
        />
      )}
    </div>
  );
}

function DTH({ children, right, sortable }: { children?: React.ReactNode; right?: boolean; sortable?: boolean }) {
  return (
    <th style={{ padding: "10px 12px", textAlign: right ? "right" : "left", color: D.txtMuted, fontWeight: 500, whiteSpace: "nowrap", fontSize: 13 }}>
      {children}{sortable ? <span style={{ marginLeft: 4, opacity: 0.5 }}>⌃⌄</span> : null}
    </th>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export function AudiencePage() {
  // Default to "leads" so the tab opens straight to the contact table.
  // The breadcrumb "← Back" still lets the user reach the Lists / upload view.
  const [view,    setView]    = useState<"lists" | "leads">("leads");
  const [current, setCurrent] = useState<AudienceImport | null>(null);
  const [imports, setImports] = useState<AudienceImport[]>([]);
  const [stats,   setStats]   = useState<AudienceStats | null>(null);
  const [uploading,    setUploading]    = useState(false);
  const [uploadError,  setUploadError]  = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<AudienceUploadResponse | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [imp, st] = await Promise.all([fetchAudienceImports(), fetchAudienceStats()]);
      setImports(imp.imports); setStats(st);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function handleUpload(file: File) {
    setUploading(true); setUploadError(null); setUploadResult(null);
    try {
      const res = await uploadAudienceCsv(file);
      setUploadResult(res);
      await refresh();
      const updated = await fetchAudienceImports();
      const newImp  = updated.imports.find(i => i.id === res.import_id) ?? null;
      setCurrent(newImp); setView("leads");
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : String(e));
    } finally { setUploading(false); }
  }

  if (view === "leads") {
    return (
      <LeadsTableView
        importRecord={current} stats={stats}
        onBack={() => { setView("lists"); setCurrent(null); refresh(); }}
      />
    );
  }

  return (
    <AudienceListsView
      imports={imports} stats={stats}
      onUpload={handleUpload}
      onDelete={async (id) => {
        try { await deleteAudienceImport(id); await refresh(); }
        catch (e: unknown) { alert(e instanceof Error ? e.message : String(e)); }
      }}
      onRename={async (id, name) => {
        try { await renameAudienceImport(id, name); await refresh(); }
        catch { /* ignore */ }
      }}
      onView={(imp) => { setCurrent(imp); setView("leads"); }}
      uploading={uploading} uploadError={uploadError} uploadResult={uploadResult}
    />
  );
}
