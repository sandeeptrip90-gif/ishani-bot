"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { GroupsPayload } from "@/types";
import { GroupsTable } from "@/components/groups/GroupsTable";
import { Card } from "@/components/shared/Card";
import { Button } from "@/components/shared/Button";
import { Notice } from "@/components/shared/Notice";
import { StatCard } from "@/components/dashboard/StatCard";

export default function GroupsPage() {
  const [data, setData] = useState<GroupsPayload | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const result = await api.groups();
    if (result.error) setError(result.error);
    else {
      setError("");
      setData(result.data);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Groups</h1>
          <p className="page-sub">
            Search, sort and inspect every group in your scope. Master Owners see all groups;
            Group Owners only see groups assigned to them.
          </p>
        </div>
        <Button variant="secondary" icon="refresh" onClick={() => void load()} loading={loading}>Reload</Button>
      </div>

      {error && <Notice onDismiss={() => setError("")}>{error}</Notice>}

      <div className="stats">
        <StatCard icon="groups" label="Groups in scope" value={data?.stats?.groups ?? 0} />
        <StatCard icon="users" label="Members" value={data?.stats?.members ?? 0} />
        <StatCard icon="shield" label="Administrators" value={data?.stats?.administrators ?? 0} />
        <StatCard icon="owners" label="Owners" value={data?.stats?.owners ?? 0} />
      </div>

      <Card title="All groups" subtitle="Select groups for scoped broadcasts, then open Manage for full details">
        {data ? (
          <GroupsTable groups={data.groups || []} role={data.role} onChanged={() => void load()} />
        ) : (
          <div className="skeleton" style={{ height: 180 }} />
        )}
      </Card>
    </div>
  );
}
