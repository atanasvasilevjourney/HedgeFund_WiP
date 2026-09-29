import { fetchYahooCloses, type PricePanel } from "../data/yahoo";
import {
  buildMacroSnapshot,
  discreteRegimeScale,
  type MacroRegimeSnapshot,
} from "./regime";
import { clip, last, mean, pctChange, percentileRank, rollingStd, sma } from "./math";

export interface DailySignalRow {
  symbol: string;
  sleeve: "equity" | "index" | "crypto";
  rank: number;
  coreScore: number;
  momentum1m: number;
  momentum6m: number;
  trend: number;
  relativeStrength: number;
  volatility: number;
  targetWeight: number;
  forecast: number;
}

export interface DailyEngineResult {
  timestamp: string;
  macro: MacroRegimeSnapshot;
  signals: DailySignalRow[];
  portfolio: Array<{ symbol: string; weight: number; sleeve: string }>;
  cashWeight: number;
  ddScale: number;
  currentDd: number;
  rebalancePlan: Array<{ symbol: string; delta: number; action: "BUY" | "SELL" | "HOLD" }>;
}

const EQUITY_TICKERS = [
  "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "NFLX",
  "SMH", "BOTZ", "QTUM", "XBI", "XLE", "XLF", "XLI", "XLV",
  "ARKK", "SOXX", "IWM", "EEM", "GLD", "SLV", "DBMF", "BUZZ",
  "FRDM", "COPX", "ITA", "PAVE",
];

const INDEX_TICKERS = ["SPY", "QQQ", "DIA"];
const CRYPTO_TICKERS = ["BTC-USD", "SOL-USD"];
const REGIME_TICKERS = ["XLY", "XLP", "XLU", "SPY", "RSP"];

const PORTFOLIO_SIZE = 8;
const MAX_SINGLE_WEIGHT = 0.2;
const TARGET_VOL = 0.1;
const MAX_DD = 0.1;

function zscoreLast(values: number[], window: number): number {
  const slice = values.slice(-window);
  if (slice.length < 20) return 0;
  const m = mean(slice);
  const s =
    Math.sqrt(slice.reduce((acc, v) => acc + (v - m) ** 2, 0) / (slice.length - 1)) || 1e-9;
  return (last(slice)! - m) / s;
}

function buildFactors(panel: PricePanel, spyKey = "SPY"): Record<string, Record<string, number>> {
  const spy = panel[spyKey] ?? panel["QQQ"];
  const spyM6 = last(pctChange(spy, 126)) ?? 0;
  const out: Record<string, Record<string, number>> = {};

  for (const [symbol, prices] of Object.entries(panel)) {
    if (REGIME_TICKERS.includes(symbol as (typeof REGIME_TICKERS)[number])) continue;
    const rets = pctChange(prices, 1);
    const m1 = last(pctChange(prices, 21)) ?? 0;
    const m6 = last(pctChange(prices, 126)) ?? 0;
    const sma50 = last(sma(prices, 50)) ?? prices[prices.length - 1];
    const sma200 = last(sma(prices, 200)) ?? prices[prices.length - 1];
    const trend = sma50 / sma200 - 1;
    const rs = m6 - spyM6;
    const vol = (last(rollingStd(rets, 30)) ?? 0.01) * Math.sqrt(252);
    out[symbol] = { m1, m6, trend, rs, vol };
  }
  return out;
}

function scoreUniverse(
  factors: Record<string, Record<string, number>>,
  sleeveMap: Record<string, DailySignalRow["sleeve"]>
): DailySignalRow[] {
  const symbols = Object.keys(factors);
  const m1R = percentileRank(symbols.map((s) => factors[s].m1));
  const m6R = percentileRank(symbols.map((s) => factors[s].m6));
  const trendR = percentileRank(symbols.map((s) => factors[s].trend));
  const rsR = percentileRank(symbols.map((s) => factors[s].rs));
  const volR = percentileRank(
    symbols.map((s) => factors[s].vol),
    false
  );

  const rows: DailySignalRow[] = symbols.map((symbol, i) => {
    const f = factors[symbol];
    const momentumScore = 0.35 * m1R[i] + 0.65 * m6R[i];
    const coreScore =
      0.4 * momentumScore + 0.25 * trendR[i] + 0.2 * rsR[i] + 0.15 * volR[i];
    const eligible = f.m6 > 0 && f.trend > 0;
    return {
      symbol,
      sleeve: sleeveMap[symbol] ?? "equity",
      rank: 0,
      coreScore: eligible ? coreScore : 0,
      momentum1m: f.m1,
      momentum6m: f.m6,
      trend: f.trend,
      relativeStrength: f.rs,
      volatility: f.vol,
      targetWeight: 0,
      forecast: clip(coreScore * 20, 0, 20),
    };
  });

  rows.sort((a, b) => b.coreScore - a.coreScore);
  rows.forEach((r, i) => {
    r.rank = i + 1;
  });
  return rows;
}

