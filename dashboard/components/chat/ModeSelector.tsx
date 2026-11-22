"use client";

import { Icon, type IconName } from "@/components/shared/Icon";

export const MODES = [
  { id: "assistant", label: "Assistant", icon: "chat", description: "General conversation with Ishani's persona" },
  { id: "group_manager", label: "Group Manager", icon: "groups", description: "Read group state and propose scoped actions" },
  { id: "research", label: "Research", icon: "search", description: "Search the web and summarize sources" },
  { id: "auto_fix", label: "Auto-Fix", icon: "wrench", description: "Read-only diagnostics and fix proposals" },
  { id: "script_generator", label: "Script Generator", icon: "script", description: "Generate Python files under generated/" },
  { id: "automation", label: "Automation", icon: "bolt", description: "Confirmed, whitelisted multi-step tasks" },
] as const;

export type ChatMode = (typeof MODES)[number]["id"];

export function ModeSelector({ value, onChange }: { value: ChatMode; onChange: (mode: ChatMode) => void }) {
  return (
    <div className="mode-list" role="tablist" aria-label="Ishani modes">
      {MODES.map((mode) => (
        <button
          key={mode.id}
          type="button"
          role="tab"
          aria-selected={value === mode.id}
          className={`mode-btn ${value === mode.id ? "active" : ""}`}
          onClick={() => onChange(mode.id)}
        >
          <Icon name={mode.icon as IconName} size={17} />
          <span>
            {mode.label}
            <small>{mode.description}</small>
          </span>
        </button>
      ))}
    </div>
  );
}
