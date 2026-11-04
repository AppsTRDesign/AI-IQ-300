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
    // Once per frame; frames also stop in covered windows and embedded panes that still report "visible",
    // so a timer applies the batch too (whichever comes first): the chat never freezes and the queue never grows.
    let timer = 0;
    const run = () => { clearTimeout(timer); if (scheduled) flush(); };
    timer = setTimeout(run, document.hidden ? 250 : 150);
    if (!document.hidden) requestAnimationFrame(run);
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
