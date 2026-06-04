import { useEffect, useState, useCallback } from "react";
import {
  InputGroup,
  HTMLTable,
  Tag,
  Spinner,
  Button,
  Drawer,
  DrawerSize,
  H5,
  Divider,
  NonIdealState,
  ButtonGroup,
  Intent,
} from "@blueprintjs/core";
import {
  fetchLeads,
  fetchLead,
  deleteLead,
  bulkDeleteLeads,
  deleteEmailOnlyLeads,
} from "../api/client";
import type { Lead, LeadDetail } from "../api/types";

const STATUS_INTENT: Record<string, Intent> = {
  sent: "success",
  dry_run: "primary",
  skipped: "warning",
  failed: "danger",
  processing: "primary",
};

const STATUS_LABEL: Record<string, string> = {
  dry_run: "Personalised",
  sent: "Sent",
  skipped: "Skipped",
  failed: "Failed",
  processing: "Processing",
};

function StatusTag({ status }: { status?: string }) {
  const s = status ?? "unknown";
  return (
    <Tag intent={STATUS_INTENT[s] ?? "none"} minimal>
      {STATUS_LABEL[s] ?? s}
    </Tag>
  );
}

function EmailTypeTag({ emailType }: { emailType?: string }) {
  if (emailType === "video") {
    return (
      <Tag
        minimal
        style={{
          background: "rgba(0,200,150,0.15)",
          color: "#00c896",
          border: "1px solid rgba(0,200,150,0.3)",
        }}
      >
        📹 Video
      </Tag>
    );
  }
  if (emailType === "email_only") {
    return (
      <Tag
        minimal
        style={{
          background: "rgba(140,150,160,0.15)",
          color: "#8c9299",
          border: "1px solid rgba(140,150,160,0.3)",
        }}
      >
        ✉️ Email
      </Tag>
    );
  }
  return null;
}

