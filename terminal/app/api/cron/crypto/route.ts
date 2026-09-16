import { NextRequest, NextResponse } from "next/server";
import { authorizeCron } from "@/lib/auth/cron";
import { runCryptoScanner } from "@/lib/engine/crypto-scanner";
import { loadPriorScannerState, saveCryptoSnapshot, logAlert } from "@/lib/db/store";
import { sendSlackAlert, formatCryptoAlert } from "@/lib/alerts/slack";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

const ALERT_STATES = new Set(["ENTRY", "WEAKENING", "EXIT"]);

export async function GET(request: NextRequest) {
  if (!authorizeCron(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const prior = await loadPriorScannerState();
    const result = await runCryptoScanner(prior.states, prior.ranks);
    await saveCryptoSnapshot(result);

    for (const t of result.transitions.filter((x) => ALERT_STATES.has(x.toState))) {
      const msg = formatCryptoAlert(t.toState, t.symbol, t.compositeScore, t.rank);
      const sent = await sendSlackAlert(msg, `crypto:${t.symbol}:${t.toState}`, 60);
      await logAlert({
        source: "crypto_scanner",
        symbol: t.symbol,
        alertType: t.toState,
        message: msg + (sent ? "" : " (logged only)"),
      });
    }

    for (const surge of result.rankSurges) {
      const row = result.scores.find((s) => s.symbol === surge.symbol);
      if (!row) continue;
      const msg = `[Crypto Scanner] *RANK_SURGE* — ${surge.symbol} +${surge.rankDelta} → #${surge.rank}`;
      const sent = await sendSlackAlert(msg, `crypto:surge:${surge.symbol}`, 60);
      await logAlert({
        source: "crypto_scanner",
        symbol: surge.symbol,
        alertType: "RANK_SURGE",
        message: msg + (sent ? "" : " (logged only)"),
      });
    }

    return NextResponse.json({
      ok: true,
      timestamp: result.timestamp,
      transitions: result.transitions.length,
      universe: result.universeSize,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
