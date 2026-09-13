import { fetchTopCoins, fetchCoinGeckoHourly } from "../data/coingecko";
import { fetchBinanceExchangeInfo, fetchBinanceOhlcv, type OhlcvBar } from "../data/binance";
import {
  clip,
  ema,
  last,
  mean,
  pctChange,
  percentileRank,
  rollingMean,
  rollingStd,
} from "./math";

export type ScannerState =
  | "WATCH"
  | "SETUP"
  | "ENTRY"
  | "HOLD"
  | "WEAKENING"
  | "EXIT";

export interface CryptoScoreRow {
  symbol: string;
  name: string;
  rank: number;
  compositeScore: number;
  momentum: number;
  relativeStrength: number;
  volumeAccel: number;
  volatility: number;
  correlation: number;
  entropy: number;
  volumeRatio: number;
  trend: number;
  price: number;
  state: ScannerState;
}

export interface StateTransition {
  symbol: string;
  fromState: ScannerState | null;
  toState: ScannerState;
  compositeScore: number;
  rank: number;
}

export interface CryptoScanResult {
  timestamp: string;
  universeSize: number;
  scores: CryptoScoreRow[];
  transitions: StateTransition[];
  rankSurges: Array<{ symbol: string; rankDelta: number; rank: number }>;
}

const CONFIG = {
  topMarketCap: 100,
  min24hVolumeUsd: 5_000_000,
  ohlcvLimit: 90,
  momentumWindows: [1, 4, 12, 24],
  momentumWeights: [0.1, 0.2, 0.3, 0.4],
  relativeStrengthWindow: 12,
  volumeWindow: 20,
  volumeAccelLookback: 5,
  emaFast: 20,
  emaSlow: 50,
  volatilityWindow: 30,
  correlationWindow: 60,
  entropyWindow: 60,
  minHistoryBars: 65,
  factorWeights: {
    momentum: 0.2,
    relativeStrength: 0.15,
    volumeAccel: 0.1,
    volatility: 0.15,
    correlation: 0.1,
    entropy: 0.1,
    volume: 0.1,
    trend: 0.1,
  },
  state: {
    setupScore: 0.5,
    entryScore: 0.65,
    weakeningScoreDrop: 0.1,
    exitScore: 0.45,
  },
  rankSurgeThreshold: 10,
};

function binaryEntropy(values: number[], window: number): number[] {
  const rets = pctChange(values, 1);
  const out: number[] = [];
  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - window + 1);
    const slice = rets.slice(start, i + 1);
    const p = clip(mean(slice.map((r) => (r > 0 ? 1 : 0))), 1e-12, 1 - 1e-12);
    out.push(-(p * Math.log2(p) + (1 - p) * Math.log2(1 - p)));
  }
  return out;
}

function momentumScoreSeries(closes: number[]): number[] {
  const out = new Array(closes.length).fill(0);
  for (let i = 0; i < closes.length; i++) {
    let score = 0;
    for (let w = 0; w < CONFIG.momentumWindows.length; w++) {
      const win = CONFIG.momentumWindows[w];
      const weight = CONFIG.momentumWeights[w];
      const idx = i - win;
      if (idx >= 0 && closes[idx] > 0) {
        score += (closes[i] / closes[idx] - 1) * weight;
      }
    }
    out[i] = score;
  }
  return out;
}

