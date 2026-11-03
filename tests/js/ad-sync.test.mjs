// How a screen keeps an ad in step: a small drift is eased out with the playback speed, a big
// one is jumped.
import { test } from "node:test";
import assert from "node:assert/strict";
import { adRate } from "../../src/koi_signage/static/screen.js";

test("in step, it plays at normal speed", () => {
  assert.equal(adRate(0), 1);
  assert.equal(adRate(0.015), 1);
  assert.equal(adRate(-0.015), 1);
});

test("a little behind, it plays a little faster; a little ahead, a little slower", () => {
  assert.ok(adRate(-0.04) > 1 && adRate(-0.04) < adRate(-0.1));
  assert.ok(adRate(0.04) < 1 && adRate(0.04) > adRate(0.1));
});

test("never more than 5% off normal speed, which no one sees", () => {
  assert.equal(adRate(-0.2), 1.05);
  assert.equal(adRate(0.2), 0.95);
});

test("far off (a late join, a stall), it jumps instead", () => {
  assert.equal(adRate(-0.3), null);
  assert.equal(adRate(0.3), null);
});
