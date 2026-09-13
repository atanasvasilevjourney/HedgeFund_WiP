import { ema, last } from "./math";
import { fetchSingleTickerCloses } from "../data/yahoo";

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
  position: -1 | 0 | 1;
  mode: "weighted" | "consensus";
}

const CFG = {
  temaPeriod: 55,
  macdFast: 12,
  macdSlow: 26,
  macdSignal: 9,
  temaWeight: 0.5,
  macdWeight: 0.5,
  longThreshold: 0.35,
  flatThreshold: 0.05,
  longOnly: true,
};

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

function combine(
  sTema: number[],
  sMacd: number[],
  mode: "weighted" | "consensus"
): number[] {
  return sTema.map((t, i) => {
    const m = sMacd[i];
    if (mode === "consensus") {
      if (t > 0 && m > 0) return 1;
      if (t < 0 && m < 0 && !CFG.longOnly) return -1;
      return 0;
    }
    const score = (CFG.temaWeight * t + CFG.macdWeight * m) / (CFG.temaWeight + CFG.macdWeight);
    if (score >= CFG.longThreshold) return 1;
    if (!CFG.longOnly && score <= -CFG.longThreshold) return -1;
    if (Math.abs(score) < CFG.flatThreshold) return 0;
    return 0;
  });
}

export async function runTemaMacdBtcEnsemble(): Promise<TemaMacdBtcSignal> {
  const { closes } = await fetchSingleTickerCloses("BTC-USD", "5y");
  const temaLine = tema(closes, CFG.temaPeriod);
  const { line, sig, hist } = macdLine(closes, CFG.macdFast, CFG.macdSlow, CFG.macdSignal);
  const sT = temaSig(closes, temaLine);
  const sM = macdSig(hist, line, sig);
  const posRaw = combine(sT, sM, "weighted");
  const i = closes.length - 1;
  const score =
    (CFG.temaWeight * sT[i] + CFG.macdWeight * sM[i]) / (CFG.temaWeight + CFG.macdWeight);

  return {
    timestamp: new Date().toISOString(),
    close: closes[i],
    tema: temaLine[i],
    macd: line[i],
    macdSignal: sig[i],
    macdHist: hist[i],
    sigTema: sT[i] as -1 | 0 | 1,
    sigMacd: sM[i] as -1 | 0 | 1,
    ensembleScore: score,
    position: posRaw[i - 1] as -1 | 0 | 1,
    mode: "weighted",
  };
}
