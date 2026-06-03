import { useEffect, useState } from "react";
import { Icon, Spinner, Tag } from "@blueprintjs/core";

interface VariantStats {
  variant_id: string;
  name: string;
  hook_style: string;
  description: string;
  script: string;
  sent: number;
  views: number;
  view_rate: number;
  replies: number;
  reply_rate: number;
  bookings: number;
  book_rate: number;
  leading: boolean;
}

interface RecentEvent {
  lead_id: string;
  company: string;
  variant_id: string;
  event_type: string;
  created_at: string;
}

function pct(n: number) {
  return (n * 100).toFixed(1) + "%";
}

function RateBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          height: 6,
          width: 90,
          background: "rgba(255,255,255,0.08)",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${Math.min(value * 100, 100)}%`,
            background: color,
            borderRadius: 3,
            transition: "width 0.6s ease",
          }}
        />
      </div>
      <span style={{ fontSize: 12, color: "#e0e0e0", minWidth: 36 }}>
        {pct(value)}
      </span>
    </div>
  );
}

const HOOK_LABELS: Record<string, { label: string; color: string }> = {
  two_reasons:       { label: "Two Reasons",   color: "#4a90d9" },
  not_a_robot:       { label: "Not a Robot",    color: "#7b68ee" },
  two_guesses:       { label: "Two Guesses",    color: "#50c878" },
  high_energy_bold:  { label: "High Energy",    color: "#ff7043" },
};

const EVENT_ICONS: Record<string, { icon: string; color: string; label: string }> = {
  viewed:  { icon: "eye-open",  color: "#4a90d9", label: "Viewed" },
  replied: { icon: "chat",      color: "#50c878", label: "Replied" },
  booked:  { icon: "calendar",  color: "#ffd700", label: "Booked" },
};

function ScriptModal({
  variant,
  onClose,
}: {
  variant: VariantStats;
  onClose: () => void;
}) {
  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
        zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#1e1e24", border: "1px solid rgba(255,255,255,0.1)",
          borderRadius: 12, padding: 32, maxWidth: 640, width: "90%",
          maxHeight: "80vh", overflow: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#fff" }}>
              {variant.variant_id}: {variant.name}
            </div>
            <div style={{ fontSize: 12, color: "#888", marginTop: 4 }}>
              {variant.description}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: "#888", cursor: "pointer", fontSize: 20 }}
          >
            ×
          </button>
        </div>
        <pre
          style={{
            whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 13,
            lineHeight: 1.7, color: "#ccc", background: "rgba(0,0,0,0.3)",
            padding: 16, borderRadius: 8, margin: 0,
          }}
        >
          {variant.script}
        </pre>
      </div>
    </div>
  );
}

export function VideoAnalyticsPage() {
  const [variants, setVariants] = useState<VariantStats[]>([]);
  const [recent, setRecent] = useState<RecentEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<VariantStats | null>(null);

  const load = async () => {
    try {
      const [analyticsRes, variantsRes] = await Promise.all([
        fetch("/api/video/analytics"),
        fetch("/api/video/variants"),
      ]);
      const analyticsData = await analyticsRes.json();
      const variantsData  = await variantsRes.json();

      // Merge script text into analytics
      const scriptMap: Record<string, string> = {};
      for (const v of variantsData.variants) {
        scriptMap[v.id] = v.script;
      }
      const merged = (analyticsData.variants as VariantStats[]).map((v) => ({
        ...v,
        script: scriptMap[v.variant_id] || "",
      }));
      setVariants(merged);
      setRecent(analyticsData.recent || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, []);

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
        <Spinner />
      </div>
    );
  }

  const totalSent    = variants.reduce((s, v) => s + v.sent,     0);
  const totalViews   = variants.reduce((s, v) => s + v.views,    0);
  const totalReplies = variants.reduce((s, v) => s + v.replies,  0);
  const totalBooked  = variants.reduce((s, v) => s + v.bookings, 0);

  return (
    <div style={{ padding: "28px 32px", maxWidth: 1100 }}>
      {selected && (
        <ScriptModal variant={selected} onClose={() => setSelected(null)} />
      )}

      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#fff" }}>
          Video Script A/B
        </h1>
        <p style={{ margin: "6px 0 0", color: "#888", fontSize: 13 }}>
          4 Loom-style variants tracking views → replies → bookings
        </p>
      </div>

      {/* Summary KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginBottom: 28 }}>
        {[
          { label: "Videos Sent",  value: totalSent,    icon: "video",    color: "#4a90d9" },
          { label: "Total Views",  value: totalViews,   icon: "eye-open", color: "#7b68ee" },
          { label: "Replies",      value: totalReplies, icon: "chat",     color: "#50c878" },
          { label: "Bookings",     value: totalBooked,  icon: "calendar", color: "#ffd700" },
        ].map((k) => (
          <div
            key={k.label}
            style={{
              background: "#1e1e24",
              border: "1px solid rgba(255,255,255,0.07)",
              borderRadius: 10, padding: "16px 20px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <Icon icon={k.icon as any} color={k.color} size={14} />
              <span style={{ fontSize: 11, color: "#888", textTransform: "uppercase", letterSpacing: 1 }}>
                {k.label}
              </span>
            </div>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#fff" }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Variant table */}
      <div
        style={{
          background: "#1e1e24",
          border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 10, overflow: "hidden", marginBottom: 28,
        }}
      >
        <div style={{ padding: "16px 20px", borderBottom: "1px solid rgba(255,255,255,0.07)" }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "#ccc" }}>
            Variant Performance
          </span>
        </div>

        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "rgba(0,0,0,0.2)" }}>
              {["Variant", "Style", "Sent", "Views", "View Rate", "Replies", "Reply Rate", "Bookings", "Book Rate", ""].map((h) => (
                <th
                  key={h}
                  style={{
                    padding: "10px 14px", textAlign: "left",
                    fontSize: 11, color: "#666",
                    textTransform: "uppercase", letterSpacing: 0.8,
                    fontWeight: 500, whiteSpace: "nowrap",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {variants.map((v, i) => {
              const hook = HOOK_LABELS[v.hook_style] || { label: v.hook_style, color: "#888" };
              return (
                <tr
                  key={v.variant_id}
                  style={{
                    borderTop: i > 0 ? "1px solid rgba(255,255,255,0.05)" : "none",
                    background: v.leading ? "rgba(80,200,120,0.05)" : "transparent",
                    transition: "background 0.15s",
                  }}
                >
                  <td style={{ padding: "14px 14px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span
                        style={{
                          fontSize: 11, fontWeight: 700,
                          background: "rgba(255,255,255,0.1)",
                          color: "#fff", padding: "2px 7px", borderRadius: 4,
                        }}
                      >
                        {v.variant_id}
                      </span>
                      {v.leading && (
                        <Tag
                          minimal intent="success"
                          style={{ fontSize: 10, padding: "1px 6px" }}
                        >
                          Leading
                        </Tag>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: "#888", marginTop: 3, maxWidth: 140 }}>
                      {v.name}
                    </div>
                  </td>
                  <td style={{ padding: "14px 14px" }}>
                    <span
                      style={{
                        fontSize: 10, fontWeight: 600,
                        background: hook.color + "22",
                        color: hook.color,
                        padding: "2px 8px", borderRadius: 4,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {hook.label}
                    </span>
                  </td>
                  <td style={{ padding: "14px 14px", color: "#ccc", fontSize: 14 }}>
                    {v.sent || <span style={{ color: "#555" }}>—</span>}
                  </td>
                  <td style={{ padding: "14px 14px", color: "#ccc", fontSize: 14 }}>
                    {v.views || <span style={{ color: "#555" }}>—</span>}
                  </td>
                  <td style={{ padding: "14px 14px" }}>
                    <RateBar value={v.view_rate} color="#7b68ee" />
                  </td>
                  <td style={{ padding: "14px 14px", color: "#ccc", fontSize: 14 }}>
                    {v.replies || <span style={{ color: "#555" }}>—</span>}
                  </td>
                  <td style={{ padding: "14px 14px" }}>
                    <RateBar value={v.reply_rate} color="#50c878" />
                  </td>
                  <td style={{ padding: "14px 14px", color: "#ccc", fontSize: 14 }}>
                    {v.bookings || <span style={{ color: "#555" }}>—</span>}
                  </td>
                  <td style={{ padding: "14px 14px" }}>
                    <RateBar value={v.book_rate} color="#ffd700" />
                  </td>
                  <td style={{ padding: "14px 14px" }}>
                    <button
                      onClick={() => setSelected(v)}
                      style={{
                        background: "rgba(255,255,255,0.06)",
                        border: "1px solid rgba(255,255,255,0.1)",
                        borderRadius: 6, color: "#aaa", fontSize: 11,
                        padding: "4px 10px", cursor: "pointer",
                        whiteSpace: "nowrap",
                      }}
                    >
                      View Script
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Recent activity */}
      <div
        style={{
          background: "#1e1e24",
          border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: 10, overflow: "hidden",
        }}
      >
        <div style={{ padding: "16px 20px", borderBottom: "1px solid rgba(255,255,255,0.07)" }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "#ccc" }}>
            Live Activity
          </span>
          <span style={{ fontSize: 11, color: "#555", marginLeft: 10 }}>
            auto-refreshes every 30s
          </span>
        </div>

        {recent.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: "#555", fontSize: 13 }}>
            No activity yet. Activity appears here when leads view, reply, or book.
          </div>
        ) : (
          <div>
            {recent.map((ev, i) => {
              const meta = EVENT_ICONS[ev.event_type] || {
                icon: "dot", color: "#888", label: ev.event_type,
              };
              return (
                <div
                  key={i}
                  style={{
                    display: "flex", alignItems: "center", gap: 14,
                    padding: "12px 20px",
                    borderTop: i > 0 ? "1px solid rgba(255,255,255,0.04)" : "none",
                  }}
                >
                  <Icon icon={meta.icon as any} color={meta.color} size={13} />
                  <span
                    style={{
                      fontSize: 11, fontWeight: 600,
                      color: meta.color, minWidth: 52,
                    }}
                  >
                    {meta.label}
                  </span>
                  <span style={{ fontSize: 12, color: "#aaa", flex: 1 }}>
                    {ev.company || ev.lead_id}
                  </span>
                  <span
                    style={{
                      fontSize: 10, background: "rgba(255,255,255,0.06)",
                      color: "#777", padding: "2px 7px", borderRadius: 4,
                    }}
                  >
                    {ev.variant_id}
                  </span>
                  <span style={{ fontSize: 11, color: "#555", minWidth: 130, textAlign: "right" }}>
                    {new Date(ev.created_at).toLocaleString()}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
