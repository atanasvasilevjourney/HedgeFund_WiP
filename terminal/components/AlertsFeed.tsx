import type { AlertRecord } from "@/lib/db/store";

interface Props {
  alerts: AlertRecord[];
}

export function AlertsFeed({ alerts }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">Trade Alerts</div>
      <div className="panel-body">
        {alerts.length === 0 ? (
          <div style={{ color: "var(--muted)" }}>
            No alerts yet. Cron jobs fire ENTRY / WEAKENING / EXIT (crypto) and BUY signals
            (daily). Set SLACK_WEBHOOK_URL for Slack delivery.
          </div>
        ) : (
          alerts.map((a, i) => (
            <div key={a.id ?? i} className="alert-item">
              <div>
                <span
                  style={{
                    color:
                      a.alertType === "ENTRY" || a.alertType === "BUY"
                        ? "var(--green)"
                        : a.alertType === "EXIT" || a.alertType === "WEAKENING"
                          ? "var(--red)"
                          : "var(--amber)",
                    fontWeight: 600,
                  }}
                >
                  {a.alertType}
                </span>
                {a.symbol && <span> · {a.symbol}</span>}
              </div>
              <div style={{ marginTop: 4 }}>{a.message}</div>
              <div className="alert-meta">
                {a.source} · {new Date(a.sentAt).toLocaleString()}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
