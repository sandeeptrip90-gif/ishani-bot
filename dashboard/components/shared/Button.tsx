"use client";

import type { ButtonHTMLAttributes } from "react";
import { Icon, type IconName } from "./Icon";

type Variant = "primary" | "secondary" | "danger" | "ghost";

export function Button({
  variant = "primary",
  size = "md",
  icon,
  loading,
  children,
  className = "",
  disabled,
  ...props
}: {
  variant?: Variant;
  size?: "sm" | "md";
  icon?: IconName;
  loading?: boolean;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`btn ${variant} ${size} ${className}`.trim()}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <span className="spinner" /> : icon ? <Icon name={icon} size={15} /> : null}
      {children}
    </button>
  );
}