function constructPortfolio(
  scored: DailySignalRow[],
  regimeScale: number
): { portfolio: DailySignalRow[]; cashWeight: number } {
  const eligible = scored.filter((r) => r.coreScore > 0);
  const selected: DailySignalRow[] = [];

  for (const row of eligible) {
    if (selected.length >= PORTFOLIO_SIZE) break;
    selected.push({ ...row });
  }

  if (selected.length === 0) {
    return { portfolio: [], cashWeight: 1 };
  }

  const invVol = selected.map((r) => r.coreScore / Math.max(r.volatility, 0.1));
  const sum = invVol.reduce((a, b) => a + b, 0);
  let weights = invVol.map((v) => v / sum);
  weights = weights.map((w) => Math.min(w, MAX_SINGLE_WEIGHT));
  const wSum = weights.reduce((a, b) => a + b, 0);
  weights = weights.map((w) => (w / wSum) * regimeScale);

  selected.forEach((r, i) => {
    r.targetWeight = weights[i];
  });

  const cashWeight = clip(1 - weights.reduce((a, b) => a + b, 0), 0, 1);
  return { portfolio: selected, cashWeight };
}

function ddGovernorScale(equityCurve: number[]): { ddScale: number; currentDd: number } {
  const peak = Math.max(...equityCurve);
  const current = last(equityCurve) ?? 1;
  const currentDd = current / peak - 1;
  const a = Math.abs(Math.min(currentDd, 0));
  const ddScale =
    a >= MAX_DD ? 0 : a >= 0.075 ? 0.25 : a >= 0.05 ? 0.5 : a >= 0.025 ? 0.75 : 1.0;
  return { ddScale, currentDd };
}

function simpleEquityCurve(panel: PricePanel, weights: Record<string, number>): number[] {
  const symbols = Object.keys(weights);
  if (!symbols.length) return [1];
  const len = panel[symbols[0]].length;
  const equity = [1];
  for (let i = 1; i < len; i++) {
    let dayRet = 0;
    for (const s of symbols) {
      const p0 = panel[s][i - 1];
      const p1 = panel[s][i];
      if (p0 > 0) dayRet += weights[s] * (p1 / p0 - 1);
    }
    equity.push(equity[equity.length - 1] * (1 + dayRet));
  }
  return equity;
}

export async function runDailyMomentumEngine(): Promise<DailyEngineResult> {
  const allTickers = [...new Set([...EQUITY_TICKERS, ...INDEX_TICKERS, ...CRYPTO_TICKERS, ...REGIME_TICKERS])];
  const { panel } = await fetchYahooCloses(allTickers, "3y");

  const regimePanel: PricePanel = {};
  for (const t of REGIME_TICKERS) regimePanel[t] = panel[t];

  const macro = buildMacroSnapshot(regimePanel);
  const regimeScale = discreteRegimeScale(macro.state);

  const tradePanel: PricePanel = {};
  const sleeveMap: Record<string, DailySignalRow["sleeve"]> = {};
  for (const t of EQUITY_TICKERS) {
    tradePanel[t] = panel[t];
    sleeveMap[t] = "equity";
  }
  for (const t of INDEX_TICKERS) {
    tradePanel[t] = panel[t];
    sleeveMap[t] = "index";
  }
  for (const t of CRYPTO_TICKERS) {
    tradePanel[t] = panel[t];
    sleeveMap[t] = "crypto";
  }

  const factors = buildFactors(tradePanel);
  const signals = scoreUniverse(factors, sleeveMap);
  const { portfolio, cashWeight } = constructPortfolio(signals, regimeScale);

  const weightMap = Object.fromEntries(portfolio.map((p) => [p.symbol, p.targetWeight]));
  const equityCurve = simpleEquityCurve(tradePanel, weightMap);
  const { ddScale, currentDd } = ddGovernorScale(equityCurve);

  portfolio.forEach((p) => {
    p.targetWeight *= ddScale;
  });

  const rebalancePlan = portfolio.map((p) => ({
    symbol: p.symbol,
    delta: p.targetWeight,
    action: (p.targetWeight > 0.02 ? "BUY" : "HOLD") as "BUY" | "SELL" | "HOLD",
  }));

  return {
    timestamp: new Date().toISOString(),
    macro,
    signals: signals.slice(0, 30),
    portfolio: portfolio.map((p) => ({
      symbol: p.symbol,
      weight: p.targetWeight,
      sleeve: p.sleeve,
    })),
    cashWeight: cashWeight + (1 - ddScale) * (1 - cashWeight),
    ddScale,
    currentDd,
    rebalancePlan,
  };
}

export { EQUITY_TICKERS, INDEX_TICKERS, CRYPTO_TICKERS, REGIME_TICKERS };
