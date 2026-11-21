// Normalized provider/agent error codes (backend llm/providers.py classify_error) -> translated message.
// The raw provider message stays available as detail.
const KNOWN = new Set([
  "missing_credentials", "missing_account", "auth", "forbidden", "terms", "payment", "quota", "rate_limit", "context_length", "no_tools",
  "model_not_found", "not_found", "bad_request", "too_large", "timeout", "unavailable", "overloaded", "server",
  "bad_gateway", "moderation", "disabled", "unknown_provider", "bad_model", "empty", "internal", "load_failed",
  "provider", "http", "request", "network", "unknown_kind", "plan_required",
]);

// A service test's raw error (search engines, maps, image and photo services answer in English, with HTTP codes)
// -> one of the codes above (or svc_*), so the user reads it in the app's language; the raw text stays as detail.
const SERVICE_RULES = [
  [/exceeded your current quota|quota|credit|billing|insufficient.?balance|limit reached|monthly limit/i, "quota"],
  [/\b429\b|rate.?limit|too many requests/i, "rate_limit"],
  [/blocked|bot check|captcha|anomaly|challenge/i, "svc_blocked"],
  [/account id is not set|account.?id.*(missing|not set)/i, "missing_account"],
  [/no key saved|key missing|not configured|missing api key|missing.*key/i, "missing_credentials"],
  [/\b401\b|unauthori[sz]ed|invalid.*(key|token)|api key not valid/i, "auth"],
  [/\b402\b|payment required/i, "payment"],
  [/\b403\b|forbidden|permission denied|not enabled/i, "forbidden"],
  [/\b404\b|not found/i, "not_found"],
  [/\b5\d\d\b|bad gateway|service unavailable|internal server error/i, "server"],
  [/timed? ?out|timeout/i, "timeout"],
  [/connecterror|getaddrinfo|name or service|connection (refused|reset)|network/i, "unavailable"],
  [/no results|no photo|no picture|nothing found/i, "svc_empty"],
];

// What a provider's own (English) message means, in the app's language: the specific cause behind a generic code
// ("high demand" behind 503, a per-minute limit behind 429...). The raw text stays under "technical detail".
const PROVIDER_HINTS = [
  [/high demand|currently experiencing|spikes in demand|temporarily overloaded|server is busy|overloaded_error/i, "hint_high_demand"],
  [/per.?minute|requests per min|rpm|tokens per min|tpm|too many requests|rate.?limit/i, "hint_rate_minute"],
  [/per.?day|daily|requests per day|rpd|free tier.*(limit|quota)|exceeded your current quota|RESOURCE_EXHAUSTED/i, "hint_quota_daily"],
  [/free GPU quota|ZeroGPU|gpu quota/i, "hint_gpu_quota"],
  [/insufficient.?balance|payment required|credit|billing/i, "hint_payment"],
  [/not found for API version|is not supported for (generateContent|predict)|model .*not found|no such model/i, "hint_model_missing"],
  [/no longer available|deprecated|retired/i, "hint_model_retired"],
  [/timed? ?out|timeout|deadline/i, "hint_timeout"],
  [/safety|blocked|moderation|content policy/i, "hint_safety"],
  [/api key not valid|invalid api key|unauthori[sz]ed|permission denied/i, "hint_auth"],
];
export function providerHint(t, message) {
  const hit = PROVIDER_HINTS.find(([re]) => re.test(String(message || "")));
  return hit ? t(hit[1]) : "";
}

export function serviceError(t, message) {
  const raw = String(message || "");
  const hit = SERVICE_RULES.find(([re]) => re.test(raw));
  const code = hit ? hit[1] : "";
  const title = !code ? t("service_test_failed") : code.startsWith("svc_") ? t(code) : t(`err_${code}`);
  return { code, title, detail: raw };
}

export function errorText(t, code, message) {
  const title = KNOWN.has(code) ? t(`err_${code}`) : t("err_generic");
  return { title, detail: message || "" };
}

// The app's own action record ("[Tool actions in this turn ...]") that a model sometimes copies into its text: the
// whole line goes (its JSON has brackets of its own, so "up to the first ]" left the rest visible).
export const ACTION_ECHO = /[ \t]*\[Tool actions in this turn[^\n]*\n?/g;
export const stripActionEcho = (s) => (s || "").replace(ACTION_ECHO, "").trim();

// A failed tool step's English output (written for the model) -> one line in the app's language above it.
const TOOL_RULES = [
  [/snippet was not found|No edit (given|found)|matches \d+ places|occurs \d+ times/i, "te_edit"],
  [/^not found:|no such (file|folder)|does not exist|cannot find path|ENOENT/im, "te_missing"],
  [/is not installed or not on PATH|not recognized as|command not found/i, "te_program"],
  [/port \d+ is already in use|EADDRINUSE/i, "te_port"],
  [/Same call as before|already ran this exact call/i, "te_repeat"],
  [/placeholders instead of real text/i, "te_placeholder"],
  [/is a binary format/i, "te_binary"],
  [/MCP .* needs |Missing required argument/i, "te_args"],
  [/download failed|HTTP [45]\d\d/i, "te_download"],
  [/DENIED|not available for this request|switched off for this task|tools are paused/i, "te_blocked"],
  [/exit_code=-?[1-9]\d*|state=failed|Traceback|Error:/i, "te_command"],
];

export function toolErrorLine(t, detail) {
  const hit = TOOL_RULES.find(([re]) => re.test(String(detail || "")));
  return hit ? t(hit[1]) : "";
}
