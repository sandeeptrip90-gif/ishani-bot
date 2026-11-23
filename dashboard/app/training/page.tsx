"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { TrainingExample, TrainingExamplesPayload } from "@/types";
import { Badge, type BadgeTone } from "@/components/shared/Badge";
import { Button } from "@/components/shared/Button";
import { Card } from "@/components/shared/Card";
import { EmptyState } from "@/components/shared/EmptyState";
import { Icon } from "@/components/shared/Icon";
import { Notice } from "@/components/shared/Notice";
import { StatCard } from "@/components/dashboard/StatCard";

function shortText(value: string | undefined, limit = 120): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "—";
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function statusTone(status: string): BadgeTone {
  if (status === "approved") return "ok";
  if (status === "rejected") return "bad";
  if (status === "pending") return "warn";
  return "neutral";
}

export default function TrainingPage() {
  const [payload, setPayload] = useState<TrainingExamplesPayload | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyIds, setBusyIds] = useState<Record<string, boolean>>({});
  const [autoCapture, setAutoCapture] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);

  const [newUserText, setNewUserText] = useState("");
  const [newReply, setNewReply] = useState("");
  const [newName, setNewName] = useState("Training");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const result = await api.trainingExamples(statusFilter === "all" ? undefined : statusFilter, 500);
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Could not load training data.");
      setPayload(null);
    } else if (result.data) {
      setPayload(result.data);
      setAutoCapture(result.data.auto_capture);
    }
    setLoading(false);
  }, [statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void api.trainingSettings().then((result) => {
      if (result.data?.ok) setAutoCapture(result.data.auto_capture);
    });
  }, []);

  const examples = payload?.examples || [];
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return examples;
    return examples.filter((example) =>
      [example.user_text, example.model_reply, example.first_name, example.source, example.status]
        .some((value) => String(value || "").toLocaleLowerCase().includes(needle)),
    );
  }, [examples, query]);

  const counts = useMemo(() => {
    const all = payload?.examples || [];
    return {
      total: payload?.total ?? all.length,
      approved: all.filter((item) => item.status === "approved").length,
      pending: all.filter((item) => item.status === "pending").length,
      rejected: all.filter((item) => item.status === "rejected").length,
    };
  }, [payload]);

  const setBusy = (id: string, value: boolean) => {
    setBusyIds((current) => ({ ...current, [id]: value }));
  };

  const updateStatus = async (example: TrainingExample, status: "approved" | "rejected" | "pending") => {
    setBusy(example.id, true);
    setError("");
    setNotice("");
    const result = status === "approved"
      ? await api.approveTrainingExample(example.id)
      : status === "rejected"
        ? await api.rejectTrainingExample(example.id)
        : await api.approveTrainingExample(example.id);
    setBusy(example.id, false);
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Could not update training example.");
      return;
    }
    setNotice(result.data?.message || `Example marked ${status}.`);
    void load();
  };

  const deleteExample = async (id: string) => {
    setBusy(id, true);
    setError("");
    setNotice("");
    const result = await api.deleteTrainingExample(id);
    setBusy(id, false);
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Could not delete training example.");
      return;
    }
    setNotice(result.data?.message || "Training example deleted.");
    void load();
  };

  const addExample = async () => {
    const userText = newUserText.trim();
    const reply = newReply.trim();
    if (!userText || !reply) {
      setError("Both user text and Ishani reply are required.");
      return;
    }
    setAdding(true);
    setError("");
    setNotice("");
    const result = await api.addTrainingExample({ user_text: userText, model_reply: reply, first_name: newName.trim() || "Training" });
    setAdding(false);
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Could not add training example.");
      return;
    }
    setNewUserText("");
    setNewReply("");
    setNotice("Training example added and approved.");
    void load();
  };

  const toggleAutoCapture = async () => {
    setSavingSettings(true);
    setError("");
    setNotice("");
    const result = await api.setTrainingSettings({ auto_capture: !autoCapture });
    setSavingSettings(false);
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Could not update training settings.");
      return;
    }
    setAutoCapture(result.data?.auto_capture ?? !autoCapture);
    setNotice(`Auto-capture ${result.data?.auto_capture ? "enabled" : "disabled"}.`);
  };

  const exportJsonl = async () => {
    setError("");
    const result = await api.exportTraining("approved");
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Could not export training data.");
      return;
    }
    const blob = new Blob([result.data?.content || ""], { type: "application/jsonl" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "ishani-training-approved.jsonl";
    link.click();
    URL.revokeObjectURL(url);
    setNotice(`Exported ${result.data?.count ?? 0} approved examples.`);
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Inbuilt training</h1>
          <p className="page-sub">
            Successful user/model turns are captured automatically. Approve the ones that sound like the Ishani you want;
            approved examples become few-shot training data in future replies.
          </p>
        </div>
        <div className="row">
          <Badge tone={autoCapture ? "ok" : "neutral"}>
            <Icon name="sparkles" size={13} /> Auto-capture {autoCapture ? "on" : "off"}
          </Badge>
          <Button variant="secondary" icon="refresh" onClick={() => void load()} loading={loading}>
            Refresh
          </Button>
        </div>
      </div>

      {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}
      {notice && <Notice kind="success" onDismiss={() => setNotice("")}>{notice}</Notice>}

      <div className="stats">
        <StatCard icon="file" label="Training examples" value={counts.total} foot={`${counts.approved} approved`} />
        <StatCard icon="checkCircle" label="Approved" value={counts.approved} foot="Used in prompts" />
        <StatCard icon="alert" label="Pending" value={counts.pending} foot="Needs review" />
        <StatCard icon="xCircle" label="Rejected" value={counts.rejected} foot="Ignored" />
      </div>

      <Card title="Training settings" subtitle="Auto-capture stores successful Telegram turns as pending examples">
        <div className="row">
          <Button
            variant={autoCapture ? "secondary" : "primary"}
            icon={autoCapture ? "xCircle" : "checkCircle"}
            loading={savingSettings}
            onClick={() => void toggleAutoCapture()}
          >
            {autoCapture ? "Disable auto-capture" : "Enable auto-capture"}
          </Button>
          <Button variant="secondary" icon="external" onClick={() => void exportJsonl()}>
            Export approved JSONL
          </Button>
          <Badge tone="neutral">{payload?.auto_capture ? "Auto-capture on" : "Auto-capture off"}</Badge>
        </div>
        <p className="fineprint">
          No raw API keys, prompts or connection strings are stored. Only user text and Ishani reply text are used.
        </p>
      </Card>

      <Card title="Add training example" subtitle="Manual examples are approved immediately">
        <div className="grid-2">
          <div className="col">
            <label className="cell-sub" htmlFor="training-user">User said</label>
            <textarea
              id="training-user"
              value={newUserText}
              onChange={(event) => setNewUserText(event.target.value)}
              rows={4}
              maxLength={1000}
              placeholder="What should Ishani answer to?"
            />
          </div>
          <div className="col">
            <label className="cell-sub" htmlFor="training-reply">Ishani should reply</label>
            <textarea
              id="training-reply"
              value={newReply}
              onChange={(event) => setNewReply(event.target.value)}
              rows={4}
              maxLength={1000}
              placeholder="The ideal Hinglish reply"
            />
          </div>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder="Label (optional)"
            aria-label="Training example label"
            style={{ maxWidth: 220 }}
          />
          <Button icon="plus" loading={adding} onClick={() => void addExample()}>
            Add approved example
          </Button>
        </div>
      </Card>

      <Card title="Training data" subtitle="Review, approve, reject or delete learned turns">
        <div className="toolbar">
          <div className="search-box">
            <Icon name="search" size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search user text or reply..."
              aria-label="Search training data"
            />
          </div>
          <div className="row">
            {["all", "approved", "pending", "rejected"].map((status) => (
              <Button
                key={status}
                size="sm"
                variant={statusFilter === status ? "primary" : "secondary"}
                onClick={() => setStatusFilter(status)}
              >
                {status}
              </Button>
            ))}
          </div>
          <Badge tone="neutral">{filtered.length} shown</Badge>
        </div>

        {loading ? (
          <div className="activity-list">
            {[0, 1, 2, 3].map((index) => (
              <div key={index} className="skeleton" style={{ height: 68 }} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState icon="sparkles" title="No training examples yet">
            Successful Telegram turns will appear here when auto-capture is enabled.
          </EmptyState>
        ) : (
          <div className="activity-list">
            {filtered.map((example) => {
              const busy = Boolean(busyIds[example.id]);
              return (
                <div className="activity-item" key={example.id}>
                  <div className="grow">
                    <div className="row" style={{ marginBottom: 6 }}>
                      <Badge tone={statusTone(example.status)}>{example.status}</Badge>
                      <Badge tone="neutral">{example.source || "telegram"}</Badge>
                      <span className="cell-sub">
                        {example.first_name || `User ${example.user_id}`} · {formatDate(example.created_at)}
                      </span>
                    </div>
                    <div className="cell-strong" style={{ marginBottom: 4 }}>User: {shortText(example.user_text, 180)}</div>
                    <div className="cell-sub" style={{ whiteSpace: "pre-wrap" }}>Ishani: {shortText(example.model_reply, 180)}</div>
                  </div>
                  <div className="row-actions">
                    <Button size="sm" variant="secondary" icon="check" loading={busy} disabled={busy || example.status === "approved"} onClick={() => void updateStatus(example, "approved")}>
                      Approve
                    </Button>
                    <Button size="sm" variant="secondary" icon="xCircle" loading={busy} disabled={busy || example.status === "rejected"} onClick={() => void updateStatus(example, "rejected")}>
                      Reject
                    </Button>
                    <Button size="sm" variant="ghost" icon="trash" loading={busy} disabled={busy} onClick={() => void deleteExample(example.id)}>
                      Delete
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
