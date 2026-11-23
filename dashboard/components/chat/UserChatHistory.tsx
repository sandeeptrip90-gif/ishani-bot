"use client";

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { ChatHistoryPayload, ChatSearchPayload } from "@/types";
import { Badge } from "@/components/shared/Badge";
import { Button } from "@/components/shared/Button";
import { Card } from "@/components/shared/Card";
import { EmptyState } from "@/components/shared/EmptyState";
import { Icon } from "@/components/shared/Icon";
import { Notice } from "@/components/shared/Notice";

const HISTORY_LIMIT = 500;
const SEARCH_LIMIT = 50;

function scopeLabel(scope: string): string {
  if (scope === "all") return "All";
  if (scope === "private") return "Private";
  if (scope === "web") return "Web";
  const group = /^group:(\d+)$/.exec(scope);
  if (group) return `Group ${group[1]}`;
  return scope;
}

function highlight(text: string, term: string): ReactNode {
  const needle = term.trim();
  if (!needle) return text;
  const haystack = text.toLocaleLowerCase();
  const target = needle.toLocaleLowerCase();
  const nodes: ReactNode[] = [];
  let cursor = 0;
  let index = haystack.indexOf(target, cursor);
  while (index >= 0) {
    if (index > cursor) nodes.push(text.slice(cursor, index));
    nodes.push(<mark key={`${index}-${nodes.length}`}>{text.slice(index, index + target.length)}</mark>);
    cursor = index + target.length;
    index = haystack.indexOf(target, cursor);
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes.length ? nodes : text;
}

export function UserChatHistory({ userId }: { userId: number }) {
  const [history, setHistory] = useState<ChatHistoryPayload | null>(null);
  const [scope, setScope] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [query, setQuery] = useState("");
  const [searchedTerm, setSearchedTerm] = useState("");
  const [search, setSearch] = useState<ChatSearchPayload | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError("");
    const result = await api.chatHistory(userId, scope, HISTORY_LIMIT);
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Could not load chat history.");
      setHistory(null);
    } else {
      setHistory(result.data);
    }
    setLoading(false);
  }, [userId, scope]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const runSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const term = query.trim();
    if (!term) {
      setSearch(null);
      setSearchError("Enter some text to search.");
      return;
    }
    setSearching(true);
    setSearchError("");
    setSearchedTerm(term);
    const result = await api.chatSearch({ q: term, user_id: userId, limit: SEARCH_LIMIT });
    setSearching(false);
    if (result.error || result.data?.ok === false) {
      setError(result.error || result.data?.message || "Could not search chat history.");
      setSearch(null);
    } else {
      setSearch(result.data);
    }
  };

  const clearSearch = () => {
    setQuery("");
    setSearchedTerm("");
    setSearch(null);
    setSearchError("");
  };

  const messages = history?.messages || [];
  const title = history?.user?.name || history?.user?.first_name || `User ${userId}`;

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>{title}</h1>
          <p className="page-sub">
            User ID <span className="mono">{userId}</span> · {history?.user?.message_count ?? 0} messages in directory
          </p>
        </div>
        <div className="row">
          <Badge tone="info"><Icon name="shield" size={13} /> Master scope</Badge>
          <Link className="btn secondary sm" href="/users"><Icon name="chevron" size={15} /> Back to users</Link>
          <Button variant="secondary" icon="refresh" loading={loading} onClick={() => void loadHistory()}>Refresh</Button>
        </div>
      </div>

      {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}
      {searchError && <Notice onDismiss={() => setSearchError("")}>{searchError}</Notice>}

      <Card title="Search messages" subtitle="Full-text search over message text only — no prompts, keys or logs are shown">
        <form className="toolbar" onSubmit={(event) => void runSearch(event)}>
          <div className="search-box">
            <Icon name="search" size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search this user's conversations..."
              aria-label="Search chat history"
            />
          </div>
          <Button type="submit" icon="search" loading={searching}>Search</Button>
          {query && <Button type="button" variant="ghost" onClick={clearSearch}>Clear</Button>}
          {search && !searching && (
            <Badge tone="neutral">
              {search.total_hits} hits{search.truncated ? " (capped)" : ""} · {search.searched_docs} docs
            </Badge>
          )}
        </form>
        {search && !searching && search.hits.length === 0 && (
          <EmptyState icon="search" title="No matching messages">
            Nothing found for “{search.query}” in this user&apos;s stored chats.
          </EmptyState>
        )}
        {search && search.hits.length > 0 && (
          <div className="activity-list">
            {search.hits.map((hit, index) => (
              <div className="activity-item" key={`${hit.at}-${hit.scope}-${index}`}>
                <div className="grow">
                  <div className="row" style={{ marginBottom: 5 }}>
                    <Badge tone={hit.role === "bot" ? "info" : "neutral"}>{hit.role === "bot" ? "Bot" : "User"}</Badge>
                    <Badge tone="neutral">{scopeLabel(hit.scope)}</Badge>
                    <span className="cell-sub">{formatDate(hit.at)}</span>
                  </div>
                  <div className="cell-sub" style={{ marginBottom: 5 }}>{hit.day}</div>
                  <div>{highlight(hit.snippet, searchedTerm)}</div>
                </div>
                <div className="row-actions">
                  <Button type="button" size="sm" variant="secondary" icon="eye" onClick={() => setScope(hit.scope)}>
                    Open scope
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Conversation history" subtitle="Whitelisted message text from this user's private, group and web chats">
        <div className="tabs">
          <button type="button" className={`tab ${scope === "all" ? "active" : ""}`} onClick={() => setScope("all")}>
            All
          </button>
          {(history?.scopes || []).map((entry) => (
            <button
              type="button"
              key={entry.scope}
              className={`tab ${scope === entry.scope ? "active" : ""}`}
              onClick={() => setScope(entry.scope)}
            >
              {scopeLabel(entry.scope)} <span className="cell-sub">({entry.count})</span>
            </button>
          ))}
        </div>
        <div className="toolbar">
          <Badge tone="neutral">{loading ? "Loading…" : `${messages.length} of ${history?.total ?? 0} messages`}</Badge>
          {!loading && history?.has_more && <Badge tone="warn">Showing the most recent {HISTORY_LIMIT}</Badge>}
        </div>
        {loading ? (
          <div className="activity-list">
            {[0, 1, 2, 3].map((index) => (
              <div key={index} className="skeleton" style={{ height: 62 }} />
            ))}
          </div>
        ) : messages.length === 0 ? (
          <EmptyState icon="chat" title="No chat history for this scope">
            No whitelisted messages are stored here yet.
          </EmptyState>
        ) : (
          <div className="activity-list">
            {messages.map((message, index) => (
              <div className="activity-item" key={`${message.day}-${message.at}-${index}`}>
                <div className="grow">
                  <div className="row" style={{ marginBottom: 6 }}>
                    <Badge tone={message.role === "bot" ? "info" : "neutral"}>
                      {message.role === "bot" ? "Bot" : "User"}
                    </Badge>
                    {scope === "all" && <Badge tone="neutral">{scopeLabel(message.scope)}</Badge>}
                    <span className="cell-sub">{message.day}</span>
                  </div>
                  <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{message.text}</div>
                </div>
                <span className="timestamp">{formatDate(message.at)}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
