// node --test tests/js: the clock-offset estimate screen.js uses.
import { test } from "node:test";
import assert from "node:assert/strict";
import { SAMPLE_WINDOW, offsetFrom } from "../../src/signage/static/screen.js";

// a sample: the page sent the ping at c and got the pong at r (page clock); the server said s
const sample = (c, rtt, offset) => ({ c, r: c + rtt, s: c + rtt / 2 + offset });
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);

test("within the window, the sample with the smallest round trip wins", () => {
  near(offsetFrom([sample(0, 0.05, 100), sample(10, 0.01, 100.2), sample(20, 0.03, 100.4)]), 100.2);
});

test("an old fast sample ages out, so drift is followed", () => {
  const old = sample(0, 0.001, 100);
  const later = Array.from({ length: SAMPLE_WINDOW }, (_, i) => sample(10 * (i + 1), 0.05, 100.5));
  near(offsetFrom([old, ...later]), 100.5);
});
