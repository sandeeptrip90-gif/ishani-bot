"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MODERATION_DEFAULTS, MODERATION_TOGGLES } from "@/lib/moderation";
import { Card } from "@/components/shared/Card";
import { Notice } from "@/components/shared/Notice";

export function GlobalModerationCard() {
  const [settings, setSettings] = useState<Record<string, boolean>>({ ...MODERATION_DEFAULTS });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    const result = await api.moderation();
    if (result.error) setError(result.error);
    else if (result.data?.settings) {
      setSettings({ ...MODERATION_DEFAULTS, ...result.data.settings });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = async (key: string, label: string) => {
    const next = !settings[key];
    setSettings((current) => ({ ...current, [key]: next }));
    setBusy(true);
    setError("");
    setNotice("");
    const result = await api.saveModeration({ key, value: next });
    setBusy(false);
    if (result.error) {
      setError(`${label}: ${result.error}`);
      void load();
      return;
    }
    if (result.data?.settings) setSettings({ ...MODERATION_DEFAULTS, ...result.data.settings });
    setNotice(result.data?.message || `${label} ${next ? "enabled" : "disabled"}.`);
  };

  return (
    <Card
      title="Group post moderation"
      subtitle="Global defaults for every group. A group's own Moderation tab can override them."
    >
      {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}
      {notice && <Notice kind="success" onDismiss={() => setNotice("")}>{notice}</Notice>}
      <div className="toggle-grid">
        {MODERATION_TOGGLES.map((item) => {
          const on = settings[item.key] !== false;
          return (
            <div className="toggle-item" key={item.key}>
              <div className="toggle-copy">
                <strong>{item.label}</strong>
                <span>{item.description}</span>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={on}
                aria-label={item.label}
                className={`switch ${on ? "on" : ""}`}
                disabled={busy}
                onClick={() => void toggle(item.key, item.label)}
              >
                <span className="switch-knob" />
              </button>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
