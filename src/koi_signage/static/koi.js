// The pond and its koi: what every screen draws, seen from above.
//
// One koi, a Taisho Sanke: white, with red patches and a few black spots. It swims near the
// surface while it is this screen's character, wanders faint and deep below while the venue
// idles, and on a handoff leaves through the edge facing the next screen, whose koi comes in
// through the facing edge as this one's tail goes, so it seems to swim across.

const TAU = Math.PI * 2;
const N = 18; // spine points, nose to tail
const CROSS_S = 0.9; // a leaving koi's nose reaches the edge this long after t
const SHELL = "#f6f1e7";
const HI = "#c8321c";
const HI_GLOW = "#e2502e";
const SUMI = "#1b1a1c";
const FIN = "246,241,231";

const now = () => performance.now() / 1000;

// Half the body's width at u (0 nose, 1 base of the tail), as a fraction of its length: a
// rounded head, widest behind it, then a long taper to the tail, as a koi looks from above.
const WIDEST = 0.27;
const halfWidth = (u) => {
  const k = Math.min(Math.max(u, 0), 1);
  if (k < WIDEST) return 0.115 * Math.sqrt(1 - ((WIDEST - k) / WIDEST) ** 2);
  return 0.115 - 0.09 * ((k - WIDEST) / (1 - WIDEST)) ** 1.25;
};

// The pattern in body coordinates, [u, v, radius along, radius across, seed]: u along the body,
// v across it, ±1 at the flanks. Patches overhang the flanks and are clipped to the body, as the
// red wraps down a real koi's sides.
const HI_PATCHES = [
  [0.105, 0.0, 0.065, 0.85, 1],
  [0.33, 0.2, 0.12, 1.35, 2],
  [0.56, -0.25, 0.1, 1.25, 3],
  [0.78, 0.35, 0.05, 0.75, 4],
];
const SUMI_SPOTS = [
  [0.25, -0.55, 0.022, 0.3, 5],
  [0.46, 0.5, 0.03, 0.38, 6],
  [0.67, 0.05, 0.018, 0.28, 7],
  [0.41, -0.15, 0.012, 0.16, 8],
];

