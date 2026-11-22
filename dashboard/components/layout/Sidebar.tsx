"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "@/components/shared/Icon";

export const navItems: Array<{ href: string; label: string; icon: IconName; masterOnly?: boolean }> = [
  { href: "/", label: "Dashboard", icon: "home" },
  { href: "/groups", label: "Groups", icon: "groups" },
  { href: "/owners", label: "Owners", icon: "owners" },
  { href: "/broadcasts", label: "Broadcasts", icon: "broadcast" },
  { href: "/ai-chats", label: "AI Chats", icon: "chat" },
  { href: "/tasks", label: "Tasks", icon: "tasks" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

export function Sidebar({
  open,
  onClose,
  role,
}: {
  open: boolean;
  onClose: () => void;
  role: "master" | "group" | "unknown";
}) {
  const pathname = usePathname();
  return (
    <>
      {open && <button className="sidebar-overlay" onClick={onClose} aria-label="Close menu" />}
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><Icon name="sparkles" size={20} /></div>
          <div>
            <strong>Ishani</strong>
            <span>Control Center</span>
          </div>
        </div>

        <nav className="side-nav">
          <p className="nav-label">Workspace</p>
          {navItems.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`side-link ${active ? "active" : ""}`}
                onClick={onClose}
              >
                <Icon name={item.icon} size={18} />
                <span>{item.label}</span>
                {item.masterOnly && role !== "master" ? <small>master</small> : null}
              </Link>
            );
          })}
        </nav>

        <div className="side-foot">
          <div className="role-chip">
            <Icon name={role === "master" ? "shield" : "users"} size={15} />
            <span>{role === "master" ? "Master Owner" : role === "group" ? "Group Owner" : "Unverified"}</span>
          </div>
          <p className="fineprint">Telegram operations stay on the Python backend.</p>
        </div>
      </aside>
    </>
  );
}
