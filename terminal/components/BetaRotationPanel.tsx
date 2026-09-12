import type { MacroRegimeSnapshot } from "@/lib/engine/regime";

interface Props {
  macro: MacroRegimeSnapshot | null;
}

function zColor(z: number, inverted: boolean): string {
  const v = inverted ? -z : z;
  if (v > 0.5) return "var(--green)";
  if (v < -0.5) return "var(--red)";
  return "var(--amber)";
}

export function BetaRotationPanel({ macro }: Props) {
  if (!macro) {
    return (
      <div className="panel">
        <div className="panel-header">Beta Rotation — Sector Ratios</div>
        <div className="panel-body loading">Awaiting regime data…</div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">Beta Rotation — Sector Ratios</div>
      <div className="panel-body">
        {macro.ratios.map((r) => {
          const inverted = r.direction === "-";
          const signed = inverted ? -r.zscore : r.zscore;
          const pct = Math.min(100, Math.max(0, ((signed + 2) / 4) * 100));
          return (
            <div key={r.name} style={{ marginBottom: 16 }}>
              <div className="stat-row" style={{ border: "none", paddingBottom: 4 }}>
                <span className="stat-label">{r.name}</span>
                <span style={{ color: zColor(r.zscore, inverted), fontWeight: 600 }}>
                  z {r.zscore >= 0 ? "+" : ""}
                  {r.zscore.toFixed(2)}
                </span>
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>
                {r.interpretation}
              </div>
              <div className="ratio-bar">
                <div
                  className="ratio-fill"
                  style={{
                    width: `${pct}%`,
                    background: zColor(r.zscore, inverted),
                  }}
                />
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                ratio {r.ratio.toFixed(4)}
              </div>
            </div>
          );
        })}
        <div
          style={{
            marginTop: 8,
            padding: 10,
            background: "rgba(89,194,255,0.06)",
            borderRadius: 6,
            fontSize: 11,
            color: "var(--muted)",
          }}
        >
          XLY/XLP and RSP/SPY rising → risk-on. XLU/SPY rising → defensive (inverted). Same
          logic as unified engine Section 9a and carver_ultimate beta_regime().
        </div>
      </div>
    </div>
  );
}
