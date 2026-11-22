"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { getSelectedGroups } from "@/lib/selection";
import { formatDate } from "@/lib/format";
import type { GroupsPayload } from "@/types";
import { Button } from "@/components/shared/Button";
import { Notice } from "@/components/shared/Notice";
import { Badge } from "@/components/shared/Badge";
import { Icon } from "@/components/shared/Icon";

type MediaType = "" | "photo" | "video" | "document";
type SendResult = { group_id: number; ok: boolean; error?: string };

export function BroadcastComposer() {
  const [data, setData] = useState<GroupsPayload | null>(null);
  const [scope, setScope] = useState<"all" | "selected">("selected");
  const [selected, setSelected] = useState<number[]>([]);
  const [message, setMessage] = useState("");
  const [mediaType, setMediaType] = useState<MediaType>("");
  const [fileId, setFileId] = useState("");
  const [url, setUrl] = useState("");
  const [caption, setCaption] = useState("");
  const [results, setResults] = useState<SendResult[] | null>(null);
  const [summary, setSummary] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const result = await api.groups();
    if (result.error) setError(result.error);
    else setData(result.data);
  }, []);

  useEffect(() => {
    void load();
    setSelected(getSelectedGroups());
  }, [load]);

  const groupName = (id: number) => data?.groups?.find((group) => group.id === id)?.name || String(id);

  const send = async () => {
    setError("");
    setSummary("");
    setResults(null);
    if (!message.trim() && !caption.trim() && !mediaType) {
      setError("Broadcast ke liye message ya media bharin.");
      return;
    }
    if (scope === "selected" && selected.length === 0) {
      setError("Pehle Groups page se groups select karein, ya 'All authorized groups' chunin.");
      return;
    }
    setBusy(true);
    const media = mediaType
      ? {
          type: mediaType,
          ...(fileId.trim() ? { file_id: fileId.trim() } : {}),
          ...(url.trim() ? { url: url.trim() } : {}),
          ...(caption.trim() ? { caption: caption.trim() } : {}),
        }
      : undefined;

    const result = await api.broadcast({
      message: message.trim(),
      group_ids: scope === "all" ? "all" : selected,
      ...(media ? { media } : {}),
    });
    setBusy(false);
    if (result.error) {
      setError(result.error);
      return;
    }
    setResults(result.data?.results || []);
    const failed = (result.data?.results || []).filter((item) => !item.ok);
    setSummary(
      `Sent: ${result.data?.sent ?? 0} · Failed: ${result.data?.failed ?? failed.length}` +
        (failed.length ? `. ${failed.map((item) => `${groupName(item.group_id)}: ${item.error || "failed"}`).join(" | ")}` : ""),
    );
  };

  return (
    <div className="stack">
      {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}
      {summary && <Notice kind={results?.some((item) => !item.ok) ? "warning" : "success"}>{summary}</Notice>}

      <div className="form-grid">
        <div className="field">
          <label htmlFor="broadcast-scope">Target groups</label>
          <select id="broadcast-scope" value={scope} onChange={(event) => setScope(event.target.value as "all" | "selected")}>
            <option value="selected">Selected groups ({selected.length})</option>
            <option value="all">All authorized groups</option>
          </select>
          <p className="fineprint" style={{ marginTop: 6 }}>
            <Link href="/groups">Select groups on the Groups page →</Link>
          </p>
        </div>
        <div className="field">
          <label htmlFor="broadcast-media-type">Media type (optional)</label>
          <select id="broadcast-media-type" value={mediaType} onChange={(event) => setMediaType(event.target.value as MediaType)}>
            <option value="">Text only</option>
            <option value="photo">Photo</option>
            <option value="video">Video</option>
            <option value="document">Document</option>
          </select>
        </div>
      </div>

      <div className="field">
        <label htmlFor="broadcast-message">Message</label>
        <textarea
          id="broadcast-message"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Text shown as the message (or as media caption when media is attached)"
          maxLength={4000}
        />
      </div>

      {mediaType && (
        <div className="stack">
          <div className="form-grid">
            <div className="field">
              <label htmlFor="broadcast-file-id">Telegram file_id</label>
              <input id="broadcast-file-id" value={fileId} onChange={(event) => setFileId(event.target.value)} placeholder="File ID from a previous Telegram upload" />
            </div>
            <div className="field">
              <label htmlFor="broadcast-url">Public file URL</label>
              <input id="broadcast-url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://..." />
            </div>
          </div>
          <div className="field">
            <label htmlFor="broadcast-caption">Caption (optional)</label>
            <input id="broadcast-caption" value={caption} onChange={(event) => setCaption(event.target.value)} placeholder="Overrides the message as caption" />
          </div>
          <p className="fineprint">
            Telegram needs a file_id or a public URL to send media. Private/local URLs are rejected by the backend.
            Nothing is uploaded from your browser.
          </p>
        </div>
      )}

      <div className="row">
        <Button icon="send" loading={busy} onClick={() => void send()}>Send broadcast</Button>
        <Badge tone="neutral">{scope === "all" ? `Up to ${data?.groups?.length || 0} groups in scope` : `${selected.length} selected`}</Badge>
      </div>

      {results && (
        <div className="stack">
          <h3>Delivery results (real Telegram responses)</h3>
          {results.length === 0 ? (
            <p className="muted">No per-group results were returned.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Group</th><th>Telegram ID</th><th>Result</th><th>Error</th></tr></thead>
                <tbody>
                  {results.map((item, index) => (
                    <tr key={`${item.group_id}-${index}`}>
                      <td className="cell-strong">{groupName(item.group_id)}</td>
                      <td className="mono">{item.group_id}</td>
                      <td><Badge tone={item.ok ? "ok" : "bad"}>{item.ok ? "Delivered" : "Failed"}</Badge></td>
                      <td className="cell-sub">{item.error || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {(data?.broadcasts || []).length > 0 && (
        <div className="stack">
          <h3>Recent recorded broadcasts</h3>
          <div className="activity-list">
            {data?.broadcasts?.map((entry, index) => (
              <div className="activity-item" key={`${entry.at}-${index}`}>
                <div>
                  <strong className="cell-strong">{entry.scope}</strong>
                  <div className="cell-sub">Sent {entry.sent} · Failed {entry.failed}</div>
                </div>
                <span className="timestamp">{formatDate(entry.at)}</span>
              </div>
            ))}
          </div>
          <p className="fineprint"><Icon name="info" size={12} /> Counts come from the backend's delivery log, not from estimates.</p>
        </div>
      )}
    </div>
  );
}
