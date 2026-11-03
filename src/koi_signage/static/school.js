// How the school of koi swims, for every creative that draws one: where each koi is, which way
// it faces, how its body bends, how deep it swims, and when it crosses to the next screen. It
// draws nothing. A creative gives it the screen's size, calls step every frame, and draws each
// koi along spine(k).
//
// Five koi swim together, in loose formation behind the leader. The school is the character: it
// swims near the surface while it is this screen's, and drifts faint and deep below while the
// venue idles. On a handoff each koi leaves through the edge facing the next screen at its own
// moment and height, and the next screen's same koi comes in through the facing edge at that
// moment and height, so the school seems to swim across one fish at a time.

export const TAU = Math.PI * 2;
export const N = 18; // spine points, nose to tail
const CROSS_S = 0.9; // the first koi's nose reaches the edge this long after t
const STAGGER_S = 0.35; // and each next one this much later

export const now = () => performance.now() / 1000;

const SCALES = [1, 0.92, 0.88, 0.84, 0.8]; // the leader is the largest
// Where each koi swims relative to the leader, [behind, beside], in koi lengths.
const FORMATION = [[0, 0], [0.75, -0.6], [0.8, 0.6], [1.5, -0.25], [1.55, 0.7]];
// The height, as a fraction of the screen, at which each koi crosses to the next screen. The
// same on every screen, so a koi leaves and arrives at the same height.
const CROSS_Y = [0.5, 0.36, 0.64, 0.43, 0.57];

