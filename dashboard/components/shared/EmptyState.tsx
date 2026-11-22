import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

export function EmptyState({
  icon = "info",
  title,
  children,
}: {
  icon?: IconName;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon name={icon} size={22} /></div>
      <strong>{title}</strong>
      {children && <p className="muted">{children}</p>}
    </div>
  );
}
