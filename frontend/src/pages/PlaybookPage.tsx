import { useEffect, useState, useCallback } from "react";
import { Card, Tag, Button, Spinner, NonIdealState, TextArea, InputGroup } from "@blueprintjs/core";

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

interface SubjectLinePerf {
  subject_line: string;
  variant_id: string;
  sent: number;
  opened: number;
  replied: number;
  booked: number;
  open_rate: number;
  reply_rate: number;
  book_rate: number;
}

interface PlaybookData {
  email: EmailVariant[];
  sms: SMSVariant[];
}

// ─── Constants ────────────────────────────────────────────────────────────────

const ICP_MARKETS = [
  { key: "coach",             label: "Coaches",           icon: "🎯" },
  { key: "agency",            label: "Agencies",          icon: "🏢" },
  { key: "consultant",        label: "Consultants",       icon: "💼" },
  { key: "financial_advisor", label: "Fin. Advisors",     icon: "💰" },
  { key: "msp",               label: "MSPs",              icon: "🖥️" },
];

const MARKET_CONTEXT: Record<string, string> = {
  coach:             "Outcome-driven language — client results, programme fills, and revenue per student.",
  agency:            "Client retention, LTV, and recurring revenue growth framing.",
  consultant:        "Authority positioning, retainer expansion, and high-ticket engagements.",
  financial_advisor: "Trust-first language around AUM growth, referrals, and appointment rate.",
  msp:               "Efficiency and cost-savings framing, IT pain points, and MRR growth.",
};

const VARIANT_LABEL: Record<string, string> = {
  "Variant 1": "V1 · PPP",
  "Variant 2": "V2 · Compact",
  "Variant 3": "V3 · PPP+Proof",
  "Variant 4": "V4 · AIDA",
  "Variant 5": "V5 · 3Cs",
  "Variant 6": "V6 · QVC",
  "Variant 7": "V7 · Demand Flip",
  "Variant 8": "V8 · Inv. Demand",
  "Variant 9": "V9 · PAS",
};

