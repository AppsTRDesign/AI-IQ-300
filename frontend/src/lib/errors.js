// Normalized provider/agent error codes (backend llm/providers.py classify_error) -> translated message.
// The raw provider message stays available as detail.
const KNOWN = new Set([
  "missing_credentials", "auth", "forbidden", "terms", "payment", "quota", "rate_limit", "context_length", "no_tools",
  "model_not_found", "not_found", "bad_request", "too_large", "timeout", "unavailable", "overloaded", "server",
  "bad_gateway", "moderation", "disabled", "unknown_provider", "bad_model", "empty", "internal", "load_failed",
  "provider", "http", "request",
]);

export function errorText(t, code, message) {
  const title = KNOWN.has(code) ? t(`err_${code}`) : t("err_generic");
  return { title, detail: message || "" };
}
