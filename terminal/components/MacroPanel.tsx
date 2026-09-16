import type { MacroRegimeSnapshot } from "@/lib/engine/regime";

interface Props {
  macro: MacroRegimeSnapshot | null;
}

function badgeClass(state: string): string {
  if (state === "RISK_ON") return "badge badge-risk-on";
  if (state === "RISK_OFF") return "badge badge-risk-off";
  return "badge badge-neutral";
}

export function MacroPanel({ macro }: Props) {
  if (!macro) {
    return (
      <div className="panel">
        <div className="panel-header">Macro Context</div>
        <div className="panel-body loading">Awaiting daily engine run…</div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">Macro Context</div>
      <div className="panel-body">
        <div style={{ marginBottom: 16 }}>
          <span className={badgeClass(macro.state)}>{macro.state.replace("_", " ")}</span>
          <span style={{ marginLeft: 12, color: "var(--muted)" }}>
            composite {macro.composite.toFixed(2)} · exposure {(macro.scale * 100).toFixed(0)}%
          </span>
        </div>
        <p style={{ color: "var(--muted)", margin: "0 0 16px", fontSize: 12 }}>
          {macro.exposureLabel}
        </p>
        <div className="stat-row">
          <span className="stat-label">Regime scale</span>
          <span className="stat-value">{(macro.scale * 100).toFixed(0)}%</span>
        </div>
        <div className="stat-row">
          <span className="stat-label">Composite z-score</span>
          <span className={macro.composite >= 0 ? "stat-value positive" : "stat-value negative"}>
            {macro.composite >= 0 ? "+" : ""}
            {macro.composite.toFixed(2)}
          </span>
        </div>
        <div className="stat-row">
          <span className="stat-label">Updated</span>
          <span className="stat-value">{new Date(macro.timestamp).toLocaleString()}</span>
        </div>
      </div>
    </div>
  );
}
