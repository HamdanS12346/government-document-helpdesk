import type { NextConfig } from "next";

// On host machine defaults to 127.0.0.1; in Docker Compose uses http://backend:8000
const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/py/:path*",
        destination: `${INTERNAL_API_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
