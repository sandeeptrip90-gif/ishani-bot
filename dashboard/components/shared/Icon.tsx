"use client";

import type { ReactNode, SVGProps } from "react";

export type IconName =
  | "home" | "groups" | "owners" | "broadcast" | "chat" | "tasks" | "settings"
  | "shield" | "users" | "check" | "alert" | "search" | "copy" | "external"
  | "plus" | "pin" | "mute" | "unmute" | "trash" | "edit" | "refresh" | "menu"
  | "logout" | "robot" | "link" | "clock" | "file" | "image" | "video"
  | "send" | "chevron" | "checkCircle" | "xCircle" | "sparkles" | "wrench"
  | "script" | "bolt" | "info" | "eye";

const paths: Record<IconName, ReactNode> = {
  home: <><path d="M3 10.5 12 3l9 7.5" /><path d="M5 9.5V21h14V9.5" /><path d="M9.5 21v-6h5v6" /></>,
  groups: <><circle cx="9" cy="8" r="3" /><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" /><path d="M16 5.5a3 3 0 0 1 0 5.6" /><path d="M17 14.5c2.4.7 4 2.8 4 5.5" /></>,
  owners: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" /><path d="m9 8 2 2 4-4" /></>,
  broadcast: <><circle cx="12" cy="12" r="2" /><path d="M7.8 7.8a6 6 0 0 0 0 8.4" /><path d="M16.2 16.2a6 6 0 0 0 0-8.4" /><path d="M4.9 4.9a10 10 0 0 0 0 14.2" /><path d="M19.1 19.1a10 10 0 0 0 0-14.2" /></>,
  chat: <><path d="M20 15a3 3 0 0 1-3 3H8l-4 3V6a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3z" /><path d="M8 9h8M8 12.5h5" /></>,
  tasks: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="m7 10 2 2 3-3" /><path d="M15 10h3M7 16h10" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4v-.2a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H2.8v-4h.2a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6v-.2h4v.2a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4h-.2a1.7 1.7 0 0 0-1.6 1z" /></>,
  shield: <><path d="M12 3 5 6v5c0 4.4 2.9 8.3 7 9.5 4.1-1.2 7-5.1 7-9.5V6z" /><path d="m9 12 2 2 4-4" /></>,
  users: <><circle cx="9" cy="8" r="3" /><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" /><path d="M16 5a3 3 0 0 1 0 6M18 14c1.8.9 3 2.7 3 5" /></>,
  check: <path d="m5 12 4.5 4.5L19 7" />,
  alert: <><path d="M12 4 2.7 20h18.6z" /><path d="M12 10v4M12 17h.01" /></>,
  search: <><circle cx="11" cy="11" r="6" /><path d="m20 20-4-4" /></>,
  copy: <><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3" /></>,
  external: <><path d="M14 4h6v6" /><path d="M20 4 10 14" /><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  pin: <><path d="m9 3 6 6-2 1 3 6-2 1-3-6-3 3 1-5z" /><path d="M12 21v-4" /></>,
  mute: <><path d="M11 5 6 9H3v6h3l5 4z" /><path d="m16 9 5 6M21 9l-5 6" /></>,
  unmute: <><path d="M11 5 6 9H3v6h3l5 4z" /><path d="M15.5 8.5a5 5 0 0 1 0 7" /><path d="M18.5 6a8.5 8.5 0 0 1 0 12" /></>,
  trash: <><path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14" /><path d="M10 11v6M14 11v6" /></>,
  edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z" /></>,
  refresh: <><path d="M20 11a8 8 0 1 0-2 6" /><path d="M20 5v6h-6" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  logout: <><path d="M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5" /><path d="M15 8l4 4-4 4M19 12H9" /></>,
  robot: <><rect x="4" y="8" width="16" height="12" rx="3" /><circle cx="9" cy="13" r="1" /><circle cx="15" cy="13" r="1" /><path d="M12 8V4M9 4h6" /></>,
  link: <><path d="M10 13a5 5 0 0 0 7 .4l2-2a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7-.4l-2 2a5 5 0 0 0 7 7l1-1" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  file: <><path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10z" /><path d="M13 3v7h7" /></>,
  image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9" r="1.5" /><path d="m21 16-5-5L5 20" /></>,
  video: <><rect x="3" y="5" width="13" height="14" rx="2" /><path d="m16 10 5-3v10l-5-3z" /></>,
  send: <><path d="m3 11 18-8-8 18-2-8z" /><path d="m11 13 10-10" /></>,
  chevron: <path d="m9 6 6 6-6 6" />,
  checkCircle: <><circle cx="12" cy="12" r="9" /><path d="m8 12 2.5 2.5L16 9" /></>,
  xCircle: <><circle cx="12" cy="12" r="9" /><path d="m9 9 6 6M15 9l-6 6" /></>,
  sparkles: <><path d="m12 3 1.7 4.3L18 9l-4.3 1.7L12 15l-1.7-4.3L6 9l4.3-1.7z" /><path d="m18 15 .8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8z" /></>,
  wrench: <path d="M14.5 5.5a4.5 4.5 0 0 0-5.9 5.9L3 17l4 4 5.6-5.6a4.5 4.5 0 0 0 5.9-5.9l-3 3-3-3z" />,
  script: <><path d="M7 3h7l5 5v13H7z" /><path d="M14 3v5h5M10 12h6M10 16h6" /></>,
  bolt: <path d="M13 2 4 14h7l-1 8 9-12h-7z" />,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  eye: <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z" /><circle cx="12" cy="12" r="2.5" /></>,
};

export function Icon({ name, size = 18, ...props }: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
