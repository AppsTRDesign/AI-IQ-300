import { useStore } from "./store";

// One event websocket with reconnect. A short break is filled from the server's replay buffer (since=<last seq>);
// a new page, a backend that restarted or a longer break gets the full state instead (a "hello" event with
// reset=true, then one snapshot per running task). Incoming events are queued and applied once per animation frame:
// streaming never re-renders per token.
const SILENCE_MS = 40000; // the server pings every 15 s: this long without a message means the connection is dead

export function connectEvents() {
  let ws, delay = 500, stopped = false, queue = [], scheduled = false, lastAt = Date.now(), retry = 0;
  const flush = () => {
    scheduled = false;
    const batch = queue;
    queue = [];
    if (batch.length) useStore.getState().applyEvents(batch);
  };
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    // Once per frame; frames also stop in covered windows and embedded panes that still report "visible",
    // so a timer applies the batch too (whichever comes first): the chat never freezes and the queue never grows.
    let timer = 0;
    const run = () => { clearTimeout(timer); if (scheduled) flush(); };
    timer = setTimeout(run, document.hidden ? 250 : 150);
    if (!document.hidden) requestAnimationFrame(run);
  };
  const reconnect = () => {
    clearTimeout(retry);
    try { ws?.close(); } catch {}
  };
  const open = () => {
    if (stopped) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const { lastSeq, boot } = useStore.getState();
    const mine = (ws = new WebSocket(`${proto}://${location.host}/ws/events?since=${lastSeq}&boot=${encodeURIComponent(boot || "")}`));
    mine.onopen = () => { delay = 500; lastAt = Date.now(); useStore.setState({ connected: true }); };
    mine.onmessage = (m) => {
      lastAt = Date.now();
      let data;
      try { data = JSON.parse(m.data); } catch { return; }
      for (const e of Array.isArray(data) ? data : [data]) {
        if (e.topic === "system" && e.type === "ping") continue;
        // The server dropped this client's backlog (it was not reading): reconnect and resync from the last event seen.
        if (e.topic === "system" && e.type === "gap") { flush(); reconnect(); return; }
        queue.push(e);
      }
      schedule();
    };
    mine.onclose = () => {
      if (ws !== mine) return; // an older socket closing after a newer one opened
      useStore.setState({ connected: false });
      if (!stopped) retry = setTimeout(open, (delay = Math.min(delay * 2, 8000)));
    };
    mine.onerror = () => { try { mine.close(); } catch {} };
  };
  open();
  // A connection that died without closing (sleep, a network change, a proxy): nothing arrives, not even pings.
  const watch = setInterval(() => {
    if (stopped || !ws) return;
    if (ws.readyState === WebSocket.OPEN && Date.now() - lastAt > SILENCE_MS) reconnect();
  }, 5000);
  const wake = () => {
    if (stopped) return;
    if (!ws || ws.readyState === WebSocket.CLOSED) { clearTimeout(retry); delay = 500; open(); }
    else if (ws.readyState === WebSocket.OPEN && Date.now() - lastAt > SILENCE_MS) reconnect();
  };
  addEventListener("online", wake);
  addEventListener("focus", wake);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) wake(); });
  return () => { stopped = true; clearInterval(watch); clearTimeout(retry); removeEventListener("online", wake); removeEventListener("focus", wake); ws?.close(); };
}
