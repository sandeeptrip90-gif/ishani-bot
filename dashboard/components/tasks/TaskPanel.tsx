"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { TaskRecord } from "@/types";
import { Badge, type BadgeTone } from "@/components/shared/Badge";
import { EmptyState } from "@/components/shared/EmptyState";
import { Notice } from "@/components/shared/Notice";

function logText(line: string | { at?: string; text?: string }): string {
  if (typeof line === "string") return line;
  return line?.text || JSON.stringify(line);
}

function resultText(result: string | Record<string, unknown> | null | undefined): string {
  if (result === null || result === undefined) return "";
  return typeof result === "string" ? result : JSON.stringify(result);
}

function toneFor(status: string): BadgeTone {
  const value = status.toLowerCase();
  if (["done", "success", "completed", "complete"].includes(value)) return "ok";
  if (["failed", "error", "rejected"].includes(value)) return "bad";
  if (["running", "pending", "queued", "awaiting_confirmation"].includes(value)) return "warn";
  return "neutral";
}

export function TaskPanel({ taskId, onRefresh }: { taskId?: string; onRefresh?: () => void }) {
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const result = taskId ? await api.task(taskId) : await api.tasks();
    if (result.error) {
      setError(result.error);
    } else {
      setError("");
      const single = (result.data as { task?: TaskRecord } | null)?.task;
      const list = (result.data as { tasks?: TaskRecord[] } | null)?.tasks;
      setTasks(single ? [single] : list || []);
    }
    setLoading(false);
  }, [taskId]);

  useEffect(() => {
    setLoading(true);
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => window.clearInterval(timer);
  }, [load]);

  const refresh = () => {
    void load();
    onRefresh?.();
  };

  if (error) return <Notice onDismiss={() => setError("")}>{error}</Notice>;
  if (loading && tasks.length === 0) return <div className="skeleton" style={{ height: 120 }} />;
  if (tasks.length === 0) {
    return (
      <EmptyState icon="tasks" title="No tasks yet">
        AI actions, automation and diagnostics create task records with real execution logs here.
      </EmptyState>
    );
  }

  return (
    <div className="stack">
      {!taskId && (
        <div className="row">
          <span className="muted">Auto-refreshing every 15 seconds</span>
          <button className="btn secondary sm" onClick={refresh} type="button">Refresh now</button>
        </div>
      )}
      {tasks.map((task) => (
        <div className="task-card" key={task.id}>
          <div className="task-head">
            <Badge tone={toneFor(String(task.status || "unknown"))}>{task.status || "unknown"}</Badge>
            <strong className="cell-strong">{task.mode || "task"}</strong>
            <span className="timestamp">{formatDate(task.at)}</span>
            <span className="cell-sub mono">{task.id}</span>
          </div>
          <p className="muted" style={{ marginTop: 8 }}>{task.message}</p>
          {(task.log || []).length > 0 && (
            <div className="log-list" style={{ marginTop: 10 }}>
              {task.log.map((line, index) => (
                <div className="log-line" key={`${task.id}-${index}`}>
                  <span className="timestamp">{String(index + 1).padStart(2, "0")}</span>
                  <span>{logText(line)}</span>
                </div>
              ))}
            </div>
          )}
          {resultText(task.result) && (
            <div className="notice info" style={{ marginTop: 10, marginBottom: 0 }}>
              <span>{resultText(task.result)}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
