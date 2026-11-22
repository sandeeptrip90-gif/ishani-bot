"use client";

import type { ReactNode } from "react";
import { Icon } from "./Icon";

export function Notice({
  kind = "error",
  children,
  onDismiss,
}: {
  kind?: "error" | "success" | "info" | "warning";
  children: ReactNode;
  onDismiss?: () => void;
}) {
  if (!children) return null;
  return (
    <div className={`notice ${kind}`} role="status">
      <Icon name={kind === "success" ? "checkCircle" : kind === "info" ? "info" : "alert"} size={16} />
      <span>{children}</span>
      {onDismiss && (
        <button className="notice-close" onClick={onDismiss} aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  );
}
