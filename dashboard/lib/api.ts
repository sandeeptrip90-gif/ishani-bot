"use client";

import type { ApiResult } from "@/types";

interface RequestOptions {
  method?: "GET" | "POST";
  body?: Record<string, unknown>;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  try {
    const response = await fetch(`/api${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
    });
    const text = await response.text();
    let payload: unknown = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = null;
      }
    }
    if (!response.ok) {
      const message =
        (payload as { message?: string } | null)?.message ||
        `Request failed (${response.status})`;
      return { data: null, error: message, status: response.status };
    }
    if (payload && typeof payload === "object" && "ok" in payload) {
      const envelope = payload as { ok?: boolean; message?: string };
      if (envelope.ok === false) {
        return { data: payload as T, error: envelope.message || "Request failed", status: response.status };
      }
    }
    return { data: payload as T, error: null, status: response.status };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Network error";
    return { data: null, error: `Cannot reach the bot server. ${message}`, status: 0 };
  }
}

export const api = {
  overview: () => apiFetch<import("@/types").OverviewPayload>("/overview"),
  groups: () => apiFetch<import("@/types").GroupsPayload>("/groups"),
  group: (id: number | string) => apiFetch<{ ok: boolean; group: import("@/types").Group }>(`/group?id=${encodeURIComponent(String(id))}`),
  members: (id: number | string) => apiFetch<import("@/types").MembersPayload>(`/group/members?id=${encodeURIComponent(String(id))}`),
  activity: () => apiFetch<{ ok: boolean; entries: import("@/types").AuditEntry[] }>("/activity"),
  owners: () => apiFetch<{ ok: boolean; owners: import("@/types").OwnerEntry[]; invitations: import("@/types").InvitationEntry[] }>("/owners"),
  inviteOwner: (body: Record<string, unknown>) => apiFetch<{ ok: boolean; token?: string; expires_at?: string; message?: string }>("/owners/invite", { method: "POST", body }),
  verifyGroup: (body: Record<string, unknown>) => apiFetch<{ ok: boolean; message?: string }>("/owners/verify", { method: "POST", body }),
  schedule: () => apiFetch<{ ok: boolean; items: import("@/types").ScheduledItem[] }>("/schedule"),
  addSchedule: (body: Record<string, unknown>) => apiFetch<{ ok: boolean; id?: string; message?: string; note?: string }>("/schedule", { method: "POST", body }),
  removeSchedule: (body: Record<string, unknown>) => apiFetch<{ ok: boolean; message?: string }>("/schedule/remove", { method: "POST", body }),
  groupAction: (body: Record<string, unknown>) => apiFetch<{ ok: boolean; verified?: boolean; action?: string; result?: string; note?: string; message?: string }>("/group/action", { method: "POST", body }),
  removeGroup: (body: Record<string, unknown>) => apiFetch<{ ok: boolean; message?: string }>("/group/remove", { method: "POST", body }),
  broadcast: (body: Record<string, unknown>) => apiFetch<{ ok: boolean; sent?: number; failed?: number; results?: Array<{ group_id: number; ok: boolean; error?: string }>; message?: string }>("/broadcast", { method: "POST", body }),
  groupSettings: (body: Record<string, unknown>) => apiFetch<{ ok: boolean; message?: string }>("/group/settings", { method: "POST", body }),
  aiHistory: () => apiFetch<{ ok: boolean; messages: import("@/types").ChatTurn[] }>("/ai/history"),
  aiChat: (body: Record<string, unknown>) => apiFetch<import("@/types").ChatPayload>("/ai/chat", { method: "POST", body }),
  tasks: () => apiFetch<{ ok: boolean; tasks: import("@/types").TaskRecord[] }>("/tasks"),
  task: (id: string) => apiFetch<{ ok: boolean; task: import("@/types").TaskRecord }>(`/tasks?id=${encodeURIComponent(id)}`),
  lessons: () => apiFetch<{ ok: boolean; lessons: string[]; link_controls: Record<string, unknown> }>("/lessons"),
  addLesson: (body: Record<string, unknown>) => apiFetch<{ ok: boolean; lessons?: string[]; message?: string }>("/lessons", { method: "POST", body }),
  config: () => apiFetch<{ ok: boolean; endpoint?: string; model?: string; has_key?: boolean; message?: string }>("/config"),
  saveConfig: (body: Record<string, unknown>) => apiFetch<{ ok: boolean; message?: string; model?: string }>("/config", { method: "POST", body }),
  testConfig: (body: Record<string, unknown>) => apiFetch<{ ok: boolean; message?: string }>("/test", { method: "POST", body }),
};
