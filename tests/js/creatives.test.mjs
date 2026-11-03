// Every creative keeps the contract screen.js relies on: create(canvas) → { show, prepare }.
// Creating one needs a canvas, so this only checks what a module exports.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync } from "node:fs";

const dir = new URL("../../src/koi_signage/static/creatives/", import.meta.url);
const names = readdirSync(dir).filter((f) => f.endsWith(".js"));

test("there is a creative", () => assert.ok(names.includes("koi.js")));

for (const name of names) {
  test(`${name} exports create`, async () => {
    const { create } = await import(new URL(name, dir));
    assert.equal(typeof create, "function");
  });
}
