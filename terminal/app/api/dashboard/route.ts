import { NextRequest, NextResponse } from "next/server";
import { authorizeApi } from "@/lib/auth/cron";
import { getDashboardPayload } from "@/lib/db/store";
import { runDailyMomentumEngine } from "@/lib/engine/daily-momentum";
import { runCryptoScanner } from "@/lib/engine/crypto-scanner";
import { loadPriorScannerState, saveDailySnapshot, saveCryptoSnapshot } from "@/lib/db/store";

export const maxDuration = 60;
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  if (!authorizeApi(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const refresh = request.nextUrl.searchParams.get("refresh") === "1";

  try {
    if (refresh) {
      const prior = await loadPriorScannerState();
      let daily = null;
      let crypto = null;
      const errors: string[] = [];

      try {
        daily = await runDailyMomentumEngine();
        await saveDailySnapshot(daily);
      } catch (e) {
        errors.push(e instanceof Error ? e.message : "Daily engine failed");
      }

      try {
        crypto = await runCryptoScanner(prior.states, prior.ranks);
        await saveCryptoSnapshot(crypto);
      } catch (e) {
        errors.push(e instanceof Error ? e.message : "Crypto scanner failed");
      }

      const payload = await getDashboardPayload();
      return NextResponse.json({
        daily: daily ?? payload.daily,
        crypto: crypto ?? payload.crypto,
        alerts: payload.alerts,
        lastDailyRun: daily?.timestamp ?? payload.lastDailyRun,
        lastCryptoRun: crypto?.timestamp ?? payload.lastCryptoRun,
        errors: errors.length ? errors : undefined,
      });
    }

    const payload = await getDashboardPayload();

    // If no persisted data yet, compute live once (engines may fail independently)
    if (!payload.daily || !payload.crypto) {
      const prior = await loadPriorScannerState();
      const errors: string[] = [];
      let daily = payload.daily;
      let crypto = payload.crypto;

      if (!daily) {
        try {
          daily = await runDailyMomentumEngine();
          await saveDailySnapshot(daily);
        } catch (e) {
          errors.push(e instanceof Error ? e.message : "Daily engine failed");
        }
      }

      if (!crypto) {
        try {
          crypto = await runCryptoScanner(prior.states, prior.ranks);
          await saveCryptoSnapshot(crypto);
        } catch (e) {
          errors.push(e instanceof Error ? e.message : "Crypto scanner failed");
        }
      }

      return NextResponse.json({
        daily,
        crypto,
        alerts: payload.alerts,
        lastDailyRun: daily?.timestamp ?? null,
        lastCryptoRun: crypto?.timestamp ?? null,
        errors: errors.length ? errors : undefined,
      });
    }

    return NextResponse.json(payload);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
