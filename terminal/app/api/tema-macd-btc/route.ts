import { NextRequest, NextResponse } from "next/server";
import { authorizeApi } from "@/lib/auth/cron";
import { runTemaMacdBtcEnsemble } from "@/lib/engine/tema-macd-btc";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  if (!authorizeApi(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const signal = await runTemaMacdBtcEnsemble();
    return NextResponse.json(signal);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
