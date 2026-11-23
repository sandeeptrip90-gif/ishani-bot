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

export interface UserEntry {
  user_id: number;
  first_name?: string;
  username?: string;
  message_count: number;
  last_seen?: string;
  full_memory: boolean;
  full_memory_since?: string;
  full_memory_by?: number | string;
  chat_file?: string;
  last_focus?: string;
  role?: string;
  logged_turns?: number;
}

export interface UsersPayload {
  ok: boolean;
  role: Role;
  users: UserEntry[];
  stats: {
    total: number;
    full_memory: number;
    mongo_primary: boolean;
    mongo_users?: number;
    stored_turns?: number;
  };
  message?: string;
}

export interface ChatHistoryMessage {
  scope: string;
  day: string;
  at: string;
  role: "user" | "bot";
  text: string;
}

export interface ChatHistoryScope {
  scope: string;
  count: number;
}

export interface ChatHistoryPayload {
  ok: boolean;
  user: { user_id: number; name: string; first_name: string; message_count: number };
  scopes: ChatHistoryScope[];
  scope: string;
  messages: ChatHistoryMessage[];
  total: number;
  has_more: boolean;
  message?: string;
}

export interface ChatSearchHit {
  user_id: number;
  first_name: string;
  scope: string;
  day: string;
  at: string;
  role: "user" | "bot";
  text: string;
  snippet: string;
}

export interface ChatSearchPayload {
  ok: boolean;
  query: string;
  hits: ChatSearchHit[];
  total_hits: number;
  truncated: boolean;
  searched_docs: number;
  message?: string;
}

export interface FullMemoryResult {
  ok: boolean;
  message?: string;
  user_id?: number;
  enabled?: boolean;
}

export interface UserMessageResult {
  ok: boolean;
  message?: string;
  user_id?: number;
  message_id?: string;
}

export interface MongoCard {
  documents: number;
  unique_users: number;
  models: string[];
}

export interface MongoTurn {
  id: string;
  user_id: number;
  first_name?: string;
  user_text?: string;
  model_reply?: string;
  response_kind?: string;
  status?: string;
  model?: string;
  created_at?: string;
  scope?: string;
}

export interface MongoOverviewPayload {
  ok: boolean;
  storage: {
    mongo_primary: boolean;
    database: string;
    chat_collection: string;
    state_collections: string[];
  };
  cards: {
    users: MongoCard;
    ai_model: MongoCard;
    admins: MongoCard;
  };
  recent: {
    users: MongoTurn[];
    ai_model: MongoTurn[];
    admins: MongoTurn[];
  };
  message?: string;
}

export interface ApiResult<T> {
  data: T | null;
  error: string | null;
  status: number;
}
