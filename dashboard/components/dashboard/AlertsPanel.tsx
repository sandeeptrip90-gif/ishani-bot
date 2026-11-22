import type { Alert } from "@/types";
import { Card } from "@/components/shared/Card";
import { EmptyState } from "@/components/shared/EmptyState";
import { formatDate } from "@/lib/format";

export function AlertsPanel({ alerts }: { alerts: Alert[] }) {
  return (
    <Card title="Alerts" subtitle="Derived from real group and bot data">
      {alerts.length === 0 ? (
        <EmptyState icon="checkCircle" title="No alerts right now">
          Nothing needs attention in your visible groups.
        </EmptyState>
      ) : (
        <div className="alert-list">
          {alerts.map((alert, index) => (
            <div className={`alert-item ${alert.level}`} key={`${alert.text}-${index}`}>
              <div>
                <div>{alert.text}</div>
                {alert.at && <span className="timestamp">Detected {formatDate(alert.at)}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
