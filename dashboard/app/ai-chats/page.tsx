"use client";

import { ChatInterface } from "@/components/chat/ChatInterface";

export default function AiChatsPage() {
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Chat with Ishani</h1>
          <p className="page-sub">
            Talk normally or switch modes for group management, research, diagnostics, scripts and confirmed automation.
            Sensitive operations always ask for confirmation. Ishani's persona, memory and lessons stay intact.
          </p>
        </div>
      </div>
      <ChatInterface />
    </div>
  );
}
