import type { AuditEntry } from "@/types";
import { Card } from "@/components/shared/Card";
import { EmptyState } from "@/components/shared/EmptyState";
import { formatDate } from "@/lib/format";

export function ActivityFeed({ entries, title = "Recent activity" }: { entries: AuditEntry[]; title?: string }) {
  return (
    <Card title={title} subtitle="Recorded backend actions — nothing is simulated">
      {entries.length === 0 ? (
        <EmptyState icon="clock" title="No activity recorded yet">
          Actions you take through the dashboard or Telegram commands will appear here.
        </EmptyState>
      ) : (
        <div className="activity-list">
          {entries.slice(0, 20).map((entry, index) => (
            <div className="activity-item" key={`${entry.at}-${entry.action}-${index}`}>
              <div>
                <strong className="cell-strong">{entry.action}</strong>
                {entry.target && <div className="cell-sub">Target: <span className="mono">{entry.target}</span></div>}
                {entry.details && <div className="cell-sub">{entry.details}</div>}
              </div>
              <span className="timestamp">
                {formatDate(entry.at)} · {String(entry.actor_id)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
