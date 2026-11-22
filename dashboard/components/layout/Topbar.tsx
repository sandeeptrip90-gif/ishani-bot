"use client";

import { usePathname } from "next/navigation";
import { Icon } from "@/components/shared/Icon";
import { Badge } from "@/components/shared/Badge";

const titles: Record<string, string> = {
  "/": "Dashboard",
  "/groups": "Groups",
  "/owners": "Owners & Permissions",
  "/broadcasts": "Broadcasts",
  "/ai-chats": "AI Chats",
  "/tasks": "Task Execution",
  "/settings": "Settings",
};

function titleFor(pathname: string): string {
  if (titles[pathname]) return titles[pathname];
  if (pathname.startsWith("/groups/")) return "Group Details";
  return "Ishani Control Center";
}

export function Topbar({
  onMenu,
  role,
  connected,
}: {
  onMenu: () => void;
  role: "master" | "group" | "unknown";
  connected: boolean | null;
}) {
  const pathname = usePathname();

  return (
    <header className="topbar">
      <button className="icon-btn menu-btn" onClick={onMenu} aria-label="Open menu">
        <Icon name="menu" size={20} />
      </button>
      <div className="topbar-title">
        <h1>{titleFor(pathname)}</h1>
        <span>Ishani / {pathname === "/" ? "overview" : pathname.replace(/^\//, "")}</span>
      </div>
      <div className="topbar-right">
        <Badge tone={connected === true ? "ok" : connected === false ? "bad" : "neutral"}>
          <span className="dot" /> {connected === true ? "Bot online" : connected === false ? "Bot offline" : "Checking"}
        </Badge>
        <Badge tone={role === "master" ? "info" : "neutral"}>
          {role === "master" ? "Master" : role === "group" ? "Owner" : "Guest"}
        </Badge>
      </div>
    </header>
  );
}
