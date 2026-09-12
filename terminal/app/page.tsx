"use client";

import { useCallback, useEffect, useState } from "react";
import { MacroPanel } from "@/components/MacroPanel";
import { BetaRotationPanel } from "@/components/BetaRotationPanel";
import { ResearchTerminal } from "@/components/ResearchTerminal";
import { AlertsFeed } from "@/components/AlertsFeed";
import type { DailyEngineResult } from "@/lib/engine/daily-momentum";
import type { CryptoScanResult } from "@/lib/engine/crypto-scanner";
import type { AlertRecord } from "@/lib/db/store";

interface DashboardData {
  daily: DailyEngineResult | null;
  crypto: CryptoScanResult | null;
  alerts: AlertRecord[];
  lastDailyRun: string | null;
  lastCryptoRun: string | null;
}

export default function HomePage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"equities" | "crypto">("equities");

  const load = useCallback(async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      setError(null);
      const url = refresh ? "/api/dashboard?refresh=1" : "/api/dashboard";
      const res = await fetch(url);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Failed to load dashboard");
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(() => load(), 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <main className="page">
      <header className="header">
        <div>
          <h1>HedgeFund Research Terminal</h1>
          <p>
            Macro regime · beta rotation · daily momentum · crypto scanner
            {data?.lastDailyRun && (
              <> · daily {new Date(data.lastDailyRun).toLocaleString()}</>
            )}
            {data?.lastCryptoRun && (
              <> · crypto {new Date(data.lastCryptoRun).toLocaleString()}</>
            )}
          </p>
        </div>
        <button className="btn" onClick={() => load(true)} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh now"}
        </button>
      </header>

      {loading && !data && <div className="loading">Loading terminal…</div>}
      {error && (
        <div className="panel" style={{ marginBottom: 16, borderColor: "var(--red)" }}>
          <div className="panel-body" style={{ color: "var(--red)" }}>
            {error}
          </div>
        </div>
      )}

      {data && (
        <>
          <section className="grid-top">
            <MacroPanel macro={data.daily?.macro ?? null} />
            <BetaRotationPanel macro={data.daily?.macro ?? null} />
          </section>

          <section className="grid-main">
            <ResearchTerminal
              daily={data.daily}
              crypto={data.crypto}
              tab={tab}
              onTabChange={setTab}
            />
            <AlertsFeed alerts={data.alerts} />
          </section>
        </>
      )}
    </main>
  );
}
