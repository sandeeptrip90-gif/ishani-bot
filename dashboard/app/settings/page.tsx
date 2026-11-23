"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { ScheduledItem } from "@/types";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/shared/Button";
import { Badge } from "@/components/shared/Badge";
import { Notice } from "@/components/shared/Notice";
import { EmptyState } from "@/components/shared/EmptyState";

export default function SettingsPage() {
  const [config, setConfig] = useState<{ endpoint?: string; model?: string; has_key?: boolean } | null>(null);
  const [endpoint, setEndpoint] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [lessons, setLessons] = useState<string[]>([]);
  const [linkControls, setLinkControls] = useState<Record<string, unknown>>({});
  const [newLesson, setNewLesson] = useState("");
  const [scheduled, setScheduled] = useState<ScheduledItem[]>([]);
  const [masterOnly, setMasterOnly] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [configResult, lessonsResult, scheduleResult] = await Promise.all([
      api.config(),
      api.lessons(),
      api.schedule(),
    ]);
    if (configResult.status === 401 || configResult.status === 403 || configResult.status === 404) setMasterOnly(true);
    else if (configResult.error) setError(configResult.error);
    else if (configResult.data) {
      setConfig(configResult.data);
      setEndpoint(configResult.data.endpoint || "");
      setModel(configResult.data.model || "");
    }
    if (lessonsResult.data?.ok) {
      setLessons(lessonsResult.data.lessons || []);
      setLinkControls(lessonsResult.data.link_controls || {});
    }
    if (scheduleResult.data?.ok) setScheduled(scheduleResult.data.items || []);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const saveConfig = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    const result = await api.saveConfig({ endpoint, model, ...(apiKey ? { api_key: apiKey } : {}) });
    setBusy(false);
    if (result.error) setError(result.error);
    else {
      setNotice(result.data?.message || "Model settings saved.");
      setApiKey("");
      void load();
    }
  };

  const testConnection = async () => {
    setBusy(true);
    setError("");
    const result = await api.testConfig({ endpoint, model, ...(apiKey ? { api_key: apiKey } : {}) });
    setBusy(false);
    if (result.error || result.data?.ok === false) setError(result.error || result.data?.message || "Connection test failed.");
    else setNotice(result.data?.message || "Connection test passed.");
  };

  const addLesson = async () => {
    if (!newLesson.trim()) {
      setError("Lesson bharin.");
      return;
    }
    setBusy(true);
    setError("");
    const result = await api.addLesson({ instruction: newLesson.trim() });
    setBusy(false);
    if (result.error) setError(result.error);
    else {
      setNotice("Lesson saved to Ishani's persona (master_prompt unchanged).");
      setNewLesson("");
      void load();
    }
  };

  const removeSchedule = async (item: ScheduledItem) => {
    setBusy(true);
    const result = await api.removeSchedule({ id: item.id });
    setBusy(false);
    if (result.error) setError(result.error);
    else {
      setNotice(`Removed scheduled message ${item.id}.`);
      void load();
    }
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Settings &amp; AI behavior</h1>
          <p className="page-sub">
            Provider/model configuration, global lessons, conversation history and scheduled messages.
            Ishani's identity, persona and group-specific instructions are preserved — nothing here replaces them.
          </p>
        </div>
      </div>

      {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}
      {notice && <Notice kind="success" onDismiss={() => setNotice("")}>{notice}</Notice>}

      <div className="grid-2">
        <Card title="AI provider &amp; model" subtitle={masterOnly ? "Master Owner only" : "Local OpenAI-compatible endpoint"}>
          {masterOnly ? (
            <EmptyState icon="shield" title="Master Owner only">Model configuration is hidden from Group Owners.</EmptyState>
          ) : (
            <>
              <div className="field"><label>Endpoint</label><input value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="https://your-endpoint.example/v1" /></div>
              <div className="field"><label>Model</label><input value={model} onChange={(event) => setModel(event.target.value)} placeholder="Exact model name" /></div>
              <div className="field">
                <label>API key {config?.has_key ? "(one is already stored — leave blank to keep)" : ""}</label>
                <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} autoComplete="off" />
              </div>
              <div className="row">
                <Button icon="check" loading={busy} onClick={() => void saveConfig()}>Save</Button>
                <Button variant="secondary" icon="bolt" loading={busy} onClick={() => void testConnection()}>Test connection</Button>
              </div>
            </>
          )}
        </Card>

        <Card title="Global admin lessons" subtitle="Stored in persona.json without changing master_prompt">
          {masterOnly ? (
            <EmptyState icon="shield" title="Master Owner only">Lessons are private to the master owner.</EmptyState>
          ) : (
            <>
              {lessons.length === 0 ? (
                <EmptyState icon="sparkles" title="No admin lessons yet">Add a durable instruction for Ishani.</EmptyState>
              ) : (
                <div className="activity-list" style={{ marginBottom: 12 }}>
                  {lessons.map((lesson, index) => (
                    <div className="activity-item" key={`${lesson}-${index}`}><span>{lesson}</span></div>
                  ))}
                </div>
              )}
              <div className="field"><label>New lesson</label><textarea value={newLesson} onChange={(event) => setNewLesson(event.target.value)} placeholder="e.g. Always mention Telegram IDs when summarizing groups." /></div>
              <Button icon="plus" loading={busy} onClick={() => void addLesson()}>Add lesson</Button>
              {Object.keys(linkControls).length > 0 && (
                <p className="fineprint">Link controls: {JSON.stringify(linkControls)}</p>
              )}
            </>
          )}
        </Card>
      </div>

      <div className="grid-2">
        <Card title="History &amp; instructions" subtitle="Existing persona data stays where it is">
          <div className="stack">
            <Link className="btn secondary" href="/ai-chats"><span>Open personal AI conversations</span></Link>
            <Link className="btn secondary" href="/tasks"><span>Open task history</span></Link>
            <Link className="btn secondary" href="/groups"><span>Edit group-specific AI instructions</span></Link>
            <p className="fineprint">Personal chats are scoped to the web dashboard and stored in the bot's JSON chat files.</p>
          </div>
        </Card>

        <Card title="Scheduled messages" subtitle="Queued in JSON; delivered by the bot scheduler">
          {scheduled.length === 0 ? (
            <EmptyState icon="clock" title="Nothing scheduled">Queue a message from a group's Moderation tab.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Group</th><th>Message</th><th>Send at</th><th>Status</th><th></th></tr></thead>
                <tbody>
                  {scheduled.map((item) => (
                    <tr key={item.id}>
                      <td className="mono">{item.group_id}</td>
                      <td className="cell-strong">{item.text}</td>
                      <td>{formatDate(item.send_at)}</td>
                      <td><Badge tone={item.status === "sent" ? "ok" : "warn"}>{item.status}</Badge></td>
                      <td><Button variant="ghost" size="sm" icon="trash" loading={busy} onClick={() => void removeSchedule(item)}>Remove</Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
