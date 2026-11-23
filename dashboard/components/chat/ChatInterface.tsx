"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { GroupsPayload } from "@/types";
import { Button } from "@/components/shared/Button";
import { Notice } from "@/components/shared/Notice";
import { Badge } from "@/components/shared/Badge";
import { Icon } from "@/components/shared/Icon";
import { ModeSelector, type ChatMode } from "./ModeSelector";

interface ChatMessage {
  id: string;
  role: "user" | "bot";
  text: string;
  at?: string;
  mode?: string;
  taskId?: string;
  taskStatus?: string;
  proposed?: Record<string, unknown>;
}

interface PendingAction {
  message: string;
  mode: ChatMode;
  group_id?: number;
}

function readableReply(text: string): string {
  // Research mode can return HTML from the search renderer; show it as plain text.
  return text
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|h\d)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .trim();
}

const EXAMPLES: Record<ChatMode, string[]> = {
  assistant: ["Ishani, kaise ho?", "What do you remember about my preferences?"],
  group_manager: [
    "Check which groups have lost admin permissions.",
    "Show a summary of my groups and their registration status.",
    "Send: Hello team",
  ],
  research: ["Search for Telegram Bot API changes and summarize them.", "Research best practices for Telegram group moderation."],
  auto_fix: ["Check the bot for problems.", "Find the problem in my bot and fix it."],
  script_generator: ["Create a script to analyze this CSV.", "Write a Python script that reports groups with low member counts."],
  automation: ["Schedule a message for tomorrow.", "Run a diagnostic and summarize my groups."],
};

