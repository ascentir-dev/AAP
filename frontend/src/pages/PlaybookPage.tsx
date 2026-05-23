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
  if (!text) return <span style={{ color: "#5f6b7c", fontStyle: "italic" }}>No template set — uses default from prompts/</span>;
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
  onSave: (variantId: string, updates: Record<string, string>) => Promise<void>;
}

function EmailVariantCard({ variant, onSave }: EmailCardProps) {
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

          {/* Subject formula */}
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
          {variant.name} — <span style={{ color: "#738091" }}>{variant.framework}</span>
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

// ─── Main Page ────────────────────────────────────────────────────────────────

type Tab = "email" | "sms";

export function PlaybookPage() {
  const [data, setData] = useState<PlaybookData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("email");

  const load = useCallback(async () => {
    try {
      setError(null);
      const r = await fetch("/api/playbook");
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const d: PlaybookData = await r.json();
      setData(d);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

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
    await load();
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
        action={<Button intent="primary" onClick={load}>Retry</Button>}
      />
    );
  }

  const emailVariants = data?.email ?? [];
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
        The plain text is your fixed template. Edit any variant and save — it
        takes effect on the next lead processed, no restart needed.
      </Callout>

      {/* Tab bar */}
      <div style={{ display: "flex", gap: 0, marginBottom: 20, borderBottom: "1px solid #30404d" }}>
        {(["email", "sms"] as Tab[]).map((t) => {
          const count  = t === "email" ? emailVariants.length : smsVariants.length;
          const edited = t === "email" ? editedEmail : editedSms;
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                background: "none",
                border: "none",
                borderBottom: tab === t ? "2px solid #1D6FA4" : "2px solid transparent",
                color: tab === t ? "#f6f7f9" : "#738091",
                padding: "8px 20px",
                cursor: "pointer",
                fontSize: 14,
                fontWeight: tab === t ? 600 : 400,
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              {t === "email" ? "✉️ Email Templates" : "📱 SMS Templates"}
              <span
                style={{
                  background: "#253545",
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
          );
        })}
      </div>

      {/* Email tab */}
      {tab === "email" && (
        <div>
          <div style={{ color: "#738091", fontSize: 13, marginBottom: 16 }}>
            9 variants running in your framework tournament. Click any variant to
            expand it, review the template, and edit. Changes override the default
            prompt — the AI will follow your custom structure instead.
          </div>
          {emailVariants.map((v) => (
            <EmailVariantCard
              key={v.variant_id}
              variant={v}
              onSave={(vid, updates) => handleSave("email", vid, updates)}
            />
          ))}
        </div>
      )}

      {/* SMS tab */}
      {tab === "sms" && (
        <div>
          <div style={{ color: "#738091", fontSize: 13, marginBottom: 16 }}>
            6 SMS variants optimized for text message replies. Targets are 1 segment
            (≤160 chars) — shown in green. Keep{" "}
            <span style={{ color: "#76D7C4" }}>{"{VIDEO_LINK}"}</span> in every
            template — the system replaces it with the lead's personalized video URL.
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
    </div>
  );
}
