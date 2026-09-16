import { ema } from "./math";
import { fetchSingleTickerCloses } from "../data/yahoo";
import { loadTemaMacdLiveConfig, type TemaMacdLiveConfig } from "./tema-macd-btc-config";

export interface TemaMacdBtcSignal {
  timestamp: string;
  close: number;
  tema: number;
  macd: number;
  macdSignal: number;
  macdHist: number;
  sigTema: -1 | 0 | 1;
  sigMacd: -1 | 0 | 1;
  ensembleScore: number;
  blendScore: number;
  position: -1 | 0 | 1;
  mode: "weighted";
  configSource: string;
  borutaFeatures: string[];
  liveConfigUpdatedAt: string;
}

function tema(close: number[], period: number): number[] {
  const e1 = ema(close, period);
  const e2 = ema(e1, period);
  const e3 = ema(e2, period);
  return e1.map((v, i) => 3 * v - 3 * e2[i] + e3[i]);
}

function macdLine(close: number[], fast: number, slow: number, signal: number) {
  const fastE = ema(close, fast);
  const slowE = ema(close, slow);
  const line = fastE.map((v, i) => v - slowE[i]);
  const sig = ema(line, signal);
  const hist = line.map((v, i) => v - sig[i]);
  return { line, sig, hist };
}

function temaSig(close: number[], temaLine: number[]): number[] {
  return close.map((c, i) => {
    if (i === 0) return 0;
    const above = c > temaLine[i];
    const slope = temaLine[i] > temaLine[i - 1];
    if (above && slope) return 1;
    if (!above && !slope) return -1;
    return 0;
  });
}

function macdSig(hist: number[], line: number[], sig: number[]): number[] {
  return hist.map((h, i) => {
    if (h > 0 && line[i] > sig[i]) return 1;
    if (h < 0 && line[i] < sig[i]) return -1;
    return 0;
  });
}

function rsi(close: number[], period: number): number[] {
  const out = new Array(close.length).fill(50);
  for (let i = period; i < close.length; i++) {
    let gain = 0;
    let loss = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const d = close[j] - close[j - 1];
      if (d >= 0) gain += d;
      else loss -= d;
    }
    const rs = gain / (loss + 1e-12);
    out[i] = 100 - 100 / (1 + rs);
  }
  return out;
}

function featureVote(name: string, close: number[], i: number, temaLine: number[], hist: number[]): number {
  if (name.startsWith("sig_tema") || name.endsWith("_sig")) {
    const above = close[i] > temaLine[i];
    const slope = i > 0 && temaLine[i] > temaLine[i - 1];
    if (above && slope) return 1;
    if (!above && !slope) return -1;
    return 0;
  }
  if (name.includes("rsi")) {
    const r = rsi(close, name.includes("7") ? 7 : 14)[i];
    if (r > 55) return 1;
    if (r < 45) return -1;
    return 0;
  }
  if (name.includes("mom_")) {
    const w = parseInt(name.split("_")[1] || "21", 10);
    if (i <= w) return 0;
    return close[i] / close[i - w] - 1 > 0 ? 1 : -1;
  }
  if (name.includes("hist")) return hist[i] > 0 ? 1 : hist[i] < 0 ? -1 : 0;
  if (name.includes("dist")) return close[i] / temaLine[i] - 1 > 0 ? 1 : -1;
  return 0;
}

function blendScore(
  baseScore: number,
  close: number[],
  temaLine: number[],
  hist: number[],
  features: string[],
  index?: number
): number {
  if (!features.length) return baseScore;
  let votes = 0;
  const i = index ?? close.length - 1;
  for (const f of features) votes += featureVote(f, close, i, temaLine, hist);
  const norm = votes / features.length;
  return 0.5 * baseScore + 0.5 * Math.max(-1, Math.min(1, norm));
}

function positionFromBlend(
  blend: number,
  cfg: TemaMacdLiveConfig["ensemble"],
  prevPos: number
): -1 | 0 | 1 {
  if (blend >= cfg.longThreshold) return 1;
  if (!cfg.longOnly && blend <= -cfg.longThreshold) return -1;
  if (Math.abs(blend) < cfg.flatThreshold) return 0;
  return prevPos as -1 | 0 | 1;
}

export async function runTemaMacdBtcEnsemble(
  liveConfig?: TemaMacdLiveConfig
): Promise<TemaMacdBtcSignal> {
  const config = liveConfig ?? loadTemaMacdLiveConfig();
  const cfg = config.ensemble;

  const { closes } = await fetchSingleTickerCloses("BTC-USD", "5y");
  const temaLine = tema(closes, cfg.temaPeriod);
  const { line, sig, hist } = macdLine(closes, cfg.macdFast, cfg.macdSlow, cfg.macdSignal);
  const sT = temaSig(closes, temaLine);
  const sM = macdSig(hist, line, sig);
  const i = closes.length - 1;

  const baseScore =
    (cfg.temaWeight * sT[i] + cfg.macdWeight * sM[i]) / (cfg.temaWeight + cfg.macdWeight);
  const blend = blendScore(baseScore, closes, temaLine, hist, config.borutaFeatures ?? []);

  const basePrev =
    i > 0
      ? (cfg.temaWeight * sT[i - 1] + cfg.macdWeight * sM[i - 1]) /
        (cfg.temaWeight + cfg.macdWeight)
      : 0;
  const blendPrev =
    i > 0
      ? blendScore(basePrev, closes, temaLine, hist, config.borutaFeatures ?? [], i - 1)
      : 0;

  const posRaw = positionFromBlend(blendPrev, cfg, 0);

  return {
    timestamp: new Date().toISOString(),
    close: closes[i],
    tema: temaLine[i],
    macd: line[i],
    macdSignal: sig[i],
    macdHist: hist[i],
    sigTema: sT[i] as -1 | 0 | 1,
    sigMacd: sM[i] as -1 | 0 | 1,
    ensembleScore: baseScore,
    blendScore: blend,
    position: posRaw,
    mode: "weighted",
    configSource: process.env.TEMA_MACD_BTC_CONFIG_JSON ? "env" : "file",
    borutaFeatures: config.borutaFeatures ?? [],
    liveConfigUpdatedAt: config.updatedAt,
  };
}
