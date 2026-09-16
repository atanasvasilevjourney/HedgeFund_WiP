import { NextRequest } from "next/server";

export function authorizeCron(request: NextRequest): boolean {
  const secret = process.env.CRON_SECRET;
  if (!secret) return process.env.NODE_ENV !== "production";

  const auth = request.headers.get("authorization");
  if (auth === `Bearer ${secret}`) return true;

  // Vercel Cron sends this header automatically
  const vercelCron = request.headers.get("x-vercel-cron");
  return vercelCron === "1" || vercelCron === "true";
}

export function authorizeApi(request: NextRequest): boolean {
  const key = process.env.TERMINAL_API_KEY;
  if (!key) return true;
  return request.headers.get("x-api-key") === key;
}
