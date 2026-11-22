"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Alert, AuditEntry, Group, OverviewPayload, GroupsPayload } from "@/types";
import { StatCard } from "@/components/dashboard/StatCard";
import { AlertsPanel } from "@/components/dashboard/AlertsPanel";
import { ActivityFeed } from "@/components/dashboard/ActivityFeed";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/shared/Button";
import { Badge } from "@/components/shared/Badge";
import { Notice } from "@/components/shared/Notice";
import { Icon } from "@/components/shared/Icon";
import { EmptyState } from "@/components/shared/EmptyState";

export default function DashboardHome() {
  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [groups, setGroups] = useState<GroupsPayload | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const [o, g] = await Promise.all([api.overview(), api.groups()]);
    if (o.error) setError(o.error);
    else {
      setError("");
      setOverview(o.data);
    }
    if (g.data?.ok) setGroups(g.data);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const stats = overview?.stats;
  const alerts: Alert[] = overview?.alerts || groups?.alerts || [];
  const activity: AuditEntry[] = overview?.activity || [];
  const visibleGroups: Group[] = groups?.groups || [];

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Command overview</h1>
          <p className="page-sub">
            Live state from the Python bot backend. Every number below comes from tracked groups,
            Telegram responses or recorded actions — never estimated.
          </p>
        </div>
        <div className="row">
          <Badge tone={overview?.role === "master" ? "info" : "neutral"}>
            <Icon name="shield" size={13} /> {overview?.role === "master" ? "Master scope" : "Owner scope"}
          </Badge>
          <Button variant="secondary" icon="refresh" onClick={() => void load()} loading={loading}>
            Refresh
          </Button>
        </div>
      </div>

      {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}

      <div className="stats">
        <StatCard icon="groups" label="Connected groups" value={stats?.groups ?? visibleGroups.length} foot="In your visible scope" />
        <StatCard icon="users" label="Group members" value={stats?.members ?? 0} foot="From Telegram counts" />
        <StatCard icon="shield" label="Administrators" value={stats?.administrators ?? 0} foot="Across visible groups" />
        <StatCard icon="owners" label="Registered owners" value={stats?.owners ?? 0} foot="Master + accepted owners" />
        <StatCard icon="checkCircle" label="Active groups" value={stats?.active_groups ?? 0} foot="Verified registration" />
        <StatCard icon="alert" label="Inactive groups" value={stats?.inactive_groups ?? 0} foot="Pending verification" />
      </div>

      <div className="grid-2">
        <Card title="Bot connection & permissions" subtitle="Real backend state">
          <div className="kv">
            <div className="kv-item">
              <span>Bot connected</span>
              <strong>
                <Badge tone={stats?.bot_connected ? "ok" : "bad"}>
                  <span className="dot" /> {stats?.bot_connected ? "Online" : "Offline"}
                </Badge>
              </strong>
            </div>
            <div className="kv-item">
              <span>Groups with bot admin</span>
              <strong>{stats?.bot_admin_groups ?? 0}</strong>
            </div>
            <div className="kv-item">
              <span>Link-protected groups</span>
              <strong>{stats?.link_protected_groups ?? 0}</strong>
            </div>
            <div className="kv-item">
              <span>Muted groups</span>
              <strong>{stats?.muted_groups ?? 0}</strong>
            </div>
          </div>
          <p className="fineprint">
            Permission details are read from Telegram when available. Unknown values stay blank rather than being guessed.
          </p>
        </Card>

        <AlertsPanel alerts={alerts} />
      </div>

      <div className="grid-2">
        <Card
          title="Your groups"
          subtitle="Top visible groups by recorded member count"
          actions={<Link href="/groups" className="btn secondary sm">Open Groups <Icon name="chevron" size={14} /></Link>}
        >
          {visibleGroups.length === 0 ? (
            <EmptyState icon="groups" title="No groups assigned yet">
              Invite a Group Owner with /assign or register a group with /registergroup.
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Group</th><th>ID</th><th>Status</th><th>Members</th><th>Admins</th></tr>
                </thead>
                <tbody>
                  {visibleGroups.slice(0, 8).map((group) => (
                    <tr key={group.id}>
                      <td>
                        <div className="cell-strong">{group.name}</div>
                        <div className="cell-sub">{group.username ? `@${group.username}` : "Private / no username"}</div>
                      </td>
                      <td className="mono">{group.id}</td>
                      <td><Badge tone={group.registration_status === "verified" ? "ok" : "warn"}>{group.registration_status}</Badge></td>
                      <td>{group.stats?.members ?? 0}</td>
                      <td>{group.stats?.administrators ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Delivery status" subtitle="Most recent broadcasts with verified results">
          {(groups?.broadcasts || []).length === 0 ? (
            <EmptyState icon="broadcast" title="No broadcasts recorded">Send one from the Broadcasts page.</EmptyState>
          ) : (
            <div className="activity-list">
              {groups?.broadcasts?.map((entry, index) => (
                <div className="activity-item" key={`${entry.at}-${index}`}>
                  <div>
                    <strong className="cell-strong">{entry.scope}</strong>
                    <div className="cell-sub">
                      <span className={entry.failed ? "cell-sub" : ""}>Sent {entry.sent}</span> · Failed {entry.failed}
                    </div>
                  </div>
                  <span className="timestamp">{formatDate(entry.at)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <ActivityFeed entries={activity} />
    </div>
  );
}
