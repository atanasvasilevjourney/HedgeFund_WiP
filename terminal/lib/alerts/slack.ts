const cooldownMs = 60 * 60 * 1000;
const lastSent = new Map<string, number>();

export async function sendSlackAlert(
  text: string,
  key: string,
  cooldownMinutes = 60
): Promise<boolean> {
  const webhook = process.env.SLACK_WEBHOOK_URL;
  if (!webhook || webhook.includes("PASTE_YOUR")) {
    return false;
  }

  const now = Date.now();
  const last = lastSent.get(key) ?? 0;
  if (now - last < cooldownMinutes * 60 * 1000) {
    return false;
  }

  const res = await fetch(webhook, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

  if (res.ok) {
    lastSent.set(key, now);
    return true;
  }
  return false;
}

export function formatCryptoAlert(
  type: string,
  symbol: string,
  score: number,
  rank: number
): string {
  return `[Crypto Scanner] *${type}* — ${symbol} | score ${score.toFixed(3)} | rank #${rank}`;
}

export function formatDailyAlert(symbol: string, weight: number, action: string): string {
  return `[Daily Momentum] *${action}* — ${symbol} | target weight ${(weight * 100).toFixed(1)}%`;
}
