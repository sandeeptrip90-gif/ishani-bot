/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // /api/* is handled by app/api/[...path]/route.ts at runtime so
  // API_BACKEND_URL is read from the actual bot-launched process.
};

export default nextConfig;
