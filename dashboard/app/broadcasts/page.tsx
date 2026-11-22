"use client";

import { Card } from "@/components/shared/Card";
import { BroadcastComposer } from "@/components/broadcasts/BroadcastComposer";

export default function BroadcastsPage() {
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Broadcasts</h1>
          <p className="page-sub">
            Send text, photos, videos or documents to selected groups or every group you are authorized for.
            Telegram calls happen on the Python backend; results shown here are the real per-group responses.
          </p>
        </div>
      </div>
      <Card title="Compose broadcast" subtitle="Scope is enforced server-side for every authorized group">
        <BroadcastComposer />
      </Card>
    </div>
  );
}
