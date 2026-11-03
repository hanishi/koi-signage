// The same school as koi.js, from images: each koi is a PNG in koi-pixi/, bent along the
// school's spine by a PixiJS MeshRope, so it swims and turns like the drawn one. Replace the PNGs
// with your own art, drawn to the same layout (see "Image creatives" in the README), and the
// school swims in it.

import { N, now, school as swim } from "../school.js";

const ART = 512; // a koi's length in its PNG, nose to the base of the tail, in pixels
const POINTS = 25; // rope points across a PNG: 24 segments, 1 before the nose, 17 body, 6 tail
const ART_FILES = [0, 1, 2, 3, 4].map((i) => new URL(`koi-pixi/${i}.png`, import.meta.url).href);
const WATER = [11, 38, 39]; // the colour a deep koi fades toward
const LIFE = 4; // a ripple lasts this long

export function create(canvas) {
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ripples = [];
  let nextRipple = now() + 2;
  const ripple = (x = W * Math.random(), y = H * Math.random()) => ripples.push({ x, y, born: now() });
  const school = swim(ripple);
  let W = canvas.clientWidth || 1, H = canvas.clientHeight || 1;
  school.resize(W, H);
  // show() works at once, as the school is only numbers; the drawing starts once PixiJS and
  // the art are loaded, which is what prepare() waits for
  const ready = start().catch((e) => console.error("koi-pixi:", e));
  return { show: school.show, prepare: () => ready };

  async function start() {
    const PIXI = await import("../vendor/pixi-8.22.0.min.mjs");
    const app = new PIXI.Application();
    await app.init({
      canvas, width: W, height: H, resolution: devicePixelRatio || 1, antialias: true,
      background: "#061516",
    });
    const art = await PIXI.Assets.load(ART_FILES);

    // A canvas gradient as a texture: PixiJS draws images, so the water is drawn once per size.
    const painted = (w, h, paint) => {
      const c = Object.assign(document.createElement("canvas"), { width: w, height: h });
      paint(c.getContext("2d"), w, h);
      return PIXI.Texture.from(c);
    };
    const water = new PIXI.Sprite();
    const vignette = new PIXI.Sprite();
    const glow = painted(128, 128, (g) => {
      const r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
      r.addColorStop(0, "rgba(159,214,194,1)");
      r.addColorStop(1, "rgba(159,214,194,0)");
      g.fillStyle = r;
      g.fillRect(0, 0, 128, 128);
    });
    const lights = Array.from({ length: 6 }, () =>
      Object.assign(new PIXI.Sprite(glow), { blendMode: "add", alpha: 0.06 }));
    lights.forEach((s) => s.anchor.set(0.5));

    const shadows = new PIXI.Container(); // on the pond floor, blurred together in one pass
    const blur = new PIXI.BlurFilter({ strength: 8, quality: 3 });
    shadows.filters = [blur];
    const fish = new PIXI.Container({ sortableChildren: true });
    const rings = new PIXI.Graphics();
    const views = school.koi.map((k) => {
      const points = Array.from({ length: POINTS }, () => new PIXI.Point());
      const texture = art[ART_FILES[k.i]];
      const body = new PIXI.Container();
      body.addChild(new PIXI.MeshRope({ texture, points }));
      const shade = new PIXI.Container();
      shade.addChild(new PIXI.MeshRope({ texture, points, tint: 0x000808 }));
      fish.addChild(body);
      shadows.addChild(shade);
      return { points, body, shade };
    });
    app.stage.addChild(water, ...lights, shadows, fish, rings, vignette);

    function resize() {
      W = canvas.clientWidth || 1;
      H = canvas.clientHeight || 1;
      app.renderer.resize(W, H);
      school.resize(W, H);
      const far = Math.hypot(W, H) * 0.6;
      for (const s of [water, vignette]) if (s.texture !== PIXI.Texture.EMPTY) s.texture.destroy(true);
      water.texture = painted(Math.ceil(W / 4), Math.ceil(H / 4), (g, w, h) => {
        const r = g.createRadialGradient(w * 0.45, h * 0.4, 0, w * 0.5, h * 0.5, far / 4);
        r.addColorStop(0, "#133839");
        r.addColorStop(0.6, "#0b2627");
        r.addColorStop(1, "#051213");
        g.fillStyle = r;
        g.fillRect(0, 0, w, h);
      });
      vignette.texture = painted(Math.ceil(W / 4), Math.ceil(H / 4), (g, w, h) => {
        const r = g.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, far / 4);
        r.addColorStop(0, "rgba(2,10,10,0)");
        r.addColorStop(1, "rgba(2,10,10,0.55)");
        g.fillStyle = r;
        g.fillRect(0, 0, w, h);
      });
      for (const s of [water, vignette]) s.setSize(W, H);
      blur.strength = school.unit * 0.03;
    }
    new ResizeObserver(resize).observe(canvas);
    resize();

    // Koi k's rope: one point ahead of the nose, the 18 of the spine, then 6 of tail, swung
    // with the stroke as koi.js swings its tail. In PNG pixels: the koi's view scales them back.
    function bend(k, points) {
      const sp = school.spine(k), seg = k.len / (N - 1), b = k.len / ART;
      const set = (p, x, y) => p.set(x / b, y / b);
      set(points[0], sp[0].x + sp[0].tx * seg, sp[0].y + sp[0].ty * seg);
      sp.forEach((q, j) => set(points[1 + j], q.x, q.y));
      const e = sp[N - 1], d = sp[N - 2];
      const back = Math.atan2(e.y - d.y, e.x - d.x) + 0.35 * Math.sin(k.phase - 4.6);
      for (let m = 1; m <= POINTS - 1 - N; m++) {
        set(points[N + m], e.x + Math.cos(back) * seg * m, e.y + Math.sin(back) * seg * m);
      }
      return sp[N >> 1];
    }

    // Shrink v by depth about the koi's middle m, as it sinks; dx, dy offset it (the shadow).
    function place(v, k, m, dx = 0, dy = 0) {
      const b = k.len / ART;
      v.position.set(m.x + dx, m.y + dy);
      v.pivot.set(m.x / b, m.y / b);
      v.scale.set(b * (1 - 0.22 * k.depth));
    }

    let last = now();
    app.ticker.add(() => {
      const t = now(), dt = Math.min(0.05, t - last);
      last = t;
      school.step(t, dt);
      if (!calm && t > nextRipple) {
        ripple();
        nextRipple = t + 4 + 5 * Math.random();
      }
      const lt = calm ? 0 : t;
      lights.forEach((s, j) => { // slow light from the surface
        s.position.set(
          W * (0.5 + 0.45 * Math.sin(lt * 0.03 * (j + 1) + j * 2.1)),
          H * (0.5 + 0.45 * Math.sin(lt * 0.025 * (j + 2) + j * 1.3)),
        );
        const r = Math.max(W, H) * (0.18 + 0.06 * Math.sin(lt * 0.05 + j));
        s.setSize(2 * r, 2 * r);
      });

      for (const k of school.koi) {
        const v = views[k.i];
        v.body.visible = v.shade.visible = k.present;
        if (!k.present) continue;
        const m = bend(k, v.points);
        const deep = k.depth, alpha = k.vis * (1 - 0.72 * deep);
        place(v.body, k, m);
        place(v.shade, k, m, 0.05 * k.len * (1 - deep), 0.08 * k.len * (1 - deep));
        v.body.zIndex = -deep; // the deepest first, so nearer koi swim over them
        v.body.alpha = alpha;
        v.shade.alpha = 0.28 * alpha;
        const a = 0.6 * deep; // the water between it and the surface
        const [r, g, bl] = WATER.map((c) => Math.round(255 * (1 - a) + c * a));
        v.body.children[0].tint = (r << 16) | (g << 8) | bl;
      }

      rings.clear();
      for (let j = ripples.length - 1; j >= 0; j--) if (t - ripples[j].born > LIFE) ripples.splice(j, 1);
      for (const rp of ripples) {
        for (const lag of [0, 0.5]) {
          const age = t - rp.born - lag;
          if (age <= 0) continue;
          rings.circle(rp.x, rp.y, age * 0.14 * school.unit).stroke({
            width: Math.max(0.6, school.unit * 0.004), color: 0xc8ebe1, alpha: 0.16 * (1 - age / LIFE),
          });
        }
      }
    });
  }
}
