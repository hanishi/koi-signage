// The pond and its school of koi: what every screen draws, seen from above.
//
// Five koi of different varieties swim together, in loose formation behind the leader. The
// school is the character: it swims near the surface while it is this screen's, and drifts faint
// and deep below while the venue idles. On a handoff each koi leaves through the edge facing the
// next screen at its own moment and height, and the next screen's same koi comes in through the
// facing edge at that moment and height, so the school seems to swim across one fish at a time.

const TAU = Math.PI * 2;
const N = 18; // spine points, nose to tail
const CROSS_S = 0.9; // the first koi's nose reaches the edge this long after t
const STAGGER_S = 0.35; // and each next one this much later

const now = () => performance.now() / 1000;

// Half the body's width at u (0 nose, 1 base of the tail), as a fraction of its length: a
// rounded head, widest behind it, then a long taper to the tail, as a koi looks from above.
const WIDEST = 0.27;
const halfWidth = (u) => {
  const k = Math.min(Math.max(u, 0), 1);
  if (k < WIDEST) return 0.115 * Math.sqrt(1 - ((WIDEST - k) / WIDEST) ** 2);
  return 0.115 - 0.09 * ((k - WIDEST) / (1 - WIDEST)) ** 1.25;
};

const SHELL = "#f6f1e7";
const RED = "#c8321c";
const RED_GLOW = "#e2502e";
const SUMI = "#1b1a1c";

// Each variety's colours and pattern. A patch is [u, v, radius along, radius across, seed,
// colour] in body coordinates: u along the body, v across it, ±1 at the flanks. Patches overhang
// the flanks and are clipped to the body, as the colour wraps down a real koi's sides.
const VARIETIES = [
  {
    name: "Taisho Sanke", body: SHELL, fin: "246,241,231", sheen: 0.13,
    patches: [
      [0.105, 0.0, 0.065, 0.85, 1, RED], [0.33, 0.2, 0.12, 1.35, 2, RED],
      [0.56, -0.25, 0.1, 1.25, 3, RED], [0.78, 0.35, 0.05, 0.75, 4, RED],
      [0.25, -0.55, 0.022, 0.3, 5, SUMI], [0.46, 0.5, 0.03, 0.38, 6, SUMI],
      [0.67, 0.05, 0.018, 0.28, 7, SUMI], [0.41, -0.15, 0.012, 0.16, 8, SUMI],
    ],
  },
  {
    name: "Kohaku", body: SHELL, fin: "246,241,231", sheen: 0.13,
    patches: [
      [0.12, 0.05, 0.07, 0.9, 11, RED], [0.37, -0.15, 0.13, 1.45, 12, RED],
      [0.63, 0.2, 0.1, 1.3, 13, RED],
    ],
  },
  {
    name: "Showa", body: "#211e20", fin: "232,226,218", sheen: 0.1,
    patches: [
      [0.11, 0.15, 0.07, 0.95, 21, RED], [0.3, -0.35, 0.08, 0.85, 22, SHELL],
      [0.46, 0.3, 0.12, 1.2, 23, RED], [0.66, -0.25, 0.08, 0.9, 24, SHELL],
      [0.82, 0.2, 0.05, 0.8, 25, RED],
    ],
  },
  { name: "Yamabuki Ogon", body: "#dca54a", fin: "238,200,118", sheen: 0.38, patches: [] },
  {
    name: "Asagi", body: "#8ea4b3", fin: "222,230,234", sheen: 0.15, net: "#53687a",
    patches: [
      [0.5, 1.3, 0.42, 0.5, 31, "#cf5a30"], [0.5, -1.3, 0.42, 0.5, 32, "#cf5a30"],
      [0.04, 0.0, 0.07, 0.9, 33, "#e8ebe6"],
    ],
  },
];
const SCALES = [1, 0.92, 0.88, 0.84, 0.8]; // the leader is the largest
// Where each koi swims relative to the leader, [behind, beside], in koi lengths.
const FORMATION = [[0, 0], [0.75, -0.6], [0.8, 0.6], [1.5, -0.25], [1.55, 0.7]];
// The height, as a fraction of the screen, at which each koi crosses to the next screen. The
// same on every screen, so a koi leaves and arrives at the same height.
const CROSS_Y = [0.5, 0.36, 0.64, 0.43, 0.57];

