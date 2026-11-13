import assert from "node:assert/strict"
import test from "node:test"
import { choiceParam, withParams } from "./url-params.ts"

const stages = ["Lead", "Won", "Lost"] as const

test("choiceParam accepts only listed values", () => {
  assert.equal(choiceParam("Won", stages), "Won")
  assert.equal(choiceParam("won", stages), "all") // case matters: the API enums are exact
  assert.equal(choiceParam("Banana", stages), "all")
  assert.equal(choiceParam(null, stages), "all")
  assert.equal(choiceParam("", stages), "all")
})

test("withParams sets, replaces and removes keys", () => {
  assert.equal(withParams("", { stage: "Won" }), "?stage=Won")
  assert.equal(withParams("?stage=Won&search=a", { stage: "Lost" }), "?stage=Lost&search=a")
  assert.equal(withParams("?stage=Won&search=a", { stage: "all" }), "?search=a")
  assert.equal(withParams("?search=a", { search: "" }), "")
  assert.equal(withParams("?open=1&stage=Won", { open: null }), "?stage=Won")
})

test("withParams encodes values", () => {
  assert.equal(withParams("", { search: "Harbor & Co." }), "?search=Harbor+%26+Co.")
})
