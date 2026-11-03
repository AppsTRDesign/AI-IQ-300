import { useStore } from "./store";

// One event websocket with reconnect + replay from the last seen sequence number.
// Incoming events are queued and applied once per animation frame: streaming never re-renders per token.
export function connectEvents() {
  let ws, delay = 500, stopped = false, queue = [], scheduled = false;
  const flush = () => {
    scheduled = false;
    const batch = queue;
    queue = [];
    if (batch.length) useStore.getState().applyEvents(batch);
  };
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    // rAF pauses in background tabs; fall back to a timer so runs keep progressing.
    document.hidden ? setTimeout(flush, 250) : requestAnimationFrame(flush);
  };
  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/events?since=${useStore.getState().lastSeq}`);
    ws.onopen = () => { delay = 500; useStore.setState({ connected: true }); };
    ws.onmessage = (m) => { queue.push(JSON.parse(m.data)); schedule(); };
    ws.onclose = () => {
      useStore.setState({ connected: false });
      if (!stopped) setTimeout(open, (delay = Math.min(delay * 2, 8000)));
    };
  };
  open();
  return () => { stopped = true; ws?.close(); };
}