export function pond(canvas) {
  const ctx = canvas.getContext("2d");
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let W = 1, H = 1, unit = 1, dpr = 1;
  let water, vignette;
  const seed = Math.random() * 100;

  const school = VARIETIES.map((variety, i) => ({
    i,
    variety,
    len: 1,
    present: false,
    pts: [],
    heading: 0,
    speed: 0,
    phase: Math.random() * TAU,
    depth: 1, depthTo: 1, // 0 at the surface, 1 deep below
    vis: 0, visTo: 0,
    leaving: null, // { side, deadline }
    arriving: null, // { side, at }
    goal: null, // where to swim before joining the school: in from the edge, after crossing
  }));
  const ripples = [];
  let nextRipple = now() + 2;

  function resize() {
    dpr = window.devicePixelRatio || 1;
    W = canvas.clientWidth || 1;
    H = canvas.clientHeight || 1;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    unit = Math.min(W * 0.21, H * 0.38); // the leader's length
    for (const k of school) k.len = unit * SCALES[k.i];
    const far = Math.hypot(W, H) * 0.6;
    water = ctx.createRadialGradient(W * 0.45, H * 0.4, 0, W * 0.5, H * 0.5, far);
    water.addColorStop(0, "#133839");
    water.addColorStop(0.6, "#0b2627");
    water.addColorStop(1, "#051213");
    vignette = ctx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.35, W / 2, H / 2, far);
    vignette.addColorStop(0, "rgba(2,10,10,0)");
    vignette.addColorStop(1, "rgba(2,10,10,0.55)");
  }
  new ResizeObserver(resize).observe(canvas);
  resize();

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
    for (const k of school) {
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
        k.depthTo = 0.85 + 0.15 * (k.i / (school.length - 1)); // deep, at a few depths
        k.visTo = 1;
      } else if (k.present) {
        if (side) k.leaving = { side, deadline: t + delay };
        else { k.visTo = 0; k.depthTo = 1; } // it sinks out of sight
      }
    }
  }

  function ripple(x = W * Math.random(), y = H * Math.random()) {
    ripples.push({ x, y, born: now() });
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
      for (const o of school) {
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
    if (k.depth < 0.3 && Math.random() < dt * 0.08) ripple(head.x, head.y);
  }

  // The spine as drawn: the chain, plus the wave that runs down it as it swims.
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

  function smooth(path, pts) { // a curve through the midpoints, the points as handles
    path.moveTo(...pts[0]);
    for (let j = 1; j < pts.length - 1; j++) {
      const [x, y] = pts[j], [nx, ny] = pts[j + 1];
      path.quadraticCurveTo(x, y, (x + nx) / 2, (y + ny) / 2);
    }
    path.lineTo(...pts[pts.length - 1]);
    path.closePath();
    return path;
  }

  function drawKoi(k) {
    const L = k.len, v = k.variety, sp = spine(k);
    const deep = k.depth;
    // No canvas blur filters anywhere: each one renders a full-canvas layer, and five koi on a
    // tablet would draw dozens a frame. Soft edges come from layered translucent strokes, and
    // depth from a wash of the water's colour.

    // A point at u along the body and v across it (±1 at the flanks).
    const at = (u, w) => {
      const f = Math.min(Math.max(u * (N - 1), 0), N - 1 - 1e-6);
      const j = Math.floor(f), r = f - j;
      const a = sp[j], b = sp[j + 1];
      const d = halfWidth(u) * L * w;
      return [
        a.x + (b.x - a.x) * r + (a.nx + (b.nx - a.nx) * r) * d,
        a.y + (b.y - a.y) * r + (a.ny + (b.ny - a.ny) * r) * d,
      ];
    };
    const side = (w) => Array.from({ length: 28 }, (_, j) => at(0.01 + (j / 27) * 0.99, w));
    const shape = smooth(new Path2D(), [at(0, 0), ...side(-1), ...side(1).reverse(), at(0, 0)]);
    const blob = ([uc, vc, ru, rv, s], grow = 1) => {
      const pts = [];
      for (let j = 0; j < 28; j++) {
        const th = (j / 28) * TAU;
        pts.push(at(
          uc + ru * grow * Math.cos(th) * (1 + 0.14 * Math.sin(3 * th + s)),
          vc + rv * grow * Math.sin(th) * (1 + 0.12 * Math.cos(2 * th + s * 1.3)),
        ));
      }
      return smooth(new Path2D(), [...pts, pts[0]]);
    };
    const fin = (x, y, angle, flip, len, wid, alpha) => {
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(angle);
      ctx.scale(1, flip);
      const g = ctx.createLinearGradient(0, 0, len, 0);
      g.addColorStop(0, `rgba(${v.fin},${alpha})`);
      g.addColorStop(1, `rgba(${v.fin},${alpha * 0.2})`);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(0, -wid * 0.25);
      ctx.quadraticCurveTo(len * 0.55, -wid * 0.95, len, -wid * 0.3);
      ctx.quadraticCurveTo(len * 1.04, wid * 0.4, len * 0.72, wid * 0.62);
      ctx.quadraticCurveTo(len * 0.3, wid * 0.45, 0, wid * 0.25);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = `rgba(255,255,255,${alpha * 0.3})`;
      ctx.lineWidth = Math.max(0.5, L * 0.003);
      for (let r = -2; r <= 2; r++) {
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(len * 0.9, r * wid * 0.17 - wid * 0.05);
        ctx.stroke();
      }
      ctx.restore();
    };
    const tail = () => {
      const e = sp[N - 1], d = sp[N - 2];
      const back = Math.atan2(e.y - d.y, e.x - d.x) + 0.35 * Math.sin(k.phase - 4.6);
      const flutter = 0.05 * L * Math.sin(k.phase - 5.4);
      const len = 0.3 * L, spread = 0.17 * L, w0 = 0.028 * L;
      ctx.save();
      ctx.translate(e.x, e.y);
      ctx.rotate(back);
      const g = ctx.createLinearGradient(0, 0, len, 0);
      g.addColorStop(0, `rgba(${v.fin},0.85)`);
      g.addColorStop(1, `rgba(${v.fin},0.16)`);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(-0.02 * L, -w0);
      ctx.bezierCurveTo(len * 0.35, -w0 * 1.3, len * 0.75, -spread * 0.9 + flutter, len, -spread + flutter);
      ctx.quadraticCurveTo(len * 0.6, flutter * 0.5, len, spread + flutter);
      ctx.bezierCurveTo(len * 0.75, spread * 0.9 + flutter, len * 0.35, w0 * 1.3, -0.02 * L, w0);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,0.14)";
      ctx.lineWidth = Math.max(0.5, L * 0.003);
      for (let r = -3; r <= 3; r++) {
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(len * (0.95 - Math.abs(r) * 0.02), (r / 3) * spread * 0.92 + flutter);
        ctx.stroke();
      }
      ctx.restore();
    };

    const mid = sp[N >> 1];
    ctx.save();
    ctx.translate(mid.x, mid.y);
    ctx.scale(1 - 0.22 * deep, 1 - 0.22 * deep);
    ctx.translate(-mid.x, -mid.y);
    ctx.globalAlpha = k.vis * (1 - 0.72 * deep);

    ctx.save(); // its shadow on the pond floor, closer the deeper it swims, soft at the edge
    ctx.translate(0.05 * L * (1 - deep), 0.08 * L * (1 - deep));
    ctx.fillStyle = "rgba(0,8,8,0.28)";
    ctx.fill(shape);
    ctx.lineJoin = "round";
    for (const [w, a] of [[0.07, 0.07], [0.035, 0.1]]) {
      ctx.strokeStyle = `rgba(0,8,8,${a})`;
      ctx.lineWidth = w * L;
      ctx.stroke(shape);
    }
    ctx.restore();

    const angle = (j) => Math.atan2(-sp[j].ty, -sp[j].tx); // pointing back along the body
    const paddle = 0.28 * Math.sin(k.phase * 0.6);
    for (const s of [1, -1]) {
      fin(...at(0.22, 0.85 * s), angle(4) - s * (1.05 + paddle), -s, 0.22 * L, 0.14 * L, 0.55);
      fin(...at(0.55, 0.75 * s), angle(10) - s * (0.65 - paddle * 0.5), -s, 0.1 * L, 0.06 * L, 0.45);
    }
    tail();

    ctx.fillStyle = v.body;
    ctx.fill(shape);
    ctx.save();
    ctx.clip(shape);
    if (v.net) { // Asagi's net: each scale edged darker
      ctx.strokeStyle = v.net;
      ctx.globalAlpha *= 0.45;
      ctx.lineWidth = Math.max(0.5, L * 0.004);
      for (let u = 0.16; u < 0.86; u += 0.045) {
        for (let w = -0.75; w <= 0.76; w += 0.3) {
          const [x, y] = at(u, w + (Math.round(u / 0.045) % 2) * 0.15);
          ctx.beginPath();
          ctx.arc(x, y, 0.018 * L, 0, TAU);
          ctx.stroke();
        }
      }
      ctx.globalAlpha /= 0.45;
    }
    for (const p of v.patches) {
      ctx.fillStyle = p[5];
      ctx.fill(blob(p));
      if (p[5] === RED) { // a lighter heart to each red patch
        ctx.save();
        ctx.globalAlpha *= 0.45;
        ctx.fillStyle = RED_GLOW;
        ctx.fill(blob(p, 0.6));
        ctx.restore();
      }
    }

    ctx.save(); // the rounding of the flanks, and the light along the back
    for (const [w, a] of [[0.06, 0.12], [0.03, 0.16]]) { // inside the clip: half of each shows
      ctx.strokeStyle = `rgba(40,32,28,${a})`;
      ctx.lineWidth = w * L;
      ctx.stroke(shape);
    }
    const back = new Path2D();
    back.moveTo(...at(0.1, -0.15));
    for (let u = 0.14; u <= 0.78; u += 0.04) back.lineTo(...at(u, -0.15));
    ctx.lineCap = "round";
    for (const [w, a] of [[0.12, 0.35], [0.07, 0.4], [0.035, 0.45]]) {
      ctx.strokeStyle = `rgba(255,255,255,${v.sheen * a})`;
      ctx.lineWidth = w * L;
      ctx.stroke(back);
    }
    ctx.restore();

    const dorsal = new Path2D(); // the dorsal fin, edge-on from above
    dorsal.moveTo(...at(0.32, 0));
    for (let u = 0.35; u <= 0.66; u += 0.03) dorsal.lineTo(...at(u, 0.06 * Math.sin(k.phase + u * 9)));
    ctx.strokeStyle = "rgba(255,250,240,0.22)";
    ctx.lineWidth = 0.018 * L;
    ctx.stroke(dorsal);
    if (deep > 0.02) { // the water between it and the surface
      ctx.fillStyle = `rgba(11,38,39,${(0.6 * deep).toFixed(3)})`;
      ctx.fill(shape);
    }
    ctx.restore();

    for (const s of [1, -1]) {
      const [x, y] = at(0.07, 0.62 * s);
      ctx.fillStyle = "#2a2422";
      ctx.beginPath();
      ctx.arc(x, y, 0.012 * L, 0, TAU);
      ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.7)";
      ctx.beginPath();
      ctx.arc(x - 0.004 * L, y - 0.004 * L, 0.004 * L, 0, TAU);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawWater(t) {
    ctx.fillStyle = water;
    ctx.fillRect(0, 0, W, H);
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    for (let j = 0; j < 6; j++) { // slow light from the surface
      const x = W * (0.5 + 0.45 * Math.sin(t * 0.03 * (j + 1) + j * 2.1));
      const y = H * (0.5 + 0.45 * Math.sin(t * 0.025 * (j + 2) + j * 1.3));
      const r = Math.max(W, H) * (0.18 + 0.06 * Math.sin(t * 0.05 + j));
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, "rgba(159,214,194,0.06)");
      g.addColorStop(1, "rgba(159,214,194,0)");
      ctx.fillStyle = g;
      ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
    }
    ctx.restore();
  }

  function drawRipples(t) {
    const LIFE = 4;
    for (let j = ripples.length - 1; j >= 0; j--) {
      if (t - ripples[j].born > LIFE) ripples.splice(j, 1);
    }
    ctx.save();
    ctx.lineWidth = Math.max(0.6, unit * 0.004);
    for (const r of ripples) {
      const age = t - r.born;
      for (const lag of [0, 0.5]) {
        const a = age - lag;
        if (a <= 0) continue;
        ctx.strokeStyle = `rgba(200,235,225,${0.16 * (1 - a / LIFE)})`;
        ctx.beginPath();
        ctx.arc(r.x, r.y, a * 0.14 * unit, 0, TAU);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  let last = now();
  function frame() {
    const t = now(), dt = Math.min(0.05, t - last);
    last = t;
    for (const k of school) update(k, t, dt);
    if (!calm && t > nextRipple) {
      ripple();
      nextRipple = t + 4 + 5 * Math.random();
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawWater(calm ? 0 : t);
    // the deepest first, so nearer koi swim over them
    for (const k of [...school].sort((a, b) => b.depth - a.depth)) if (k.present) drawKoi(k);
    drawRipples(t);
    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, W, H);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  return { show, ripple: () => ripple() };
}
