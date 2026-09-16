# HedgeFund Research Terminal

Live web platform for the momentum engine and crypto scanner — deployed on **Vercel**.

## Layout

```
┌─────────────────────────────────────────────────────────┐
│  MACRO CONTEXT          │  BETA ROTATION (sector ratios) │
│  RISK_ON / NEUTRAL / OFF│  XLY/XLP · XLU/SPY · RSP/SPY   │
├─────────────────────────┴───────────────────────────────┤
│  RESEARCH TERMINAL (Daily Momentum | Crypto Scanner)    │
├─────────────────────────────────────────────────────────┤
│  TRADE ALERTS (Slack + in-app feed)                     │
└─────────────────────────────────────────────────────────┘
```

## What runs where

| Job | Schedule | Source notebook logic |
|-----|----------|----------------------|
| Daily momentum + macro | Mon–Fri 14:00 UTC (`vercel.json`) | `unified_swing_momentum_engine (4)`, `crypto_alpha_engine_v4` |
| Crypto scanner | Every 15 min | `live_momentum_scanner_slack` |
| Dashboard | On demand + auto-refresh 5 min | Reads latest snapshots |

## Deploy to Vercel

1. **Import repo** in [vercel.com/new](https://vercel.com/new) and set **Root Directory** to `terminal`.

2. **Add Vercel Postgres** (Storage → Postgres → Connect). Copy `POSTGRES_URL` into env vars.

3. **Initialize DB** — run `lib/db/schema.sql` in the Postgres SQL console.

4. **Set environment variables:**

   | Variable | Required | Purpose |
   |----------|----------|---------|
   | `POSTGRES_URL` | Yes (prod) | Persist snapshots, scanner state, alerts |
   | `CRON_SECRET` | Yes (prod) | Protect `/api/cron/*` if not invoked by Vercel Cron |
   | `SLACK_WEBHOOK_URL` | No | Push ENTRY/EXIT/BUY alerts to Slack |
   | `TERMINAL_API_KEY` | No | Lock `/api/dashboard` in production |

5. **Deploy.** Cron jobs activate automatically from `vercel.json`.

6. **First load:** open the site and click **Refresh now** (or hit `/api/dashboard?refresh=1`) to seed data before the first cron tick.

## TEMA + MACD BTC (Optuna/Boruta live config)

The BTC ensemble panel reads **`config/tema_macd_btc_live.json`**, produced by:

```bash
pip install -r requirements_tema_macd_research.txt
python3 scripts/export_tema_macd_live_config.py
```

This runs multi-objective Optuna (Sharpe vs drawdown Pareto), walk-forward checks, and writes params + Boruta features for the terminal API.

Override in production with env var `TEMA_MACD_BTC_CONFIG_JSON` (full JSON blob).

## Local development

```bash
cd terminal
npm install
cp .env.example .env.local
npm run dev
```

Without `POSTGRES_URL`, the app uses in-memory storage (fine for dev; resets on restart).

## Architecture notes

### Why Vercel (and what it cannot do)

- **Good fit:** Next.js dashboard, serverless cron, Slack webhooks, Postgres via `@vercel/postgres`.
- **Not a fit:** Infinite `while True` scanner loops from the Jupyter notebooks. Those become **scheduled cron invocations** (15 min crypto, daily equities).
- **Execution limit:** API routes set `maxDuration = 60`. Full Carver stack with 28 tickers fits; scanning 100 coins may need batching (currently top 40 by liquidity).

### Engine ports

| Module | Notebook source |
|--------|-----------------|
| `lib/engine/regime.ts` | Beta rotation: XLY/XLP, XLU/SPY (−), RSP/SPY |
| `lib/engine/daily-momentum.ts` | Daily factor scoring, portfolio, DD governor |
| `lib/engine/crypto-scanner.ts` | 8-factor composite, state machine, rank surge |

### Recommended evolution

1. Extract full Carver forecast stack (EWMAC, breakout, CS momentum) from Python into `lib/engine/carver/` or a small Python microservice on Railway/Fly for heavy backtests only.
2. Add email/SMS via Resend or Twilio alongside Slack.
3. Add auth (Clerk / NextAuth) before exposing live weights publicly.
4. Move crypto scan to **every 5 min** on Vercel Pro if needed.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/dashboard` | GET | Latest snapshots + alerts |
| `/api/dashboard?refresh=1` | GET | Re-run both engines, persist, return |
| `/api/cron/daily` | GET | Cron: daily engine (authorized) |
| `/api/cron/crypto` | GET | Cron: crypto scanner (authorized) |

Manual cron test:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" https://your-app.vercel.app/api/cron/daily
```