function LeadDrawer({
  leadId,
  onClose,
}: {
  leadId: string | null;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!leadId) return;
    setLoading(true);
    setDetail(null);
    fetchLead(leadId)
      .then(setDetail)
      .finally(() => setLoading(false));
  }, [leadId]);

  const email = detail?.stages?.email as
    | { subject?: string; body?: string; variant_id?: string; framework_used?: string }
    | undefined;
  const hosting = detail?.stages?.hosting as
    | { video_url?: string; landing_url?: string; email_only?: boolean }
    | undefined;

  // Resolve the email body for preview — replace {VIDEO_LINK} placeholder so the user
  // never sees the raw token. Email-only leads show the Reply VIDEO CTA text.
  // Video leads show a "(personalized video link)" note.
  const resolvedEmailBody = (() => {
    const body = email?.body ?? "";
    if (!body.includes("{VIDEO_LINK}")) return body;
    if (hosting?.email_only) {
      return body.replace(
        "{VIDEO_LINK}",
        `\n→ Reply VIDEO and I'll send you a personalized demo of the AI Client Acquisition System showing exactly how we'll book ${detail?.company ?? "your company"}. No call. No pitch. Just the demo.\n`
      );
    }
    return body.replace("{VIDEO_LINK}", "\n→ [Personalized video link goes here]\n");
  })();
  const analysis = detail?.stages?.analysis as
    | { vertical?: string; motion?: string; intent_confidence?: number; personalized_hook?: string; recommended_angle?: string }
    | undefined;

  return (
    <Drawer
      isOpen={!!leadId}
      onClose={onClose}
      title={detail ? `${detail.first_name ?? ""} ${detail.last_name ?? ""} — ${detail.company ?? ""}` : "Lead Detail"}
      size={DrawerSize.STANDARD}
      className="bp5-dark"
    >
      <div className="lead-drawer-inner">
        {loading && (
          <div style={{ textAlign: "center", padding: 32 }}>
            <Spinner size={32} />
          </div>
        )}

        {!loading && detail && (
          <>
            {/* Basic info */}
            <div>
              <H5 style={{ color: "#f6f7f9", marginBottom: 8 }}>Lead Info</H5>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                  fontSize: 13,
                }}
              >
                {[
                  ["Email", detail.email],
                  ["Company", detail.company],
                  ["Role", detail.role],
                  ["Website", detail.website],
                  ["Status", detail.status],
                  ["Variant", detail.variant_id],
                ].map(([label, value]) => (
                  <div key={label}>
                    <span style={{ color: "#5f6b7c", fontSize: 11 }}>{label}</span>
                    <div style={{ color: "#abb3bf" }}>{value ?? "—"}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Analysis */}
            {analysis && (
              <>
                <Divider />
                <div>
                  <H5 style={{ color: "#f6f7f9", marginBottom: 8 }}>AI Analysis</H5>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 8,
                      fontSize: 13,
                    }}
                  >
                    {[
                      ["Vertical", analysis.vertical],
                      ["Motion", analysis.motion],
                      ["Intent Score", analysis.intent_confidence],
                      ["Angle", analysis.recommended_angle],
                    ].map(([label, value]) => (
                      <div key={String(label)}>
                        <span style={{ color: "#5f6b7c", fontSize: 11 }}>
                          {label}
                        </span>
                        <div style={{ color: "#abb3bf" }}>{value ?? "—"}</div>
                      </div>
                    ))}
                  </div>
                  {analysis.personalized_hook && (
                    <div style={{ marginTop: 8 }}>
                      <span style={{ color: "#5f6b7c", fontSize: 11 }}>
                        Personalized Hook
                      </span>
                      <div
                        style={{
                          color: "#abb3bf",
                          fontSize: 13,
                          marginTop: 2,
                          fontStyle: "italic",
                        }}
                      >
                        "{analysis.personalized_hook}"
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* Email preview */}
            {email && (
              <>
                <Divider />
                <div>
                  <H5 style={{ color: "#f6f7f9", marginBottom: 8 }}>
                    Email Preview{" "}
                    {email.framework_used && (
                      <Tag minimal intent="primary" style={{ marginLeft: 6 }}>
                        {email.framework_used}
                      </Tag>
                    )}
                  </H5>
                  {email.subject && (
                    <div
                      style={{
                        fontSize: 12,
                        color: "#5f6b7c",
                        marginBottom: 4,
                      }}
                    >
                      Subject:{" "}
                      <strong style={{ color: "#abb3bf" }}>{email.subject}</strong>
                    </div>
                  )}
                  <div className="email-preview">
                    {resolvedEmailBody || "No body generated yet."}
                  </div>
                </div>
              </>
            )}

            {/* Video */}
            {hosting?.video_url && (
              <>
                <Divider />
                <div>
                  <H5 style={{ color: "#f6f7f9", marginBottom: 8 }}>
                    Personalized Video
                  </H5>
                  <div className="video-player">
                    <video
                      src={hosting.video_url}
                      controls
                      style={{ width: "100%", maxHeight: 300 }}
                    />
                  </div>
                  {hosting.landing_url && (
                    <div style={{ marginTop: 8 }}>
                      <a
                        href={hosting.landing_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ fontSize: 12, color: "#4c90f0" }}
                      >
                        View Landing Page ↗
                      </a>
                    </div>
                  )}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </Drawer>
  );
}

const PAGE_SIZE = 50;
const STATUSES = ["all", "dry_run", "skipped", "failed", "sent"];
const STATUS_DISPLAY: Record<string, string> = {
  all: "All",
  dry_run: "Personalised",
  skipped: "Skipped",
  failed: "Failed",
  sent: "Sent",
};

export function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Multi-select state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [deleteEmailOnlyLoading, setDeleteEmailOnlyLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const statusParam = status !== "all" ? status : undefined;
      const res = await fetchLeads(page, PAGE_SIZE, statusParam);
      setLeads(res.leads);
      setTotal(res.total);
    } finally {
      setLoading(false);
    }
  }, [page, status]);

  useEffect(() => {
    load();
  }, [load]);

  // Clear selection on page or filter change
  useEffect(() => {
    setSelectedIds(new Set());
  }, [page, status]);

  const filtered = search
    ? leads.filter(
        (l) =>
          l.email.toLowerCase().includes(search.toLowerCase()) ||
          (l.company ?? "").toLowerCase().includes(search.toLowerCase())
      )
    : leads;

  const totalPages = Math.ceil(total / PAGE_SIZE);

  // Select-all logic
  const allVisibleIds = filtered.map((l) => l.lead_id);
  const allSelected =
    allVisibleIds.length > 0 && allVisibleIds.every((id) => selectedIds.has(id));
  const someSelected =
    allVisibleIds.some((id) => selectedIds.has(id)) && !allSelected;

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(allVisibleIds));
    }
  };

  const toggleSelectOne = (leadId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(leadId)) {
        next.delete(leadId);
      } else {
        next.add(leadId);
      }
      return next;
    });
  };

  const handleBulkDelete = async () => {
    const ids = Array.from(selectedIds);
    if (!window.confirm(`Delete ${ids.length} leads? This cannot be undone.`)) return;
    setBulkDeleting(true);
    try {
      await bulkDeleteLeads(ids);
      setLeads((prev) => prev.filter((l) => !selectedIds.has(l.lead_id)));
      setTotal((t) => t - ids.length);
      setSelectedIds(new Set());
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setBulkDeleting(false);
    }
  };

  const handleDeleteEmailOnly = async () => {
    if (
      !window.confirm(
        "Delete all email-only leads? This keeps all video leads. Cannot be undone."
      )
    )
      return;
    setDeleteEmailOnlyLoading(true);
    try {
      const result = await deleteEmailOnlyLeads();
      alert(`Deleted ${result.deleted} email-only leads.`);
      await load();
      setSelectedIds(new Set());
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setDeleteEmailOnlyLoading(false);
    }
  };

  const hasEmailOnlyVisible = filtered.some((l) => l.email_type === "email_only");

  return (
    <div>
      <h1 className="page-title">Leads</h1>

      {/* Filters */}
      <div
        style={{
          display: "flex",
          gap: 12,
          marginBottom: 16,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <InputGroup
          placeholder="Search email or company…"
          leftIcon="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 280 }}
        />
        <ButtonGroup>
          {STATUSES.map((s) => (
            <Button
              key={s}
              active={status === s}
              onClick={() => {
                setStatus(s);
                setPage(0);
              }}
              small
            >
              {STATUS_DISPLAY[s] ?? s}
            </Button>
          ))}
        </ButtonGroup>
        <span style={{ fontSize: 12, color: "#738091", marginLeft: "auto" }}>
          {total.toLocaleString()} leads total
        </span>
        <a
          href="/api/leads/export"
          download="leads_export.csv"
          style={{ textDecoration: "none" }}
        >
          <Button icon="download" minimal>Export CSV</Button>
        </a>
        {hasEmailOnlyVisible && (
          <Button
            intent="danger"
            outlined
            small
            loading={deleteEmailOnlyLoading}
            onClick={handleDeleteEmailOnly}
          >
            Delete All Email-Only
          </Button>
        )}
      </div>

      {/* Selection action bar */}
      {selectedIds.size > 0 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            background: "#1c2127",
            border: "1px solid #e63946",
            borderRadius: 8,
            padding: "10px 16px",
            marginBottom: 12,
          }}
        >
          <span style={{ fontSize: 13, color: "#abb3bf" }}>
            ☑ {selectedIds.size} lead{selectedIds.size !== 1 ? "s" : ""} selected
          </span>
          <Button
            intent="danger"
            small
            loading={bulkDeleting}
            onClick={handleBulkDelete}
          >
            Delete Selected
          </Button>
          <Button
            small
            minimal
            onClick={() => setSelectedIds(new Set())}
          >
            Deselect All
          </Button>
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: "center", padding: 48 }}>
          <Spinner size={32} />
        </div>
      ) : filtered.length === 0 ? (
        <NonIdealState
          className="empty-state"
          icon="people"
          title="No leads found"
          description="Upload a CSV via the Pipeline tab to get started."
        />
      ) : (
        <>
          <div className="variant-table-wrap">
            <HTMLTable interactive style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th style={{ width: 32, paddingRight: 8 }}>
                    <input
                      type="checkbox"
                      checked={allSelected}
                      ref={(el) => {
                        if (el) el.indeterminate = someSelected;
                      }}
                      onChange={toggleSelectAll}
                      style={{ cursor: "pointer", width: 16, height: 16 }}
                    />
                  </th>
                  <th>Name</th>
                  <th>Company</th>
                  <th>Email</th>
                  <th>Vertical</th>
                  <th>Variant</th>
                  <th>Framework</th>
                  <th>Status</th>
                  <th>Type</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((l) => (
                  <tr
                    key={l.lead_id}
                    onClick={() => setSelectedId(l.lead_id)}
                    style={{ cursor: "pointer" }}
                  >
                    <td
                      style={{ paddingRight: 8 }}
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleSelectOne(l.lead_id);
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(l.lead_id)}
                        onChange={() => toggleSelectOne(l.lead_id)}
                        onClick={(e) => e.stopPropagation()}
                        style={{ cursor: "pointer", width: 16, height: 16 }}
                      />
                    </td>
                    <td>
                      {l.first_name ?? ""} {l.last_name ?? ""}
                    </td>
                    <td>{l.company ?? "—"}</td>
                    <td>{l.email}</td>
                    <td>{l.vertical ?? "—"}</td>
                    <td>
                      {l.variant_id ? (
                        <Tag minimal intent="primary">
                          {l.variant_id}
                        </Tag>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>{l.framework ?? "—"}</td>
                    <td>
                      <StatusTag status={l.status} />
                    </td>
                    <td>
                      <EmailTypeTag emailType={l.email_type} />
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <Button
                        icon="trash"
                        minimal
                        small
                        intent="danger"
                        onClick={async (e) => {
                          e.stopPropagation();
                          if (
                            !window.confirm(
                              `Delete ${l.first_name ?? ""} ${l.last_name ?? ""} @ ${l.company ?? l.email}? This cannot be undone.`
                            )
                          )
                            return;
                          try {
                            await deleteLead(l.lead_id);
                            setLeads((prev) =>
                              prev.filter((x) => x.lead_id !== l.lead_id)
                            );
                            setTotal((t) => t - 1);
                            setSelectedIds((prev) => {
                              const next = new Set(prev);
                              next.delete(l.lead_id);
                              return next;
                            });
                          } catch (err) {
                            alert(
                              err instanceof Error ? err.message : String(err)
                            );
                          }
                        }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </HTMLTable>
          </div>

          {/* Pagination */}
          <div
            style={{
              display: "flex",
              gap: 8,
              marginTop: 12,
              alignItems: "center",
              justifyContent: "flex-end",
            }}
          >
            <Button
              small
              disabled={page === 0}
              icon="chevron-left"
              onClick={() => setPage((p) => p - 1)}
            />
            <span style={{ fontSize: 12, color: "#738091" }}>
              Page {page + 1} / {totalPages}
            </span>
            <Button
              small
              disabled={page >= totalPages - 1}
              icon="chevron-right"
              onClick={() => setPage((p) => p + 1)}
            />
          </div>
        </>
      )}

      <LeadDrawer leadId={selectedId} onClose={() => setSelectedId(null)} />
    </div>
  );
}