// surfaced(x, y) is called now and then where a koi swims near the surface, for a ripple.
export function school(surfaced = () => {}) {
  let W = 1, H = 1, unit = 1;
  const seed = Math.random() * 100;

  const koi = FORMATION.map((_, i) => ({
    i, // which koi: 0 leads, and a creative draws koi i the same on every screen
    len: 1, // nose to the base of the tail, in pixels
    present: false,
    pts: [],
    heading: 0,
    speed: 0,
    phase: Math.random() * TAU, // the swimming stroke: the body's wave, the fins and tail
    depth: 1, depthTo: 1, // 0 at the surface, 1 deep below
    vis: 0, visTo: 0,
    leaving: null, // { side, deadline }
    arriving: null, // { side, at }
    goal: null, // where to swim before joining the school: in from the edge, after crossing
  }));

  function resize(w, h) {
    W = w;
    H = h;
    unit = Math.min(W * 0.21, H * 0.38); // the leader's length
    for (const k of koi) k.len = unit * SCALES[k.i];
  }

  // Where the school is heading: the leader's wander, and the direction it moves in.
  function lead(t) {
    const at = (s) => ({
      x: W * (0.5 + 0.2 * Math.sin(s * 0.09 + seed)), // kept near the middle: the school
      y: H * (0.5 + 0.15 * Math.sin(s * 0.14 + seed * 1.7)), // spreads out behind the leader
    });
    const p = at(t), q = at(t - 0.5);
    return { ...p, dir: Math.atan2(p.y - q.y, p.x - q.x) };
  }

  function slot(k, t) { // this koi's place in the formation
    const s = lead(t);
    const [back, side] = FORMATION[k.i];
    const fx = Math.cos(s.dir), fy = Math.sin(s.dir);
    return { x: s.x - fx * back * unit - fy * side * unit, y: s.y - fy * back * unit + fx * side * unit };
  }

  function place(k, x, y, heading) {
    const seg = k.len / (N - 1);
    k.pts = Array.from({ length: N }, (_, j) => ({
      x: x - Math.cos(heading) * seg * j,
      y: y - Math.sin(heading) * seg * j,
    }));
    k.heading = heading;
    k.present = true;
  }

  function rise(k) { // in its place in the school, deep and unseen yet
    const p = slot(k, now());
    place(k, p.x, p.y, lead(now()).dir);
    k.vis = 0;
    k.depth = 1;
    k.goal = null;
  }

  // "character", "idle" or "blank"; side is the edge of a handoff, or null.
  function show(state, side) {
    const t = now();
    for (const k of koi) {
      k.arriving = null;
      const delay = CROSS_S + k.i * STAGGER_S;
      if (state === "character") {
        k.leaving = null;
        if (side) {
          k.present = false;
          k.arriving = { side, at: t + delay };
          continue;
        }
        if (!k.present) rise(k);
        k.depthTo = 0;
        k.visTo = 1;
      } else if (state === "idle") {
        k.leaving = null;
        if (!k.present) rise(k);
        k.depthTo = 0.85 + 0.15 * (k.i / (koi.length - 1)); // deep, at a few depths
        k.visTo = 1;
      } else if (k.present) {
        if (side) k.leaving = { side, deadline: t + delay };
        else { k.visTo = 0; k.depthTo = 1; } // it sinks out of sight
      }
    }
  }

  function target(k, t) {
    if (k.leaving) {
      const beyond = k.leaving.side === "left" ? -2 * k.len : W + 2 * k.len;
      return { x: beyond, y: H * CROSS_Y[k.i] };
    }
    return k.goal ?? slot(k, t);
  }

  function update(k, t, dt) {
    if (k.arriving && t >= k.arriving.at) {
      const fromLeft = k.arriving.side === "left";
      place(k, fromLeft ? 0 : W, H * CROSS_Y[k.i], fromLeft ? 0 : Math.PI);
      k.speed = 1.6 * k.len;
      k.depth = k.depthTo = 0;
      k.vis = k.visTo = 1;
      k.goal = { x: W * (fromLeft ? 0.35 : 0.65), y: H * CROSS_Y[k.i] };
      k.arriving = null;
    }
    if (!k.present) return;
    const head = k.pts[0];
    const goal = target(k, t);
    const dist = Math.hypot(goal.x - head.x, goal.y - head.y);
    if (k.goal && dist < 0.3 * k.len) k.goal = null;

    // Speed: cruise, quicker when it has fallen behind its place, and on a handoff whatever
    // gets its nose to the edge on time.
    const cruise = 0.3 * unit * (1 - 0.4 * k.depth);
    let want = cruise * Math.min(2, Math.max(0.6, 0.6 + dist / (1.5 * unit)));
    if (k.leaving) {
      const edge = k.leaving.side === "left" ? 0 : W;
      const past = k.leaving.side === "left" ? head.x < 0 : head.x > W;
      const left = k.leaving.deadline - t;
      want = past || left < 0.05
        ? Math.max(k.speed, k.len)
        : Math.max(cruise, Math.hypot(edge - head.x, H * CROSS_Y[k.i] - head.y) / left);
    }
    k.speed += (want - k.speed) * Math.min(1, dt * (k.leaving ? 6 : 0.8));

    // Steer toward its goal, and away from any koi whose head is too close.
    let vx = (goal.x - head.x) / (dist || 1), vy = (goal.y - head.y) / (dist || 1);
    if (!k.leaving) {
      for (const o of koi) {
        if (o === k || !o.present) continue;
        const dx = head.x - o.pts[0].x, dy = head.y - o.pts[0].y;
        const d = Math.hypot(dx, dy), r = 0.8 * unit;
        if (d > 0 && d < r) { vx += (dx / d) * 3 * (1 - d / r); vy += (dy / d) * 3 * (1 - d / r); }
      }
    }
    const off = ((Math.atan2(vy, vx) - k.heading + 3 * Math.PI) % TAU) - Math.PI;
    const turn = (k.leaving ? 2.2 : 0.6) * dt; // wide, unhurried turns
    k.heading += Math.max(-turn, Math.min(turn, off));
    head.x += Math.cos(k.heading) * k.speed * dt;
    head.y += Math.sin(k.heading) * k.speed * dt;

    const seg = k.len / (N - 1); // the body follows the head, a fixed length apart
    for (let j = 1; j < N; j++) {
      const a = k.pts[j - 1], b = k.pts[j];
      const len = Math.hypot(b.x - a.x, b.y - a.y) || 1;
      b.x = a.x + ((b.x - a.x) / len) * seg;
      b.y = a.y + ((b.y - a.y) / len) * seg;
    }
    k.phase += dt * (1.5 + (5 * k.speed) / k.len);
    k.depth += (k.depthTo - k.depth) * Math.min(1, dt * 0.6);
    k.vis += (k.visTo - k.vis) * Math.min(1, dt * 0.8);

    if (k.visTo === 0 && k.vis < 0.02) k.present = false;
    if (k.leaving) {
      const gone = k.leaving.side === "left"
        ? k.pts.every((p) => p.x < -0.2 * k.len)
        : k.pts.every((p) => p.x > W + 0.2 * k.len);
      if (gone) { k.present = false; k.leaving = null; }
    }
    if (k.depth < 0.3 && Math.random() < dt * 0.08) surfaced(head.x, head.y);
  }

  // The spine as drawn: the chain, plus the wave that runs down it as it swims. Each point has
  // its position, the unit tangent toward the nose (tx, ty) and the unit normal (nx, ny).
  function spine(k) {
    const amp = 0.045 * k.len;
    return k.pts.map((q, j) => {
      const a = k.pts[Math.max(0, j - 1)], b = k.pts[Math.min(N - 1, j + 1)];
      const len = Math.hypot(a.x - b.x, a.y - b.y) || 1;
      const tx = (a.x - b.x) / len, ty = (a.y - b.y) / len; // toward the nose
      const u = j / (N - 1);
      const sway = amp * Math.pow(u, 1.6) * Math.sin(k.phase - u * 4.2);
      return { x: q.x - ty * sway, y: q.y + tx * sway, tx, ty, nx: -ty, ny: tx };
    });
  }

  return {
    koi,
    resize,
    show,
    spine,
    step: (t, dt) => { for (const k of koi) update(k, t, dt); },
    get unit() { return unit; }, // the leader's length, for sizing what goes with the school
  };
}