export function pond(canvas) {
  const ctx = canvas.getContext("2d");
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let W = 1, H = 1, L = 1, dpr = 1;
  let water, vignette;

  const koi = {
    present: false,
    pts: [],
    heading: 0,
    speed: 0,
    phase: 0,
    depth: 1, depthTo: 1, // 0 at the surface, 1 deep below
    vis: 0, visTo: 0,
    leaving: null, // { side, deadline }
    arriving: null, // { side, at }
    goal: null, // where to swim before wandering: the middle, after crossing in
    seed: Math.random() * 100,
  };
  const ripples = [];
  let nextRipple = now() + 2;

  function resize() {
    dpr = window.devicePixelRatio || 1;
    W = canvas.clientWidth || 1;
    H = canvas.clientHeight || 1;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    L = Math.min(W * 0.36, H * 0.62);
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

  function place(x, y, heading) {
    const seg = L / (N - 1);
    koi.pts = Array.from({ length: N }, (_, i) => ({
      x: x - Math.cos(heading) * seg * i,
      y: y - Math.sin(heading) * seg * i,
    }));
    koi.heading = heading;
    koi.present = true;
  }

  function rise() { // somewhere deep, unseen yet
    place(W * (0.3 + 0.4 * Math.random()), H * (0.3 + 0.4 * Math.random()), Math.random() * TAU);
    koi.vis = 0;
    koi.depth = 1;
    koi.goal = null;
  }

  // "character", "idle" or "blank"; side is the edge of a handoff, or null.
  function show(state, side) {
    koi.arriving = null;
    if (state === "character") {
      koi.leaving = null;
      if (side) {
        koi.present = false;
        koi.arriving = { side, at: now() + CROSS_S };
        return;
      }
      if (!koi.present) rise();
      koi.depthTo = 0;
      koi.visTo = 1;
    } else if (state === "idle") {
      koi.leaving = null;
      if (!koi.present) rise();
      koi.depthTo = 1;
      koi.visTo = 1;
    } else if (koi.present) {
      if (side) koi.leaving = { side, deadline: now() + CROSS_S };
      else { koi.visTo = 0; koi.depthTo = 1; } // it sinks out of sight
    }
  }

  function ripple(x = W * Math.random(), y = H * Math.random()) {
    ripples.push({ x, y, born: now() });
  }

  function wander(t) {
    if (koi.leaving) return { x: koi.leaving.side === "left" ? -2 * L : W + 2 * L, y: H / 2 };
    if (koi.goal) return koi.goal;
    const s = koi.seed;
    return {
      x: W * (0.5 + 0.26 * Math.sin(t * 0.09 + s)),
      y: H * (0.5 + 0.2 * Math.sin(t * 0.14 + s * 1.7)),
    };
  }

  function update(t, dt) {
    if (koi.arriving && t >= koi.arriving.at) {
      const fromLeft = koi.arriving.side === "left";
      place(fromLeft ? 0 : W, H / 2, fromLeft ? 0 : Math.PI);
      koi.speed = 1.6 * L;
      koi.depth = koi.depthTo = 0;
      koi.vis = koi.visTo = 1;
      koi.goal = { x: W * (fromLeft ? 0.6 : 0.4), y: H / 2 };
      koi.arriving = null;
    }
    if (!koi.present) return;
    const head = koi.pts[0];

    const cruise = 0.3 * L * (1 - 0.4 * koi.depth);
    let want = cruise;
    if (koi.leaving) {
      const edge = koi.leaving.side === "left" ? 0 : W;
      const past = koi.leaving.side === "left" ? head.x < 0 : head.x > W;
      const left = koi.leaving.deadline - t;
      want = past || left < 0.05
        ? Math.max(koi.speed, L)
        : Math.max(cruise, Math.hypot(edge - head.x, H / 2 - head.y) / left);
    }
    koi.speed += (want - koi.speed) * Math.min(1, dt * (koi.leaving ? 6 : 0.8));

    const goal = wander(t);
    if (koi.goal && Math.hypot(goal.x - head.x, goal.y - head.y) < 0.3 * L) koi.goal = null;
    const desired = Math.atan2(goal.y - head.y, goal.x - head.x);
    const off = ((desired - koi.heading + 3 * Math.PI) % TAU) - Math.PI;
    const turn = (koi.leaving ? 2.2 : 0.45) * dt; // wide, unhurried turns
    koi.heading += Math.max(-turn, Math.min(turn, off));
    head.x += Math.cos(koi.heading) * koi.speed * dt;
    head.y += Math.sin(koi.heading) * koi.speed * dt;

    const seg = L / (N - 1); // the body follows the head, a fixed length apart
    for (let i = 1; i < N; i++) {
      const a = koi.pts[i - 1], b = koi.pts[i];
      const len = Math.hypot(b.x - a.x, b.y - a.y) || 1;
      b.x = a.x + ((b.x - a.x) / len) * seg;
      b.y = a.y + ((b.y - a.y) / len) * seg;
    }
    koi.phase += dt * (1.5 + (5 * koi.speed) / L);
    koi.depth += (koi.depthTo - koi.depth) * Math.min(1, dt * 0.6);
    koi.vis += (koi.visTo - koi.vis) * Math.min(1, dt * 0.8);

    if (koi.visTo === 0 && koi.vis < 0.02) koi.present = false;
    if (koi.leaving) {
      const gone = koi.leaving.side === "left"
        ? koi.pts.every((p) => p.x < -0.2 * L)
        : koi.pts.every((p) => p.x > W + 0.2 * L);
      if (gone) { koi.present = false; koi.leaving = null; }
    }
    if (koi.depth < 0.3 && Math.random() < dt * 0.25) ripple(head.x, head.y);
  }

  // The spine as drawn: the chain, plus the wave that runs down it as it swims.
  function spine() {
    const amp = 0.045 * L;
    return koi.pts.map((q, i) => {
      const a = koi.pts[Math.max(0, i - 1)], b = koi.pts[Math.min(N - 1, i + 1)];
      const len = Math.hypot(a.x - b.x, a.y - b.y) || 1;
      const tx = (a.x - b.x) / len, ty = (a.y - b.y) / len; // toward the nose
      const u = i / (N - 1);
      const sway = amp * Math.pow(u, 1.6) * Math.sin(koi.phase - u * 4.2);
      return { x: q.x - ty * sway, y: q.y + tx * sway, tx, ty, nx: -ty, ny: tx };
    });
  }

  // A point at u along the body and v across it (±1 at the flanks).
  function at(sp, u, v) {
    const f = Math.min(Math.max(u * (N - 1), 0), N - 1 - 1e-6);
    const i = Math.floor(f), k = f - i;
    const a = sp[i], b = sp[i + 1];
    const w = halfWidth(u) * L * v;
    return [
      a.x + (b.x - a.x) * k + (a.nx + (b.nx - a.nx) * k) * w,
      a.y + (b.y - a.y) * k + (a.ny + (b.ny - a.ny) * k) * w,
    ];
  }

  function smooth(path, pts) { // a curve through the midpoints, the points as handles
    path.moveTo(...pts[0]);
    for (let i = 1; i < pts.length - 1; i++) {
      const [x, y] = pts[i], [nx, ny] = pts[i + 1];
      path.quadraticCurveTo(x, y, (x + nx) / 2, (y + ny) / 2);
    }
    path.lineTo(...pts[pts.length - 1]);
    path.closePath();
    return path;
  }

  function outline(sp) {
    const side = (v) => Array.from({ length: 28 }, (_, k) => at(sp, 0.01 + (k / 27) * 0.99, v));
    return smooth(new Path2D(), [at(sp, 0, 0), ...side(-1), ...side(1).reverse(), at(sp, 0, 0)]);
  }

  function blob(sp, [uc, vc, ru, rv, seed], grow = 1) {
    const pts = [];
    for (let k = 0; k < 28; k++) {
      const th = (k / 28) * TAU;
      const u = uc + ru * grow * Math.cos(th) * (1 + 0.14 * Math.sin(3 * th + seed));
      const v = vc + rv * grow * Math.sin(th) * (1 + 0.12 * Math.cos(2 * th + seed * 1.3));
      pts.push(at(sp, u, v));
    }
    return smooth(new Path2D(), [...pts, pts[0]]);
  }

  function fin(x, y, angle, flip, len, wid, alpha) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);
    ctx.scale(1, flip);
    const g = ctx.createLinearGradient(0, 0, len, 0);
    g.addColorStop(0, `rgba(${FIN},${alpha})`);
    g.addColorStop(1, `rgba(${FIN},${alpha * 0.2})`);
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
  }

  function tail(sp) {
    const e = sp[N - 1], d = sp[N - 2];
    const back = Math.atan2(e.y - d.y, e.x - d.x) + 0.35 * Math.sin(koi.phase - 4.6);
    const flutter = 0.05 * L * Math.sin(koi.phase - 5.4);
    const len = 0.3 * L, spread = 0.17 * L, w0 = 0.028 * L;
    ctx.save();
    ctx.translate(e.x, e.y);
    ctx.rotate(back);
    const g = ctx.createLinearGradient(0, 0, len, 0);
    g.addColorStop(0, `rgba(${FIN},0.85)`);
    g.addColorStop(1, `rgba(${FIN},0.16)`);
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.moveTo(-0.02 * L, -w0);
    ctx.bezierCurveTo(len * 0.35, -w0 * 1.3, len * 0.75, -spread * 0.9 + flutter, len, -spread + flutter);
    ctx.quadraticCurveTo(len * 0.6, flutter * 0.5, len, spread + flutter);
    ctx.bezierCurveTo(len * 0.75, spread * 0.9 + flutter, len * 0.35, w0 * 1.3, -0.02 * L, w0);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = `rgba(255,255,255,0.14)`;
    ctx.lineWidth = Math.max(0.5, L * 0.003);
    for (let r = -3; r <= 3; r++) {
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(len * (0.95 - Math.abs(r) * 0.02), (r / 3) * spread * 0.92 + flutter);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawKoi() {
    const sp = spine();
    const deep = koi.depth;
    const haze = deep * 5; // px of blur the water lays over a deep koi
    const filter = (px) => { ctx.filter = px > 0.05 ? `blur(${px.toFixed(1)}px)` : "none"; };
    const mid = sp[N >> 1];
    const shape = outline(sp);

    ctx.save();
    ctx.translate(mid.x, mid.y);
    ctx.scale(1 - 0.22 * deep, 1 - 0.22 * deep);
    ctx.translate(-mid.x, -mid.y);
    ctx.globalAlpha = koi.vis * (1 - 0.72 * deep);

    ctx.save(); // its shadow on the pond floor, closer the deeper it swims
    ctx.translate(0.05 * L * (1 - deep), 0.08 * L * (1 - deep));
    filter(L * 0.04 + haze);
    ctx.fillStyle = "rgba(0,8,8,0.5)";
    ctx.fill(shape);
    ctx.restore();

    filter(haze);
    const angle = (i) => Math.atan2(-sp[i].ty, -sp[i].tx); // pointing back along the body
    const paddle = 0.28 * Math.sin(koi.phase * 0.6);
    for (const s of [1, -1]) {
      fin(...at(sp, 0.22, 0.85 * s), angle(4) - s * (1.05 + paddle), -s, 0.22 * L, 0.14 * L, 0.55);
      fin(...at(sp, 0.55, 0.75 * s), angle(10) - s * (0.65 - paddle * 0.5), -s, 0.1 * L, 0.06 * L, 0.45);
    }
    tail(sp);

    ctx.fillStyle = SHELL;
    ctx.fill(shape);
    ctx.save();
    ctx.clip(shape);
    for (const p of HI_PATCHES) {
      ctx.fillStyle = HI;
      ctx.fill(blob(sp, p));
      ctx.save();
      ctx.globalAlpha *= 0.55;
      filter(L * 0.012 + haze);
      ctx.fillStyle = HI_GLOW;
      ctx.fill(blob(sp, p, 0.6));
      ctx.restore();
    }
    ctx.fillStyle = SUMI;
    for (const p of SUMI_SPOTS) ctx.fill(blob(sp, p));

    ctx.save(); // the rounding of the flanks, and the light along the back
    filter(L * 0.008 + haze);
    ctx.strokeStyle = "rgba(70,60,52,0.3)";
    ctx.lineWidth = 0.035 * L;
    ctx.stroke(shape);
    const back = new Path2D();
    back.moveTo(...at(sp, 0.1, -0.15));
    for (let u = 0.14; u <= 0.78; u += 0.04) back.lineTo(...at(sp, u, -0.15));
    filter(L * 0.025 + haze);
    ctx.strokeStyle = "rgba(255,255,255,0.13)";
    ctx.lineWidth = 0.09 * L;
    ctx.lineCap = "round";
    ctx.stroke(back);
    ctx.restore();

    const dorsal = new Path2D(); // the dorsal fin, edge-on from above
    dorsal.moveTo(...at(sp, 0.32, 0));
    for (let u = 0.35; u <= 0.66; u += 0.03) dorsal.lineTo(...at(sp, u, 0.06 * Math.sin(koi.phase + u * 9)));
    filter(L * 0.006 + haze);
    ctx.strokeStyle = "rgba(255,250,240,0.3)";
    ctx.lineWidth = 0.018 * L;
    ctx.stroke(dorsal);
    ctx.restore();

    for (const s of [1, -1]) {
      const [x, y] = at(sp, 0.07, 0.62 * s);
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
    for (let i = 0; i < 6; i++) { // slow light from the surface
      const x = W * (0.5 + 0.45 * Math.sin(t * 0.03 * (i + 1) + i * 2.1));
      const y = H * (0.5 + 0.45 * Math.sin(t * 0.025 * (i + 2) + i * 1.3));
      const r = Math.max(W, H) * (0.18 + 0.06 * Math.sin(t * 0.05 + i));
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
    for (let i = ripples.length - 1; i >= 0; i--) {
      const age = t - ripples[i].born;
      if (age > LIFE) ripples.splice(i, 1);
    }
    ctx.save();
    ctx.lineWidth = Math.max(0.6, L * 0.004);
    for (const r of ripples) {
      const age = t - r.born;
      for (const lag of [0, 0.5]) {
        const a = age - lag;
        if (a <= 0) continue;
        ctx.strokeStyle = `rgba(200,235,225,${0.16 * (1 - a / LIFE)})`;
        ctx.beginPath();
        ctx.arc(r.x, r.y, a * 0.14 * L, 0, TAU);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  let last = now();
  function frame() {
    const t = now(), dt = Math.min(0.05, t - last);
    last = t;
    update(t, dt);
    if (!calm && t > nextRipple) {
      ripple();
      nextRipple = t + 4 + 5 * Math.random();
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawWater(calm ? 0 : t);
    if (koi.present) drawKoi();
    drawRipples(t);
    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, W, H);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  return { show, ripple: () => ripple() };
}
