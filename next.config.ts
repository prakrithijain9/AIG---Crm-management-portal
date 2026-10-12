import type { NextConfig } from "next";

// FastAPI backend. Server-side only (no NEXT_PUBLIC_ prefix), so it is not bundled for the browser.
const crmApiUrl = process.env.CRM_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  /* config options here */
  // The browser calls same-origin /api/*; Next.js proxies it to FastAPI (no CORS needed).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${crmApiUrl}/api/:path*` }];
  },
  experimental: {
    agentFeedback: true,
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
