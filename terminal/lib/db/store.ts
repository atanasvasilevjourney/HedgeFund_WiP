import { sql } from "@vercel/postgres";
import type { CryptoScanResult, ScannerState } from "../engine/crypto-scanner";
import type { DailyEngineResult } from "../engine/daily-momentum";

export interface DashboardPayload {
  daily: DailyEngineResult | null;
  crypto: CryptoScanResult | null;
  alerts: AlertRecord[];
  lastDailyRun: string | null;
  lastCryptoRun: string | null;
}

export interface AlertRecord {
  id?: number;
  source: string;
  symbol: string | null;
  alertType: string;
  message: string;
  sentAt: string;
}

const memoryStore: {
  daily: DailyEngineResult | null;
  crypto: CryptoScanResult | null;
  alerts: AlertRecord[];
  signalState: Record<string, { state: ScannerState; peakScore: number; lastRank: number }>;
} = {
  daily: null,
  crypto: null,
  alerts: [],
  signalState: {},
};

function dbEnabled(): boolean {
  return Boolean(process.env.POSTGRES_URL);
}

export async function saveDailySnapshot(result: DailyEngineResult): Promise<void> {
  if (!dbEnabled()) {
    memoryStore.daily = result;
    return;
  }
  await sql`INSERT INTO daily_snapshots (payload) VALUES (${JSON.stringify(result)}::jsonb)`;
}

export async function saveCryptoSnapshot(result: CryptoScanResult): Promise<void> {
  if (!dbEnabled()) {
    memoryStore.crypto = result;
    for (const row of result.scores) {
      memoryStore.signalState[row.symbol] = {
        state: row.state,
        peakScore: row.compositeScore,
        lastRank: row.rank,
      };
    }
    return;
  }
  await sql`INSERT INTO crypto_scan_history (payload) VALUES (${JSON.stringify(result)}::jsonb)`;
  for (const row of result.scores) {
    await sql`
      INSERT INTO signal_state (symbol, state, peak_score, last_rank, updated_at)
      VALUES (${row.symbol}, ${row.state}, ${row.compositeScore}, ${row.rank}, NOW())
      ON CONFLICT (symbol) DO UPDATE SET
        state = EXCLUDED.state,
        peak_score = EXCLUDED.peak_score,
        last_rank = EXCLUDED.last_rank,
        updated_at = NOW()
    `;
  }
}

export async function loadPriorScannerState(): Promise<{
  states: Record<string, { state: ScannerState; peakScore: number }>;
  ranks: Record<string, number>;
}> {
  if (!dbEnabled()) {
    const states: Record<string, { state: ScannerState; peakScore: number }> = {};
    const ranks: Record<string, number> = {};
    for (const [sym, v] of Object.entries(memoryStore.signalState)) {
      states[sym] = { state: v.state, peakScore: v.peakScore };
      ranks[sym] = v.lastRank;
    }
    return { states, ranks };
  }

  const { rows } = await sql`SELECT symbol, state, peak_score, last_rank FROM signal_state`;
  const states: Record<string, { state: ScannerState; peakScore: number }> = {};
  const ranks: Record<string, number> = {};
  for (const r of rows) {
    states[r.symbol as string] = {
      state: r.state as ScannerState,
      peakScore: Number(r.peak_score),
    };
    ranks[r.symbol as string] = Number(r.last_rank);
  }
  return { states, ranks };
}

export async function logAlert(alert: Omit<AlertRecord, "id" | "sentAt">): Promise<void> {
  const record: AlertRecord = { ...alert, sentAt: new Date().toISOString() };
  if (!dbEnabled()) {
    memoryStore.alerts.unshift(record);
    memoryStore.alerts = memoryStore.alerts.slice(0, 100);
    return;
  }
  await sql`
    INSERT INTO alert_log (source, symbol, alert_type, message)
    VALUES (${alert.source}, ${alert.symbol}, ${alert.alertType}, ${alert.message})
  `;
}

export async function getDashboardPayload(): Promise<DashboardPayload> {
  if (!dbEnabled()) {
    return {
      daily: memoryStore.daily,
      crypto: memoryStore.crypto,
      alerts: memoryStore.alerts,
      lastDailyRun: memoryStore.daily?.timestamp ?? null,
      lastCryptoRun: memoryStore.crypto?.timestamp ?? null,
    };
  }

  const [dailyRes, cryptoRes, alertsRes] = await Promise.all([
    sql`SELECT payload, run_timestamp FROM daily_snapshots ORDER BY run_timestamp DESC LIMIT 1`,
    sql`SELECT payload, run_timestamp FROM crypto_scan_history ORDER BY run_timestamp DESC LIMIT 1`,
    sql`SELECT id, source, symbol, alert_type, message, sent_at FROM alert_log ORDER BY sent_at DESC LIMIT 50`,
  ]);

  return {
    daily: (dailyRes.rows[0]?.payload as DailyEngineResult) ?? null,
    crypto: (cryptoRes.rows[0]?.payload as CryptoScanResult) ?? null,
    alerts: alertsRes.rows.map((r) => ({
      id: r.id as number,
      source: r.source as string,
      symbol: r.symbol as string | null,
      alertType: r.alert_type as string,
      message: r.message as string,
      sentAt: (r.sent_at as Date).toISOString(),
    })),
    lastDailyRun: dailyRes.rows[0]?.run_timestamp
      ? new Date(dailyRes.rows[0].run_timestamp as string).toISOString()
      : null,
    lastCryptoRun: cryptoRes.rows[0]?.run_timestamp
      ? new Date(cryptoRes.rows[0].run_timestamp as string).toISOString()
      : null,
  };
}

export async function initDb(): Promise<void> {
  if (!dbEnabled()) return;
  // Tables created via schema.sql — no-op at runtime
}
