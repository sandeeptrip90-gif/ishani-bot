"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { copyToClipboard, formatDate } from "@/lib/format";
import type { GroupsPayload, InvitationEntry, OwnerEntry } from "@/types";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/shared/Button";
import { Badge } from "@/components/shared/Badge";
import { Notice } from "@/components/shared/Notice";
import { EmptyState } from "@/components/shared/EmptyState";

export default function OwnersPage() {
  const [owners, setOwners] = useState<OwnerEntry[]>([]);
  const [invitations, setInvitations] = useState<InvitationEntry[]>([]);
  const [groups, setGroups] = useState<GroupsPayload | null>(null);
  const [userId, setUserId] = useState("");
  const [username, setUsername] = useState("");
  const [inviteGroup, setInviteGroup] = useState("");
  const [verifyGroup, setVerifyGroup] = useState("");
  const [issuedToken, setIssuedToken] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [restricted, setRestricted] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [ownerResult, groupResult] = await Promise.all([api.owners(), api.groups()]);
    if (ownerResult.status === 401 || ownerResult.status === 403 || ownerResult.status === 404) {
      setRestricted(true);
      setError(ownerResult.error || "Owner management is available to Master Owners only.");
    } else if (ownerResult.error) {
      setError(ownerResult.error);
    } else {
      setRestricted(false);
      setOwners(ownerResult.data?.owners || []);
      setInvitations(ownerResult.data?.invitations || []);
    }
    if (groupResult.data?.ok) setGroups(groupResult.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const invite = async () => {
    setError("");
    setNotice("");
    setIssuedToken("");
    if (!userId.trim() && !username.trim()) {
      setError("Invitee ka Telegram user ID ya username bharin.");
      return;
    }
    setBusy(true);
    const result = await api.inviteOwner({
      ...(userId.trim() ? { user_id: Number(userId.trim()) } : {}),
      ...(username.trim() ? { username: username.trim() } : {}),
      ...(inviteGroup ? { group_id: Number(inviteGroup) } : {}),
    });
    setBusy(false);
    if (result.error) {
      setError(result.error);
      return;
    }
    setIssuedToken(result.data?.token || "");
    setNotice(`Invitation created${result.data?.expires_at ? ` — expires ${formatDate(result.data.expires_at)}` : ""}. Copy the token now; it is shown once.`);
    void load();
  };

  const verify = async () => {
    if (!verifyGroup) {
      setError("Verify karne ke liye group chunin.");
      return;
    }
    setBusy(true);
    const result = await api.verifyGroup({ group_id: Number(verifyGroup) });
    setBusy(false);
    if (result.error || result.data?.ok === false) setError(result.error || result.data?.message || "Verification failed.");
    else {
      setNotice(result.data?.message || "Group verified.");
      void load();
    }
  };

  const copyToken = async () => {
    const ok = await copyToClipboard(issuedToken);
    setNotice(ok ? "Invitation token copied." : "Copy failed — select the token manually.");
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Owners &amp; permissions</h1>
          <p className="page-sub">
            Master Owners manage everything. Group Owners can only access groups assigned to them — the backend
            enforces this on every endpoint, not just in the interface.
          </p>
        </div>
        <Button variant="secondary" icon="refresh" onClick={() => void load()}>Reload</Button>
      </div>

      {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}
      {notice && <Notice kind="success" onDismiss={() => setNotice("")}>{notice}</Notice>}

      {restricted ? (
        <Card title="Master Owner area">
          <EmptyState icon="shield" title="Restricted to Master Owners">
            Your token is scoped to assigned groups. Owner invitations, verification and private owner records are
            not visible to Group Owners.
          </EmptyState>
        </Card>
      ) : (
        <>
          <div className="grid-2">
            <Card title="Invite a Group Owner" subtitle="A one-time token is generated here and never stored in plain text">
              <div className="form-grid">
                <div className="field"><label>Telegram user ID</label><input value={userId} onChange={(event) => setUserId(event.target.value)} placeholder="e.g. 123456789" /></div>
                <div className="field"><label>Username (optional)</label><input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="@username" /></div>
                <div className="field">
                  <label>Restrict to group (optional)</label>
                  <select value={inviteGroup} onChange={(event) => setInviteGroup(event.target.value)}>
                    <option value="">No group restriction yet</option>
                    {(groups?.groups || []).map((group) => <option value={group.id} key={group.id}>{group.name} ({group.id})</option>)}
                  </select>
                </div>
              </div>
              <Button icon="plus" loading={busy} onClick={() => void invite()}>Create invitation</Button>
              {issuedToken && (
                <div className="notice info" style={{ marginTop: 12, marginBottom: 0 }}>
                  <div>
                    <strong>Token (shown once):</strong>
                    <div className="mono" style={{ marginTop: 5, userSelect: "all" }}>{issuedToken}</div>
                    <Button variant="secondary" size="sm" icon="copy" onClick={() => void copyToken()}>Copy</Button>
                  </div>
                </div>
              )}
            </Card>

            <Card title="Verify a group" subtitle="Marks a registered group as active after ownership checks">
              <div className="field">
                <label>Group</label>
                <select value={verifyGroup} onChange={(event) => setVerifyGroup(event.target.value)}>
                  <option value="">Choose a group…</option>
                  {(groups?.groups || []).map((group) => <option value={group.id} key={group.id}>{group.name} ({group.id})</option>)}
                </select>
              </div>
              <Button icon="shield" loading={busy} onClick={() => void verify()}>Verify ownership</Button>
            </Card>
          </div>

          <Card title="Registered owners" subtitle="Status and visible group scope (no tokens or secrets)">
            {owners.length === 0 ? (
              <EmptyState icon="owners" title="No owners recorded yet">Invitations accepted through Telegram will appear here.</EmptyState>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>User ID</th><th>Role</th><th>Status</th><th>Group scope</th><th>Accepted</th></tr></thead>
                  <tbody>
                    {owners.map((owner) => (
                      <tr key={String(owner.user_id)}>
                        <td className="cell-strong mono">{String(owner.user_id)}</td>
                        <td><Badge tone={owner.role === "master" ? "info" : "neutral"}>{owner.role || "unknown"}</Badge></td>
                        <td><Badge tone={owner.status === "accepted" || owner.status === "active" ? "ok" : "warn"}>{owner.status || "unknown"}</Badge></td>
                        <td className="cell-sub">{owner.group_ids?.length ? owner.group_ids.join(", ") : "All / none"}</td>
                        <td>{formatDate(owner.accepted_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Invitations" subtitle="Raw invitation tokens are deliberately never returned by this endpoint">
            {invitations.length === 0 ? (
              <EmptyState icon="link" title="No invitations yet">Create one above to onboard a Group Owner.</EmptyState>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Invitee</th><th>Group</th><th>Created</th><th>Expires</th><th>Status</th></tr></thead>
                  <tbody>
                    {invitations.map((invite) => (
                      <tr key={String(invite.id)}>
                        <td className="cell-strong">{String(invite.invitee || "Anyone with the token")}</td>
                        <td className="mono">{invite.group_id ?? "—"}</td>
                        <td>{formatDate(invite.created_at)}</td>
                        <td>{formatDate(invite.expires_at)}</td>
                        <td><Badge tone={invite.accepted ? "ok" : "warn"}>{invite.accepted ? "Accepted" : "Pending"}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
