"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type {
  BroadcastTemplate,
  MongoOverviewPayload,
  MongoTurn,
  UserBroadcastResult,
  UserEntry,
  UsersPayload,
} from "@/types";
import { StatCard } from "@/components/dashboard/StatCard";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/shared/Button";
import { Badge, type BadgeTone } from "@/components/shared/Badge";
import { Notice } from "@/components/shared/Notice";
import { EmptyState } from "@/components/shared/EmptyState";
import { Icon } from "@/components/shared/Icon";

function shortText(value: string | undefined, limit = 90): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "—";
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function statusTone(status: string | undefined): BadgeTone {
  const value = String(status || "").toLowerCase();
  if (["ok", "success", "done", "completed", "sent"].includes(value)) return "ok";
  if (["error", "failed", "fail"].includes(value)) return "bad";
  if (["pending", "queued", "warning"].includes(value)) return "warn";
  return "neutral";
}

function TurnList({ turns, emptyTitle }: { turns: MongoTurn[]; emptyTitle: string }) {
  if (turns.length === 0) {
    return <EmptyState icon="file" title={emptyTitle}>No Mongo turns recorded for this scope yet.</EmptyState>;
  }
  return (
    <div className="activity-list">
      {turns.slice(0, 5).map((turn) => (
        <div className="activity-item" key={turn.id}>
          <div>
            <div className="cell-strong">
              {turn.first_name || `User ${turn.user_id}`} <span className="mono">· {turn.user_id}</span>
            </div>
            <div className="cell-sub">User: {shortText(turn.user_text)}</div>
            <div className="cell-sub">Reply: {shortText(turn.model_reply)}</div>
            <div className="row" style={{ marginTop: 5 }}>
              {turn.model && <Badge tone="neutral">{turn.model}</Badge>}
              {turn.status && <Badge tone={statusTone(turn.status)}>{turn.status}</Badge>}
              {turn.response_kind && <Badge tone="info">{turn.response_kind}</Badge>}
              {turn.scope && <Badge tone="neutral">{turn.scope}</Badge>}
            </div>
          </div>
          <span className="timestamp">{formatDate(turn.created_at)}</span>
        </div>
      ))}
    </div>
  );
}

