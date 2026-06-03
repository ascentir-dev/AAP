import { useEffect, useState, useCallback } from "react";
import {
  Card,
  Tag,
  Button,
  Spinner,
  NonIdealState,
  TextArea,
  InputGroup,
  Callout,
} from "@blueprintjs/core";

// ─── Types ────────────────────────────────────────────────────────────────────

interface EmailVariant {
  variant_id: string;
  framework: string;
  description: string;
  subject_formula: string;
  template: string;
  word_count: string;
  ai_fills: string;
  is_edited: boolean;
  market?: string;
}

interface SubjectLinePerf {
  subject_line: string;
  variant_id: string;
  sent: number;
  opened: number;
  replied: number;
  booked: number;
  open_rate: number;   // already multiplied × 100 by backend
  reply_rate: number;
  book_rate: number;
}

interface SMSVariant {
  variant_id: string;
  name: string;
  framework: string;
  description: string;
  template: string;
  char_limit: number;
  ai_fills: string;
  is_edited: boolean;
}

interface PlaybookData {
  email: EmailVariant[];
  sms: SMSVariant[];
}

// ─── Placeholder Highlighter ─────────────────────────────────────────────────

function HighlightedTemplate({ text }: { text: string }) {
  if (!text) return <span style={{ color: "#5f6b7c", fontStyle: "italic" }}>No template set, uses default from prompts/</span>;
  const parts = text.split(/(\{[^}]+\})/g);
  return (
    <>
      {parts.map((part, i) =>
        /^\{[^}]+\}$/.test(part) ? (
          <span
            key={i}
            style={{
              color: "#76D7C4",
              background: "rgba(118,215,196,0.12)",
              borderRadius: 3,
              padding: "0 3px",
              fontWeight: 600,
            }}
          >
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

// ─── Email Variant Card ───────────────────────────────────────────────────────

interface EmailCardProps {
  variant: EmailVariant;
  subjectPerf: SubjectLinePerf[];
  onSave: (variantId: string, updates: Record<string, string>) => Promise<void>;
  videoMode: "all" | "video" | "email_only";
  showAllMarkets: boolean;
}

function SubjectPerfBadge({ perf }: { perf: SubjectLinePerf | undefined }) {
  if (!perf) {
    return (
      <div style={{ color: "#5f6b7c", fontSize: 11, marginTop: 6, fontStyle: "italic" }}>
        No data yet — needs 10+ sends to surface
      </div>
    );
  }
  const replyColour = perf.reply_rate >= 8 ? "#3ddc84" : perf.reply_rate >= 4 ? "#f0b429" : "#e06060";
  const openColour  = perf.open_rate  >= 40 ? "#3ddc84" : perf.open_rate  >= 25 ? "#f0b429" : "#e06060";
  return (
    <div style={{ display: "flex", gap: 12, marginTop: 8, flexWrap: "wrap" }}>
      {[
        { label: "Sent",       value: String(perf.sent),              colour: "#738091" },
        { label: "Open rate",  value: `${perf.open_rate.toFixed(1)}%`, colour: openColour  },
        { label: "Reply rate", value: `${perf.reply_rate.toFixed(1)}%`, colour: replyColour },
        { label: "Booked",     value: `${perf.book_rate.toFixed(1)}%`, colour: "#738091"   },
      ].map(({ label, value, colour }) => (
        <div key={label} style={{ textAlign: "center", minWidth: 64 }}>
          <div style={{ color: colour, fontWeight: 700, fontSize: 16, lineHeight: 1 }}>
            {value}
          </div>
          <div style={{ color: "#5f6b7c", fontSize: 10, marginTop: 2, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            {label}
          </div>
        </div>
      ))}
    </div>
  );
}

function EmailVariantCard({ variant, subjectPerf, onSave, videoMode, showAllMarkets }: EmailCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [template, setTemplate] = useState(variant.template);
  const [subjectFormula, setSubjectFormula] = useState(variant.subject_formula);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const wordCount = template.trim().split(/\s+/).filter(Boolean).length;

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(variant.variant_id, {
        template,
        subject_formula: subjectFormula,
      });
      setSaved(true);
      setEditing(false);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setTemplate(variant.template);
    setSubjectFormula(variant.subject_formula);
    setEditing(false);
    setSaveError(null);
  };

  return (
    <Card
      style={{
        marginBottom: 12,
        background: "#1a2433",
        border: expanded ? "1px solid #30404d" : "1px solid #1e2d3d",
        borderRadius: 8,
        padding: 0,
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "12px 16px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
        onClick={() => { setExpanded((e) => !e); setEditing(false); }}
      >
        <span style={{ color: "#9FA8DA", fontWeight: 700, fontSize: 13, minWidth: 72 }}>
          {variant.variant_id}
        </span>
        <span style={{ color: "#f6f7f9", fontSize: 13, flex: 1 }}>
          {variant.framework}
        </span>
        {/* Market badge — shown when viewing all markets */}
        {showAllMarkets && variant.market && (
          <span
            style={{
              fontSize: 10,
              padding: "1px 7px",
              borderRadius: 10,
              background: "rgba(159,168,218,0.15)",
              color: "#9FA8DA",
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            {variant.market}
          </span>
        )}
        {/* Video mode badge */}
        {videoMode === "video" && (
          <span
            style={{
              fontSize: 10,
              padding: "1px 7px",
              borderRadius: 10,
              background: "rgba(29,111,164,0.25)",
              color: "#76C8F6",
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            📹 Video mode
          </span>
        )}
        {videoMode === "email_only" && (
          <span
            style={{
              fontSize: 10,
              padding: "1px 7px",
              borderRadius: 10,
              background: "rgba(61,220,132,0.18)",
              color: "#3ddc84",
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            ✉️ Email only
          </span>
        )}
        {variant.is_edited && (
          <Tag intent="primary" minimal style={{ fontSize: 10 }}>
            Edited
          </Tag>
        )}
        {saved && (
          <Tag intent="success" minimal icon="tick" style={{ fontSize: 10 }}>
            Saved
          </Tag>
        )}
        <span style={{ color: "#5f6b7c", fontSize: 11 }}>
          {variant.word_count} words
        </span>
        <span style={{ color: "#5f6b7c", fontSize: 12, marginLeft: 4 }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {expanded && (
        <div style={{ borderTop: "1px solid #1e2d3d", padding: "14px 16px" }}>
          {/* Description */}
          <div style={{ color: "#738091", fontSize: 12, marginBottom: 12 }}>
            {variant.description}
          </div>

          {/* Subject formula + live performance */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ color: "#738091", fontSize: 11, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Subject Line Formula
            </div>
            {editing ? (
              <InputGroup
                value={subjectFormula}
                onChange={(e) => setSubjectFormula(e.target.value)}
                placeholder="e.g. saw {company}'s {observation}"
                small
              />
            ) : (
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: 12,
                  color: "#f6f7f9",
                  background: "#12202e",
                  borderRadius: 4,
                  padding: "6px 10px",
                }}
              >
                <HighlightedTemplate text={subjectFormula || "—"} />
              </div>
            )}
            {/* Live performance for this subject line */}
            {!editing && (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid #1e2d3d" }}>
                <div style={{ color: "#5f6b7c", fontSize: 10, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Live Performance
                </div>
                <SubjectPerfBadge
                  perf={subjectPerf.find((p) => p.variant_id === variant.variant_id)}
                />
              </div>
            )}
          </div>

          {/* Template body */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <div style={{ color: "#738091", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Template Body
              </div>
              <span style={{ color: "#5f6b7c", fontSize: 11 }}>
                {wordCount} words
              </span>
            </div>
            {editing ? (
              <TextArea
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
                fill
                rows={12}
                style={{
                  fontFamily: "monospace",
                  fontSize: 12,
                  background: "#12202e",
                  color: "#f6f7f9",
                  resize: "vertical",
                }}
              />
            ) : (
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: 12,
                  color: "#f6f7f9",
                  background: "#12202e",
                  borderRadius: 4,
                  padding: "10px 12px",
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.7,
                  maxHeight: 320,
                  overflowY: "auto",
                }}
              >
                <HighlightedTemplate text={template} />
              </div>
            )}
          </div>

          {/* AI fills */}
          {variant.ai_fills && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ color: "#738091", fontSize: 11, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                What AI Personalizes Per Lead
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {variant.ai_fills.split(",").map((f) => f.trim()).filter(Boolean).map((f) => (
                  <Tag key={f} minimal style={{ fontSize: 10, color: "#76D7C4", background: "rgba(118,215,196,0.1)" }}>
                    {f}
                  </Tag>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          {saveError && (
            <div style={{ color: "#e06060", fontSize: 12, marginBottom: 8 }}>{saveError}</div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            {editing ? (
              <>
                <Button
                  intent="primary"
                  icon="floppy-disk"
                  small
                  loading={saving}
                  onClick={handleSave}
                >
                  Save Changes
                </Button>
                <Button small onClick={handleCancel}>Cancel</Button>
              </>
            ) : (
              <Button icon="edit" small onClick={() => setEditing(true)}>
                Edit Template
              </Button>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

// ─── SMS Variant Card ─────────────────────────────────────────────────────────

interface SMSCardProps {
  variant: SMSVariant;
  onSave: (variantId: string, updates: Record<string, string>) => Promise<void>;
}

function SMSVariantCard({ variant, onSave }: SMSCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [template, setTemplate] = useState(variant.template);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Count chars without {VIDEO_LINK} (it gets replaced with a real URL ~30 chars)
  const charCount = template.replace("{VIDEO_LINK}", "https://go.example.com/abc").length;
  const overLimit = charCount > 320;
  const oneSegment = charCount <= 160;

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(variant.variant_id, { template });
      setSaved(true);
      setEditing(false);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setTemplate(variant.template);
    setEditing(false);
    setSaveError(null);
  };

  return (
    <Card
      style={{
        marginBottom: 12,
        background: "#1a2433",
        border: expanded ? "1px solid #30404d" : "1px solid #1e2d3d",
        borderRadius: 8,
        padding: 0,
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "12px 16px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
        onClick={() => { setExpanded((e) => !e); setEditing(false); }}
      >
        <span style={{ color: "#9FA8DA", fontWeight: 700, fontSize: 13, minWidth: 72 }}>
          {variant.variant_id}
        </span>
        <span style={{ color: "#f6f7f9", fontSize: 13, flex: 1 }}>
          {variant.name}: <span style={{ color: "#738091" }}>{variant.framework}</span>
        </span>
        {variant.is_edited && (
          <Tag intent="primary" minimal style={{ fontSize: 10 }}>Edited</Tag>
        )}
        {saved && (
          <Tag intent="success" minimal icon="tick" style={{ fontSize: 10 }}>Saved</Tag>
        )}
        <span style={{ color: "#5f6b7c", fontSize: 11 }}>
          ≤{variant.char_limit} chars
        </span>
        <span style={{ color: "#5f6b7c", fontSize: 12, marginLeft: 4 }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {expanded && (
        <div style={{ borderTop: "1px solid #1e2d3d", padding: "14px 16px" }}>
          <div style={{ color: "#738091", fontSize: 12, marginBottom: 12 }}>
            {variant.description}
          </div>

          {/* Template */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <div style={{ color: "#738091", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Message Template
              </div>
              <span
                style={{
                  fontSize: 11,
                  color: overLimit ? "#e06060" : oneSegment ? "#76D7C4" : "#738091",
                  fontWeight: overLimit || oneSegment ? 600 : undefined,
                }}
              >
                ~{charCount} chars {oneSegment ? "· 1 segment ✓" : overLimit ? "· OVER LIMIT" : "· 2 segments"}
              </span>
            </div>
            {editing ? (
              <TextArea
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
                fill
                rows={4}
                style={{
                  fontFamily: "monospace",
                  fontSize: 13,
                  background: "#12202e",
                  color: "#f6f7f9",
                  resize: "vertical",
                }}
              />
            ) : (
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: 13,
                  color: "#f6f7f9",
                  background: "#12202e",
                  borderRadius: 4,
                  padding: "10px 12px",
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.7,
                }}
              >
                <HighlightedTemplate text={template} />
              </div>
            )}
          </div>

          {/* AI fills */}
          {variant.ai_fills && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ color: "#738091", fontSize: 11, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                What AI Personalizes Per Lead
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                {variant.ai_fills.split(",").map((f) => f.trim()).filter(Boolean).map((f) => (
                  <Tag key={f} minimal style={{ fontSize: 10, color: "#76D7C4", background: "rgba(118,215,196,0.1)" }}>
                    {f}
                  </Tag>
                ))}
              </div>
            </div>
          )}

          {saveError && (
            <div style={{ color: "#e06060", fontSize: 12, marginBottom: 8 }}>{saveError}</div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            {editing ? (
              <>
                <Button intent="primary" icon="floppy-disk" small loading={saving} onClick={handleSave}>
                  Save Changes
                </Button>
                <Button small onClick={handleCancel}>Cancel</Button>
              </>
            ) : (
              <Button icon="edit" small onClick={() => setEditing(true)}>
                Edit Template
              </Button>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

// ─── Constants ────────────────────────────────────────────────────────────────

const MARKETS = [
  { key: "all",               label: "All ICPs" },
  { key: "coach",             label: "🎯 Coaches" },
  { key: "agency",            label: "🏢 Agencies" },
  { key: "consultant",        label: "💼 Consultants" },
  { key: "financial_advisor", label: "💰 Financial Advisors" },
  { key: "msp",               label: "🖥️ MSPs" },
];

const MARKET_CONTEXT: Record<string, string> = {
  coach: "Promise language tuned for coaches — outcome-driven language around client results, programme fills, and revenue per student.",
  agency: "Promise language tuned for agencies — framing around client retention, LTV, and recurring revenue growth.",
  consultant: "Promise language tuned for consultants — authority positioning, retainer expansion, and high-ticket positioning.",
  financial_advisor: "Promise language tuned for financial advisors — trust-first language around AUM growth, referrals, and appointment rate.",
  msp: "Promise language tuned for MSPs — efficiency and cost-savings framing, IT pain points, and MRR growth.",
};

// ─── Main Page ────────────────────────────────────────────────────────────────

type Tab = "email" | "sms" | "subjects";

export function PlaybookPage() {
  const [data, setData] = useState<PlaybookData | null>(null);
  const [subjectPerf, setSubjectPerf] = useState<SubjectLinePerf[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("email");
  const [selectedMarket, setSelectedMarket] = useState("all");
  const [videoMode, setVideoMode] = useState<"all" | "video" | "email_only">("all");

  const load = useCallback(async (market = "all") => {
    try {
      setError(null);
      setLoading(true);
      const playbookUrl = market === "all" ? "/api/playbook" : `/api/playbook?market=${market}`;
      const [playbookRes, perfRes] = await Promise.all([
        fetch(playbookUrl),
        fetch("/api/analytics/subject-lines?min_sent=10"),
      ]);
      if (!playbookRes.ok) throw new Error(`${playbookRes.status} ${playbookRes.statusText}`);
      const d: PlaybookData = await playbookRes.json();
      setData(d);
      // Subject line perf — graceful degradation if endpoint not yet seeded
      if (perfRes.ok) {
        const perf = await perfRes.json();
        setSubjectPerf(perf.subject_lines ?? []);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load("all"); }, [load]);

  const handleMarketChange = (market: string) => {
    setSelectedMarket(market);
    load(market);
  };

  const handleSave = async (
    channel: "email" | "sms",
    variantId: string,
    updates: Record<string, string>
  ) => {
    const r = await fetch("/api/playbook/template", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel, variant_id: variantId, updates }),
    });
    if (!r.ok) {
      const txt = await r.text();
      throw new Error(`Save failed: ${r.status} ${txt}`);
    }
    // Refresh data to update is_edited flags
    await load(selectedMarket);
  };

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <Spinner size={40} />
        <p style={{ color: "#738091", marginTop: 16 }}>Loading playbook…</p>
      </div>
    );
  }

  if (error) {
    return (
      <NonIdealState
        icon="error"
        title="Could not load playbook"
        description={error}
        action={<Button intent="primary" onClick={() => load(selectedMarket)}>Retry</Button>}
      />
    );
  }

  const rawEmailVariants = data?.email ?? [];
  // De-duplicate by variant_id when showing all markets (backend may return 9 × 5 = 45 rows)
  const emailVariants = selectedMarket === "all"
    ? rawEmailVariants.filter((v, idx, arr) => arr.findIndex((x) => x.variant_id === v.variant_id) === idx)
    : rawEmailVariants;
  const smsVariants   = data?.sms ?? [];
  const editedEmail   = emailVariants.filter((v) => v.is_edited).length;
  const editedSms     = smsVariants.filter((v) => v.is_edited).length;

  return (
    <div>
      <h1 className="page-title">Playbook</h1>

      <Callout
        intent="primary"
        icon="info-sign"
        style={{ marginBottom: 24, fontSize: 13 }}
      >
        <strong>How this works:</strong> The{" "}
        <span style={{ color: "#76D7C4" }}>{"{highlighted}"}</span> parts are
        filled in by AI per lead using their company, role, and website research.
        The plain text is your fixed template. Edit any variant and save. It
        takes effect on the next lead processed, no restart needed.
      </Callout>

      {/* Tab bar */}
      <div style={{ display: "flex", gap: 0, marginBottom: 20, borderBottom: "1px solid #30404d" }}>
        {([
          { key: "email",    label: "✉️ Email Templates", count: emailVariants.length, edited: editedEmail },
          { key: "sms",      label: "📱 SMS Templates",   count: smsVariants.length,   edited: editedSms   },
          { key: "subjects", label: "📊 Subject Lines",   count: subjectPerf.length,   edited: 0           },
        ] as { key: Tab; label: string; count: number; edited: number }[]).map(({ key, label, count, edited }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            style={{
              background: "none",
              border: "none",
              borderBottom: tab === key ? "2px solid #1D6FA4" : "2px solid transparent",
              color: tab === key ? "#f6f7f9" : "#738091",
              padding: "8px 20px",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: tab === key ? 600 : 400,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            {label}
            <span style={{ background: "#253545", borderRadius: 10, padding: "1px 7px", fontSize: 11, color: "#738091" }}>
              {count}
            </span>
            {edited > 0 && (
              <Tag intent="primary" minimal style={{ fontSize: 10 }}>
                {edited} edited
              </Tag>
            )}
          </button>
        ))}
      </div>

      {/* Email tab */}
      {tab === "email" && (
        <div>
          <div style={{ color: "#738091", fontSize: 13, marginBottom: 16 }}>
            9 variants running in your framework tournament. Click any variant to
            expand it, review the template, and edit. Changes override the default
            prompt. The AI will follow your custom structure instead.
          </div>

          {/* ── ICP / Market filter ────────────────────────────────────── */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ color: "#5f6b7c", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
              ICP / Market
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {MARKETS.map(({ key, label }) => {
                const active = selectedMarket === key;
                return (
                  <button
                    key={key}
                    onClick={() => handleMarketChange(key)}
                    style={{
                      background: active ? "#1D6FA4" : "#1a2433",
                      border: active ? "1px solid #1D6FA4" : "1px solid #30404d",
                      borderRadius: 20,
                      color: active ? "#fff" : "#738091",
                      padding: "4px 13px",
                      fontSize: 12,
                      fontWeight: active ? 600 : 400,
                      cursor: "pointer",
                      transition: "all 0.15s",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Market context callout */}
          {selectedMarket !== "all" && MARKET_CONTEXT[selectedMarket] && (
            <Callout
              intent="primary"
              icon="person"
              style={{ marginBottom: 16, fontSize: 12 }}
            >
              {MARKET_CONTEXT[selectedMarket]}
            </Callout>
          )}

          {/* ── Video / Email-only mode toggle ─────────────────────────── */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ color: "#5f6b7c", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
              Send Mode
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              {(
                [
                  { key: "all",        label: "All Sends" },
                  { key: "video",      label: "📹 With Video (Score 8-10)" },
                  { key: "email_only", label: "✉️ Email Only (Score 1-7)" },
                ] as { key: "all" | "video" | "email_only"; label: string }[]
              ).map(({ key, label }) => {
                const active = videoMode === key;
                return (
                  <button
                    key={key}
                    onClick={() => setVideoMode(key)}
                    style={{
                      background: active ? "#253545" : "#1a2433",
                      border: active ? "1px solid #30404d" : "1px solid #1e2d3d",
                      borderRadius: 20,
                      color: active ? "#f6f7f9" : "#738091",
                      padding: "4px 13px",
                      fontSize: 12,
                      fontWeight: active ? 600 : 400,
                      cursor: "pointer",
                      transition: "all 0.15s",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Video mode context callout */}
          {videoMode === "video" && (
            <Callout
              intent="none"
              icon="video"
              style={{ marginBottom: 16, fontSize: 12, background: "rgba(29,111,164,0.12)", border: "1px solid rgba(29,111,164,0.3)" }}
            >
              Email ends with the personalized video thumbnail. Sent to leads scoring <strong>8–10</strong>.
            </Callout>
          )}
          {videoMode === "email_only" && (
            <Callout
              intent="success"
              icon="envelope"
              style={{ marginBottom: 16, fontSize: 12 }}
            >
              No video. CTA is <strong>Reply VIDEO</strong>. Sent to leads scoring <strong>1–7</strong>. Email generated without any video references.
            </Callout>
          )}

          {emailVariants.map((v) => (
            <EmailVariantCard
              key={v.variant_id}
              variant={v}
              subjectPerf={subjectPerf}
              onSave={(vid, updates) => handleSave("email", vid, updates)}
              videoMode={videoMode}
              showAllMarkets={selectedMarket === "all"}
            />
          ))}
        </div>
      )}

      {/* SMS tab */}
      {tab === "sms" && (
        <div>
          <div style={{ color: "#738091", fontSize: 13, marginBottom: 16 }}>
            6 SMS variants optimized for text message replies. Targets are 1 segment
            (≤160 chars), shown in green. Keep{" "}
            <span style={{ color: "#76D7C4" }}>{"{VIDEO_LINK}"}</span> in every
            template. The system replaces it with the lead's personalized video URL.
          </div>
          {smsVariants.map((v) => (
            <SMSVariantCard
              key={v.variant_id}
              variant={v}
              onSave={(vid, updates) => handleSave("sms", vid, updates)}
            />
          ))}
        </div>
      )}

      {/* Subject Lines performance tab */}
      {tab === "subjects" && (
        <div>
          <div style={{ color: "#738091", fontSize: 13, marginBottom: 20 }}>
            Live performance by subject line. Each row is the actual subject text sent
            to prospects. Sorted by reply rate — the metric that matters most for cold outreach.
            Rows appear once 10+ sends have been recorded (removes noise from small samples).
          </div>

          {subjectPerf.length === 0 ? (
            <div
              style={{
                background: "#1a2433",
                borderRadius: 8,
                padding: "32px 24px",
                textAlign: "center",
                border: "1px solid #1e2d3d",
              }}
            >
              <div style={{ fontSize: 32, marginBottom: 12 }}>📬</div>
              <div style={{ color: "#f6f7f9", fontSize: 15, fontWeight: 600, marginBottom: 8 }}>
                No data yet
              </div>
              <div style={{ color: "#738091", fontSize: 13 }}>
                Subject line performance appears here once leads start being sent.
                Each subject line needs 10+ sends before it shows up (to avoid noise).
              </div>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 13,
                  color: "#f6f7f9",
                }}
              >
                <thead>
                  <tr style={{ borderBottom: "1px solid #30404d", textAlign: "left" }}>
                    {["Rank", "Subject Line", "Variant", "Sent", "Open Rate", "Reply Rate", "Booked"].map((h) => (
                      <th
                        key={h}
                        style={{
                          padding: "8px 12px",
                          color: "#738091",
                          fontSize: 11,
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                          fontWeight: 600,
                          whiteSpace: "nowrap",
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {subjectPerf
                    .slice()
                    .sort((a, b) => b.reply_rate - a.reply_rate)
                    .map((row, i) => {
                      const replyColour = row.reply_rate >= 8 ? "#3ddc84" : row.reply_rate >= 4 ? "#f0b429" : "#e06060";
                      const openColour  = row.open_rate  >= 40 ? "#3ddc84" : row.open_rate  >= 25 ? "#f0b429" : "#e06060";
                      const isLeader = i === 0;
                      return (
                        <tr
                          key={row.subject_line + row.variant_id}
                          style={{
                            borderBottom: "1px solid #1e2d3d",
                            background: isLeader ? "rgba(29,111,164,0.08)" : "transparent",
                          }}
                        >
                          <td style={{ padding: "10px 12px", color: "#5f6b7c", fontWeight: isLeader ? 700 : 400 }}>
                            {isLeader ? "🥇" : `#${i + 1}`}
                          </td>
                          <td style={{ padding: "10px 12px", fontFamily: "monospace", maxWidth: 320 }}>
                            {row.subject_line}
                            {isLeader && (
                              <Tag intent="success" minimal style={{ marginLeft: 8, fontSize: 9 }}>
                                Leader
                              </Tag>
                            )}
                          </td>
                          <td style={{ padding: "10px 12px", color: "#9FA8DA", fontSize: 12 }}>
                            {row.variant_id}
                          </td>
                          <td style={{ padding: "10px 12px", color: "#738091" }}>
                            {row.sent.toLocaleString()}
                          </td>
                          <td style={{ padding: "10px 12px", color: openColour, fontWeight: 600 }}>
                            {row.open_rate.toFixed(1)}%
                          </td>
                          <td style={{ padding: "10px 12px", color: replyColour, fontWeight: 700 }}>
                            {row.reply_rate.toFixed(1)}%
                          </td>
                          <td style={{ padding: "10px 12px", color: "#738091" }}>
                            {row.book_rate.toFixed(1)}%
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ marginTop: 16, color: "#5f6b7c", fontSize: 11 }}>
            Colour thresholds — Open rate: green ≥40%, amber ≥25%, red &lt;25%.
            Reply rate: green ≥8%, amber ≥4%, red &lt;4%.
            Once a clear leader emerges (p &lt; 0.05), consider routing more volume to that variant.
          </div>
        </div>
      )}
    </div>
  );
}
