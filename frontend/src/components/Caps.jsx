import { Brain, Eye, EyeOff, Wrench } from "lucide-react";
import { useT } from "../lib/store";

// Capability badges from the provider's API (tools / vision / thinking). Tool use always works: natively when the
// model supports function calling, otherwise through AI IQ 300's text protocol.
export function CapBadges({ m, size = "md" }) {
  const t = useT();
  if (!m) return null;
  const cls = size === "sm" ? "px-1.5 py-px text-[10px] gap-1" : "px-2 py-1 text-xs gap-1";
  const native = m.native_tools ?? m.tools !== false;
  return (
    <>
      <span title={t(native ? "cap_tools_native_desc" : "cap_tools_text_desc")}
        className={`flex items-center rounded-lg ${cls} ${native ? "bg-ok/10 text-ok" : "bg-hover text-muted"}`}>
        <Wrench size={size === "sm" ? 10 : 12} />{t(native ? "cap_tools_native" : "cap_tools_text")}
      </span>
      {m.vision != null && (
        <span title={t(m.vision ? "cap_vision_desc" : "cap_no_vision_desc")}
          className={`flex items-center rounded-lg ${cls} ${m.vision ? "bg-violet-500/10 text-violet-500" : "bg-hover text-subtle"}`}>
          {m.vision ? <Eye size={size === "sm" ? 10 : 12} /> : <EyeOff size={size === "sm" ? 10 : 12} />}{t(m.vision ? "cap_vision" : "cap_no_vision")}
        </span>
      )}
      {m.thinking && (
        <span title={t("cap_thinking_desc")} className={`flex items-center rounded-lg bg-accent-soft text-accent ${cls}`}>
          <Brain size={size === "sm" ? 10 : 12} />{t("cap_thinking")}
        </span>
      )}
    </>
  );
}

// Compact icon row for dense lists (model picker).
export function CapIcons({ m }) {
  const t = useT();
  if (!m) return null;
  return (
    <span className="flex shrink-0 items-center gap-1 text-subtle">
      {m.tools && <Wrench size={11} className="text-ok" title={t("cap_tools_native")} />}
      {m.vision && <Eye size={11} className="text-violet-500" title={t("cap_vision")} />}
      {m.thinking && <Brain size={11} className="text-accent" title={t("cap_thinking")} />}
    </span>
  );
}

export const capsHint = (t, m) => [m.tools && t("cap_tools_native"), m.vision && t("cap_vision"), m.thinking && t("cap_thinking")]
  .filter(Boolean).join(" · ");
