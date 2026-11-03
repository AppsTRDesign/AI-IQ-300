import { memo, useState } from "react";
import { Check, ChevronDown, ListTodo } from "lucide-react";
import { useT } from "../lib/store";

// The model's live task list (todo tool): pinned under the running answer, kept with the finished message.
function Mark({ status }) {
  if (status === "completed") {
    return <span className="grid h-[17px] w-[17px] shrink-0 place-items-center rounded-full bg-fg/80 text-bg"><Check size={11} strokeWidth={3} /></span>;
  }
  if (status === "in_progress") {
    return (
      <span className="relative grid h-[17px] w-[17px] shrink-0 place-items-center">
        <span className="absolute inset-0 animate-spin rounded-full border-2 border-accent/25 border-t-accent" />
      </span>
    );
  }
  return <span className="block h-[17px] w-[17px] shrink-0 rounded-full border-[1.5px] border-dashed border-subtle" />;
}

function TodoList({ todos, live }) {
  const t = useT();
  const [open, setOpen] = useState(true);
  if (!todos?.length) return null;
  const done = todos.filter((x) => x.status === "completed").length;
  const pct = Math.round((done / todos.length) * 100);
  const current = todos.find((x) => x.status === "in_progress");
  return (
    <div className="fade-in my-3 overflow-hidden rounded-2xl border border-line bg-elev shadow-[0_1px_6px_rgb(0_0_0/0.04)]">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left hover:bg-hover/60">
        <ListTodo size={15} className="shrink-0 text-accent" />
        <span className="text-[13px] font-semibold">{t("todo_title")}</span>
        <span className="rounded-full bg-hover px-2 py-px font-mono text-[11px] text-muted">{done}/{todos.length}</span>
        {!open && current && <span className="min-w-0 flex-1 truncate text-xs text-muted">{current.content}</span>}
        <span className="ml-auto flex items-center gap-2">
          <span className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-hover sm:block">
            <span className="block h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${pct}%` }} />
          </span>
          <ChevronDown size={14} className={`text-subtle transition ${open ? "" : "-rotate-90"}`} />
        </span>
      </button>
      {open && (
        <ul className="space-y-0.5 border-t border-line px-4 py-2.5">
          {todos.map((x, i) => (
            <li key={i} className="flex items-start gap-2.5 py-[3px] text-[13.5px] leading-5">
              <span className="mt-px shrink-0"><Mark status={live || x.status === "completed" ? x.status : "pending"} /></span>
              <span className={x.status === "completed" ? "text-muted" : x.status === "in_progress" ? "font-medium text-fg" : "text-fg/85"}>
                {x.content}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default memo(TodoList);
