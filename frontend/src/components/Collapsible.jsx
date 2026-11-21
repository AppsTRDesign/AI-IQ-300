import { useLayoutEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useT } from "../lib/store";

// A long message (the user's own, a steering message, a steering note in the steps) shows its first part with a
// soft fade and a "Show more" button; opened, it shows everything with "Show less". Short ones show as they are.
// The content is whatever is passed in (Markdown with code blocks), so it looks like every other message.
export default function Collapsible({ children, max = 260, className = "" }) {
  const t = useT();
  const box = useRef(null);
  const [long, setLong] = useState(false);
  const [open, setOpen] = useState(false);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const measure = () => setLong(el.scrollHeight > max + 48);
    measure();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    ro?.observe(el);
    return () => ro?.disconnect();
  }, [max]);
  const clamped = long && !open;
  return (
    <div className={className}>
      <div ref={box} className="relative" style={clamped ? { maxHeight: max, overflow: "hidden",
        WebkitMaskImage: "linear-gradient(to bottom, #000 70%, transparent)", maskImage: "linear-gradient(to bottom, #000 70%, transparent)" } : undefined}>
        {children}
      </div>
      {long && (
        <button type="button" onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
          className="mt-1 inline-flex items-center gap-1 text-[12px] font-medium text-muted hover:text-fg">
          {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}{t(open ? "show_less" : "show_more")}
        </button>
      )}
    </div>
  );
}
