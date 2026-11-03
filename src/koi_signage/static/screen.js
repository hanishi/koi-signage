// One screen: what a tablet runs. Shared by the one-page view (index.html) and screen.html.
//
// The venue's clock is the server's monotonic clock. Pings measure this page's offset from it,
// from the fastest ping of the last minute, and enter/exit run at local time t - offset,
// so two screens change on the same frame.

const now = () => performance.now() / 1000;

// Pings go every 10 s, so 6 samples is the last minute. Keeping the smallest round trip of all
// time would freeze the offset, and a tablet's crystal drifts 10-50 ppm against the Pi.
export const SAMPLE_WINDOW = 6;

// The creative fades out this long before an ad starts. Under AD_LEAD_S in character.py, which
// is how far ahead an ad is sent.
const AD_FADE_S = 1;

// The playback speed that brings an ad back in step, from its drift: where the clip is minus
// where it should be on the venue clock, in seconds. Within IN_STEP_S, normal speed. A bit
// behind or ahead, a little faster or slower, closing the gap over about a second but never
// more than MAX_NUDGE off normal, which nobody sees. Beyond JUMP_S (a late join, a stall),
// null: jump there, as easing would take too long.
const IN_STEP_S = 0.02;
const MAX_NUDGE = 0.05;
const JUMP_S = 0.25;
export function adRate(drift) {
  if (Math.abs(drift) > JUMP_S) return null;
  if (Math.abs(drift) <= IN_STEP_S) return 1;
  return 1 - Math.max(-MAX_NUDGE, Math.min(MAX_NUDGE, drift));
}

// The venue clock minus the page clock, from the fastest of the last SAMPLE_WINDOW pings. A
// sample is {c: sent, r: received} on the page clock and {s} on the venue clock.
export function offsetFrom(samples) {
  const best = samples.slice(-SAMPLE_WINDOW).reduce((a, b) => (b.r - b.c < a.r - a.c ? b : a));
  return best.s - (best.c + (best.r - best.c) / 2);
}

// Screen n in el, drawn by create, the creative's entry point: see "Making a creative" in the
// README for the contract.
export function connectScreen(n, el, create) {
  let ws;
  let offset = 0;
  let samples = [];
  let backoff = 0.5;
  let pending = [];

  const creative = create(el.querySelector("canvas"));
  const video = el.querySelector("video");
  const show = (state, side = null) => {
    delete el.dataset.video; // any command but an ad ends one: the video fades out
    el.dataset.state = state; // and the creative fades back in
    creative.show(state, side);
  };
  video.addEventListener("transitionend", () => { if (!("video" in el.dataset)) video.pause(); });
  // Keep the clip on the venue clock: a seek takes time, and a tablet's decoder drifts. A few
  // times a second each screen eases its speed back in step, or jumps when far off (adRate).
  let adStart = null;
  video.addEventListener("timeupdate", () => {
    const due = now() + offset - adStart;
    if (adStart === null || video.paused || due > video.duration) return;
    const rate = adRate(video.currentTime - due);
    if (rate === null) video.currentTime = due;
    else video.playbackRate = rate;
  });
  const send = (frame) => { if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(frame)); };
  const ping = () => send({ type: "ping", c: now() });
  // every t is now or now + handoff_lead_s on the venue clock: anything further means the
  // offset is wrong, and running it at once beats a screen that stays blank
  const MAX_AHEAD_MS = 2000;
  const at = (t, fn) => {
    const ms = (t - offset - now()) * 1000;
    pending.push(setTimeout(fn, ms > MAX_AHEAD_MS ? 0 : Math.max(0, ms)));
  };

  // An ad: load the clip now, fade the creative out over the second before t, start the clip at
  // t. Late (a slow load, or a screen that connected mid-ad), it starts where the others are.
  function playAd(clip, t) {
    pending.forEach(clearTimeout);
    pending = [];
    const src = new URL(`/ads/${encodeURIComponent(clip)}`, location.href).href;
    if (video.src !== src) video.src = src;
    at(t - AD_FADE_S, () => {
      el.dataset.state = "ad";
      creative.show("blank");
    });
    at(t, () => {
      adStart = t;
      video.playbackRate = 1;
      const start = () => {
        const late = now() + offset - t;
        video.currentTime = late > 0.25 ? late : 0;
        video.play().catch(() => {}); // muted, so autoplay is allowed
        el.dataset.video = "";
      };
      if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) start();
      else video.addEventListener("loadeddata", start, { once: true });
    });
  }

  function open() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/screen/${n}`);
    ws.onopen = () => {
      backoff = 0.5;
      samples = [];
      for (let i = 0; i < 5; i++) setTimeout(ping, i * 200);
    };
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      switch (m.type) {
        case "pong":
          samples = [...samples, { c: m.c, r: now(), s: m.s }].slice(-SAMPLE_WINDOW);
          offset = offsetFrom(samples);
          break;
        case "idle":
          pending.forEach(clearTimeout);
          pending = [];
          show("idle");
          break;
        case "prepare":
          // ready once the creative has what the entrance needs; the handoff waits for it, up
          // to ready_timeout_s
          Promise.resolve(creative.prepare()).then(() => send({ type: "ready" }));
          break;
        case "cancel":
          break;
        case "enter":
          at(m.t, () => show("character", m.side));
          break;
        case "exit":
          at(m.t, () => show("blank", m.side));
          break;
        case "ad":
          playAd(m.clip, m.t);
          break;
      }
    };
    ws.onclose = () => {
      setTimeout(open, backoff * 1000);
      backoff = Math.min(backoff * 2, 8);
    };
  }

  open();
  setInterval(ping, 10000);
}

export const SCREEN_CSS = `
.screen { position: relative; overflow: hidden; background: #061516; }
.screen canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block;
  transition: opacity 1s; }
.screen[data-state="ad"] canvas { opacity: 0; }
.screen video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain;
  background: #000; opacity: 0; transition: opacity 0.5s; pointer-events: none; }
.screen[data-video] video { opacity: 1; }
`;

export function screenElement() {
  const el = document.createElement("div");
  el.className = "screen";
  el.dataset.state = "blank";
  const video = Object.assign(document.createElement("video"), { muted: true, playsInline: true, preload: "auto" });
  el.append(document.createElement("canvas"), video);
  return el;
}
