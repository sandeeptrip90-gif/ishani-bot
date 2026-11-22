const KEY = "ishani_selected_groups";

export function getSelectedGroups(): number[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(Number).filter((id) => Number.isFinite(id));
  } catch {
    return [];
  }
}

export function setSelectedGroups(ids: number[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(ids));
  } catch {
    /* storage may be disabled; selection just stays in-memory */
  }
}
