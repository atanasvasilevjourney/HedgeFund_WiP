"use client";

import { useEffect, useState } from "react";

interface TemaMacdSignal {
  timestamp: string;
  close: number;
  tema: number;
  macdHist: number;
  sigTema: number;
  sigMacd: number;
  ensembleScore: number;
  position: number;
}

export function TemaMacdBtcPanel() {
  const [data, setData] = useState<TemaMacdSignal | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/tema-macd-btc")
      .then((r) => r.json())
      .then((j) => {
        if (j.error) setError(j.error);
        else setData(j);
      })
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="panel">
      <div className="panel-header">TEMA + MACD Ensemble — BTC</div>
      <div className="panel-body">
        {error && <div style={{ color: "var(--red)" }}>{error}</div>}
        {!data && !error && <div style={{ color: "var(--muted)" }}>Loading BTC ensemble…</div>}
        {data && (
          <>
            <div className="stat-row">
              <span className="stat-label">BTC-USD</span>
              <span className="stat-value">${data.close.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            </div>
            <div className="stat-row">
              <span className="stat-label">TEMA(55)</span>
              <span className="stat-value">${data.tema.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            </div>
            <div className="stat-row">
              <span className="stat-label">MACD hist</span>
              <span className={data.macdHist >= 0 ? "stat-value positive" : "stat-value negative"}>
                {data.macdHist.toFixed(2)}
              </span>
            </div>
            <div className="stat-row">
              <span className="stat-label">TEMA / MACD vote</span>
              <span className="stat-value">
                {data.sigTema > 0 ? "+1" : data.sigTema < 0 ? "-1" : "0"} /{" "}
                {data.sigMacd > 0 ? "+1" : data.sigMacd < 0 ? "-1" : "0"}
              </span>
            </div>
            <div className="stat-row">
              <span className="stat-label">Ensemble score</span>
              <span className="stat-value">{data.ensembleScore.toFixed(2)}</span>
            </div>
            <div className="stat-row">
              <span className="stat-label">Position (next bar)</span>
              <span
                className={
                  data.position > 0 ? "stat-value positive" : data.position < 0 ? "stat-value negative" : "stat-value"
                }
              >
                {data.position > 0 ? "LONG" : data.position < 0 ? "SHORT" : "FLAT"}
              </span>
            </div>
            <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 12, marginBottom: 0 }}>
              Long-only weighted ensemble (50% TEMA trend + 50% MACD). Matches{" "}
              <code>tema_macd_ensemble_btc.ipynb</code>.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