export default function UsersPage() {
  const [users, setUsers] = useState<UsersPayload | null>(null);
  const [overview, setOverview] = useState<MongoOverviewPayload | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyIds, setBusyIds] = useState<Record<number, boolean>>({});
  const [query, setQuery] = useState("");

  const [templates, setTemplates] = useState<BroadcastTemplate[]>([]);
  const [startedQuery, setStartedQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [broadcastText, setBroadcastText] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [newTemplateName, setNewTemplateName] = useState("");
  const [newTemplateText, setNewTemplateText] = useState("");
  const [sendingBroadcast, setSendingBroadcast] = useState(false);
  const [broadcastResult, setBroadcastResult] = useState<UserBroadcastResult | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [usersResult, mongoResult, templatesResult] = await Promise.all([
      api.users(),
      api.mongoOverview(),
      api.broadcastTemplates(),
    ]);
    const messages = [
      usersResult.error,
      mongoResult.error,
      templatesResult.error,
    ].filter((message): message is string => Boolean(message));
    setError(messages.join(" "));
    if (usersResult.data) setUsers(usersResult.data);
    if (mongoResult.data) setOverview(mongoResult.data);
    if (templatesResult.data) setTemplates(templatesResult.data.templates || []);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleFullMemory = async (user: UserEntry) => {
    const enabled = !user.full_memory;
    setBusyIds((current) => ({ ...current, [user.user_id]: true }));
    setError("");
    setNotice("");
    const result = await api.setFullMemory({ user_id: user.user_id, enabled });
    setBusyIds((current) => ({ ...current, [user.user_id]: false }));
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Could not update full-memory access.");
      return;
    }
    setNotice(result.data?.message || `Full memory ${enabled ? "enabled" : "disabled"} for user ${user.user_id}.`);
    void load();
  };

  const chooseTemplate = (id: string) => {
    setTemplateId(id);
    const template = templates.find((item) => item.id === id);
    if (template) setBroadcastText(template.text);
  };

  const addTemplate = async () => {
    const text = newTemplateText.trim();
    if (!text) {
      setError("Template text is required.");
      return;
    }
    const result = await api.addBroadcastTemplate({ name: newTemplateName.trim(), text });
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Could not save template.");
      return;
    }
    setTemplates(result.data?.templates || []);
    setNewTemplateName("");
    setNewTemplateText("");
    setNotice("Broadcast template saved.");
  };

  const removeTemplate = async (id: string) => {
    const result = await api.removeBroadcastTemplate({ id });
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Could not delete template.");
      return;
    }
    setTemplates(result.data?.templates || []);
    if (templateId === id) {
      setTemplateId("");
      setBroadcastText("");
    }
    setNotice("Broadcast template deleted.");
  };

  const toggleSelected = (userId: number) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  };

  const sendBroadcast = async () => {
    const text = broadcastText.trim();
    if (!text && !templateId) {
      setError("Write a message or choose a template first.");
      return;
    }
    setSendingBroadcast(true);
    setError("");
    setNotice("");
    setBroadcastResult(null);
    const result = await api.broadcastUsers({
      user_ids: selectedIds.size ? Array.from(selectedIds) : "all_started",
      message: text,
      ...(templateId ? { template_id: templateId } : {}),
    });
    setSendingBroadcast(false);
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Broadcast failed.");
      return;
    }
    setBroadcastResult(result.data || null);
    setNotice(`Broadcast sent to ${result.data?.sent ?? 0} user(s), ${result.data?.failed ?? 0} failed.`);
  };

  const master = users?.role === "master";
  const storage = overview?.storage;
  const cards = overview?.cards;
  const allUsers = users?.users || [];
  const filteredUsers = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return allUsers;
    return allUsers.filter((user) =>
      [String(user.user_id), user.first_name, user.username, user.role]
        .some((value) => String(value || "").toLocaleLowerCase().includes(needle)),
    );
  }, [allUsers, query]);

  const startedUsers = useMemo(() => allUsers.filter((user) => user.started_bot), [allUsers]);
  const filteredStarted = useMemo(() => {
    const needle = startedQuery.trim().toLocaleLowerCase();
    if (!needle) return startedUsers;
    return startedUsers.filter((user) =>
      [String(user.user_id), user.first_name, user.username]
        .some((value) => String(value || "").toLocaleLowerCase().includes(needle)),
    );
  }, [startedUsers, startedQuery]);
  const allFilteredSelected = filteredStarted.length > 0
    && filteredStarted.every((user) => selectedIds.has(user.user_id));

  const toggleAllFiltered = () => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allFilteredSelected) filteredStarted.forEach((user) => next.delete(user.user_id));
      else filteredStarted.forEach((user) => next.add(user.user_id));
      return next;
    });
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Users &amp; Mongo memory</h1>
          <p className="page-sub">
            Mongo is the primary store for conversation turns and bot state. Full-memory trusted mode lets a user
            carry more history into AI replies — it grants memory only and never grants admin or owner powers.
          </p>
        </div>
        <div className="row">
          <Badge tone={master ? "info" : "neutral"}>
            <Icon name="shield" size={13} /> {master ? "Master scope" : "Read-only scope"}
          </Badge>
          <Button variant="secondary" icon="refresh" onClick={() => void load()} loading={loading}>
            Refresh
          </Button>
        </div>
      </div>

      {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}
      {notice && <Notice kind="success" onDismiss={() => setNotice("")}>{notice}</Notice>}
      {users && !master && (
        <Notice kind="warning">
          Master scope is required to change full-memory access. Available data is shown read-only below.
        </Notice>
      )}

      <div className="stats">
        <StatCard
          icon="users"
          label="Mongo users"
          value={users?.stats.mongo_users ?? cards?.users.unique_users ?? 0}
          foot={`${users?.stats.stored_turns ?? cards?.users.documents ?? 0} stored turns`}
        />
        <StatCard
          icon="checkCircle"
          label="Started users"
          value={users?.stats.started_users ?? startedUsers.length}
          foot={`${users?.stats.total ?? allUsers.length} known users`}
        />
        <StatCard
          icon="robot"
          label="AI model turns"
          value={cards?.ai_model.documents ?? 0}
          foot={`${cards?.ai_model.unique_users ?? 0} users`}
        />
        <StatCard
          icon="shield"
          label="Admin turns"
          value={cards?.admins.documents ?? 0}
          foot={`${cards?.admins.unique_users ?? 0} users`}
        />
        <StatCard
          icon="sparkles"
          label="Full-memory users"
          value={users?.stats.full_memory ?? 0}
          foot={`of ${users?.stats.total ?? 0} known users`}
        />
        <StatCard
          icon="file"
          label="Stored turns"
          value={users?.stats.stored_turns ?? cards?.users.documents ?? 0}
          foot={`${users?.stats.mongo_users ?? cards?.users.unique_users ?? 0} users with chat state`}
        />
      </div>

      <Card title="Storage" subtitle="Read from the bot's Mongo configuration">
        <div className="kv">
          <div className="kv-item">
            <span>Mongo primary</span>
            <strong>
              <Badge tone={storage?.mongo_primary ? "ok" : "bad"}>
                <span className="dot" /> {storage?.mongo_primary ? "Online" : "Offline"}
              </Badge>
            </strong>
          </div>
          <div className="kv-item">
            <span>Database</span>
            <strong className="mono">{storage?.database || "—"}</strong>
          </div>
          <div className="kv-item">
            <span>Chat collection</span>
            <strong className="mono">{storage?.chat_collection || "—"}</strong>
          </div>
          <div className="kv-item">
            <span>State collections</span>
            <strong className="mono">{storage?.state_collections?.length ? storage.state_collections.join(", ") : "—"}</strong>
          </div>
        </div>
        <p className="fineprint">
          Conversation turns live in Mongo; JSON files remain for bot-owned state. No credentials or connection strings are shown here.
        </p>
      </Card>

      <Card
        title="Users who started your bot"
        subtitle={`${startedUsers.length} user${startedUsers.length === 1 ? "" : "s"} started Ishani with /start`}
      >
        {startedUsers.length === 0 ? (
          <EmptyState icon="users" title="No /start records yet">
            Users will appear here after they send /start. Older users are backfilled on first launch.
          </EmptyState>
        ) : (
          <>
            <div className="toolbar">
              <div className="search-box">
                <Icon name="search" size={16} />
                <input
                  value={startedQuery}
                  onChange={(event) => setStartedQuery(event.target.value)}
                  placeholder="Search started users..."
                  aria-label="Search started users"
                />
              </div>
              <Button variant="secondary" size="sm" icon="check" onClick={toggleAllFiltered} disabled={!master}>
                {allFilteredSelected ? "Clear selection" : "Select filtered"}
              </Button>
              <Badge tone={selectedIds.size ? "ok" : "neutral"}>
                {selectedIds.size} selected · {filteredStarted.length} shown
              </Badge>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 36 }}>Select</th>
                    <th>User</th>
                    <th>Started</th>
                    <th>Messages</th>
                    <th>Last seen</th>
                    <th>Chat</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStarted.map((user) => (
                    <tr key={user.user_id}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Select ${user.first_name || user.user_id}`}
                          checked={selectedIds.has(user.user_id)}
                          disabled={!master}
                          onChange={() => toggleSelected(user.user_id)}
                        />
                      </td>
                      <td>
                        <div className="cell-strong">{user.first_name || user.username || `User ${user.user_id}`}</div>
                        <div className="cell-sub mono">
                          {user.user_id}{user.username ? ` · @${user.username}` : ""}
                        </div>
                      </td>
                      <td>{formatDate(user.started_at)}</td>
                      <td>{user.message_count}</td>
                      <td>{formatDate(user.last_seen)}</td>
                      <td>
                        <Link className="profile-link" href={`/users/${user.user_id}`}>
                          <Icon name="eye" size={15} /> Open chat
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="section-head" style={{ marginTop: 18 }}>
              <div>
                <h2>Mass message broadcast</h2>
                <p className="muted">
                  Sends a Telegram DM to selected users. Leave selection empty to target all {startedUsers.length} starters.
                  Templates support {"{first_name}"}, {"{name}"} and {"{id}"}.
                </p>
              </div>
              {broadcastResult && (
                <Badge tone="ok">
                  {broadcastResult.sent} sent · {broadcastResult.failed} failed
                </Badge>
              )}
            </div>

            <div className="grid-2">
              <div className="col">
                <label className="cell-sub" htmlFor="broadcast-template">Saved templates</label>
                <select
                  id="broadcast-template"
                  value={templateId}
                  onChange={(event) => chooseTemplate(event.target.value)}
                  disabled={!master}
                >
                  <option value="">— Write your own message —</option>
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>{template.name}</option>
                  ))}
                </select>
                {templateId && (
                  <Button
                    variant="ghost"
                    size="sm"
                    icon="trash"
                    disabled={!master}
                    onClick={() => void removeTemplate(templateId)}
                  >
                    Delete selected template
                  </Button>
                )}
                <div className="row">
                  <input
                    value={newTemplateName}
                    onChange={(event) => setNewTemplateName(event.target.value)}
                    placeholder="Template name"
                    aria-label="New template name"
                    disabled={!master}
                  />
                  <Button size="sm" icon="plus" disabled={!master || !newTemplateText.trim()} onClick={() => void addTemplate()}>
                    Add template
                  </Button>
                </div>
                <textarea
                  value={newTemplateText}
                  onChange={(event) => setNewTemplateText(event.target.value)}
                  placeholder="New template text — use {first_name} for a personal touch"
                  aria-label="New template text"
                  rows={3}
                  maxLength={4000}
                  disabled={!master}
                />
              </div>
              <div className="col">
                <label className="cell-sub" htmlFor="broadcast-message">Message to send</label>
                <textarea
                  id="broadcast-message"
                  value={broadcastText}
                  onChange={(event) => {
                    setBroadcastText(event.target.value);
                    setTemplateId("");
                  }}
                  placeholder="Type the broadcast message..."
                  aria-label="Broadcast message"
                  rows={6}
                  maxLength={4000}
                  disabled={!master}
                />
                <div className="row">
                  <Button
                    icon="broadcast"
                    loading={sendingBroadcast}
                    disabled={!master || (!broadcastText.trim() && !templateId)}
                    onClick={() => void sendBroadcast()}
                  >
                    Send to {selectedIds.size ? `${selectedIds.size} selected` : `all ${startedUsers.length}`}
                  </Button>
                  <Badge tone="neutral">{broadcastText.length}/4000</Badge>
                </div>
                <p className="fineprint">
                  Real Telegram sends only — no simulated results. Each delivery is recorded in the broadcast log.
                </p>
              </div>
            </div>

            {broadcastResult?.results && broadcastResult.results.some((item) => !item.ok) && (
              <div className="fineprint">
                Failures: {broadcastResult.results.filter((item) => !item.ok).slice(0, 10)
                  .map((item) => `${item.user_id}: ${item.error || "failed"}`).join(" · ")}
              </div>
            )}
          </>
        )}
      </Card>

      <Card title="Full-memory trusted users" subtitle="Memory trust only — this does not change Telegram permissions">
        {allUsers.length === 0 ? (
          <EmptyState icon="users" title="No known users yet">Users will appear after their first recorded turn.</EmptyState>
        ) : (
          <>
            <div className="toolbar">
              <div className="search-box">
                <Icon name="search" size={16} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search by name, username or ID..."
                  aria-label="Search users"
                />
              </div>
              <Badge tone="neutral">{filteredUsers.length} of {allUsers.length} users</Badge>
            </div>
            {filteredUsers.length === 0 ? (
              <EmptyState icon="search" title="No users match this search">Try a different name, username or user ID.</EmptyState>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Started</th>
                      <th>Messages</th>
                      <th>Mongo turns</th>
                      <th>Last seen</th>
                      <th>Role</th>
                      <th>Memory</th>
                      <th>Chats</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUsers.map((user) => {
                      const busy = Boolean(busyIds[user.user_id]);
                      return (
                        <tr key={user.user_id}>
                          <td>
                            <div className="cell-strong">{user.first_name || user.username || `User ${user.user_id}`}</div>
                            <div className="cell-sub mono">
                              {user.user_id}{user.username ? ` · @${user.username}` : ""}
                            </div>
                          </td>
                          <td>
                            <Badge tone={user.started_bot ? "ok" : "neutral"}>
                              {user.started_bot ? "Yes" : "No"}
                            </Badge>
                          </td>
                          <td>{user.message_count}</td>
                          <td>{user.logged_turns ?? "—"}</td>
                          <td>{formatDate(user.last_seen)}</td>
                          <td>
                            {user.role ? (
                              <Badge tone={user.role === "master" ? "info" : "neutral"}>{user.role}</Badge>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td>
                            <Badge tone={user.full_memory ? "ok" : "neutral"}>
                              {user.full_memory ? "Full memory" : "Standard"}
                            </Badge>
                            {user.full_memory_since && <div className="cell-sub">Since {formatDate(user.full_memory_since)}</div>}
                          </td>
                          <td>
                            <Link className="profile-link" href={`/users/${user.user_id}`}>
                              <Icon name="eye" size={15} /> Open chat
                            </Link>
                          </td>
                          <td>
                            <Button
                              variant={user.full_memory ? "secondary" : "primary"}
                              size="sm"
                              icon={user.full_memory ? "xCircle" : "checkCircle"}
                              loading={busy}
                              disabled={!master || busy}
                              onClick={() => void toggleFullMemory(user)}
                            >
                              {user.full_memory ? "Disable" : "Enable"}
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
        <p className="fineprint">
          Enabling full memory changes how much history Ishani may recall for that user. It does not grant admin powers,
          owner status or Telegram group permissions.
        </p>
      </Card>

      <div className="grid-3">
        <Card title="User turns" subtitle="Most recent Mongo turns from users">
          <TurnList turns={overview?.recent.users || []} emptyTitle="No user turns yet" />
        </Card>
        <Card title="AI model turns" subtitle="Most recent Mongo turns from AI replies">
          <TurnList turns={overview?.recent.ai_model || []} emptyTitle="No AI model turns yet" />
        </Card>
        <Card title="Admin turns" subtitle="Most recent Mongo turns from admins">
          <TurnList turns={overview?.recent.admins || []} emptyTitle="No admin turns yet" />
        </Card>
      </div>
    </div>
  );
}
