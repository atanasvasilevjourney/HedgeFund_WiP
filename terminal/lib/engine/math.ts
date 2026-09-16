export function mean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

export function std(values: number[]): number {
  if (values.length < 2) return 0;
  const m = mean(values);
  const v = values.reduce((s, x) => s + (x - m) ** 2, 0) / (values.length - 1);
  return Math.sqrt(v);
}

export function zscoreSeries(values: number[], window: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - window + 1);
    const slice = values.slice(start, i + 1);
    if (slice.length < Math.min(window, 60)) {
      out.push(0);
      continue;
    }
    const m = mean(slice);
    const s = std(slice) || 1e-9;
    out.push((values[i] - m) / s);
  }
  return out;
}

export function pctChange(values: number[], periods: number): number[] {
  const out = new Array(values.length).fill(0);
  for (let i = periods; i < values.length; i++) {
    const prev = values[i - periods];
    out[i] = prev !== 0 ? values[i] / prev - 1 : 0;
  }
  return out;
}

export function rollingMean(values: number[], window: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - window + 1);
    const slice = values.slice(start, i + 1);
    out.push(mean(slice));
  }
  return out;
}

export function rollingStd(values: number[], window: number): number[] {
  const out: number[] = [];
  for (let i = 0; i < values.length; i++) {
    const start = Math.max(0, i - window + 1);
    const slice = values.slice(start, i + 1);
    out.push(std(slice));
  }
  return out;
}

export function sma(values: number[], window: number): number[] {
  return rollingMean(values, window);
}

export function ema(values: number[], span: number): number[] {
  const alpha = 2 / (span + 1);
  const out: number[] = [];
  for (let i = 0; i < values.length; i++) {
    if (i === 0) out.push(values[i]);
    else out.push(alpha * values[i] + (1 - alpha) * out[i - 1]);
  }
  return out;
}

export function percentileRank(values: number[], higherIsBetter = true): number[] {
  const indexed = values.map((v, i) => ({ v, i }));
  indexed.sort((a, b) => (higherIsBetter ? b.v - a.v : a.v - b.v));
  const ranks = new Array(values.length).fill(0);
  indexed.forEach((item, rank) => {
    ranks[item.i] = 1 - rank / Math.max(values.length - 1, 1);
  });
  return ranks;
}

export function clip(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function last<T>(arr: T[]): T | undefined {
  return arr.length ? arr[arr.length - 1] : undefined;
}
