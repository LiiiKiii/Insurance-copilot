import type { NextConfig } from "next";

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // Keep trailing slashes so `/api/admin/users/` reaches FastAPI unchanged.
  // Stripping them makes FastAPI answer with a 307 to its own host, which the
  // browser then blocks as a cross-origin request.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      // `:path*` drops a trailing slash, so match it explicitly first.
      {
        source: "/api/:path*/",
        destination: `${BACKEND}/api/:path*/`,
      },
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
