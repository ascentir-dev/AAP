import { useEffect, useState, useCallback, useRef } from "react";
import {
  InputGroup,
  Button,
  Tag,
  Spinner,
  NonIdealState,
} from "@blueprintjs/core";

// ─── Types ────────────────────────────────────────────────────────────────────

interface SMSLead {
  lead_id: string;
  first_name: string;
  last_name: string;
  phone: string;
  company: string;
  role: string;
  status: string;
  assigned_number: string;
  variant_id: string;
  last_message?: string;
  last_message_at?: number;
  unread?: boolean;
}

interface SMSMessage {
  id: number;
  lead_id: string;
  direction: "outbound" | "inbound";
  from_number: string;
  to_number: string;
  body: string;
  twilio_sid: string;
  variant_id?: string;
  sent_at: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatTime(ts: number) {
  const d = new Date(ts * 1000);
  const now = new Date();
  const diffDays = Math.floor(
    (now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24)
  );
  if (diffDays === 0) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return d.toLocaleDateString([], { weekday: "short" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function statusIntent(
  status: string
): "none" | "primary" | "success" | "warning" | "danger" {
  switch (status) {
    case "replied":
      return "success";
    case "sent":
      return "primary";
    case "opted_out":
      return "danger";
    case "booked":
      return "success";
    default:
      return "none";
  }
}

function maskPhone(phone: string) {
  if (phone.length >= 10) return phone.slice(0, -4) + "****";
  return phone;
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function SMSConversationsPage() {
  const [leads, setLeads] = useState<SMSLead[]>([]);
  const [selectedLead, setSelectedLead] = useState<SMSLead | null>(null);
  const [messages, setMessages] = useState<SMSMessage[]>([]);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [leadsLoading, setLeadsLoading] = useState(true);
  const [msgsLoading, setMsgsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);

  // Load leads list
  const loadLeads = useCallback(async () => {
    try {
      const r = await fetch("/api/sms/leads");
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const d: { leads: SMSLead[] } = await r.json();
      setLeads(d.leads);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLeadsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLeads();
    const id = setInterval(loadLeads, 15_000);
    return () => clearInterval(id);
  }, [loadLeads]);

  // Load conversation for selected lead
  const loadConversation = useCallback(async (lead: SMSLead) => {
    setMsgsLoading(true);
    try {
      const r = await fetch(
        `/api/sms/conversations/${encodeURIComponent(lead.lead_id)}`
      );
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const d: { messages: SMSMessage[] } = await r.json();
      setMessages(d.messages);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setMsgsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedLead) return;
    loadConversation(selectedLead);
    const id = setInterval(() => loadConversation(selectedLead), 10_000);
    return () => clearInterval(id);
  }, [selectedLead, loadConversation]);

  // Scroll to bottom when messages change
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSelectLead = (lead: SMSLead) => {
    setSelectedLead(lead);
    setReplyText("");
    setSendError(null);
    setMessages([]);
  };

  const handleSend = async () => {
    if (!selectedLead || !replyText.trim()) return;
    setSending(true);
    setSendError(null);
    try {
      const r = await fetch("/api/sms/reply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lead_id: selectedLead.lead_id,
          body: replyText.trim(),
        }),
      });
      if (!r.ok) {
        const txt = await r.text();
        throw new Error(`${r.status}: ${txt}`);
      }
      setReplyText("");
      await loadConversation(selectedLead);
      await loadLeads();
    } catch (e: unknown) {
      setSendError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSend();
    }
  };

  const filteredLeads = leads.filter((l) => {
    if (!filter) return true;
    const q = filter.toLowerCase();
    return (
      l.first_name?.toLowerCase().includes(q) ||
      l.last_name?.toLowerCase().includes(q) ||
      l.company?.toLowerCase().includes(q) ||
      l.phone?.includes(q)
    );
  });

  if (leadsLoading) {
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <Spinner size={40} />
        <p style={{ color: "#738091", marginTop: 16 }}>Loading conversations…</p>
      </div>
    );
  }

  if (error && leads.length === 0) {
    return (
      <NonIdealState
        icon="error"
        title="Could not load SMS conversations"
        description={error}
        action={
          <Button intent="primary" onClick={loadLeads}>
            Retry
          </Button>
        }
      />
    );
  }

  return (
    <div style={{ display: "flex", height: "calc(100vh - 60px)", gap: 0 }}>
      {/* ── Left panel — lead list ── */}
      <div
        style={{
          width: 300,
          minWidth: 260,
          borderRight: "1px solid #30404d",
          display: "flex",
          flexDirection: "column",
          background: "#1a2433",
        }}
      >
        <div style={{ padding: "16px 12px 8px" }}>
          <h2 style={{ margin: "0 0 10px", fontSize: 16, color: "#f6f7f9" }}>
            SMS Conversations
          </h2>
          <InputGroup
            placeholder="Search leads…"
            leftIcon="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            small
          />
        </div>

        {filteredLeads.length === 0 ? (
          <div
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#738091",
              fontSize: 13,
              padding: 24,
              textAlign: "center",
            }}
          >
            {leads.length === 0
              ? "No SMS leads yet. Run the SMS pipeline to start conversations."
              : "No leads match your search."}
          </div>
        ) : (
          <div style={{ flex: 1, overflowY: "auto" }}>
            {filteredLeads.map((lead) => {
              const isActive = selectedLead?.lead_id === lead.lead_id;
              return (
                <button
                  key={lead.lead_id}
                  onClick={() => handleSelectLead(lead)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    background: isActive ? "#253545" : "transparent",
                    border: "none",
                    borderBottom: "1px solid #1e2d3d",
                    padding: "10px 14px",
                    cursor: "pointer",
                    transition: "background 0.1s",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive)
                      (e.currentTarget as HTMLButtonElement).style.background =
                        "#1e2d3d";
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive)
                      (e.currentTarget as HTMLButtonElement).style.background =
                        "transparent";
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <span
                      style={{
                        fontWeight: 600,
                        color: "#f6f7f9",
                        fontSize: 13,
                      }}
                    >
                      {lead.first_name} {lead.last_name}
                    </span>
                    {lead.last_message_at && (
                      <span style={{ color: "#738091", fontSize: 11 }}>
                        {formatTime(lead.last_message_at)}
                      </span>
                    )}
                  </div>
                  <div
                    style={{
                      color: "#738091",
                      fontSize: 12,
                      marginTop: 2,
                    }}
                  >
                    {lead.company}
                    {lead.role ? ` · ${lead.role}` : ""}
                  </div>
                  <div
                    style={{
                      display: "flex",
                      gap: 6,
                      marginTop: 4,
                      alignItems: "center",
                    }}
                  >
                    <Tag
                      minimal
                      intent={statusIntent(lead.status)}
                      style={{ fontSize: 10 }}
                    >
                      {lead.status}
                    </Tag>
                    {lead.variant_id && (
                      <Tag minimal style={{ fontSize: 10 }}>
                        {lead.variant_id}
                      </Tag>
                    )}
                  </div>
                  {lead.last_message && (
                    <div
                      style={{
                        color: "#5f6b7c",
                        fontSize: 11,
                        marginTop: 4,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        maxWidth: 240,
                      }}
                    >
                      {lead.last_message}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* ── Right panel — conversation thread ── */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          background: "#192433",
        }}
      >
        {!selectedLead ? (
          <div
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <NonIdealState
              icon="mobile-phone"
              title="Select a conversation"
              description="Choose a lead from the left panel to view their SMS thread."
            />
          </div>
        ) : (
          <>
            {/* Thread header */}
            <div
              style={{
                padding: "14px 20px",
                borderBottom: "1px solid #30404d",
                background: "#1a2433",
                display: "flex",
                alignItems: "center",
                gap: 12,
              }}
            >
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: "50%",
                  background: "#253F6E",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#90CAF9",
                  fontWeight: 700,
                  fontSize: 14,
                  flexShrink: 0,
                }}
              >
                {(selectedLead.first_name?.[0] || "?").toUpperCase()}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ color: "#f6f7f9", fontWeight: 600, fontSize: 15 }}>
                  {selectedLead.first_name} {selectedLead.last_name}
                </div>
                <div style={{ color: "#738091", fontSize: 12 }}>
                  {selectedLead.company} ·{" "}
                  <code style={{ color: "#738091" }}>
                    {maskPhone(selectedLead.phone)}
                  </code>{" "}
                  · via{" "}
                  <code style={{ color: "#738091" }}>
                    {maskPhone(selectedLead.assigned_number || "")}
                  </code>
                </div>
              </div>
              <Tag
                minimal
                intent={statusIntent(selectedLead.status)}
                style={{ fontSize: 11 }}
              >
                {selectedLead.status}
              </Tag>
              {selectedLead.status === "opted_out" && (
                <Tag intent="danger" minimal icon="ban-circle">
                  Opted out
                </Tag>
              )}
            </div>

            {/* Message thread */}
            <div
              ref={threadRef}
              style={{
                flex: 1,
                overflowY: "auto",
                padding: "20px 20px 8px",
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              {msgsLoading && messages.length === 0 ? (
                <div style={{ textAlign: "center", paddingTop: 40 }}>
                  <Spinner size={24} />
                </div>
              ) : messages.length === 0 ? (
                <div
                  style={{
                    textAlign: "center",
                    color: "#738091",
                    paddingTop: 40,
                  }}
                >
                  No messages yet.
                </div>
              ) : (
                messages.map((msg) => {
                  const isOutbound = msg.direction === "outbound";
                  return (
                    <div
                      key={msg.id}
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: isOutbound ? "flex-end" : "flex-start",
                      }}
                    >
                      <div
                        style={{
                          maxWidth: "70%",
                          background: isOutbound ? "#1D6FA4" : "#253545",
                          color: "#f6f7f9",
                          borderRadius: isOutbound
                            ? "18px 18px 4px 18px"
                            : "18px 18px 18px 4px",
                          padding: "10px 14px",
                          fontSize: 14,
                          lineHeight: 1.5,
                          wordBreak: "break-word",
                        }}
                      >
                        {msg.body}
                      </div>
                      <div
                        style={{
                          color: "#5f6b7c",
                          fontSize: 10,
                          marginTop: 3,
                          marginLeft: isOutbound ? 0 : 4,
                          marginRight: isOutbound ? 4 : 0,
                        }}
                      >
                        {formatTime(msg.sent_at)}{" "}
                        {isOutbound ? "· You" : "· Lead"}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Reply input */}
            <div
              style={{
                padding: "12px 16px",
                borderTop: "1px solid #30404d",
                background: "#1a2433",
              }}
            >
              {selectedLead.status === "opted_out" ? (
                <div
                  style={{
                    textAlign: "center",
                    color: "#e06060",
                    fontSize: 13,
                    padding: "8px 0",
                  }}
                >
                  This lead has opted out. You cannot send more messages.
                </div>
              ) : (
                <>
                  {sendError && (
                    <div
                      style={{
                        color: "#e06060",
                        fontSize: 12,
                        marginBottom: 6,
                      }}
                    >
                      {sendError}
                    </div>
                  )}
                  <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
                    <textarea
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Type your reply… (⌘↵ to send)"
                      style={{
                        flex: 1,
                        background: "#253545",
                        border: "1px solid #30404d",
                        borderRadius: 8,
                        color: "#f6f7f9",
                        padding: "10px 12px",
                        fontSize: 13,
                        resize: "none",
                        minHeight: 56,
                        maxHeight: 120,
                        outline: "none",
                        fontFamily: "inherit",
                      }}
                      rows={2}
                    />
                    <Button
                      intent="primary"
                      icon="send-message"
                      loading={sending}
                      disabled={!replyText.trim() || sending}
                      onClick={handleSend}
                      style={{ flexShrink: 0 }}
                    >
                      Send
                    </Button>
                  </div>
                  <div
                    style={{
                      color: "#5f6b7c",
                      fontSize: 10,
                      marginTop: 4,
                    }}
                  >
                    {replyText.length}/320 chars · sending from{" "}
                    {maskPhone(selectedLead.assigned_number || "—")}
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
