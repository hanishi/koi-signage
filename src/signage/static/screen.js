// One screen: what a tablet runs. Shared by the one-page view (index.html) and screen.html.
//
// The venue's clock is the server's monotonic clock. Pings measure this page's offset from it,
// from the fastest ping of the last minute, and enter/exit run at local time t - offset,
// so two screens change on the same frame.

const now = () => performance.now() / 1000;

// Pings go every 10 s, so 6 samples is the last minute. Keeping the smallest round trip of all
// time would freeze the offset, and a tablet's crystal drifts 10-50 ppm against the Pi.
export const SAMPLE_WINDOW = 6;

// The venue clock minus the page clock, from the fastest of the last SAMPLE_WINDOW pings. A
// sample is {c: sent, r: received} on the page clock and {s} on the venue clock.
export function offsetFrom(samples) {
  const best = samples.slice(-SAMPLE_WINDOW).reduce((a, b) => (b.r - b.c < a.r - a.c ? b : a));
  return best.s - (best.c + (best.r - best.c) / 2);
}

export function connectScreen(n, el) {
  let ws;
  let offset = 0;
  let samples = [];
  let backoff = 0.5;
  let pending = [];

  const show = (state) => { el.dataset.state = state; };
  const prepared = (on) => { el.classList.toggle("prepared", on); };
  const send = (frame) => { if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(frame)); };
  const ping = () => send({ type: "ping", c: now() });
  // every t is now or now + handoff_lead_s on the venue clock: anything further means the
  // offset is wrong, and running it at once beats a screen that stays blank
  const MAX_AHEAD_MS = 2000;
  const at = (t, fn) => {
    const ms = (t - offset - now()) * 1000;
    pending.push(setTimeout(fn, ms > MAX_AHEAD_MS ? 0 : Math.max(0, ms)));
  };

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
          prepared(false);
          show("idle");
          break;
        case "prepare":
          // ponytail: the placeholder glyph needs no loading; real creatives preload here
          prepared(true);
          send({ type: "ready" });
          break;
        case "cancel":
          prepared(false);
          break;
        case "enter":
          prepared(false);
          at(m.t, () => show("character"));
          break;
        case "exit":
          at(m.t, () => show("blank"));
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
.screen { position: relative; display: grid; place-items: center; overflow: hidden;
  background: #11151c; color: #e8edf4; border: 2px solid transparent; }
.screen.prepared { border-color: #4f8cff55; border-style: dashed; }
.screen .glyph { font: 600 clamp(28px, 7vw, 120px)/1 system-ui, sans-serif; display: none; }
.screen[data-state="character"] .glyph.character { display: block; animation: bob 1.2s ease-in-out infinite; }
.screen[data-state="idle"] .glyph.attract { display: block; animation: pulse 2.4s ease-in-out infinite; }
@keyframes bob { 50% { transform: translateY(-8%); } }
@keyframes pulse { 0%, 100% { opacity: .35; } 50% { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { .screen .glyph { animation: none !important; } }
`;

export function screenElement() {
  const el = document.createElement("div");
  el.className = "screen";
  el.dataset.state = "blank";
  el.innerHTML = '<div class="glyph character">(^_^)</div><div class="glyph attract">◎</div>';
  return el;
}
