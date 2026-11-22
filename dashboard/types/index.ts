export type Role = "master" | "group" | "unknown";

export interface Alert {
  level: "info" | "warning" | "danger";
  text: string;
  at?: string;
}

export interface AuditEntry {
  at: string;
  action: string;
  actor_id: number | string;
  target: string;
  details: string;
}

export interface GroupStats {
  members: number;
  administrators: number;
  title?: string;
  checked_at?: string;
  username?: string;
  invite_link?: string;
  title_error?: string;
  [key: string]: unknown;
}

export interface Group {
  id: number;
  name: string;
  username?: string | null;
  owner_id?: number | null;
  registration_status: string;
  business: Record<string, unknown>;
  settings: Record<string, unknown>;
  stats: GroupStats;
  invite_link?: string | null;
  is_public?: boolean;
  bot_is_admin?: boolean | null;
  bot_permissions?: Record<string, boolean> | null;
  known_members?: number;
  created_at?: string;
  registered_at?: string;
  alerts?: Alert[];
}

export interface GroupsPayload {
  ok: boolean;
  role: Role;
  user_id: number;
  stats: { groups: number; owners: number; administrators: number; members: number };
  groups: Group[];
  broadcasts: BroadcastEntry[];
  alerts?: Alert[];
  message?: string;
}

export interface OverviewPayload {
  ok: boolean;
  role: Role;
  stats: {
    groups: number;
    active_groups: number;
    inactive_groups: number;
    members: number;
    administrators: number;
    owners: number;
    bot_connected: boolean;
    bot_admin_groups: number;
    muted_groups: number;
    link_protected_groups: number;
  };
  alerts: Alert[];
  activity: AuditEntry[];
  message?: string;
}

export interface BroadcastEntry {
  at: string;
  scope: string;
  sent: number;
  failed: number;
}

export interface Administrator {
  id: number;
  username?: string;
  first_name?: string;
  status?: string;
  is_bot?: boolean;
}

export interface KnownMember {
  id: number;
  username?: string;
  first_name?: string;
  last_seen?: string;
  source?: string;
}

export interface MembersPayload {
  ok: boolean;
  group_id: number;
  administrators: Administrator[];
  known_members: KnownMember[];
  members_available: boolean;
  note?: string;
  message?: string;
}

export interface OwnerEntry {
  user_id: number | string;
  role: string;
  status: string;
  accepted_at?: string;
  group_ids?: number[];
}

export interface InvitationEntry {
  id: number | string;
  invitee?: string;
  group_id?: number | null;
  created_at?: string;
  expires_at?: string;
  accepted?: boolean;
}

export interface ScheduledItem {
  id: string;
  group_id: number;
  text: string;
  send_at: string;
  status: string;
  actor_id?: number | string;
}

export interface TaskLogEntry {
  at?: string;
  text?: string;
}

export interface TaskRecord {
  id: string;
  at: string;
  actor_id: number | string;
  mode: string;
  message: string;
  status: string;
  log: Array<string | TaskLogEntry>;
  result?: string | Record<string, unknown> | null;
}

export interface ChatTurn {
  id: string;
  role: "user" | "bot";
  text: string;
  at: string;
  mode?: string;
  task_id?: string;
}

export interface ChatPayload {
  ok: boolean;
  reply: string;
  task_id?: string;
  requires_confirmation?: boolean;
  proposed_action?: Record<string, unknown>;
  message?: string;
}

export interface ApiResult<T> {
  data: T | null;
  error: string | null;
  status: number;
}
