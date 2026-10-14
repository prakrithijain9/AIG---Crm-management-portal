import type { NextConfig } from "next";

// FastAPI backend. Server-side only (no NEXT_PUBLIC_ prefix), so it is not bundled for the browser.
const crmApiUrl = process.env.CRM_API_URL ?? "http://127.0.0.1:8000";

// Sent with every response (pages, assets and the /api proxy).
const securityHeaders = [
  // Never allow the CRM to be framed (clickjacking). CSP frame-ancestors is the current
  // control; X-Frame-Options covers older browsers. Only this CSP directive is set, so
  // scripts, styles and API calls are unaffected.
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  { key: "X-Frame-Options", value: "DENY" },
  // Don't let browsers reinterpret responses as another content type.
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Full Referer only to this site (the API's same-origin check still works); origin elsewhere.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // The CRM uses no device features.
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  /* config options here */
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
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
