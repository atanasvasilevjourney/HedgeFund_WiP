import { readFileSync } from "fs";
import { join } from "path";

export interface TemaMacdLiveConfig {
  version: number;
  updatedAt: string;
  ensemble: {
    temaPeriod: number;
    macdFast: number;
    macdSlow: number;
    macdSignal: number;
    temaWeight: number;
    macdWeight: number;
    longThreshold: number;
    flatThreshold: number;
    longOnly: boolean;
    costBps: number;
  };
  borutaFeatures: string[];
  selection?: {
    method?: string;
    sharpe?: number;
    maxDrawdown?: number;
  };
  walkForward?: {
    folds?: number;
    medianTestSharpe?: number;
    medianTestMaxDd?: number;
  };
}

const DEFAULT: TemaMacdLiveConfig = {
  version: 1,
  updatedAt: "default",
  ensemble: {
    temaPeriod: 55,
    macdFast: 12,
    macdSlow: 26,
    macdSignal: 9,
    temaWeight: 0.5,
    macdWeight: 0.5,
    longThreshold: 0.35,
    flatThreshold: 0.05,
    longOnly: true,
    costBps: 10,
  },
  borutaFeatures: [],
};

export function loadTemaMacdLiveConfig(): TemaMacdLiveConfig {
  const envJson = process.env.TEMA_MACD_BTC_CONFIG_JSON;
  if (envJson) {
    try {
      return { ...DEFAULT, ...JSON.parse(envJson) };
    } catch {
      /* fall through */
    }
  }

  try {
    const path = join(process.cwd(), "config", "tema_macd_btc_live.json");
    const raw = readFileSync(path, "utf-8");
    return { ...DEFAULT, ...JSON.parse(raw) };
  } catch {
    return DEFAULT;
  }
}
