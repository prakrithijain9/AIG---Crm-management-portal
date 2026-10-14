// Checks the security headers and API proxy in next.config.ts. Run: npm run test:frontend
import assert from "node:assert/strict"
import { describe, it } from "node:test"
import nextConfig from "../next.config.ts"

async function headerRules() {
  assert.ok(nextConfig.headers, "next.config.ts must define headers()")
  return nextConfig.headers()
}

describe("next.config security headers", () => {
  it("apply to every path, including the login page and the /api proxy", async () => {
    const rules = await headerRules()
    assert.equal(rules.length, 1)
    assert.equal(rules[0].source, "/:path*")
  })

  it("forbid framing (clickjacking) and set safe defaults", async () => {
    const [rule] = await headerRules()
    const headers = Object.fromEntries(rule.headers.map(({ key, value }) => [key, value]))
    assert.equal(headers["Content-Security-Policy"], "frame-ancestors 'none'")
    assert.equal(headers["X-Frame-Options"], "DENY")
    assert.equal(headers["X-Content-Type-Options"], "nosniff")
    assert.equal(headers["Referrer-Policy"], "strict-origin-when-cross-origin")
    assert.match(headers["Permissions-Policy"], /camera=\(\)/)
  })

  it("only restrict framing in CSP, so scripts, styles and API calls are unaffected", async () => {
    const [rule] = await headerRules()
    const csp = rule.headers.find(({ key }) => key === "Content-Security-Policy")?.value ?? ""
    assert.deepEqual(csp.split(";").map((part) => part.trim().split(" ")[0]), ["frame-ancestors"])
  })

  it("keep the same-origin /api proxy to FastAPI", async () => {
    assert.ok(nextConfig.rewrites)
    const rewrites = await nextConfig.rewrites()
    assert.ok(Array.isArray(rewrites))
    assert.equal(rewrites[0].source, "/api/:path*")
    assert.match(rewrites[0].destination, /\/api\/:path\*$/)
  })
})
