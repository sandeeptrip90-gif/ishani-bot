import path from "node:path";
import { fileURLToPath } from "node:url";

const dashboardDir = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Explicit alias so "@/..." resolves on case-sensitive Linux hosts even if
  // the tsconfig paths mapping is not picked up by the bundler there.
  webpack: (config) => {
    config.resolve.alias["@"] = dashboardDir;
    return config;
  },
  // The dashboard lives at "/"; keep the bookmarked /dashboard URL working.
  async redirects() {
    return [{ source: "/dashboard", destination: "/", permanent: false }];
  },
  // /api/* is handled by app/api/[...path]/route.ts at runtime so
  // API_BACKEND_URL is read from the actual bot-launched process.
};

export default nextConfig;