export function ChatInterface() {
  const [mode, setMode] = useState<ChatMode>("assistant");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [groupId, setGroupId] = useState("");
  const [groups, setGroups] = useState<GroupsPayload | null>(null);
  const [attachments, setAttachments] = useState<string[]>([]);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [messageQuery, setMessageQuery] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const messageNeedle = messageQuery.trim().toLocaleLowerCase();
  const visibleMessages = useMemo(
    () => (messageNeedle ? messages.filter((item) => item.text.toLocaleLowerCase().includes(messageNeedle)) : messages),
    [messages, messageNeedle],
  );

  const loadHistory = useCallback(async () => {
    const result = await api.aiHistory();
    if (!result.error && result.data?.ok) {
      const history = (result.data.messages || []).map((item, index): ChatMessage => {
        const raw = item as unknown as { role?: string; text?: string; content?: string; at?: string };
        const role = String(raw.role || "user").toLowerCase();
        return {
          id: `history-${index}`,
          role: role === "bot" || role === "assistant" ? "bot" : "user",
          text: String(raw.text || raw.content || ""),
          at: raw.at,
        };
      });
      setMessages(history);
    }
    setHistoryLoaded(true);
  }, []);

  useEffect(() => {
    void loadHistory();
    void api.groups().then((result) => {
      if (result.data?.ok) setGroups(result.data);
    });
  }, [loadHistory]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const appendMessage = (message: ChatMessage) => setMessages((items) => [...items, message]);

  const updateTaskStatus = async (taskId: string, messageId: string) => {
    const result = await api.task(taskId);
    const task = result.data?.task;
    if (!task) return;
    setMessages((items) =>
      items.map((item) => (item.id === messageId ? { ...item, taskStatus: task.status } : item)),
    );
  };

  const send = async (override?: PendingAction) => {
    const action: PendingAction = override || {
      message: input.trim(),
      mode,
      group_id: groupId ? Number(groupId) : undefined,
    };
    if (!action.message) {
      setError("Pehle message likhin ya example chunin.");
      return;
    }
    setError("");
    const attachmentNote = attachments.length
      ? `\n\n[Attached file names: ${attachments.join(", ")}. These are metadata only — paste a Telegram file_id or public URL in the message if Ishani must send media.]`
      : "";
    const visibleMessage = action.message + attachmentNote;

    setBusy(true);
    if (!override) {
      appendMessage({ id: `u-${Date.now()}`, role: "user", text: visibleMessage, at: new Date().toISOString(), mode: action.mode });
      setInput("");
      setAttachments([]);
    }
    const result = await api.aiChat({
      message: visibleMessage,
      mode: action.mode,
      ...(action.group_id ? { group_id: action.group_id } : {}),
      confirm: Boolean(override),
    });
    setBusy(false);

    if (result.error) {
      setError(result.error);
      return;
    }
    const data = result.data;
    const replyId = `b-${Date.now()}`;
    appendMessage({
      id: replyId,
      role: "bot",
      text: data?.reply || "(No reply returned)",
      at: new Date().toISOString(),
      mode: action.mode,
      taskId: data?.task_id,
      proposed: data?.proposed_action,
    });
    setPending(data?.requires_confirmation ? action : null);
    if (data?.task_id) void updateTaskStatus(data.task_id, replyId);
  };

  const confirm = () => {
    if (!pending) return;
    appendMessage({ id: `u-${Date.now()}`, role: "user", text: "Confirm — execute the proposed action.", at: new Date().toISOString() });
    void send(pending);
  };

  return (
    <div className="chat-layout">
      <div className="card">
        <h2>Ishani modes</h2>
        <p className="muted" style={{ margin: "4px 0 12px" }}>Persona and memory stay the same in every mode.</p>
        <ModeSelector value={mode} onChange={(value) => { setMode(value); setPending(null); }} />
        <div className="field" style={{ marginTop: 14 }}>
          <label htmlFor="chat-group">Group context (optional)</label>
          <select id="chat-group" value={groupId} onChange={(event) => setGroupId(event.target.value)}>
            <option value="">All visible groups</option>
            {(groups?.groups || []).map((group) => (
              <option value={group.id} key={group.id}>{group.name} ({group.id})</option>
            ))}
          </select>
        </div>
      </div>

      <div className="card chat-panel">
        {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}
        <div className="toolbar" style={{ marginTop: 12 }}>
          <div className="search-box">
            <Icon name="search" size={16} />
            <input
              value={messageQuery}
              onChange={(event) => setMessageQuery(event.target.value)}
              placeholder="Filter messages in this conversation..."
              aria-label="Filter chat messages"
            />
          </div>
          <Badge tone="neutral">
            {messageNeedle ? `${visibleMessages.length} of ${messages.length} messages` : `${messages.length} messages`}
          </Badge>
          {messageNeedle && (
            <button className="btn ghost sm" type="button" onClick={() => setMessageQuery("")}>Clear</button>
          )}
        </div>
        <div className="chat-messages">
          {!historyLoaded && <div className="skeleton" style={{ height: 140 }} />}
          {historyLoaded && messages.length === 0 && (
            <div className="bubble bot">
              Namaste! Main Ishani hoon. Ask me anything, or try one of the examples below.
              <span className="bubble-meta">Persona & memory preserved from the Telegram bot</span>
            </div>
          )}
          {visibleMessages.map((item) => (
            <div key={item.id} className={`bubble ${item.role}`}>
              {item.role === "bot" ? readableReply(item.text) : item.text}
              {(item.mode || item.taskId || item.at) && (
                <span className="bubble-meta">
                  {item.mode ? `${item.mode} · ` : ""}
                  {item.taskId ? (
                    <>task <Link href={`/tasks?task=${encodeURIComponent(item.taskId)}`}>{item.taskId}</Link> {item.taskStatus ? `(${item.taskStatus})` : ""} · </>
                  ) : null}
                  {item.at ? formatDate(item.at) : ""}
                </span>
              )}
              {item.proposed && (
                <div className="confirm-box">
                  <strong>Proposed action</strong>
                  <pre>{JSON.stringify(item.proposed, null, 2)}</pre>
                </div>
              )}
            </div>
          ))}
          {pending && (
            <div className="row" style={{ alignSelf: "center" }}>
              <Button icon="shield" loading={busy} onClick={confirm}>Confirm &amp; execute</Button>
              <Button variant="ghost" onClick={() => setPending(null)}>Cancel</Button>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="chat-examples">
          {EXAMPLES[mode].map((example) => (
            <button key={example} className="chip-btn" type="button" onClick={() => setInput(example)} disabled={busy}>
              {example}
            </button>
          ))}
        </div>

        <div className="chat-composer">
          <div className="grow">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (!busy) void send();
                }
              }}
              placeholder={mode === "research" ? "What should Ishani research?" : "Message Ishani… (Enter to send, Shift+Enter for a new line)"}
              aria-label="Message Ishani"
            />
            <div className="row" style={{ marginTop: 7 }}>
              <label className="attach-btn">
                <Icon name="file" size={14} /> Attach files
                <input
                  type="file"
                  multiple
                  onChange={(event) => setAttachments(Array.from(event.target.files || []).map((file) => file.name))}
                  hidden
                />
              </label>
              {attachments.map((name) => <Badge key={name} tone="neutral">{name}</Badge>)}
              {attachments.length > 0 && (
                <button className="btn ghost sm" type="button" onClick={() => setAttachments([])}>Clear</button>
              )}
              <span className="fineprint" style={{ marginTop: 0 }}>File names only — provide a file_id/URL to actually send media.</span>
            </div>
          </div>
          <Button icon="send" loading={busy} onClick={() => void send()} disabled={!input.trim()}>Send</Button>
        </div>
      </div>
    </div>
  );
}
