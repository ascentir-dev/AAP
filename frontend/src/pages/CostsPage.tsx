import { useEffect, useState, useCallback } from "react";
import { Card, Spinner, NonIdealState, Button, Callout } from "@blueprintjs/core";
import { fetchAnalytics } from "../api/client";
import type { AnalyticsData } from "../api/types";

export function CostsPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const d = await fetchAnalytics();
      setData(d);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <Spinner size={40} />
      </div>
    );
  }

  if (error) {
    return (
      <NonIdealState
        icon="error"
        title="Could not load cost data"
        description={error}
        action={
          <Button intent="primary" onClick={load}>
            Retry
          </Button>
        }
      />
    );
  }

  const cost = data?.cost;

  const perLead =
    data && data.total_sent > 0
      ? (cost?.total_cost_usd ?? 0) / data.total_sent
      : null;

  // Volume ramp projections
  const ramp = [5_000, 12_000, 30_000];

  return (
    <div>
      <h1 className="page-title">Cost Tracker</h1>

      {cost && (
        <div className="kpi-grid" style={{ marginBottom: 24 }}>
          <Card className="kpi-card">
            <div className="kpi-label">Total Spend</div>
            <div className="kpi-value">${cost.total_cost_usd.toFixed(2)}</div>
            <div className="kpi-sub">across all leads</div>
          </Card>

          <Card className="kpi-card">
            <div className="kpi-label">Calls Booked</div>
            <div className="kpi-value">{cost.booked}</div>
            <div className="kpi-sub">from pipeline</div>
          </Card>

          <Card className="kpi-card">
            <div className="kpi-label">Cost / Booked Call</div>
            <div className="kpi-value">
              {cost.cost_per_booked != null
                ? `$${cost.cost_per_booked.toFixed(2)}`
                : "—"}
            </div>
            <div className="kpi-sub">customer acquisition cost</div>
          </Card>

          <Card className="kpi-card">
            <div className="kpi-label">Cost / Lead</div>
            <div className="kpi-value">
              {perLead != null ? `$${perLead.toFixed(4)}` : "—"}
            </div>
            <div className="kpi-sub">target: $0.024</div>
          </Card>
        </div>
      )}

      {perLead != null && perLead > 0.024 && (
        <Callout intent="warning" icon="warning-sign" style={{ marginBottom: 24 }}>
          Cost per lead (${perLead.toFixed(4)}) is above the $0.024 target. Check model
          routing and prompt caching configuration.
        </Callout>
      )}

      {perLead != null && perLead <= 0.024 && (
        <Callout intent="success" icon="tick" style={{ marginBottom: 24 }}>
          Cost per lead (${perLead.toFixed(4)}) is on target ✓
        </Callout>
      )}

      {/* Volume projections */}
      <Card
        style={{
          background: "#252a31",
          border: "1px solid #383e47",
          marginBottom: 24,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600, color: "#f6f7f9", marginBottom: 16 }}>
          Monthly Volume Cost Projections
        </div>
        <div style={{ fontSize: 12, color: "#738091", marginBottom: 16 }}>
          Based on target $0.024/lead and current actual cost per lead.
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 12,
          }}
        >
          {ramp.map((vol) => (
            <Card
              key={vol}
              style={{
                background: "#1c2127",
                border: "1px solid #383e47",
                padding: 16,
                textAlign: "center",
              }}
            >
              <div
                style={{ fontSize: 11, color: "#5f6b7c", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}
              >
                {vol.toLocaleString()} leads/mo
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, color: "#f6f7f9" }}>
                ${(vol * 0.024).toFixed(0)}
              </div>
              <div style={{ fontSize: 11, color: "#738091", marginTop: 2 }}>
                @ $0.024 target
              </div>
              {perLead != null && (
                <div
                  style={{
                    fontSize: 11,
                    color: perLead <= 0.024 ? "#72ca9b" : "#fa999c",
                    marginTop: 4,
                  }}
                >
                  ${(vol * perLead).toFixed(0)} actual
                </div>
              )}
            </Card>
          ))}
        </div>
      </Card>

      {/* Per-variant cost breakdown */}
      {data && data.variants.length > 0 && (
        <Card
          style={{
            background: "#252a31",
            border: "1px solid #383e47",
          }}
        >
          <div
            style={{ fontSize: 13, fontWeight: 600, color: "#f6f7f9", marginBottom: 16 }}
          >
            Variant Cost Allocation
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
              gap: 10,
            }}
          >
            {data.variants.map((v) => {
              const share =
                data.total_sent > 0 ? v.sent / data.total_sent : 0;
              const variantCost = (cost?.total_cost_usd ?? 0) * share;
              return (
                <div
                  key={v.variant_id}
                  style={{
                    background: "#1c2127",
                    border: "1px solid #383e47",
                    borderRadius: 4,
                    padding: 12,
                    textAlign: "center",
                  }}
                >
                  <div
                    style={{
                      fontSize: 11,
                      color: "#5f6b7c",
                      marginBottom: 4,
                    }}
                  >
                    {v.variant_id}
                  </div>
                  <div
                    style={{ fontSize: 18, fontWeight: 700, color: "#f6f7f9" }}
                  >
                    ${variantCost.toFixed(2)}
                  </div>
                  <div style={{ fontSize: 11, color: "#738091", marginTop: 2 }}>
                    {v.sent} leads · {(share * 100).toFixed(0)}%
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}
