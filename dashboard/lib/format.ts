export function formatNumber(value: unknown): string {
  const n = Number(value || 0);
  return Number.isFinite(n) ? n.toLocaleString("en-IN") : "0";
}

export function formatDate(value: unknown): string {
  if (!value) return "—";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("en-IN", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function initials(name: unknown): string {
  return String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}

export function telegramLink(usernameOrId: unknown): string | null {
  const raw = String(usernameOrId || "").trim();
  if (!raw) return null;
  if (/^\d+$/.test(raw)) return `tg://user?id=${raw}`;
  return `https://t.me/${raw.replace(/^@/, "")}`;
}

export function copyToClipboard(text: string): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).then(
      () => true,
      () => false,
    );
  }
  return Promise.resolve(false);
}
