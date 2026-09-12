import { clip, last, mean, zscoreSeries } from "./math";
import type { PricePanel } from "../data/yahoo";

export type RegimeState = "RISK_ON" | "NEUTRAL" | "RISK_OFF";

export interface RegimeRatioSignal {
  name: string;
  ratio: number;
  zscore: number;
  direction: "+" | "-";
  interpretation: string;
}

export interface MacroRegimeSnapshot {
  timestamp: string;
  composite: number;
  scale: number;
  state: RegimeState;
  ratios: RegimeRatioSignal[];
  exposureLabel: string;
}

const REGIME_TICKERS = ["XLY", "XLP", "XLU", "SPY", "RSP"] as const;

/** Continuous scale from unified_swing_momentum_engine (4) */
export function computeContinuousRegime(regimePanel: PricePanel, zWindow = 252): {
  composite: number;
  scale: number;
  ratios: RegimeRatioSignal[];
} {
  const xly = regimePanel["XLY"];
  const xlp = regimePanel["XLP"];
  const xlu = regimePanel["XLU"];
  const spy = regimePanel["SPY"];
  const rsp = regimePanel["RSP"];

  if (!xly || !xlp || !xlu || !spy || !rsp) {
    throw new Error("Regime panel missing required tickers");
  }

  const len = spy.length;
  const ratioDefs: Array<{
    name: string;
    values: number[];
    sign: 1 | -1;
    interpretation: string;
  }> = [
    {
      name: "XLY/XLP",
      values: xly.map((v, i) => v / (xlp[i] || 1)),
      sign: 1,
      interpretation: "Consumer discretionary vs staples — risk appetite",
    },
    {
      name: "XLU/SPY",
      values: xlu.map((v, i) => v / (spy[i] || 1)),
      sign: -1,
      interpretation: "Utilities vs market — defensive rotation (inverted)",
    },
    {
      name: "RSP/SPY",
      values: rsp.map((v, i) => v / (spy[i] || 1)),
      sign: 1,
      interpretation: "Equal-weight vs cap-weight — breadth / small-cap leadership",
    },
  ];

  const zs: number[] = [];
  const ratios: RegimeRatioSignal[] = [];

  for (const def of ratioDefs) {
    const zArr = zscoreSeries(def.values, zWindow);
    const z = last(zArr) ?? 0;
    const signed = def.sign * z;
    zs.push(signed);
    ratios.push({
      name: def.name,
      ratio: last(def.values) ?? 0,
      zscore: z,
      direction: def.sign === 1 ? "+" : "-",
      interpretation: def.interpretation,
    });
  }

  const composite = mean(zs);
  const scale = clip(1 + 0.25 * composite, 0.3, 1.3);

  return { composite, scale, ratios };
}

/** Discrete states from carver_ultimate / crypto_alpha v4 */
export function discreteRegimeState(composite: number): RegimeState {
  if (composite >= 0.5) return "RISK_ON";
  if (composite <= -0.5) return "RISK_OFF";
  return "NEUTRAL";
}

export function discreteRegimeScale(state: RegimeState): number {
  return { RISK_ON: 1.0, NEUTRAL: 0.65, RISK_OFF: 0.35 }[state];
}

export function buildMacroSnapshot(regimePanel: PricePanel): MacroRegimeSnapshot {
  const { composite, scale, ratios } = computeContinuousRegime(regimePanel);
  const state = discreteRegimeState(composite);
  const discreteScale = discreteRegimeScale(state);

  return {
    timestamp: new Date().toISOString(),
    composite,
    scale: discreteScale,
    state,
    ratios,
    exposureLabel:
      state === "RISK_ON"
        ? "Full risk budget — cyclicals leading, breadth supportive"
        : state === "RISK_OFF"
          ? "Defensive posture — reduce gross, favor quality / cash"
          : "Neutral — partial exposure, wait for clearer macro tilt",
  };
}

export { REGIME_TICKERS };