function buildFactorSnapshot(
  priceData: Record<string, OhlcvBar[]>,
  benchmark: OhlcvBar[]
): Record<string, Record<string, number>> {
  const benchmarkCloses = benchmark.map((b) => b.close);
  const returnsMatrix: Record<string, number[]> = {};
  const raw: Record<string, Record<string, number>> = {};

  for (const [symbol, bars] of Object.entries(priceData)) {
    const closes = bars.map((b) => b.close);
    const volumes = bars.map((b) => b.volume);
    if (closes.length < CONFIG.minHistoryBars) continue;

    const mom = last(momentumScoreSeries(closes)) ?? 0;
    const benchSlice = benchmarkCloses.slice(-closes.length);
    const rsWindow = CONFIG.relativeStrengthWindow;
    const symRet = closes.length > rsWindow && closes[closes.length - rsWindow - 1] > 0
      ? closes[closes.length - 1] / closes[closes.length - rsWindow - 1] - 1
      : 0;
    const benchRet =
      benchSlice.length > rsWindow && benchSlice[benchSlice.length - rsWindow - 1] > 0
        ? benchSlice[benchSlice.length - 1] / benchSlice[benchSlice.length - rsWindow - 1] - 1
        : 0;

    const vol = (last(rollingStd(pctChange(closes, 1), CONFIG.volatilityWindow)) ?? 0) * Math.sqrt(365);
    const volRatioArr = volumes.map((v, i) => {
      const m = rollingMean(volumes, CONFIG.volumeWindow)[i] || 1;
      return v / m;
    });
    const volRatio = last(volRatioArr) ?? 1;
    const volAccel = volRatio - (volRatioArr[volRatioArr.length - 1 - CONFIG.volumeAccelLookback] ?? volRatio);
    const ent = last(binaryEntropy(closes, CONFIG.entropyWindow)) ?? 0;
    const fast = last(ema(closes, CONFIG.emaFast)) ?? closes[closes.length - 1];
    const slow = last(ema(closes, CONFIG.emaSlow)) ?? closes[closes.length - 1];
    const trend = fast > slow ? 1 : 0;

    returnsMatrix[symbol] = pctChange(closes, 1);
    raw[symbol] = {
      momentum: mom,
      relativeStrength: symRet - benchRet,
      volumeAccel: volAccel,
      volatility: vol,
      entropy: ent,
      volumeRatio: volRatio,
      trend,
      price: last(closes) ?? 0,
    };
  }

  // Correlation penalty
  const symbols = Object.keys(raw);
  for (const symbol of symbols) {
    const symRets = returnsMatrix[symbol];
    const corrs: number[] = [];
    for (const other of symbols) {
      if (other === symbol) continue;
      const oRets = returnsMatrix[other];
      const n = Math.min(symRets.length, oRets.length, CONFIG.correlationWindow);
      const a = symRets.slice(-n);
      const b = oRets.slice(-n);
      if (a.length < 10) continue;
      const ma = mean(a);
      const mb = mean(b);
      const cov = mean(a.map((v, i) => (v - ma) * (b[i] - mb)));
      const sa = std(a) || 1e-9;
      const sb = std(b) || 1e-9;
      corrs.push(Math.abs(cov / (sa * sb)));
    }
    raw[symbol].correlation = corrs.length ? mean(corrs) : 0;
  }

  return raw;
}

function std(values: number[]): number {
  if (values.length < 2) return 0;
  const m = mean(values);
  return Math.sqrt(values.reduce((s, x) => s + (x - m) ** 2, 0) / (values.length - 1));
}

function buildScores(raw: Record<string, Record<string, number>>): CryptoScoreRow[] {
  const symbols = Object.keys(raw);
  const factors = [
    "momentum",
    "relativeStrength",
    "volumeAccel",
    "volatility",
    "correlation",
    "entropy",
    "volumeRatio",
    "trend",
  ] as const;

  const pctRanks: Record<string, number[]> = {};
  for (const f of factors) {
    const vals = symbols.map((s) => raw[s][f] ?? 0);
    const higher = f !== "volatility" && f !== "correlation" && f !== "entropy";
    pctRanks[f] = percentileRank(vals, higher);
  }

  const rows: CryptoScoreRow[] = symbols.map((symbol, i) => {
    let composite = 0;
    for (const f of factors) {
      const w = CONFIG.factorWeights[f === "volumeRatio" ? "volume" : f] ?? 0;
      composite += (pctRanks[f][i] ?? 0) * w;
    }
    return {
      symbol,
      name: symbol.replace("USDT", ""),
      rank: 0,
      compositeScore: composite,
      momentum: raw[symbol].momentum,
      relativeStrength: raw[symbol].relativeStrength,
      volumeAccel: raw[symbol].volumeAccel,
      volatility: raw[symbol].volatility,
      correlation: raw[symbol].correlation ?? 0,
      entropy: raw[symbol].entropy,
      volumeRatio: raw[symbol].volumeRatio,
      trend: raw[symbol].trend,
      price: raw[symbol].price,
      state: "WATCH" as ScannerState,
    };
  });

  rows.sort((a, b) => b.compositeScore - a.compositeScore);
  rows.forEach((r, idx) => {
    r.rank = idx + 1;
  });
  return rows;
}