type Tab = "email" | "sms" | "subjects";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function HighlightedTemplate({ text }: { text: string }) {
  if (!text)
    return <span style={{ color: "#5f6b7c", fontStyle: "italic" }}>No template set — uses AI default</span>;
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

function PerfBadges({ perf }: { perf: SubjectLinePerf | undefined }) {
  if (!perf)
    return (
      <span style={{ color: "#5f6b7c", fontSize: 11, fontStyle: "italic" }}>
        No data yet — needs 10+ sends
      </span>
    );
  const replyColor = perf.reply_rate >= 8 ? "#3ddc84" : perf.reply_rate >= 4 ? "#f0b429" : "#e06060";
  const openColor  = perf.open_rate  >= 40 ? "#3ddc84" : perf.open_rate  >= 25 ? "#f0b429" : "#e06060";
  return (
    <div style={{ display: "flex", gap: 20 }}>
      {[
        { label: "Sent",   value: perf.sent.toLocaleString(),        color: "#738091"   },
        { label: "Open",   value: `${perf.open_rate.toFixed(1)}%`,   color: openColor   },
        { label: "Reply",  value: `${perf.reply_rate.toFixed(1)}%`,  color: replyColor  },
        { label: "Booked", value: `${perf.book_rate.toFixed(1)}%`,   color: "#738091"   },
      ].map(({ label, value, color }) => (
        <div key={label} style={{ textAlign: "center" }}>
          <div style={{ color, fontWeight: 700, fontSize: 15, lineHeight: 1 }}>{value}</div>
          <div style={{ color: "#5f6b7c", fontSize: 10, marginTop: 2, textTransform: "uppercase", letterSpacing: "0.04em" }}>
            {label}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Shared styles ────────────────────────────────────────────────────────────

const SECTION_LABEL: React.CSSProperties = {
  color: "#5f6b7c",
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: "0.07em",
  fontWeight: 700,
  marginBottom: 7,
};

const CODE_BOX: React.CSSProperties = {
  fontFamily: "monospace",
  fontSize: 12,
  color: "#f6f7f9",
  background: "#0f1923",
  borderRadius: 5,
  padding: "10px 13px",
  lineHeight: 1.75,
};

// ─── Email Content Panel ──────────────────────────────────────────────────────

function EmailContentPanel({
  variant,
  subjectPerf,
  videoMode,
  onSave,
}: {
  variant: EmailVariant;
  subjectPerf: SubjectLinePerf[];
  videoMode: "all" | "video" | "email_only";
  onSave: (variantId: string, updates: Record<string, string>) => Promise<void>;
}) {
  const [editing, setEditing]   = useState(false);
  const [template, setTemplate] = useState(variant.template);
  const [subject, setSubject]   = useState(variant.subject_formula);
  const [saving, setSaving]     = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved]       = useState(false);

  useEffect(() => {
    setTemplate(variant.template);
    setSubject(variant.subject_formula);
    setEditing(false);
    setSaveError(null);
    setSaved(false);
  }, [variant.variant_id, variant.template, variant.subject_formula]);

  const wordCount = template.trim().split(/\s+/).filter(Boolean).length;
  const perf = subjectPerf.find((p) => p.variant_id === variant.variant_id);

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(variant.variant_id, { template, subject_formula: subject });
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
    setSubject(variant.subject_formula);
    setEditing(false);
    setSaveError(null);
  };

  return (
    <Card
      style={{
        background: "#161d27",
        border: "1px solid #253545",
        borderRadius: 8,
        padding: 0,
        overflow: "hidden",
      }}
    >
      {/* Card header */}
      <div
        style={{
          padding: "13px 20px",
          background: "#1c2a3a",
          borderBottom: "1px solid #253545",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <span style={{ color: "#9FA8DA", fontWeight: 700, fontSize: 14, flex: 1 }}>
          {VARIANT_LABEL[variant.variant_id] ?? variant.variant_id}
        </span>
        <span style={{ color: "#738091", fontSize: 12 }}>{variant.framework}</span>
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
        {videoMode === "video" && (
          <span
            style={{
              fontSize: 10, padding: "2px 9px", borderRadius: 10,
              background: "rgba(29,111,164,0.25)", color: "#76C8F6", fontWeight: 600,
            }}
          >
            📹 Video
          </span>
        )}
        {videoMode === "email_only" && (
          <span
            style={{
              fontSize: 10, padding: "2px 9px", borderRadius: 10,
              background: "rgba(61,220,132,0.18)", color: "#3ddc84", fontWeight: 600,
            }}
          >
            ✉️ Email Only
          </span>
        )}
      </div>

      {/* Subject + Performance */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto",
          gap: 28,
          padding: "16px 20px",
          borderBottom: "1px solid #1e2d3d",
          alignItems: "start",
        }}
      >
        <div>
          <div style={SECTION_LABEL}>Subject Line Formula</div>
          {editing ? (
            <InputGroup
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              small
              placeholder="e.g. saw {company}'s {observation}"
              style={{ fontFamily: "monospace" }}
            />
          ) : (
            <div style={CODE_BOX}>
              <HighlightedTemplate text={subject || "—"} />
            </div>
          )}
        </div>
        <div>
          <div style={SECTION_LABEL}>Live Performance</div>
          <PerfBadges perf={perf} />
        </div>
      </div>

      {/* Template body */}
      <div style={{ padding: "16px 20px", borderBottom: "1px solid #1e2d3d" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 8,
          }}
        >
          <div style={SECTION_LABEL}>Template Body</div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ color: "#5f6b7c", fontSize: 11 }}>{wordCount} words</span>
            {editing ? (
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                {saveError && (
                  <span style={{ color: "#e06060", fontSize: 11 }}>{saveError}</span>
                )}
                <Button intent="primary" icon="floppy-disk" small loading={saving} onClick={handleSave}>
                  Save
                </Button>
                <Button small onClick={handleCancel}>
                  Cancel
                </Button>
              </div>
            ) : (
              <Button icon="edit" small minimal onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
          </div>
        </div>
        {editing ? (
          <TextArea
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            fill
            rows={14}
            style={{
              fontFamily: "monospace",
              fontSize: 12,
              background: "#0f1923",
              color: "#f6f7f9",
              resize: "vertical",
            }}
          />
        ) : (
          <div
            style={{
              ...CODE_BOX,
              whiteSpace: "pre-wrap",
              maxHeight: 440,
              overflowY: "auto",
            }}
          >
            <HighlightedTemplate text={template} />
          </div>
        )}
      </div>

      {/* AI fills */}
      {variant.ai_fills && (
        <div
          style={{
            padding: "10px 20px",
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
          }}
        >
          <span style={{ ...SECTION_LABEL, marginBottom: 0 }}>AI fills per lead:</span>
          {variant.ai_fills
            .split(",")
            .map((f) => f.trim())
            .filter(Boolean)
            .map((f) => (
              <Tag
                key={f}
                minimal
                style={{ fontSize: 10, color: "#76D7C4", background: "rgba(118,215,196,0.1)" }}
              >
                {f}
              </Tag>
            ))}
        </div>
      )}
    </Card>
  );
}

// ─── SMS Content Panel ────────────────────────────────────────────────────────

function SMSContentPanel({
  variant,
  onSave,
}: {
  variant: SMSVariant;
  onSave: (variantId: string, updates: Record<string, string>) => Promise<void>;
}) {
  const [editing, setEditing]   = useState(false);
  const [template, setTemplate] = useState(variant.template);
  const [saving, setSaving]     = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved]       = useState(false);

  useEffect(() => {
    setTemplate(variant.template);
    setEditing(false);
    setSaveError(null);
    setSaved(false);
  }, [variant.variant_id, variant.template]);

  const charCount  = template.length;
  const overLimit  = charCount > 320;
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

  return (
    <Card
      style={{
        background: "#161d27",
        border: "1px solid #253545",
        borderRadius: 8,
        padding: 0,
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "13px 20px",
          background: "#1c2a3a",
          borderBottom: "1px solid #253545",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <span style={{ color: "#9FA8DA", fontWeight: 700, fontSize: 14, flex: 1 }}>
          {variant.variant_id} · {variant.name}
        </span>
        <span style={{ color: "#738091", fontSize: 12 }}>{variant.framework}</span>
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
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: overLimit ? "#e06060" : oneSegment ? "#3ddc84" : "#738091",
          }}
        >
          {charCount} chars{" "}
          {oneSegment ? "· 1 segment ✓" : overLimit ? "· OVER LIMIT" : "· 2 segments"}
        </span>
      </div>

      {/* Message */}
      <div style={{ padding: "16px 20px", borderBottom: variant.ai_fills ? "1px solid #1e2d3d" : undefined }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 8,
          }}
        >
          <div style={SECTION_LABEL}>Message</div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            {editing ? (
              <>
                {saveError && (
                  <span style={{ color: "#e06060", fontSize: 11 }}>{saveError}</span>
                )}
                <Button intent="primary" icon="floppy-disk" small loading={saving} onClick={handleSave}>
                  Save
                </Button>
                <Button
                  small
                  onClick={() => {
                    setTemplate(variant.template);
                    setEditing(false);
                    setSaveError(null);
                  }}
                >
                  Cancel
                </Button>
              </>
            ) : (
              <Button icon="edit" small minimal onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
          </div>
        </div>
        {editing ? (
          <TextArea
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            fill
            rows={5}
            style={{
              fontFamily: "monospace",
              fontSize: 13,
              background: "#0f1923",
              color: "#f6f7f9",
              resize: "vertical",
            }}
          />
        ) : (
          <div
            style={{
              ...CODE_BOX,
              fontSize: 13,
              whiteSpace: "pre-wrap",
            }}
          >
            <HighlightedTemplate text={template} />
          </div>
        )}
      </div>

      {/* AI fills */}
      {variant.ai_fills && (
        <div
          style={{
            padding: "10px 20px",
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
          }}
        >
          <span style={{ ...SECTION_LABEL, marginBottom: 0 }}>AI fills per lead:</span>
          {variant.ai_fills
            .split(",")
            .map((f) => f.trim())
            .filter(Boolean)
            .map((f) => (
              <Tag
                key={f}
                minimal
                style={{ fontSize: 10, color: "#76D7C4", background: "rgba(118,215,196,0.1)" }}
              >
                {f}
              </Tag>
            ))}
        </div>
      )}
    </Card>
  );
}

// ─── Variant tab strip ────────────────────────────────────────────────────────

function VariantTabStrip({
  variants,
  selected,
  getLabel,
  isEdited,
  onSelect,
}: {
  variants: string[];
  selected: string;
  getLabel: (id: string) => string;
  isEdited: (id: string) => boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        gap: 0,
        border: "1px solid #253545",
        borderRadius: 8,
        overflow: "hidden",
        marginBottom: 16,
        overflowX: "auto",
      }}
    >
      {variants.map((id, i) => {
        const active = selected === id;
        return (
          <button
            key={id}
            onClick={() => onSelect(id)}
            style={{
              padding: "9px 18px",
              background: active ? "#1c3a5e" : "#161d27",
              border: "none",
              borderRight: i < variants.length - 1 ? "1px solid #253545" : "none",
              color: active ? "#90caf9" : "#738091",
              fontSize: 12,
              fontWeight: active ? 700 : 400,
              cursor: "pointer",
              transition: "background 0.15s, color 0.15s",
              whiteSpace: "nowrap",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            {getLabel(id)}
            {isEdited(id) && (
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: "#4c90f0",
                  flexShrink: 0,
                }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function PlaybookPage() {
  const [tab, setTab]                             = useState<Tab>("email");
  const [selectedMarket, setSelectedMarket]       = useState("coach");
  const [selectedEmailVariant, setEmailVariant]   = useState("Variant 1");
  const [selectedSMSVariant, setSMSVariant]       = useState("SMS-V1");
  const [videoMode, setVideoMode]                 = useState<"all" | "video" | "email_only">("all");
  const [data, setData]                           = useState<PlaybookData | null>(null);
  const [subjectPerf, setSubjectPerf]             = useState<SubjectLinePerf[]>([]);
  const [loading, setLoading]                     = useState(true);
  const [error, setError]                         = useState<string | null>(null);

  const load = useCallback(async (market: string) => {
    try {
      setError(null);
      setLoading(true);
      const [pr, perfR] = await Promise.all([
        fetch(`/api/playbook?market=${market}`),
        fetch("/api/analytics/subject-lines?min_sent=10"),
      ]);
      if (!pr.ok) throw new Error(`${pr.status} ${pr.statusText}`);
      setData(await pr.json());
      if (perfR.ok) setSubjectPerf((await perfR.json()).subject_lines ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(selectedMarket);
  }, [load, selectedMarket]);

  const handleSave = async (
    channel: "email" | "sms",
    variantId: string,
    updates: Record<string, string>
  ) => {
    const r = await fetch("/api/playbook/template", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel, variant_id: variantId, updates, market: selectedMarket }),
    });
    if (!r.ok) throw new Error(`Save failed: ${r.status} ${await r.text()}`);
    await load(selectedMarket);
  };

  if (loading)
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <Spinner size={40} />
        <p style={{ color: "#738091", marginTop: 16 }}>Loading playbook…</p>
      </div>
    );

  if (error)
    return (
      <NonIdealState
        icon="error"
        title="Could not load playbook"
        description={error}
        action={
          <Button intent="primary" onClick={() => load(selectedMarket)}>
            Retry
          </Button>
        }
      />
    );

  const emailVariants = data?.email ?? [];
  const smsVariants   = data?.sms   ?? [];

  const selectedEmailData = emailVariants.find((v) => v.variant_id === selectedEmailVariant);
  const selectedSMSData   = smsVariants.find((v) => v.variant_id === selectedSMSVariant);

  const emailEdited = emailVariants.filter((v) => v.is_edited).length;
  const smsEdited   = smsVariants.filter((v) => v.is_edited).length;

  return (
    <div>
      {/* Page header */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          marginBottom: 20,
        }}
      >
        <h1 className="page-title" style={{ margin: 0 }}>
          Playbook
        </h1>
        <span style={{ fontSize: 12, color: "#5f6b7c" }}>
          <span style={{ color: "#76D7C4", fontFamily: "monospace" }}>{"{highlighted}"}</span>
          {" "}= AI-filled per lead · plain text is your fixed template
        </span>
      </div>

      {/* ── ICP selector ─────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 22 }}>
        <div style={{ ...SECTION_LABEL, marginBottom: 8 }}>Target ICP</div>
        <div
          style={{
            display: "inline-flex",
            gap: 0,
            border: "1px solid #253545",
            borderRadius: 8,
            overflow: "hidden",
          }}
        >
          {ICP_MARKETS.map(({ key, label, icon }, i) => {
            const active = selectedMarket === key;
            return (
              <button
                key={key}
                onClick={() => setSelectedMarket(key)}
                style={{
                  padding: "9px 22px",
                  background: active ? "#215db0" : "#161d27",
                  border: "none",
                  borderRight: i < ICP_MARKETS.length - 1 ? "1px solid #253545" : "none",
                  color: active ? "#fff" : "#738091",
                  fontSize: 13,
                  fontWeight: active ? 700 : 400,
                  cursor: "pointer",
                  transition: "background 0.15s, color 0.15s",
                  whiteSpace: "nowrap",
                  display: "flex",
                  alignItems: "center",
                  gap: 7,
                }}
              >
                <span>{icon}</span>
                <span>{label}</span>
              </button>
            );
          })}
        </div>
        {MARKET_CONTEXT[selectedMarket] && (
          <div style={{ marginTop: 8, fontSize: 12, color: "#5f6b7c" }}>
            {MARKET_CONTEXT[selectedMarket]}
          </div>
        )}
      </div>

      {/* ── Channel tabs ─────────────────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          gap: 0,
          marginBottom: 20,
          borderBottom: "1px solid #253545",
        }}
      >
        {(
          [
            { key: "email"    as Tab, label: "✉️ Email",    count: emailVariants.length, edited: emailEdited },
            { key: "sms"      as Tab, label: "📱 SMS",      count: smsVariants.length,   edited: smsEdited   },
            { key: "subjects" as Tab, label: "📊 Subjects", count: subjectPerf.length,   edited: 0           },
          ] as { key: Tab; label: string; count: number; edited: number }[]
        ).map(({ key, label, count, edited }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            style={{
              background: "none",
              border: "none",
              borderBottom: tab === key ? "2px solid #215db0" : "2px solid transparent",
              color: tab === key ? "#f6f7f9" : "#738091",
              padding: "9px 22px",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: tab === key ? 600 : 400,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            {label}
            <span
              style={{
                background: "#1c2a3a",
                borderRadius: 10,
                padding: "1px 7px",
                fontSize: 11,
                color: "#738091",
              }}
            >
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

      {/* ── Email tab ────────────────────────────────────────────────────── */}
      {tab === "email" && (
        <div>
          {/* Send mode toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 18 }}>
            <span style={{ ...SECTION_LABEL, marginBottom: 0 }}>Send Mode:</span>
            {(
              [
                { key: "all"        as const, label: "All" },
                { key: "video"      as const, label: "📹 With Video (Score 8-10)" },
                { key: "email_only" as const, label: "✉️ Email Only (Score 1-7)" },
              ] as { key: "all" | "video" | "email_only"; label: string }[]
            ).map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setVideoMode(key)}
                style={{
                  background: videoMode === key ? "#1c2a3a" : "transparent",
                  border: videoMode === key ? "1px solid #253545" : "1px solid transparent",
                  borderRadius: 20,
                  color: videoMode === key ? "#f6f7f9" : "#5f6b7c",
                  padding: "4px 14px",
                  fontSize: 12,
                  fontWeight: videoMode === key ? 600 : 400,
                  cursor: "pointer",
                  transition: "all 0.15s",
                  whiteSpace: "nowrap",
                }}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Variant tab strip */}
          <VariantTabStrip
            variants={emailVariants.map((v) => v.variant_id)}
            selected={selectedEmailVariant}
            getLabel={(id) => VARIANT_LABEL[id] ?? id}
            isEdited={(id) => emailVariants.find((v) => v.variant_id === id)?.is_edited ?? false}
            onSelect={setEmailVariant}
          />

          {/* Content panel */}
          {selectedEmailData ? (
            <EmailContentPanel
              variant={selectedEmailData}
              subjectPerf={subjectPerf}
              videoMode={videoMode}
              onSave={(vid, updates) => handleSave("email", vid, updates)}
            />
          ) : (
            <div style={{ textAlign: "center", color: "#5f6b7c", padding: 48 }}>
              Select a variant above
            </div>
          )}
        </div>
      )}

      {/* ── SMS tab ──────────────────────────────────────────────────────── */}
      {tab === "sms" && (
        <div>
          {/* SMS variant tab strip */}
          <VariantTabStrip
            variants={smsVariants.map((v) => v.variant_id)}
            selected={selectedSMSVariant}
            getLabel={(id) => id}
            isEdited={(id) => smsVariants.find((v) => v.variant_id === id)?.is_edited ?? false}
            onSelect={setSMSVariant}
          />

          {selectedSMSData ? (
            <SMSContentPanel
              variant={selectedSMSData}
              onSave={(vid, updates) => handleSave("sms", vid, updates)}
            />
          ) : (
            <div style={{ textAlign: "center", color: "#5f6b7c", padding: 48 }}>
              Select a variant above
            </div>
          )}
        </div>
      )}

      {/* ── Subject Lines tab ─────────────────────────────────────────────── */}
      {tab === "subjects" && (
        <div>
          <div style={{ color: "#738091", fontSize: 13, marginBottom: 20 }}>
            Live performance by subject line — sorted by reply rate. Rows appear once
            10+ sends have been recorded to remove noise.
          </div>

          {subjectPerf.length === 0 ? (
            <div
              style={{
                background: "#161d27",
                borderRadius: 8,
                padding: "32px 24px",
                textAlign: "center",
                border: "1px solid #253545",
              }}
            >
              <div style={{ fontSize: 32, marginBottom: 12 }}>📬</div>
              <div style={{ color: "#f6f7f9", fontSize: 15, fontWeight: 600, marginBottom: 8 }}>
                No data yet
              </div>
              <div style={{ color: "#738091", fontSize: 13 }}>
                Subject line performance appears once leads start being sent (10+ sends per line).
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
                  <tr style={{ borderBottom: "1px solid #253545" }}>
                    {["Rank", "Subject Line", "Variant", "Sent", "Open %", "Reply %", "Book %"].map((h) => (
                      <th
                        key={h}
                        style={{
                          padding: "8px 12px",
                          textAlign: "left",
                          color: "#5f6b7c",
                          fontSize: 10,
                          textTransform: "uppercase",
                          letterSpacing: "0.07em",
                          fontWeight: 700,
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
                      const replyColor = row.reply_rate >= 8 ? "#3ddc84" : row.reply_rate >= 4 ? "#f0b429" : "#e06060";
                      const openColor  = row.open_rate  >= 40 ? "#3ddc84" : row.open_rate  >= 25 ? "#f0b429" : "#e06060";
                      const isLeader   = i === 0;
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
                          <td
                            style={{
                              padding: "10px 12px",
                              fontFamily: "monospace",
                              fontSize: 12,
                              maxWidth: 320,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
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
                          <td style={{ padding: "10px 12px", color: openColor, fontWeight: 600 }}>
                            {row.open_rate.toFixed(1)}%
                          </td>
                          <td style={{ padding: "10px 12px", color: replyColor, fontWeight: 700 }}>
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
            Thresholds — Open: green ≥40%, amber ≥25%, red &lt;25% · Reply: green ≥8%, amber ≥4%, red &lt;4%
          </div>
        </div>
      )}
    </div>
  );
}
