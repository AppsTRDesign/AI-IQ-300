import { Toggle, inputCls } from "./ui";
import Select from "./Select";
import { useT } from "../lib/store";

// The arguments of an MCP tool as form fields, from its input schema: text / number inputs, a toggle for booleans,
// a list for enums, JSON for objects and arrays. Used by Settings > MCP > Try and by the composer's MCP tool chip.

const complex = (p) => ["object", "array"].includes(p?.type) || (!p?.type && !p?.enum);

// the form values as the tool's arguments (numbers as numbers, JSON parsed, empty fields left out)
export function argsFromVals(schema, vals) {
  const out = {};
  for (const [k, p] of Object.entries(schema?.properties || {})) {
    const v = vals?.[k];
    if (v === undefined || v === "") continue;
    if (p.type === "number" || p.type === "integer") out[k] = Number(v);
    else if (p.type === "boolean") out[k] = !!v;
    else if (complex(p)) { try { out[k] = JSON.parse(v); } catch { out[k] = v; } }
    else out[k] = v;
  }
  return out;
}

// arguments back into form values (a pasted / edited message keeps what was filled in)
export function valsFromArgs(schema, args) {
  const out = {};
  for (const [k, v] of Object.entries(args || {})) {
    const p = schema?.properties?.[k];
    out[k] = typeof v === "object" && v !== null ? JSON.stringify(v) : p?.type === "boolean" ? !!v : String(v);
  }
  return out;
}

export const missingArgs = (schema, vals) => (schema?.required || []).filter((k) => vals?.[k] === undefined || vals?.[k] === "");

export function McpArgFields({ schema, vals, onChange, compact = false }) {
  const t = useT();
  const props = schema?.properties || {};
  const req = new Set(schema?.required || []);
  const set = (k, v) => onChange({ ...vals, [k]: v });
  if (!Object.keys(props).length) return <p className="text-xs text-subtle">{t("mcp_no_args")}</p>;
  return (
    <div className={compact ? "grid gap-2 sm:grid-cols-2" : "space-y-3"}>
      {Object.entries(props).map(([k, p]) => (
        <label key={k} className={`block min-w-0 ${compact && complex(p) ? "sm:col-span-2" : ""}`}>
          <span className="mb-1 flex items-center gap-1.5 text-[12.5px] font-medium"><span className="font-mono">{k}</span>
            {req.has(k) && <span className="text-danger">*</span>}
            <span className="font-mono text-[10.5px] font-normal text-subtle">{p.type || "json"}</span></span>
          {p.enum ? (
            <Select value={vals[k] ?? ""} onChange={(v) => set(k, v)} options={[{ id: "", label: "—" }, ...p.enum.map((x) => ({ id: String(x), label: String(x) }))]} />
          ) : p.type === "boolean" ? (
            <Toggle checked={!!vals[k]} onChange={(v) => set(k, v)} />
          ) : complex(p) ? (
            <textarea rows={compact ? 2 : 3} className={`${inputCls} font-mono text-[12.5px]`} value={vals[k] ?? ""} placeholder={p.type === "array" ? "[...]" : "{...}"}
              onChange={(e) => set(k, e.target.value)} />
          ) : (
            <input className={`${inputCls} ${compact ? "!py-1.5 text-[13px]" : ""}`} type={p.type === "number" || p.type === "integer" ? "number" : "text"} value={vals[k] ?? ""}
              placeholder={p.description ? String(p.description).slice(0, 120) : ""} title={p.description || ""} onChange={(e) => set(k, e.target.value)} />
          )}
        </label>
      ))}
    </div>
  );
}
