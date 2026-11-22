import { Icon, type IconName } from "@/components/shared/Icon";
import { formatNumber } from "@/lib/format";

export function StatCard({
  icon,
  label,
  value,
  foot,
}: {
  icon: IconName;
  label: string;
  value: number | string;
  foot?: string;
}) {
  return (
    <div className="stat">
      <div className="stat-icon"><Icon name={icon} size={19} /></div>
      <strong className="stat-value">{typeof value === "number" ? formatNumber(value) : value}</strong>
      <span className="stat-label">{label}</span>
      {foot && <div className="stat-foot">{foot}</div>}
    </div>
  );
}
