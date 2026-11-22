"use client";

import { useEffect, useState } from "react";
import { TaskPanel } from "@/components/tasks/TaskPanel";
import { Card } from "@/components/shared/Card";

export default function TasksPage() {
  const [taskId, setTaskId] = useState<string | undefined>(undefined);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("task");
    if (id) setTaskId(id);
  }, []);

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Task execution</h1>
          <p className="page-sub">
            Real task records from AI chats and automation: status, step-by-step logs and outcomes.
            Anything that failed reports the backend's actual error.
          </p>
        </div>
      </div>
      <Card title={taskId ? `Task ${taskId}` : "All tasks"} subtitle="Refreshes automatically while this page is open">
        <TaskPanel taskId={taskId} />
      </Card>
    </div>
  );
}
