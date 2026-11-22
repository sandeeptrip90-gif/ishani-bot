"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { Role } from "@/types";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [role, setRole] = useState<Role>("unknown");
  const [connected, setConnected] = useState<boolean | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      const [overview, groups] = await Promise.all([api.overview(), api.groups()]);
      if (!active) return;
      if (overview.data?.ok) {
        setRole(overview.data.role);
        setConnected(Boolean(overview.data.stats?.bot_connected));
      } else {
        setRole("unknown");
        setConnected(false);
      }
      if (groups.data?.ok && groups.data.role) setRole(groups.data.role);
    };
    load();
    const timer = window.setInterval(load, 60000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  return (
    <div className="app-shell">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} role={role} />
      <div className="app-main">
        <Topbar onMenu={() => setMenuOpen(true)} role={role} connected={connected} />
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
