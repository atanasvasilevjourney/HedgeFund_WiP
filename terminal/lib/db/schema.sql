-- Run once after connecting Vercel Postgres

CREATE TABLE IF NOT EXISTS daily_snapshots (
  id SERIAL PRIMARY KEY,
  run_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS crypto_scan_history (
  id SERIAL PRIMARY KEY,
  run_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_state (
  symbol TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  peak_score DOUBLE PRECISION DEFAULT 0,
  last_rank INTEGER,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alert_log (
  id SERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  symbol TEXT,
  alert_type TEXT NOT NULL,
  message TEXT NOT NULL,
  payload JSONB,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_snapshots_ts ON daily_snapshots(run_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_crypto_scan_ts ON crypto_scan_history(run_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_alert_log_ts ON alert_log(sent_at DESC);
