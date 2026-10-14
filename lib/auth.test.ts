// Unit tests for the sign-in redirect helpers. Run: npm run test:frontend
import assert from "node:assert/strict"
import { describe, it } from "node:test"
import { loginUrl, safeNextPath } from "./auth.ts"

describe("safeNextPath", () => {
  it("keeps same-site paths, including query strings", () => {
    for (const path of ["/", "/companies", "/deals?stage=Won", "/contacts#top"]) {
      assert.equal(safeNextPath(path), path)
    }
  })

  it("rejects anything that could leave the site or loop back to login", () => {
    const unsafe = [
      null,
      undefined,
      "",
      "companies",
      "https://evil.example/",
      "//evil.example",
      "/\\evil.example", // browsers treat "/\" like "//"
      "/\\/evil.example",
      "javascript:alert(1)",
      "/ok\nLocation: https://evil.example",
      "/ok\u0000",
      "/login",
      "/login?next=/login",
      "/login/",
    ]
    for (const path of unsafe) {
      assert.equal(safeNextPath(path), "/", String(path))
    }
  })
})

describe("loginUrl", () => {
  it("carries the page to return to and the reason", () => {
    assert.equal(loginUrl("/deals?stage=Won", "expired"), "/login?next=%2Fdeals%3Fstage%3DWon&reason=expired")
    assert.equal(loginUrl("/companies"), "/login?next=%2Fcompanies")
  })

  it("omits a pointless or unsafe next", () => {
    assert.equal(loginUrl("/"), "/login")
    assert.equal(loginUrl("//evil.example", "signed-out"), "/login?reason=signed-out")
  })
})
