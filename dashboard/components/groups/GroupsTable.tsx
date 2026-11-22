"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { Group } from "@/types";
import { getSelectedGroups, setSelectedGroups } from "@/lib/selection";
import { Badge } from "@/components/shared/Badge";
import { Button } from "@/components/shared/Button";
import { Icon } from "@/components/shared/Icon";
import { Notice } from "@/components/shared/Notice";
import { copyToClipboard, formatDate } from "@/lib/format";

type SortKey = "name" | "id" | "members" | "administrators" | "registration" | "owner";

export function GroupsTable({
  groups,
  role,
  onChanged,
}: {
  groups: Group[];
  role: "master" | "group" | "unknown";
  onChanged: () => void;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("name");
  const [asc, setAsc] = useState(true);
  const [selected, setSelected] = useState<number[]>([]);
  const [selectionReady, setSelectionReady] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setSelected(getSelectedGroups());
    setSelectionReady(true);
  }, []);

  useEffect(() => {
    if (selectionReady) setSelectedGroups(selected);
  }, [selected, selectionReady]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = needle
      ? groups.filter((group) =>
          [group.name, group.id, group.username, group.owner_id, group.registration_status]
            .some((value) => String(value ?? "").toLowerCase().includes(needle)),
        )
      : [...groups];
    rows.sort((a, b) => {
      const value = (g: Group) => {
        switch (sort) {
          case "name": return g.name.toLowerCase();
          case "id": return g.id;
          case "members": return Number(g.stats?.members || 0);
          case "administrators": return Number(g.stats?.administrators || 0);
          case "registration": return String(g.registered_at || g.created_at || "");
          case "owner": return Number(g.owner_id || 0);
        }
      };
      const av = value(a);
      const bv = value(b);
      const result = typeof av === "string" && typeof bv === "string"
        ? av.localeCompare(bv)
        : Number(av) - Number(bv);
      return asc ? result : -result;
    });
    return rows;
  }, [groups, query, sort, asc]);

  const toggleSort = (key: SortKey) => {
    if (key === sort) setAsc((value) => !value);
    else {
      setSort(key);
      setAsc(true);
    }
  };

  const sortHeader = (key: SortKey, label: string) => (
    <button className="sort-btn" onClick={() => toggleSort(key)}>
      {label} {sort === key ? (asc ? "↑" : "↓") : ""}
    </button>
  );

  const copyInvite = async (group: Group) => {
    const link = String(group.invite_link || group.business?.join_link || "");
    if (!link) {
      setError("Is group ke liye koi invite link recorded nahi hai.");
      return;
    }
    const ok = await copyToClipboard(link);
    setMessage(ok ? "Invite link copied." : "Copy failed — select the link manually.");
  };

  const removeGroup = async (group: Group) => {
    if (role !== "master") {
      setError("Sirf Master Owner group remove kar sakta hai.");
      return;
    }
    if (!window.confirm(`Unassign group ${group.name} (${group.id})? Group data will not be deleted.`)) return;
    setBusy(group.id);
    setError("");
    const result = await apiFetchRemove(group.id);
    setMessage(result);
    setBusy(null);
    onChanged();
  };

  return (
    <>
      {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}
      {message && <Notice kind="success" onDismiss={() => setMessage("")}>{message}</Notice>}
      <div className="toolbar">
        <div className="search-box">
          <Icon name="search" size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by name, username, ID or owner..."
          />
        </div>
        <Badge tone="neutral">{filtered.length} of {groups.length} groups</Badge>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th><input type="checkbox" checked={selected.length === groups.length && groups.length > 0} onChange={(event) => setSelected(event.target.checked ? groups.map((g) => g.id) : [])} aria-label="Select all groups" /></th>
              <th>{sortHeader("name", "Group")}</th>
              <th>{sortHeader("id", "Telegram ID")}</th>
              <th>Type</th>
              <th>{sortHeader("members", "Members")}</th>
              <th>{sortHeader("administrators", "Admins")}</th>
              <th>{sortHeader("owner", "Owner")}</th>
              <th>Bot status</th>
              <th>{sortHeader("registration", "Registered")}</th>
              <th>Invite link</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan={11} className="muted">No groups match this search.</td></tr>
            ) : filtered.map((group) => {
              const link = String(group.invite_link || group.business?.join_link || "");
              return (
                <tr key={group.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.includes(group.id)}
                      onChange={() => setSelected((items) => items.includes(group.id) ? items.filter((id) => id !== group.id) : [...items, group.id])}
                      aria-label={`Select ${group.name}`}
                    />
                  </td>
                  <td>
                    <div className="cell-strong">{group.name}</div>
                    <div className="cell-sub">{group.username ? `@${group.username}` : "No public username"}</div>
                  </td>
                  <td className="mono">{group.id}</td>
                  <td><Badge tone={group.is_public || group.username ? "info" : "neutral"}>{group.is_public || group.username ? "Public" : "Private"}</Badge></td>
                  <td>{group.stats?.members ?? 0}</td>
                  <td>{group.stats?.administrators ?? 0}</td>
                  <td className="mono">{group.owner_id ?? "—"}</td>
                  <td>
                    {group.bot_is_admin === true ? <Badge tone="ok">Admin</Badge>
                      : group.bot_is_admin === false ? <Badge tone="bad">Not admin</Badge>
                      : <Badge tone="neutral">Unknown</Badge>}
                  </td>
                  <td>
                    <div>{formatDate(group.registered_at || group.created_at)}</div>
                    <div className="cell-sub"><Badge tone={group.registration_status === "verified" ? "ok" : "warn"}>{group.registration_status}</Badge></div>
                  </td>
                  <td>
                    {link ? (
                      <Button variant="ghost" size="sm" icon="copy" onClick={() => void copyInvite(group)}>Copy</Button>
                    ) : <span className="muted">Not recorded</span>}
                  </td>
                  <td>
                    <div className="row-actions">
                      <Link href={`/groups/${group.id}`} className="btn secondary sm"><Icon name="eye" size={14} /> Manage</Link>
                      <Button variant="ghost" size="sm" icon="trash" disabled={busy === group.id} onClick={() => void removeGroup(group)}>Remove</Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="fineprint">
        Selected groups are saved in this browser and prefilled on the Broadcasts page. Member counts are Telegram
        counts; admins are read from Telegram when the bot is connected.
      </p>
    </>
  );
}

// Local import kept at the bottom so the component file stays easy to scan.
import { api } from "@/lib/api";

async function apiFetchRemove(groupId: number): Promise<string> {
  const result = await api.removeGroup({ group_id: groupId });
  if (result.error) return `Remove failed: ${result.error}`;
  return result.data?.message || `Group ${groupId} unassigned.`;
}
