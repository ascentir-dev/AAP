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
import { fetchLeads, fetchLead } from "../api/client";
import type { Lead, LeadDetail } from "../api/types";

const STATUS_INTENT: Record<string, Intent> = {
  sent: "success",
  dry_run: "primary",
  skipped: "warning",
  failed: "danger",
  processing: "primary",
};

function StatusTag({ status }: { status?: string }) {
  const s = status ?? "unknown";
  return (
    <Tag intent={STATUS_INTENT[s] ?? "none"} minimal>
      {s}
    </Tag>
  );
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
    | { video_url?: string; landing_url?: string }
    | undefined;
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
                    {email.body ?? "No body generated yet."}
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
const STATUSES = ["all", "sent", "dry_run", "skipped", "failed"];

export function LeadsPage() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

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

  const filtered = search
    ? leads.filter(
        (l) =>
          l.email.toLowerCase().includes(search.toLowerCase()) ||
          (l.company ?? "").toLowerCase().includes(search.toLowerCase())
      )
    : leads;

  const totalPages = Math.ceil(total / PAGE_SIZE);

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
              {s}
            </Button>
          ))}
        </ButtonGroup>
        <span style={{ fontSize: 12, color: "#738091", marginLeft: "auto" }}>
          {total.toLocaleString()} leads total
        </span>
      </div>

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
                  <th>Name</th>
                  <th>Company</th>
                  <th>Email</th>
                  <th>Vertical</th>
                  <th>Variant</th>
                  <th>Framework</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((l) => (
                  <tr
                    key={l.lead_id}
                    onClick={() => setSelectedId(l.lead_id)}
                    style={{ cursor: "pointer" }}
                  >
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
