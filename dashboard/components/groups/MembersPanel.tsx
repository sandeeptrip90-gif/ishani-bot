"use client";

import type { Administrator, KnownMember } from "@/types";
import { Badge } from "@/components/shared/Badge";
import { EmptyState } from "@/components/shared/EmptyState";
import { telegramLink, formatDate } from "@/lib/format";

function ProfileLink({ user }: { user: { id: number; username?: string; first_name?: string } }) {
  const href = telegramLink(user.username || user.id);
  return (
    <a href={href || "#"} target="_blank" rel="noreferrer" className="profile-link">
      <Icon name="external" size={13} />
      {user.username ? `@${user.username}` : `ID ${user.id}`}
    </a>
  );
}

function Icon({ name, size }: { name: "external"; size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 4h6v6" /><path d="M20 4 10 14" /><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
    </svg>
  );
}

export function AdministratorsPanel({ admins, note }: { admins: Administrator[]; note?: string }) {
  return (
    <div className="stack">
      {note && <div className="notice info"><span>{note}</span></div>}
      {admins.length === 0 ? (
        <EmptyState icon="shield" title="No administrator data available">
          The bot must be in the group with permission to read its administrator list.
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Profile</th><th>Telegram ID</th><th>Status</th><th>Bot</th></tr></thead>
            <tbody>
              {admins.map((admin) => (
                <tr key={admin.id}>
                  <td className="cell-strong">{admin.first_name || "Unknown"}</td>
                  <td><ProfileLink user={admin} /></td>
                  <td className="mono">{admin.id}</td>
                  <td><Badge tone={String(admin.status || "").includes("creator") ? "info" : "neutral"}>{admin.status || "administrator"}</Badge></td>
                  <td>{admin.is_bot ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function MembersPanel({ members, note }: { members: KnownMember[]; note?: string }) {
  return (
    <div className="stack">
      <div className="notice info">
        <span>
          {note || "Telegram's Bot API cannot list every non-admin member. Only users actually observed by the bot are tracked here."}
        </span>
      </div>
      {members.length === 0 ? (
        <EmptyState icon="users" title="No members tracked yet">
          Nothing has been observed in this group. Tracked users appear here as the bot sees real Telegram updates.
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Profile</th><th>Telegram ID</th><th>Last seen</th><th>Source</th></tr></thead>
            <tbody>
              {members.map((member) => (
                <tr key={member.id}>
                  <td className="cell-strong">{member.first_name || "Unknown"}</td>
                  <td><ProfileLink user={member} /></td>
                  <td className="mono">{member.id}</td>
                  <td>{formatDate(member.last_seen)}</td>
                  <td><Badge tone="neutral">{member.source || "Telegram update"}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
