import { useT } from "../lib/store";

export function Logo({ size = 28 }) {
  return <img src="/favicon.svg" width={size} height={size} alt="AI IQ 300" className="shrink-0 rounded-[22%]" />;
}

const ROLE_KEYS = { assistant: "role_assistant", planner: "role_planner", coder: "role_coder", debugger: "role_debugger", tester: "role_tester" };

// Animated "thinking" indicator: orbiting gradient arcs + shimmering label + current agent role.
export function Thinking({ role, label, compact }) {
  const t = useT();
  if (compact) {
    return (
      <div className="fade-in mt-1 flex items-center gap-1.5 py-1" aria-label={t("working")}>
        {[0, 1, 2].map((i) => <span key={i} className="pulse-dot h-1.5 w-1.5 rounded-full bg-accent" style={{ animationDelay: `${i * 0.2}s` }} />)}
        <span className="shimmer ml-1 text-xs">{t("working")}</span>
      </div>
    );
  }
  return (
    <div className="fade-in flex items-center gap-3 py-1">
      <svg width="30" height="30" viewBox="0 0 40 40" aria-hidden>
        <defs>
          <linearGradient id="tg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#2563eb" /><stop offset=".6" stopColor="#7c3aed" /><stop offset="1" stopColor="#db2777" />
          </linearGradient>
        </defs>
        <circle cx="20" cy="20" r="16" fill="none" stroke="var(--line)" strokeWidth="3" />
        <g className="orbit"><path d="M20 4a16 16 0 0 1 16 16" fill="none" stroke="url(#tg)" strokeWidth="3.5" strokeLinecap="round" /></g>
        <g className="orbit-rev"><circle cx="20" cy="9" r="2.6" fill="#7c3aed" /></g>
        <circle cx="20" cy="20" r="4" fill="url(#tg)" className="pulse-dot" />
      </svg>
      <div className="leading-tight">
        <div className="shimmer text-[14px] font-medium">{label || t("thinking")}…</div>
        {role && <div className="text-xs text-subtle">{t(ROLE_KEYS[role] || role)}</div>}
      </div>
    </div>
  );
}