export function transitionState(
  current: ScannerState | null,
  row: CryptoScoreRow,
  peakScore: number
): { state: ScannerState; peak: number } {
  const s = CONFIG.state;
  const score = row.compositeScore;
  const cur = current ?? "WATCH";
  let peak = peakScore;

  if (cur === "WATCH" || cur === "EXIT") {
    if (score >= s.setupScore) return { state: "SETUP", peak: score };
    return { state: "WATCH", peak: 0 };
  }
  if (cur === "SETUP") {
    if (score >= s.entryScore && row.trend === 1 && row.volumeRatio > 1)
      return { state: "ENTRY", peak: score };
    if (score < s.setupScore) return { state: "WATCH", peak: 0 };
    return { state: "SETUP", peak: score };
  }
  if (cur === "ENTRY" || cur === "HOLD" || cur === "WEAKENING") {
    peak = Math.max(peak, score);
    if (score < s.exitScore) return { state: "EXIT", peak: 0 };
    if (peak - score >= s.weakeningScoreDrop) return { state: "WEAKENING", peak };
    return { state: cur === "ENTRY" ? "HOLD" : cur, peak };
  }
  return { state: cur, peak };
}

async function loadOhlcvForCoin(
  coin: { id: string; symbol: string },
  binanceSymbols: Set<string> | null
): Promise<{ key: string; bars: OhlcvBar[] } | null> {
  const sym = `${coin.symbol.toUpperCase()}USDT`;
  const key = sym;

  if (binanceSymbols?.has(sym)) {
    try {
      return { key, bars: await fetchBinanceOhlcv(sym, "1h", CONFIG.ohlcvLimit) };
    } catch {
      /* fall through to CoinGecko */
    }
  }

  try {
    const cg = await fetchCoinGeckoHourly(coin.id, 7);
    const bars: OhlcvBar[] = cg.map((b) => ({
      timestamp: b.timestamp,
      open: b.close,
      high: b.close,
      low: b.close,
      close: b.close,
      volume: b.volume,
    }));
    return bars.length >= CONFIG.minHistoryBars ? { key, bars } : null;
  } catch {
    return null;
  }
}

export async function runCryptoScanner(
  priorStates: Record<string, { state: ScannerState; peakScore: number }> = {},
  priorRanks: Record<string, number> = {}
): Promise<CryptoScanResult> {
  const coins = await fetchTopCoins(CONFIG.topMarketCap);

  let binanceSymbols: Set<string> | null = null;
  try {
    binanceSymbols = await fetchBinanceExchangeInfo();
  } catch {
    binanceSymbols = null;
  }

  const universe = coins.filter((c) => c.total_volume >= CONFIG.min24hVolumeUsd);

  const priceData: Record<string, OhlcvBar[]> = {};
  const batchSize = 5;
  for (let i = 0; i < Math.min(universe.length, 30); i += batchSize) {
    const batch = universe.slice(i, i + batchSize);
    const results = await Promise.all(batch.map((coin) => loadOhlcvForCoin(coin, binanceSymbols)));
    for (const r of results) {
      if (r) priceData[r.key] = r.bars;
    }
  }

  let benchmark: OhlcvBar[];
  if (priceData["BTCUSDT"]) {
    benchmark = priceData["BTCUSDT"];
  } else {
    const btc = await fetchCoinGeckoHourly("bitcoin", 7);
    benchmark = btc.map((b) => ({
      timestamp: b.timestamp,
      open: b.close,
      high: b.close,
      low: b.close,
      close: b.close,
      volume: b.volume,
    }));
  }
  const raw = buildFactorSnapshot(priceData, benchmark);
  const scores = buildScores(raw);

  const transitions: StateTransition[] = [];
  const rankSurges: CryptoScanResult["rankSurges"] = [];

  for (const row of scores) {
    const prior = priorStates[row.symbol];
    const { state, peak } = transitionState(prior?.state ?? null, row, prior?.peakScore ?? 0);
    row.state = state;

    if (prior?.state !== state) {
      transitions.push({
        symbol: row.symbol,
        fromState: prior?.state ?? null,
        toState: state,
        compositeScore: row.compositeScore,
        rank: row.rank,
      });
    }

    const prevRank = priorRanks[row.symbol];
    if (prevRank !== undefined) {
      const delta = prevRank - row.rank;
      if (delta >= CONFIG.rankSurgeThreshold) {
        rankSurges.push({ symbol: row.symbol, rankDelta: delta, rank: row.rank });
      }
    }
  }

  return {
    timestamp: new Date().toISOString(),
    universeSize: universe.length,
    scores: scores.slice(0, 50),
    transitions,
    rankSurges,
  };
}
