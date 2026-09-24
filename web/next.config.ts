import type { NextConfig } from "next";

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND}/api/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `${BACKEND}/ws/:path*`,
      },
      // Admin API now lives under /api/admin/* (covered by the /api/:path*
      // rule above), so /admin/* is purely Next.js page routes — no rewrite.
    ];
  },
};

export default nextConfig;
