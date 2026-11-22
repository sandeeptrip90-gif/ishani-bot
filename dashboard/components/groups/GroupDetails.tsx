"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { AuditEntry, Group, MembersPayload } from "@/types";
import { Card } from "@/components/shared/Card";
import { Badge } from "@/components/shared/Badge";
import { Button } from "@/components/shared/Button";
import { Notice } from "@/components/shared/Notice";
import { Icon } from "@/components/shared/Icon";
import { ActivityFeed } from "@/components/dashboard/ActivityFeed";
import { AdministratorsPanel, MembersPanel } from "./MembersPanel";

const TABS = ["Overview", "Administrators", "Members", "Permissions", "Moderation", "Settings", "Activity"] as const;
type Tab = (typeof TABS)[number];

export function GroupDetails({ groupId }: { groupId: number }) {
  const [tab, setTab] = useState<Tab>("Overview");
  const [group, setGroup] = useState<Group | null>(null);
  const [members, setMembers] = useState<MembersPayload | null>(null);
  const [activity, setActivity] = useState<AuditEntry[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [messageId, setMessageId] = useState("");
  const [scheduledText, setScheduledText] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [detail, people, log] = await Promise.all([
      api.group(groupId),
      api.members(groupId),
      api.activity(),
    ]);
    if (detail.error) setError(detail.error);
    else if (detail.data?.group) {
      setGroup(detail.data.group);
      const business = detail.data.group.business || {};
      const s = detail.data.group.settings || {};
      setSettings({
        name: String(business.name || ""),
        join_link: String(business.join_link || ""),
        welcome_message: String(business.welcome_message || ""),
        goodbye_message: String(business.goodbye_message || ""),
        ai_instructions: String(business.ai_instructions || ""),
        links_allowed: String(Boolean(s.links_allowed)),
        spam_protection: String(Boolean(s.spam_protection)),
        active: String(s.active === undefined ? true : Boolean(s.active)),
        bot_muted: String(Boolean(s.bot_muted)),
      });
    }
    if (people.data?.ok) setMembers(people.data);
    if (log.data?.ok) {
      setActivity(
        (log.data.entries || []).filter((entry) =>
          String(entry.target) === String(groupId) || String(entry.details).includes(String(groupId)),
        ),
      );
    }
    setLoading(false);
  }, [groupId]);

  useEffect(() => {
    void load();
  }, [load]);

  const action = async (name: "pin" | "unpin" | "delete" | "mute" | "unmute") => {
    setError("");
    setNotice("");
    if ((name === "pin" || name === "unpin" || name === "delete") && !messageId.trim()) {
      setError("Pehle message ID bharin.");
      return;
    }
    if (name === "delete" && !window.confirm("This message will be deleted from Telegram. Continue?")) return;
    setBusy(true);
    const result = await api.groupAction({ group_id: groupId, action: name, message_id: messageId.trim(), confirm: true });
    setBusy(false);
    if (result.error) setError(result.error);
    else {
      setNotice(result.data?.note || `${name} request completed. Verified: ${result.data?.verified ? "yes" : "not available"}`);
      void load();
    }
  };

  const saveSettings = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    const keys = ["name", "join_link", "welcome_message", "goodbye_message", "ai_instructions", "links_allowed", "spam_protection", "active", "bot_muted"];
    let changed = 0;
    for (const key of keys) {
      const result = await api.groupSettings({ group_id: groupId, key, value: settings[key] ?? "" });
      if (result.error) {
        setError(`${key}: ${result.error}`);
        setBusy(false);
        return;
      }
      changed += 1;
    }
    setBusy(false);
    setNotice(`${changed} settings saved.`);
    void load();
  };

  const schedule = async () => {
    if (!scheduledText.trim() || !scheduledAt) {
      setError("Message aur future time dono bharin.");
      return;
    }
    setBusy(true);
    const result = await api.addSchedule({ group_id: groupId, text: scheduledText, send_at: new Date(scheduledAt).toISOString() });
    setBusy(false);
    if (result.error) setError(result.error);
    else {
      setNotice(result.data?.note || `Scheduled with id ${result.data?.id}.`);
      setScheduledText("");
      setScheduledAt("");
    }
  };

  if (loading && !group) return <div className="skeleton" style={{ height: 260 }} />;

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{group?.name || `Group ${groupId}`}</h1>
          <p className="page-sub">
            Telegram ID <span className="mono">{groupId}</span> · {group?.username ? `@${group.username}` : "Private group"}
          </p>
        </div>
        <div className="row">
          <Badge tone={group?.registration_status === "verified" ? "ok" : "warn"}>{group?.registration_status || "unknown"}</Badge>
          <Button variant="secondary" icon="refresh" onClick={() => void load()}>Reload</Button>
        </div>
      </div>

      {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}
      {notice && <Notice kind="success" onDismiss={() => setNotice("")}>{notice}</Notice>}

      <Card>
        <div className="tabs">
          {TABS.map((item) => (
            <button key={item} className={`tab ${tab === item ? "active" : ""}`} onClick={() => setTab(item)}>{item}</button>
          ))}
        </div>

        {tab === "Overview" && group && (
          <div className="stack">
            <div className="kv">
              <div className="kv-item"><span>Members</span><strong>{group.stats?.members ?? 0}</strong></div>
              <div className="kv-item"><span>Administrators</span><strong>{group.stats?.administrators ?? 0}</strong></div>
              <div className="kv-item"><span>Owner ID</span><strong className="mono">{group.owner_id ?? "—"}</strong></div>
              <div className="kv-item"><span>Registered</span><strong>{formatDate(group.registered_at || group.created_at)}</strong></div>
              <div className="kv-item"><span>Invite link</span><strong>{group.invite_link || group.business?.join_link ? String(group.invite_link || group.business?.join_link) : "Not recorded"}</strong></div>
              <div className="kv-item"><span>Stats checked</span><strong>{formatDate(group.stats?.checked_at)}</strong></div>
            </div>
            {group.stats?.title_error && <Notice kind="warning">Group title lookup failed: {group.stats.title_error}</Notice>}
            {(group.alerts || []).map((alert, index) => <Notice key={index} kind={alert.level === "danger" ? "error" : "warning"}>{alert.text}</Notice>)}
          </div>
        )}

        {tab === "Administrators" && (
          <AdministratorsPanel admins={members?.administrators || []} note={members?.note} />
        )}

        {tab === "Members" && (
          <MembersPanel members={members?.known_members || []} note={members?.note} />
        )}

        {tab === "Permissions" && (
          <div className="stack">
            <div className="kv">
              {Object.entries(group?.bot_permissions || {}).length === 0 ? (
                <div className="kv-item"><span>Bot permissions</span><strong>Not reported by Telegram</strong></div>
              ) : Object.entries(group?.bot_permissions || {}).map(([key, value]) => (
                <div className="kv-item" key={key}><span>{key.replace(/_/g, " ")}</span><strong>{String(value)}</strong></div>
              ))}
            </div>
            <div className="kv">
              <div className="kv-item"><span>Bot is admin</span><strong>{group?.bot_is_admin === undefined || group?.bot_is_admin === null ? "Unknown" : String(group.bot_is_admin)}</strong></div>
              <div className="kv-item"><span>Bot muted</span><strong>{String(Boolean(group?.settings?.bot_muted))}</strong></div>
            </div>
            <p className="fineprint">Permission values are shown only when the backend has actually read them from Telegram.</p>
          </div>
        )}

        {tab === "Moderation" && (
          <div className="stack">
            <div className="form-grid">
              <div className="field">
                <label htmlFor="message-id">Telegram message ID</label>
                <input id="message-id" value={messageId} onChange={(event) => setMessageId(event.target.value)} placeholder="e.g. 1234" />
              </div>
            </div>
            <div className="row">
              <Button icon="pin" variant="secondary" loading={busy} onClick={() => void action("pin")}>Pin message</Button>
              <Button icon="pin" variant="ghost" loading={busy} onClick={() => void action("unpin")}>Unpin</Button>
              <Button icon="trash" variant="danger" loading={busy} onClick={() => void action("delete")}>Delete message</Button>
              <Button icon="mute" variant="secondary" loading={busy} onClick={() => void action("mute")}>Mute bot</Button>
              <Button icon="unmute" variant="ghost" loading={busy} onClick={() => void action("unmute")}>Unmute bot</Button>
            </div>
            <Card title="Schedule a message" subtitle="Queued in JSON; delivered by the bot when its scheduler runs">
              <div className="form-grid">
                <div className="field"><label>Message</label><textarea value={scheduledText} onChange={(event) => setScheduledText(event.target.value)} /></div>
                <div className="field"><label>Send at</label><input type="datetime-local" value={scheduledAt} onChange={(event) => setScheduledAt(event.target.value)} /></div>
              </div>
              <Button icon="clock" loading={busy} onClick={() => void schedule()}>Queue message</Button>
            </Card>
          </div>
        )}

        {tab === "Settings" && (
          <div className="stack">
            <div className="form-grid">
              {["name", "join_link", "welcome_message", "goodbye_message", "ai_instructions"].map((key) => (
                <div className="field" key={key}>
                  <label>{key.replace(/_/g, " ")}</label>
                  {key.includes("message") || key === "ai_instructions"
                    ? <textarea value={settings[key] || ""} onChange={(event) => setSettings((s) => ({ ...s, [key]: event.target.value }))} />
                    : <input value={settings[key] || ""} onChange={(event) => setSettings((s) => ({ ...s, [key]: event.target.value }))} />}
                </div>
              ))}
            </div>
            <div className="row">
              {["links_allowed", "spam_protection", "active", "bot_muted"].map((key) => (
                <label className="checkbox" key={key}>
                  <input
                    type="checkbox"
                    checked={settings[key] === "true"}
                    onChange={(event) => setSettings((s) => ({ ...s, [key]: String(event.target.checked) }))}
                  />
                  {key.replace(/_/g, " ")}
                </label>
              ))}
            </div>
            <Button icon="check" loading={busy} onClick={() => void saveSettings()}>Save settings</Button>
          </div>
        )}

        {tab === "Activity" && <ActivityFeed entries={activity} title="Group activity" />}
      </Card>
    </div>
  );
}
