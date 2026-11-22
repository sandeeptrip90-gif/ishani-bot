import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "ok" | "bad" | "info" | "warn";

export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
