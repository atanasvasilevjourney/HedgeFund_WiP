"use client";

import type { DailyEngineResult } from "@/lib/engine/daily-momentum";
import type { CryptoScanResult } from "@/lib/engine/crypto-scanner";

interface Props {
  daily: DailyEngineResult | null;
  crypto: CryptoScanResult | null;
  tab: "equities" | "crypto";
  onTabChange: (tab: "equities" | "crypto") => void;
}

function stateClass(state: string): string {
  return `state-${state.toLowerCase()}`;
}

export function ResearchTerminal({ daily, crypto, tab, onTabChange }: Props) {
  return (
    <div className="panel">
      <div
        className="panel-header"
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
      >
        <span>Research Terminal</span>
        <span>
          <button
            className="btn"
            style={{
              marginRight: 8,
              background: tab === "equities" ? "var(--blue)" : undefined,
              color: tab === "equities" ? "#000" : undefined,
            }}
            onClick={() => onTabChange("equities")}
          >
            Daily Momentum
          </button>
          <button
            className="btn"
            style={{
              background: tab === "crypto" ? "var(--purple)" : undefined,
              color: tab === "crypto" ? "#000" : undefined,
            }}
            onClick={() => onTabChange("crypto")}
          >
            Crypto Scanner
          </button>
        </span>
      </div>
      <div className="panel-body" style={{ padding: 0, overflowX: "auto" }}>
        {tab === "equities" ? (
          daily ? (
            <>
              <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>
                <span style={{ color: "var(--muted)" }}>Portfolio </span>
                {(daily.portfolio.length ? daily.portfolio : []).map((p) => (
                  <span key={p.symbol} style={{ marginRight: 12 }}>
                    {p.symbol}{" "}
                    <span className="positive">{(p.weight * 100).toFixed(1)}%</span>
                  </span>
                ))}
                <span style={{ color: "var(--muted)" }}>
                  cash {(daily.cashWeight * 100).toFixed(1)}% · DD{" "}
                  {(daily.currentDd * 100).toFixed(1)}% · governor{" "}
                  {(daily.ddScale * 100).toFixed(0)}%
                </span>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Symbol</th>
                    <th>Sleeve</th>
                    <th>Score</th>
                    <th>6M Mom</th>
                    <th>Trend</th>
                    <th>RS vs SPY</th>
                    <th>Vol</th>
                    <th>Forecast</th>
                  </tr>
                </thead>
                <tbody>
                  {daily.signals.map((r) => (
                    <tr key={r.symbol}>
                      <td>{r.rank}</td>
                      <td>{r.symbol}</td>
                      <td>{r.sleeve}</td>
                      <td>{r.coreScore.toFixed(3)}</td>
                      <td className={r.momentum6m >= 0 ? "positive" : "negative"}>
                        {(r.momentum6m * 100).toFixed(1)}%
                      </td>
                      <td>{(r.trend * 100).toFixed(1)}%</td>
                      <td>{(r.relativeStrength * 100).toFixed(1)}%</td>
                      <td>{(r.volatility * 100).toFixed(1)}%</td>
                      <td>{r.forecast.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <div className="loading">Run daily engine to populate equity signals…</div>
          )
        ) : crypto ? (
          <>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)" }}>
              <span style={{ color: "var(--muted)" }}>
                Universe {crypto.universeSize} · scanned {crypto.scores.length} ·{" "}
                {new Date(crypto.timestamp).toLocaleString()}
              </span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Pair</th>
                  <th>State</th>
                  <th>Score</th>
                  <th>Mom</th>
                  <th>RS vs BTC</th>
                  <th>Vol Acc</th>
                  <th>Trend</th>
                  <th>Price</th>
                </tr>
              </thead>
              <tbody>
                {crypto.scores.map((r) => (
                  <tr key={r.symbol}>
                    <td>{r.rank}</td>
                    <td>{r.symbol}</td>
                    <td className={stateClass(r.state)}>{r.state}</td>
                    <td>{r.compositeScore.toFixed(3)}</td>
                    <td>{(r.momentum * 100).toFixed(2)}%</td>
                    <td className={r.relativeStrength >= 0 ? "positive" : "negative"}>
                      {(r.relativeStrength * 100).toFixed(2)}%
                    </td>
                    <td>{r.volumeAccel.toFixed(2)}</td>
                    <td>{r.trend ? "▲" : "▼"}</td>
                    <td>${r.price.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <div className="loading">Run crypto scanner to populate rankings…</div>
        )}
      </div>
    </div>
  );
}
