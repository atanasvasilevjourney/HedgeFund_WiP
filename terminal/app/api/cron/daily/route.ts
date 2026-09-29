import { NextRequest, NextResponse } from "next/server";
import { authorizeCron } from "@/lib/auth/cron";
import { runDailyMomentumEngine } from "@/lib/engine/daily-momentum";
import { saveDailySnapshot, logAlert } from "@/lib/db/store";
import { sendSlackAlert, formatDailyAlert } from "@/lib/alerts/slack";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  if (!authorizeCron(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const result = await runDailyMomentumEngine();
    await saveDailySnapshot(result);

    for (const row of result.rebalancePlan.filter((r) => r.action === "BUY")) {
      const msg = formatDailyAlert(row.symbol, row.delta, row.action);
      const sent = await sendSlackAlert(msg, `daily:${row.symbol}`, 1440);
      await logAlert({
        source: "daily_momentum",
        symbol: row.symbol,
        alertType: row.action,
        message: msg + (sent ? "" : " (logged only)"),
      });
    }

    await logAlert({
      source: "daily_momentum",
      symbol: null,
      alertType: "MACRO",
      message: `Regime ${result.macro.state} | composite ${result.macro.composite.toFixed(2)} | DD scale ${result.ddScale.toFixed(2)}`,
    });

    return NextResponse.json({ ok: true, timestamp: result.timestamp, state: result.macro.state });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
