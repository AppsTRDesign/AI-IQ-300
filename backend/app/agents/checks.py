"""How a request and a reply are read: reply language, intents (small talk, work, web, browser...), tool groups,
and the checks that keep weak models honest (code printed instead of run, promises, false file claims,
missing deliverables). Moved out of orchestrator.py; it re-exports every name."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from .. import workspace
from ..tools.browser_tools import BROWSER_TOOLS
from .prompts import *  # noqa: F401,F403
from .prompts import RULE_TOPICS

# Language names for the reply-language rule.
LANG_NAMES = {"tr": "Turkish (Türkçe)", "en": "English", "de": "German (Deutsch)", "fr": "French (Français)",
              "es": "Spanish (Español)", "it": "Italian (Italiano)", "pt": "Portuguese (Português)",
              "nl": "Dutch (Nederlands)", "ar": "Arabic (العربية)", "fa": "Persian (فارسی)", "ru": "Russian (Русский)",
              "uk": "Ukrainian (Українська)", "zh": "Chinese (中文)", "ja": "Japanese (日本語)", "ko": "Korean (한국어)",
              "el": "Greek (Ελληνικά)", "he": "Hebrew (עברית)", "hi": "Hindi (हिन्दी)", "th": "Thai (ไทย)"}
# Writing systems that identify a language on their own (checked before the Latin-script heuristics).
SCRIPTS = [("ja", r"[\u3040-\u30ff]"), ("ko", r"[\uac00-\ud7af]"), ("zh", r"[\u4e00-\u9fff]"),
           ("ar", r"[\u0600-\u06ff]"), ("ru", r"[\u0400-\u04ff]"), ("el", r"[\u0370-\u03ff]"),
           ("he", r"[\u0590-\u05ff]"), ("th", r"[\u0e00-\u0e7f]"), ("hi", r"[\u0900-\u097f]")]
# Case-sensitive on purpose: with re.I, "İ" would match every "i"/"I" and English would look Turkish.
TR_CHARS = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
TR_WORDS = re.compile(r"\b(merhaba|selam|nasıl|nasılsın|bana|bir|ve|ile|için|mısın|misin|musun|yap|yaz|oluştur|kur|"
                      r"neden|nedir|lütfen|teşekkür|evet|hayır|şunu|bunu|dosya|klasör|araştır|ben|sen|bu|şu|ne|var|"
                      r"yok|gibi|daha|çok|olarak|olan|sana|size|kodu|kod)\b", re.I)
EN_WORDS = re.compile(r"\b(the|and|you|your|with|this|that|there|here|is|are|was|be|to|of|in|on|for|please|what|how|"
                      r"why|who|create|write|make|build|can|could|would|should|thanks|hello|hi|i|i'm|am|it|my|me)\b", re.I)


# Intent words of every other language (agents/intents.json, plus "ai_intents" in any languages/<code>.json): the
# Turkish/English patterns below are extended with them, so a German, Arabic or Chinese request opens the same tools,
# gets the same checks and is detected the same way. A new language file can bring its own words.
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


def _load_intents() -> dict[str, dict[str, list[str]]]:
    from ..config import LANG_DIR
    out: dict[str, dict[str, list[str]]] = {}
    sources = [Path(__file__).with_name("intents.json")] + sorted(LANG_DIR.glob("*.json"))
    for f in sources:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if f.parent == LANG_DIR:
            data = {k: {f.stem: v} for k, v in (data.get("ai_intents") or {}).items() if isinstance(v, list)}
        for intent, langs in data.items():
            if intent.startswith("_") or not isinstance(langs, dict):
                continue
            for code, words in langs.items():
                out.setdefault(intent, {}).setdefault(code, [])
                out[intent][code] += [w for w in words if isinstance(w, str) and w.strip()]
    return out


INTENTS = _load_intents()


def intent_alt(intent: str, skip: tuple = ("tr", "en")) -> str:
    """One regex alternation of an intent's words in all languages except `skip` (word starts; CJK anywhere)."""
    parts = []
    for code, words in (INTENTS.get(intent) or {}).items():
        if code in skip:
            continue
        for w in words:
            w = re.escape(w.lower()).replace(r"\ ", r"\s+")
            parts.append(w if _CJK.search(w) else r"(?<!\w)" + w)
    return "|".join(sorted(set(parts), key=len, reverse=True))


class _LangRx:
    """A Turkish / English pattern plus the same intent's words of other languages, which are tried only when the
    text is not Turkish or English: their word starts hit our own words ("bild" = picture in German matched
    "bildiren" in a Turkish request and the app asked for a chart nobody wanted)."""

    def __init__(self, base: re.Pattern, foreign: re.Pattern):
        self.base, self.foreign = base, foreign
        self.pattern, self.flags = f"(?:{base.pattern})|{foreign.pattern}", base.flags

    @staticmethod
    def _native(text: str) -> bool:
        """The text is Turkish or English (the app's own language detector)."""
        s = (text or "")[:3000]
        lang = reply_language(s, "xx")
        if lang == "tr":
            return True
        return lang == "en" and _lang_counts(s)[1] > 0  # really English words, not a short foreign greeting

    def _pick(self, text: str) -> re.Pattern:
        return self.base if self._native(text) else re.compile(self.pattern, self.flags)

    def search(self, text, *a):
        return self.base.search(text, *a) or (None if self._native(text) else self.foreign.search(text, *a))

    def finditer(self, text, *a):
        return self._pick(text).finditer(text, *a)

    def findall(self, text, *a):
        return self._pick(text).findall(text, *a)

    def sub(self, repl, text, *a, **k):
        return self._pick(text).sub(repl, text, *a, **k)

    def match(self, text, *a):
        return self._pick(text).match(text, *a)


def _extend(rx: re.Pattern, intent: str, wrap: str = "{}"):
    alt = intent_alt(intent)
    return _LangRx(rx, re.compile(wrap.format("(?:" + alt + ")"), rx.flags)) if alt else rx


def _lang_rx(code: str, words: list[str]) -> re.Pattern:
    """Common words (whole) plus the language's intent stems (word starts) - a short greeting still counts."""
    stems = {w.lower() for i, langs in INTENTS.items() if i != "lang_words" for w in langs.get(code, [])}
    alt = "|".join(sorted({re.escape(w) for w in words}, key=len, reverse=True))
    stem_alt = "|".join(sorted({re.escape(s).replace(r"\ ", r"\s+") for s in stems}, key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:(?:" + alt + r")(?!\w)" + (f"|(?:{stem_alt})" if stem_alt else "") + ")", re.I)


LANG_WORD_RX = {code: _lang_rx(code, words) for code, words in (INTENTS.get("lang_words") or {}).items()}


def _lang_counts(text: str) -> tuple[int, int]:
    sample = re.sub(r"```.*?```|`[^`]*`|https?://\S+|[\w./\\-]+\.\w{1,5}\b", " ", text or "", flags=re.S)
    tr = len(TR_CHARS.findall(sample)) + 2 * len(TR_WORDS.findall(sample))
    return tr, len(EN_WORDS.findall(sample))


def reply_language(text: str, ui_lang: str | None) -> str:
    """The language of the user's latest message (fallback: the UI language)."""
    sample = re.sub(r"```.*?```|`[^`]*`", " ", text or "", flags=re.S)
    letters = max(1, len(re.findall(r"\w", sample)))
    for code, pattern in SCRIPTS:
        if len(re.findall(pattern, sample)) / letters > 0.3:
            if code == "ru" and ui_lang == "uk":
                return "uk"
            if code == "ar" and ui_lang == "fa":
                return "fa"
            return code
    tr, en = _lang_counts(text)
    # Other Latin-script languages (German, French, Spanish, Italian, Portuguese, Dutch) by their common words.
    clean = re.sub(r"```.*?```|`[^`]*`|https?://\S+", " ", text or "", flags=re.S)
    others = {code: len(rx.findall(clean)) for code, rx in LANG_WORD_RX.items()}
    if others:
        best = max(others, key=others.get)
        if others[best] >= 2 and others[best] > 1.3 * max(tr, en) and list(others.values()).count(others[best]) == 1:
            return best
    if tr > en:
        return "tr"
    if en > tr:
        return "en"
    return ui_lang or "tr"


SMALL_TALK = re.compile(
    r"^\W*(merhaba|selam(lar)?|günaydın|iyi (akşamlar|geceler|günler)|nasılsın(ız)?|naber|ne haber|kimsin|"
    r"sen kimsin|kendini tanıt\w*|bana kendini tanıt\w*( mısın)?|(bana )?kendinden (biraz )?bahse?\w*|"
    r"(sen )?(kaç yılında|ne zaman|hangi yıl\w*) (modellen|eğitil|geliştiril|yapıl|üretil)\w*|(sen )?hangi modelsin|"
    r"seni kim (yaptı|geliştirdi|eğitti|üretti)|"
    r"(neler|ne) yapabilirsin|teşekkür(ler| ederim)?|sağ ?ol|eyvallah|"
    r"hello|hi|hey|good (morning|evening|night)|how are you|who are you|what are you|introduce yourself|"
    r"tell me about yourself|what can you do|"
    r"thanks|thank you)\b[\w\s,.!?']{0,60}$", re.I)
ACTION = re.compile(r"\b(oluştur|yaz|kur|çalıştır|araştır|ara|sil|düzenle|create|write|build|run|search|delete|"
                    r"edit|install|make|fix|list)\b", re.I)
# Words that ask for work on the computer or the web (stems: Turkish suffixes vary).
WORK = re.compile(r"\b(oluştur|yaz|kur|çalıştır|araştır|ara|bul|sil|düzenle|yap|hazırla|ekle|kaydet|indir|güncelle|"
                  r"düzelt|test|başlat|derle|dosya|klasör|proje|uygulama|site|belge|excel|word|pdf|tablo|kod|script|"
                  r"web|internet|güncel|create|write|build|run|search|delete|edit|install|make|fix|list|generate|add|"
                  r"save|update|setup|deploy|start|file|folder|project|app|code|document|look up|find|latest|current)",
                  re.I)
QUESTION = re.compile(r"\?\s*$|\b(nasıl|neden|nedir|ne demek|hangi|kaç|mı|mi|mu|mü|how|why|what|which|when|who)\b", re.I)

# The browser_* tools add ~2500 tokens of definitions to every prompt (14 tools): offered only when the task looks
# like it needs them, so an ordinary file/code/chat task - especially on a small local model's tight context window -
# is not crowded out by tools it will never call. See CODE_NOT_RUN above for the failure this also guards against.
# Dynamic tool offer: the core set always, each group only when the conversation is about it (or the model asks for
# it with need_tools). Group names are what need_tools accepts.
CORE_TOOLS = {"read_file", "list_dir", "search_code", "write_file", "edit_file", "delete_file", "run", "start", "stop",
              "todo", "use_skill", "need_tools", "browser_check"}
WEB_WORDS = re.compile(
    r"ara[şs]t[ıi]r|internet|\bweb\s*(de|den|te|ten|search)|google|g[üu]ncel|son\s*s[üu]r[üu]m|fiyat|haber|kaynak|"
    r"https?://|www\.|sitesin|sitede|siteyi|\bkur\b|kurulu|kurul|y[üu]kle|indir|install|download|setup|"
    r"s[üu]r[üu]m[üu]?\b|version|winget|choco|brew\b|apt\b|"
    r"\bara\b|aray|\bbul\b|link|search|look\s*up|latest|current|price|news|source|docs?\b|documentation|"
    r"d[öo]k[üu]mantasyon|ekran\s*g[öo]r[üu]nt|screenshot|pdf|kar[şs][ıi]la[şs]t[ıi]r|compare|review|yorum", re.I)
GROUP_TOOLS = {
    "web": {"web_search", "research", "fetch_url", "web_screenshot", "read_document"},
    "design": {"stock_photo", "web_screenshot", "generate_image", "render_diagram"},
    "browser": set(BROWSER_TOOLS),
    "places": {"places", "my_location"},
    "docs": {"make_doc", "read_document", "doc_template", "render_diagram"},
    "memory": {"remember", "save_catalog", "recall"},
    "project": {"impact", "symbols"},
    "team": {"team", "ask_model"},
    "mcp": {"mcp"},
    "google": {"google"},
    "mcp_setup": {"mcp_add", "mcp_search"},
    # "foto" opens this group, so the photo search must be offered with it (it was missing: the model then claimed
    # downloads that never happened)
    "media": {"inspect_media", "speech_to_text", "text_to_speech", "generate_image", "edit_video", "stock_photo",
              "animate_image", "generate_video", "render_diagram"},
    "system": {"system_info", "hardware_info", "software_info", "mobile_info"},
    "mobile": {"mobile_env"},
}
GROUPED = set().union(*GROUP_TOOLS.values())
# The user's own account data (answered only from a tool, never from memory)
OWN_DATA = re.compile(
    r"\b(takvim|ajanda|e-?posta|mail|gelen\s*kutu|drive|dosya|klas[öo]r|ki[şs]i|rehber|toplant[ıi]|etkinlik|randevu|"
    r"tablo|belge|depo|repo)\w*(?:[ıiuü]m|lar[ıi]m|ler[ıi]m|[ıiuü]m[ıiuü]|lar[ıi]m[ıi]|ler[ıi]m[ıi]|[ıiuü]mda|"
    r"lar[ıi]mda|ler[ıi]mde|[ıiuü]mdaki|lar[ıi]mdaki|ler[ıi]mdeki)\b|"
    r"\bmy\s+(calendar|e-?mails?|mails?|inbox|drive|files?|contacts?|meetings?|events?|sheets?|docs?|repos?|repositories)\b|"
    r"okunmam[ıi][şs]|unread", re.I)
# Actions on the connected Google account ("kendime taslak e-posta hazırla", "takvime toplantı ekle"): with Google
# connected, a text-only reply ("Taslağınız hazır") claims something that never happened in Gmail.
GOOGLE_ACT = re.compile(
    r"\b(taslak|draft)\w*\b.{0,40}\b(e-?posta|e-?mail|mail|gmail)|\b(e-?posta|e-?mail|mail|gmail)\w*\b.{0,40}\b(taslak|draft)|"
    r"\bgmail\b|\b(takvim|calendar)\w*\b.{0,40}\b(ekle|olu[şs]tur|add|create|schedule)|"
    r"\b(drive|sheets?|google\s+(docs?|sheets?|drive|calendar|takvim))\b", re.I)
GROUP_WORDS = {
    "mobile": re.compile(r"\b(android|ios|iphone|apk|ipa|flutter|react\s*native|expo|capacitor|emülatör|emulator|"
                         r"simülatör|simulator|adb|maestro)\b|mobil\s*uygulama|mobile\s*app", re.I),
    "system": re.compile(r"donan[ıi]m|sistem\s*(bilgi|[öo]zellik)|bilgisayar[ıi]m|pc'?\s*(m|nin|imin)|[öo]zellikler|"
                         r"i[şs]lemci|ekran\s*kart|anakart|\bram\b|bellek|\bgpu\b|\bcpu\b|\bvram\b|disk|hardware|specs?\b|"
                         r"system\s*info|my\s*(pc|computer|machine)|processor|graphics\s*card|motherboard|"
                         r"kurulu\s*(paket|program|mod[üu]l|yaz[ıi]l[ıi]m)|y[üu]kl[üu]\s*(paket|program)|"
                         r"installed\s*(packages?|programs?|software|modules?)|what\s*is\s*installed|"
                         r"pip\s*list|npm\s*(ls|list)\s*-g", re.I),
    "places": re.compile(
        r"yak[ıi]n|nerede|harita|konum|mekan|restoran|kafe|cafe|otel|eczane|ma[ğg]aza|adres|semt|il[çc]e|mahalle|"
        r"\bnear|\bmap|location|venue|restaurant|hotel|pharmacy|store|address|place|rakip|competitor", re.I),
    "docs": re.compile(r"pdf|word|docx|excel|xlsx|pptx|powerpoint|sunum|belge|d[öo]k[üu]man|rapor|tablo|slayt|"
                       r"document|report|spreadsheet|presentation|slide", re.I),
    "memory": re.compile(r"hat[ıi]rla|unutma|her\s*zaman|bundan\s*sonra|kural|remember|always|from\s*now\s*on|rule|"
                         r"skill|yetenek|ajan|agent|katalog|catalog|"
                         # questions about earlier work of the chat (the ledger's recall tool)
                         r"daha\s*[öo]nce|[öo]nceki|ge[çc]en\s*sefer|ne(ler)?\s*yapt[ıi]n|hangi\s*dosya|"
                         r"previous(ly)?|earlier|last\s*time|what\s*did\s*you\s*(do|make|change)|which\s*files?", re.I),
    "team": re.compile(r"tak[ıi]m|ekip|paralel|ajanlar|ba[şs]ka\s*model|team|parallel|agents|another\s*model|"
                       r"b[üu]y[üu]k\s*proje|kapsaml[ıi]|large\s*project", re.I),
    "project": re.compile(r".", re.S),  # a project chat: always (availability decides)
    "mcp": re.compile(r".", re.S),
    # offered only while Google is connected (orchestrator availability); then for any mail / file / calendar talk
    "google": re.compile(r"google|gmail|e-?posta|\bmail|mesaj|gelen\s*kutu|inbox|drive|dosya|klas[öo]r|takvim|"
                         r"calendar|toplant|etkinlik|randevu|meeting|event|sheets?|tablo|spreadsheet|docs?\b|belge|"
                         r"slides?|sunum|ki[şs]i(ler)?\b|rehber|contact|fatura|invoice|ajanda|hat[ıi]rlat|okunmam[ıi][şs]|"
                         r"unread|taslak|draft", re.I),
    "design": RULE_TOPICS["design"][0],
    "mcp_setup": re.compile(r"\bmcp\b|model\s*context\s*protocol|ara[çc]\s*sunucu|tool\s*server|entegrasyon|"
                            r"integration|connector|ba[ğg]lay[ıi]c[ıi]", re.I),
    "media": re.compile(r"resim|g[öo]rsel|foto|video|\bses\b|ses\s*kayd|klip|film|g[öo]r[üu]nt[üu]|transkript|"
                        r"deşifre|ne\s*(var|g[öo]r[üu]n)|image|photo|picture|audio|recording|transcri|seslendir|"
                        r"ses(e|ine|li|le)?\s*(ile\s*)?([çc]evir|d[öo]n[üu][şs]t[üu]r|oku)|(kad[ıi]n|erkek)\s*ses|"
                        r"sesli\s*(oku|anlat)|okut|mp3|tts\b|"
                        r"sese\s*[çc]evir|yaz[ıi]ya\s*(d[öo]k|[çc]evir)|konu[şs]ma|dublaj|altyaz|subtitle|tts\b|"
                        r"\bstt\b|speech|voice|narrat|\.(png|jpe?g|webp|gif|bmp|mp4|mov|mkv|webm|avi|mp3|wav|m4a|ogg|flac)\b", re.I),
}


def tool_groups(text: str) -> dict:
    """Group -> (tool names, trigger words); research-type questions open the web group too."""
    web = WEB_WORDS if not needs_research(text) else re.compile(r".", re.S)
    return {g: (names, {"web": web, "browser": BROWSER_WORDS}.get(g) or GROUP_WORDS.get(g))
            for g, names in GROUP_TOOLS.items()}
STRONG_BROWSER = re.compile(r"giri[şs]\s*yap|login|log\s*in|sign\s*(in|up)|kay[ıi]t\s*ol|t[ıi]kla|click|form\s*doldur|"
                            r"fill\s*(in|out)|taray[ıi]c|browser|navigate|gezin|oturum\s*a[çc]", re.I)
BROWSER_WORDS = re.compile(r"\b(siteye|siteyi|sitesine|sitesini|sitede|sayfaya|sayfay[ıi]\s*a[çc]|taray[ıi]c[ıi]|giri[şs]\s*yap|login|sign\s*in|tıkla|t[ıi]kl[ae]|"
                           r"click|form\s*doldur|buton|button|localhost|127\.0\.0\.1|web\s*sitesi|website|webpage|"
                           r"webapp|web\s*uygulamas|browser|navigate|"
                           r"test\s*et|projeyi\s*test|teste?\s*et|canlı\s*test)\b", re.I)
# A URL or "take a screenshot" alone opens the web group (fetch_url, web_screenshot). The 14 browser tools (~2K tokens
# of definitions) come with words about acting on a page, or when the model opens the group with need_tools.

# A reply that is (mostly) a fenced code block meant to install/run something, printed as text instead of actually
# called with a tool (install a package, query an API by hand, "python -c ..."): the task looks finished but nothing
# ran. Catches the common small-model failure of writing a command instead of using run/my_location/places/research.
CODE_NOT_RUN = re.compile(r"```[\s\S]{0,30}(pip3?\s+install|npm\s+(i|install|ci)|apt(-get)?\s+install|"
                          r"choco\s+install|winget\s+install|pip\s+install|python3?\s+-c\b|requests\.(get|post)\(|"
                          r"subprocess\.(run|call|popen)|curl\s+-|Invoke-WebRequest|Invoke-RestMethod)", re.I)


# A verb about work already done ("test ettin", "çalıştırdın mı", "oluşturuldu", "did you run") asks about the past,
# not for new work. Seen live: "bu sistemde çalışıyor, test ettin?" was taken for a run request, the finished answer
# (which reported earlier commands in code blocks) was thrown away and the model was told "you only printed the code".
_PAST_TAIL = re.compile(r"(?:[dt][ıiuü](?:n|n[ıiuü]z|m|k|ğ\w*|r|ysa)?|[ıiuü]?l?d[ıiuü]\w*|[ıiuü]?ld[ıiuü]\w*|m[ıiuü]ş\w*|"
                        r"il(?:di|miş)\w*)$", re.I)
_LIGHT_VERB = re.compile(r"\s+e[td](\w*)", re.I)  # Turkish "test et / kontrol et": the tense is on "et"
_PAST_EN = re.compile(r"\b(did|have|has|had|was|were)\s+(you|it|we|they|i|he|she|that|this)\s+(\w+\s+){0,2}$", re.I)
_EN_PAST_WORD = re.compile(r"(ed|ran|wrote|made|built|found|done)$", re.I)


def asks_for(rx: re.Pattern, text: str) -> bool:
    """rx (WORK, RUN_ASK...) used as a request: matches inside past-tense / perfect forms do not count."""
    for m in rx.finditer(text or ""):
        end = m.end()
        while end < len(text) and (text[end].isalnum() or text[end] == "_"):
            end += 1
        tail = text[m.end():end]
        if not tail and (lv := _LIGHT_VERB.match(text, end)):
            tail = lv.group(1)
            if not tail:
                return True  # "test et" itself is the imperative
        if tail and (_PAST_TAIL.match(tail) or _EN_PAST_WORD.search(text[m.start():end])):
            continue
        if _PAST_EN.search(text[max(0, m.start() - 40):m.start()]):
            continue
        return True
    return False


# The answer itself says a step failed / was not finished: an honest report, not a false "done". The guards that
# stop a final answer for "the last command failed" let it stand (the user saw a finished answer erased and rewritten).
ADMITS_FAILURE = re.compile(
    r"ba[şs]ar[ıi]s[ıi]z|tamamlan(ma)?mad[ıi]|tamamlanamad[ıi]|[çc]al[ıi][şs]mad[ıi]|[çc]al[ıi][şs]m[ıi]yor|yap[ıi]lamad[ıi]|"
    r"olu[şs]turulamad[ıi]|ger[çc]ekle[şs](me|e)med[ıi]|hata (ver|al)d[ıi]|bitmedi|ilerlemedi|tak[ıi]l[ıi] ?kald[ıi]|"
    r"\bfail(ed|s|ure)?\b|did(n'?t| not) (work|run|finish|complete)|could(n'?t| not)|not (completed?|finished|done)|"
    r"\bstuck\b|\bunable to\b|❌", re.I)


def admits_failure(answer: str) -> bool:
    return bool(ADMITS_FAILURE.search(answer or ""))


_OUTPUT_FENCES = {"", "text", "txt", "output", "log", "console-output", "plaintext", "stdout", "json", "md", "markdown"}


def printed_code(answer: str) -> bool:
    """The answer holds code to create / run (a tagged source block, or a command line), not just an earlier run's
    output pasted in an untagged / text block."""
    for lang, body in re.findall(r"```[ \t]*([\w+-]*)[^\n]*\n(.*?)```", answer or "", re.S):
        lang = lang.lower()
        if lang not in _OUTPUT_FENCES:
            if lang in SHELL_FENCES and not any(CMD_START.match(ln) or ln.strip().startswith("$") for ln in body.splitlines()):
                continue  # a "bash" block holding only output
            return True
        if any(ln.strip().startswith("$ ") for ln in body.splitlines()):
            return True
    return False


# "How do I ...?" asks for instructions: a command in the answer is meant to be read, not run.
HOWTO = re.compile(r"\bnas[ıi]l\b|\bhow (do|can|to|would|should)\b|\bne(yi)? yazmal|komutu (nedir|ne)\b|"
                   r"\b(explain|a[çc][ıi]kla|g[öo]ster bana)\b", re.I)
SHELL_FENCES = {"bash": "bash", "sh": "bash", "shell": "bash", "zsh": "bash", "console": "bash", "terminal": "bash",
                "powershell": "powershell", "ps": "powershell", "ps1": "powershell", "pwsh": "powershell",
                "cmd": "cmd", "bat": "cmd", "batch": "cmd", "": ""}
FENCE = re.compile(r"```[ \t]*([\w+-]*)[^\n]*\n(.*?)```", re.S)
CMD_START = re.compile(r"^\s*(?:\$\s*)?(ffmpeg|ffprobe|yt-dlp|youtube-dl|python3?|py|pip3?|npm|npx|node|git|curl|wget|"
                       r"magick|convert|pandoc|mkdir|cp|mv|copy|move|ren|rename|del|rm|ls|dir|cd|tar|zip|unzip|7z|"
                       r"choco|winget|dotnet|cargo|go|java|javac|gcc|g\+\+|make|cmake|docker|php|composer|"
                       r"Get-|Set-|New-|Remove-|Copy-|Move-|Invoke-|Start-|Expand-|Compress-)", re.I)


def fenced_commands(text: str, run_python: bool = False) -> list[tuple[str, str]]:
    """Shell commands a reply printed in code blocks (```bash ffmpeg ...```), as (shell, command) pairs to run.
    Only blocks that are commands: a shell-tagged fence, or an untagged one whose lines start with a known program.
    Python blocks only when the user asked to run something."""
    from ..tools.registry import DEFAULT_SHELL
    from ..hostinfo import git_bash
    out = []
    for lang_tag, body in FENCE.findall(text):
        tag = lang_tag.lower()
        body = body.strip()
        if not body or len(body) > 4000:
            continue
        lines = [ln for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
        if tag in ("python", "py") and run_python:
            out.append(("python", body))
            continue
        if tag not in SHELL_FENCES or not lines:
            continue
        if not CMD_START.match(lines[0]) and (tag == "" or len(lines) > 1 and not all(CMD_START.match(ln) for ln in lines)):
            continue
        body = "\n".join(ln.lstrip()[1:].lstrip() if ln.lstrip().startswith("$ ") else ln for ln in body.splitlines())
        shell = SHELL_FENCES[tag] or DEFAULT_SHELL
        if shell == "bash" and sys.platform == "win32" and not git_bash():
            shell = DEFAULT_SHELL
        out.append((shell, body))
    return out[:3]


def is_small_talk(text: str) -> bool:
    """Greetings / identity / thanks: answered in text without offering tools, so eager models cannot run commands."""
    t = text.strip()
    return len(t) <= 80 and bool(SMALL_TALK.match(t)) and not ACTION.search(t)


FILE_NAME = re.compile(r"(?<![\w/\\.-])([\w./\\-]+\.(?:txt|md|csv|json|ya?ml|xml|html?|css|js|jsx|ts|tsx|py|php|java|go|rs|"
                       r"c|cpp|h|cs|rb|sh|ps1|bat|ini|cfg|toml|log|sql))\b", re.I)


# Common failures and the other routes that fix them (any OS). A weak model retried the same command with small
# changes; these lines name the real alternatives so the next try is a different one.
ERROR_PLAYBOOK = [
    # type C:\Users\Onur GamePC\x.json: the path was split at the space ("cannot find a positional parameter that
    # accepts argument 'GamePC\...'"; cmd: "The system cannot find the path specified").
    (re.compile(r"positional parameter cannot be found that accepts argument '[^']*[\\/]|"
                r"A positional parameter cannot be found that accepts argument", re.I),
     "The path contains a space and was split into two arguments. Quote it: Get-Content -LiteralPath "
     "'C:\\Users\\Some Name\\file.json' (or read it with read_file, which needs no quoting)."),
    # npm uninstall -g pkg@latest: "Remove arguments must only contain package names"
    (re.compile(r"ERMARGS|Remove arguments must only contain package names", re.I),
     "npm uninstall takes the bare package name without a version: npm uninstall -g <name> (no @latest / @1.2)."),
    # create-expo-app --template typescript takes the npm package "typescript" as the template: the folder holds the
    # TypeScript compiler's own package.json ("author": "Microsoft Corp.", bin tsgo), not an app.
    (re.compile(r"declare exactly one bin entry named tsgo|Microsoft Corp\.", re.I),
     "This folder is not an app: it was scaffolded from the npm package 'typescript' (create-expo-app --template "
     "typescript). Delete the folder and scaffold again with `npx create-expo-app@latest <name> --template "
     "blank-typescript --yes` (expo-router tabs: --template tabs), then run commands with cwd=<name>."),
    # Windows Installer is busy (another MSI install / update runs): winget exits 1618 and every retry fails the same.
    (re.compile(r"exit code:? 1618|another installation is (already )?in progress|0x80070652|ERROR_INSTALL_ALREADY_RUNNING",
                re.I),
     "Windows Installer is locked by another installation (MSI 1618), so any MSI-based install fails until it ends. Do "
     "not retry the same winget line. Use an install that needs no MSI: Java -> mobile_env action=java (portable JDK); "
     "other tools -> their portable ZIP (winget's portable/zip package, the vendor's .zip, `npm i` / `pip install` "
     "inside the project, scoop) unpacked into the project or the user's folder and called by full path. Only if "
     "the MSI is required: wait in one command until it is free (PowerShell: while (Get-Process msiexec -EA 0 | "
     "Where-Object {$_.SessionId -ne 0}) {Start-Sleep 10}) then run winget once more."),
    # Get-ChildItem -Recurse / dir /s through node_modules hits Windows' 260-character path limit and fails.
    (re.compile(r"DirIOError|PathTooLongException|path is too long|exceeds the maximum path length", re.I),
     "A recursive listing went into node_modules and hit the Windows path-length limit. Use list_dir (it skips "
     "node_modules / .git) or search_code to find files; in a shell exclude node_modules, e.g. "
     "`git ls-files` or `Get-ChildItem -Recurse -File -Exclude node_modules` on the source folders only."),
    (re.compile(r"npm (error|ERR!) (code )?E404.*@types/", re.I | re.S),
     "That @types package does not exist: the library ships its own types (zustand, axios, expo-* ...). Install it "
     "without the @types/ package."),
    (re.compile(r"sqlite3?\b.*(ParserError|Unexpected token|missing (the )?terminator|unrecognized token|"
                r"is not recognized|syntax error)|ParserError.*sqlite", re.I | re.S),
     "SQL inside a shell command breaks on quotes, and the sqlite3 program is often not installed. Write the schema "
     "into a script and run it with its interpreter instead: write_file create_db.py (import sqlite3; con = "
     "sqlite3.connect('db.sqlite'); con.executescript('''CREATE TABLE ...'''); con.commit()) then run `python "
     "create_db.py`, or the same with PHP (new PDO('sqlite:db.sqlite'); $db->exec(...)) and `php create_db.php`."),
    (re.compile(r"is not recognized as (the name of )?a cmdlet|not recognized as an internal or external command|"
                r"command not found|: not found$|CommandNotFoundException|tanınmıyor", re.I | re.M),
     "The program is not installed or not on this shell's PATH. Check it (`Get-Command x` / `where x` / `which x`), "
     "then: install it (winget / brew / apt / pip / npm), call it by its full path, or use a built-in alternative: "
     "unzip -> `tar -xf file.zip` or Expand-Archive; wget / curl -> fetch_url url=... save=...; git clone -> fetch_url "
     "the repository ZIP (https://github.com/<owner>/<repo>/archive/HEAD.zip) with save=...; make -> run its steps."),
    (re.compile(r"cannot find path|No such file or directory|can'?t open file|does not exist|ENOENT|FileNotFoundError|"
                r"ItemNotFoundException|PathNotFound|bulunamıyor|bulunamadı", re.I),
     "A path is wrong or the file was never created. list_dir the folder and copy the exact path it shows (paths are "
     "from the working folder; a ZIP unpacks into <repo>-<branch>/). If the file is missing, create or download it "
     "first (fetch_url ... save=... really writes the file; reading a URL does not)."),
    (re.compile(r"Access is denied|Permission denied|EACCES|EPERM|UnauthorizedAccess|requires elevation|"
                r"run as administrator|erişim engellendi", re.I),
     "A permission problem: stay inside the project folder, use a user-level install (pip --user, winget --scope user, "
     "npm without -g), for a blocked PowerShell script run `powershell -ExecutionPolicy Bypass -File x.ps1`; admin "
     "rights only after asking the user."),
    (re.compile(r"gh auth login|GH_TOKEN|GITHUB_TOKEN environment variable", re.I),
     "GitHub CLI is not signed in. Do not wait for a login: search with fetch_url "
     "https://api.github.com/search/repositories?q=<words>+language:<lang>&sort=stars&per_page=10 (no key needed), "
     "and download a repository with fetch_url url=https://github.com/<owner>/<repo>/archive/HEAD.zip save=<repo>.zip."),
    (re.compile(r"unknown (flag|option|command)|unrecognized (argument|option)|invalid (option|argument)|Usage:", re.I),
     "Wrong flags for this program: read the usage text in the output (it lists the real flags) or run "
     "`<program> --help` once, then use exactly those flags; do not guess another variant."),
    (re.compile(r"EADDRINUSE|address already in use|Only one usage of each socket|port \d+ (is )?(already )?in use", re.I),
     "The port is busy: start it on another free port (or stop only the process this task started)."),
    (re.compile(r"Input redirection is not supported", re.I),
     "Windows `timeout /t N` needs a console window and fails here. To wait use `Start-Sleep -Seconds N` (PowerShell) "
     "- or better, no wait at all: the start tool already waits until a server answers, then open it with the browser "
     "tool."),
    (re.compile(r"ERR_EMPTY_RESPONSE|connection was closed unexpectedly|Bağlantı beklenmedik bir şekilde kapatıldı|"
                r"ECONNRESET|Connection reset by peer", re.I),
     "Something answers on that port but closes every connection - usually an old, broken server left from an earlier "
     "task. Do not kill processes by name: start your server on another free port and open that one."),
    (re.compile(r"ModuleNotFoundError|No module named|Cannot find module|could not find driver|Class \"?[\w\\]+\"? not "
                r"found|Call to undefined function|extension .* (missing|not loaded)", re.I),
     "A package or extension is missing: install it with the project's package manager (pip / npm / composer) inside "
     "the project, or enable the PHP extension in php.ini (`php --ini` shows the file), then run it again."),
    (re.compile(r"certificate verify failed|SSL: |CERT_|self[- ]signed certificate", re.I),
     "A TLS / certificate error: retry with the tool's own trusted source, update the CA bundle (pip install certifi), "
     "or download the file with fetch_url save=... instead."),
    (re.compile(r"timed out|timeout|took too long", re.I),
     "It ran out of time: a server or watcher must use `start`, not `run`; a long install needs a longer timeout or "
     "a smaller step; check the network once."),
]


def error_playbook(failure: str) -> str:
    """The other routes for a failed command (up to two matching kinds), or ''."""
    tail = failure[-2500:]
    hits = [tip for rx, tip in ERROR_PLAYBOOK if rx.search(tail)][:2]
    return " ".join(hits)


# A command failed because a file it names is missing (any OS, any language of the error message).
NOT_FOUND = re.compile(r"No such file|can'?t open file|cannot find|could not find|not found|does not exist|"
                       r"bulunam|mevcut de[ğg]il|bulunmuyor|ObjectNotFound|FileNotFoundError|ENOENT", re.I)


def _unread_files(text: str, root: Path, messages: list[dict]) -> list[str]:
    """Existing files the user names in this request whose content is not in the conversation yet."""
    seen = "\n".join(m.get("content") or "" for m in messages if isinstance(m.get("content"), str))
    out = []
    for name in dict.fromkeys(FILE_NAME.findall(text)):
        try:
            f = (root / name).resolve()
            if f.is_file() and root.resolve() in f.parents and f"[Attached file: {name}" not in seen:
                out.append(name)
        except OSError:
            continue
    return out[:3]


# Questions whose answer changes over time or that ask for sources: answering them from memory invents facts.
CURRENT_INFO = re.compile(r"güncel|bugün|şu an(ki)?|son (durum|haber|fiyat)|fiyat|kaç (tl|lira|dolar|euro)|döviz|"
                          r"hava durumu|haber|kaynak|\b(link|202[5-9])\b|\b(current|latest|today|price|prices|cost|"
                          r"news|weather|source|sources|cite)\b", re.I)


def needs_research(text: str) -> bool:
    return bool(CURRENT_INFO.search(text or ""))


def is_knowledge_question(text: str) -> bool:
    """A plain question that asks for no work: only read-only tools are offered, so small models cannot write
    unrequested files ("How should I start learning PHP?")."""
    t = text.strip()
    return len(t) <= 400 and bool(QUESTION.search(t)) and not WORK.search(t)


# A reply that only announces the next step ("Now I'll create the routes.") means the model stopped mid-task.
ANNOUNCE = re.compile(r"(şimdi|ardından|sonra|sıradaki|devam|now|next|then|let me|i'?ll|i will|i'm going to)\b.{0,160}"
                      r"(\w+(uyorum|üyorum|ıyorum|iyorum|ayım|eyim|acağım|eceğim)\b|let me|i'?ll|i will|going to)|"
                      r"(oluştur|yaz|ekl|kur|başl|geç|düzenl|devam ed)\w*(uyorum|üyorum|ıyorum|iyorum|ayım|eyim|acağım|"
                      r"eceğim)\W*$|:\s*$|(^|[.!]\s+)(now,? |next,? )?(let me|i'?ll|i will|i'm going to)\b[^.!?]*[.!]?\s*$",
                      re.I | re.S)


# "It is being created... / I'll start now / please wait": words that promise work. Written in a turn where no tool
# ran, nothing is happening at all - the task would end with a promise the user waits on forever.
PROMISE = _extend(re.compile(
    r"olu[şs]turuluyor|haz[ıi]rlan[ıi]yor|ekleniyor|[üu]retiliyor|ba[şs]lat[ıi]yorum|ba[şs]l[ıi]yorum|olu[şs]turuyorum|"
    r"haz[ıi]rl[ıi]yorum|\w+(aca[ğg][ıi]m|ece[ğg]im|ay[ıi]m|eyim)\b|birka[çc]\s+(saniye|dakika)|l[üu]tfen\s+bekle|"
    r"please\s+wait|\b(is|are)\s+being\s+(created|generated|prepared|added)|\bi\s*(am|'m)\s+(now\s+)?(creating|generating|"
    r"preparing|starting|working)|\bi\s*('ll|\s+will)\b|this\s+(may|might|will)\s+take|working\s+on\s+it", re.I), "announce")


# The request asks for a picture in the result (a chart, graph, image, logo...).
VISUAL_ASK = _extend(re.compile(r"grafi[kğg]|g[öo]rsel|resim|[şs]ema|diyagram|\bchart|\bgraph|\bplot\b|\bimage|\bpicture|"
                                r"\bdiagram|\bfigure\b|illustration", re.I), "visual")


def is_promise(text: str) -> bool:
    """A short reply that only says work will be / is being done (no result, no code, no question to the user)."""
    t = text.strip()
    return 0 < len(t) <= 700 and "```" not in t and not t.endswith("?") and bool(PROMISE.search(t))


def is_announcement(text: str) -> bool:
    t = text.strip()
    return 0 < len(t) <= 500 and "```" not in t and bool(ANNOUNCE.search(t))


# "I saved it to a file" although no file tool ran in this task: a hallucinated action.
FILE_CLAIM = re.compile(r"(dosya\w*|belge\w*|klasör\w*)\s+(\w+\s+){0,3}(oluştur|kaydet|yaz|hazırla)\w*(dım|dim|dum|düm|ldı|ldi)|"
                        r"(dosya|belge)\w*\s+(oluştur|kaydet|yaz|hazırla)\w*(arak|ıp|ip|up)\s+(\w+\s+){0,3}\w+(dım|dim|dum|düm|tım|tim)\b|"
                        r"(dosyaya yazdım|diske kaydettim)|\b(i('ve| have)? (created|saved|written|wrote)|"
                        r"(has|have) been (created|saved|written))\b.{0,40}\b(file|document|folder)", re.I)


# The note _history adds to earlier answers; a model that copies it into its reply is pretending to have acted.
# The whole line: its content holds JSON with its own brackets (`"photos": ["a.jpg"]`), so "up to the first ]" left
# the rest of the line visible in the chat.
ACTION_ECHO = re.compile(r"[ \t]*\[Tool actions in this turn[^\n]*(?:\n|$)")
# "I updated / ran it" in a turn where no tool ran, although the user asked for a change: a hallucinated action.
CHANGE_REQUEST = re.compile(r"düzenle|güncelle|değiştir|düzelt|ekle|kaldır|çalıştır|oluştur|yaz\b|\b(edit|update|change|fix|"
                            r"modify|add|remove|run|create|write)\b", re.I)
CHANGE_CLAIM = re.compile(r"\b\w*(güncelle|düzenle|değiştir|düzelt|ekle|kaydet|oluştur|çalıştır)\w*(dim|dım|dum|düm|tim|tım|tum|tüm)\b|"
                          r"\b\w*(güncellen|düzenlen|değiştiril|düzeltil|eklen|kaydedil|oluşturul|çalıştırıl|yazıl)\w*(di|dı|du|dü)\b|"
                          r"\bi('ve| have)? (updated|edited|modified|changed|fixed|ran|executed|created|saved)\b|"
                          r"\b(has|have) been (updated|edited|modified|changed|fixed|created|saved)\b|"
                          r"\b(is|was|were) (now )?(updated|edited|modified|changed|fixed|created|saved)\b", re.I)


# The request asks to change a file's content (not only to run or read it).
FILE_EDIT_ASK = re.compile(r"\bekle|de[ğg]i[şs]tir|d[üu]zenle|g[üu]ncelle|d[üu]zelt|kald[ıi]r|\b(add|append|insert|change|"
                           r"edit|update|modify|remove|replace|fix)\b", re.I)
FILE_REF = re.compile(r"dosya|\bfile\b|" + FILE_NAME.pattern, re.I)

# The request asks for a file of a kind as its result ("pdf rapor olarak yaz", "excel tablosu hazırla"). A final answer
# while no such file was written in this task is a false "done" (a weak model prints a script and says "created").
DELIVER_VERB = re.compile(r"olu[şs]tur|haz[ıi]rla|\byaz|\byap|kaydet|[çc][ıi]kar|d[öo]n[üu][şs]t[üu]r|aktar|[üu]ret|"
                          r"\b(create|make|generate|write|export|save|convert|build|produce|prepare)\b", re.I)
DELIVERABLES = [
    (re.compile(r"\bpdf\b", re.I), (".pdf",), "pdf"),
    (re.compile(r"\bword\b|\bdocx\b", re.I), (".docx", ".doc", ".odt"), "docx"),
    (re.compile(r"\bexcel\b|\bxlsx\b|elektronik tablo|\bspreadsheet", re.I), (".xlsx", ".xls", ".csv", ".ods"), "xlsx"),
    (re.compile(r"power\s?point|\bpptx\b|slayt|\bslides\b", re.I), (".pptx", ".odp"), "pptx"),
]
# Output files named in the answer's prose ("open donanim_raporu.pdf"): each must exist on disk.
CLAIMED_FILE = re.compile(r"(?<![\w/\\.-])([\w./\\-]*\w\.(?:pdf|docx|xlsx|pptx|png|jpe?g|gif|webp|svg|mp4|mp3|wav|"
                          r"zip|csv|html?))\b", re.I | re.U)


def _shown_files(missing: list[str]) -> str:
    """'*.pdf' (a requested kind) reads as 'PDF' for the user; file names stay as they are."""
    return ", ".join(m[2:].upper() if m.startswith("*.") else m for m in missing)


def tool_hint(request: str) -> str:
    """One line naming the made-for-the-job tool of this request (not stored). Weak models otherwise hand-write fpdf
    scripts for a PDF or locale-dependent systeminfo pipes for the PC's specs, and fail."""
    if not WORK.search(request) or HOWTO.search(request):
        return ""
    hints = []
    if GROUP_WORDS["system"].search(request):
        hints.append("system_info gives a quick overview of this computer and app; hardware_info / software_info / "
                     "mobile_info give the details (no systeminfo/wmic commands)")
    if DELIVER_VERB.search(request):
        for rx, _exts, kind in DELIVERABLES:
            if rx.search(request):
                hints.append(f"make the .{kind} with make_doc (type=\"{kind}\", path=\"name.{kind}\", content as "
                             "HTML) - no fpdf/reportlab/python-docx script")
                break
    if TODO_ASK.search(request) or len(NUMBERED_STEP.findall(request)) >= 3:
        # A weak model skipped the list even when the user asked for one: name it in the same reply as the first step.
        hints.append("start with todo (the whole list, first item in_progress) in the same reply as the first action, "
                     "and tick each item when it is done with todo advance=true (no retyped list)")
    return f"\n[Tool hint: {'; '.join(hints)}.]" if hints else ""


def request_core(text: str) -> str:
    """The user's own words of a request, for to-do items: without the app's instructions in front of them
    ("/docs PDF: [Şablon: ... make_doc template=...]" became the to-do items "/docs PDF" and "[Şablon: ..."), the
    Markdown stars and the "1.)" style of numbering."""
    t = text or ""
    t = re.sub(r"\[(?:[^\[\]]{0,40}:\s*)?[^\[\]]*(?:make_doc|doc_template|generate_video|generate_image|template=)[^\[\]]*\]", " ", t)
    t = re.sub(r"^\s*(?:/[\w-]+\s+)+", "", t)  # /docs /web-research ...
    t = re.sub(r"^\s*(?:Word|PDF|Excel|PowerPoint|HTML)\s*:\s*", "", t, flags=re.I)
    t = re.sub(r"\*\*|__", "", t)
    t = re.sub(r"(?m)(^|\s)(\d{1,2})\.\)", r"\1\2)", t)  # "1.)" -> "1)"
    return t.strip()


def request_steps(request: str) -> list[str]:
    """The steps a user wrote ("1) make x, 2) count y, 3) tell me") when they asked for a list or gave 3+ of them."""
    request = request_core(request)
    parts = [p.strip(" ,;.-") for p in re.split(r"(?:^|\s)(?:\d{1,2}[.)]|[-•])\s+", request) if p.strip(" ,;.-")]
    numbered = len(NUMBERED_STEP.findall(request))
    if numbered < 3 and not (TODO_ASK.search(request) and numbered >= 2):
        return []
    steps = parts[1:] if len(parts) > numbered else parts  # the text before "1)" is the intro, not a step
    out = []
    for s in steps[:12]:
        s = TODO_ASK.sub("", re.split(r"(?<=[.!?])\s", s)[0]).strip(" ,;.-")
        if len(s) >= 3:
            out.append(s[:90])
    return out if len(out) >= 2 else []


def plan_steps(text: str) -> list[str]:
    """A numbered plan the model wrote as text ("1. **Settings API:** ...", "2) ...") instead of calling todo: its
    items, the bold title when there is one (short enough for the list), at least 3."""
    items = re.findall(r"^\s{0,3}(?:\d{1,2}[.)])\s+(.+)$", text or "", re.M)
    out = []
    for it in items[:12]:
        m = re.match(r"\*\*(.+?)\*\*", it)
        s = (m.group(1) if m else it).strip(" :*-")
        s = re.sub(r"[*`_]+", "", s).strip(" :")
        from ..tools.agent_tools import JUNK_ITEM
        if len(s) >= 3 and not JUNK_ITEM.search(s):  # a tool tag or a command line is no plan item
            out.append(s[:90])
    return out if len(out) >= 3 else []


def _top_split(text: str, seps: re.Pattern) -> list[str]:
    """Split at the separators that are not inside parentheses."""
    parts, depth, last = [], 0, 0
    for i, ch in enumerate(text):
        depth += ch == "(" or ch == "["
        depth -= (ch == ")" or ch == "]") and depth > 0
        if depth == 0 and (m := seps.match(text, i)) and m.end() > i:
            parts.append(text[last:i])
            last = m.end()
    parts.append(text[last:])
    return [p.strip(" ,;.-\n") for p in parts if p.strip(" ,;.-\n")]


LIST_SEP = re.compile(r",\s*|;\s*|\s+(?:ve|and|ile birlikte|plus)\s+(?=\S)", re.I)


def request_parts(request: str) -> list[str]:
    """The parts of a request written as running text ("make X: a, b, c and d. Mobile friendly. Start it, test it,
    report."), for the to-do list when the model never opens one: the listed features, then each later sentence.
    3-10 items or nothing."""
    core = request_core(request or "")
    if len(NUMBERED_STEP.findall(core)) >= 2:
        return []  # a numbered request: its own numbers are the steps (request_steps), not its commas
    text = re.sub(r"\s+", " ", core).strip()
    sentences = [s for s in re.split(r"(?<=[.!?])\s+(?=[^\s])", text) if s.strip()]
    if not sentences:
        return []
    first, rest = sentences[0], sentences[1:]
    out = []
    if ":" in first[:220]:
        intro, listed = first.split(":", 1)
        items = _top_split(listed, LIST_SEP)
        if len(items) >= 2:
            out += [intro.strip()] + items  # the project itself (set-up), then its parts
        else:
            out.append(first)
    else:
        out.append(first)
    out += [s.strip(" .") for s in rest]
    tr = bool(re.search(r"[çğıöşüÇĞİÖŞÜ]", text))

    def cap(s: str) -> str:
        head = "İ" if tr and s[:1] == "i" else s[:1].upper()
        return head + s[1:90]
    out = [cap(o.strip()) for o in out if len(o.strip()) >= 3]
    return out if 3 <= len(out) <= 10 else []


TODO_ASK =re.compile(r"yap[ıi]lacak(lar)?\s*(liste|kullan)|to-?do|g[öo]rev\s*listesi|plan\s*(liste|yap|kullan)|"
                      r"task\s*list|checklist|ad[ıi]m\s*ad[ıi]m", re.I)
NUMBERED_STEP = re.compile(r"(?:^|\s)(?:\d{1,2}[.)]|[-•]\s)\s*\S", re.M)


def missing_deliverables(request: str, answer: str, root: Path, since: float) -> list[str]:
    """What the answer presents as produced but is not on disk: a requested file kind no file of this task has, and
    output files the answer names that do not exist. Empty for questions and how-to answers."""
    if not asks_for(WORK, request) or HOWTO.search(request) or not DELIVER_VERB.search(request):
        return []
    out = []
    for rx, exts, kind in DELIVERABLES:
        if rx.search(request) and not workspace.files_since(root, exts, since - 2):
            out.append(f"*.{kind}")
    prose = re.sub(r"https?://\S+", " ", FENCE.sub(" ", answer))
    # A file the answer says was NOT made ("sahne2 ve sahne3 oluşturulamadı", "failed: x.mp4") is an honest report,
    # not a claim: the lines that say so are left out (the model was told "your answer is false" for telling the truth).
    prose = "\n".join(ln for ln in prose.splitlines() if not NOT_MADE.search(ln))
    names = {Path(n.replace("\\", "/")).name: n for n in CLAIMED_FILE.findall(prose)}
    # A file the answer names must exist on disk, also when the request named it (asking for videos/x.mp4 and then
    # claiming it was made, with no such file, was exactly the false claim this check exists for).
    out += [n for n in names.values() if not _on_disk(root, n)]
    # Source files the request itself names as part of what to build (`data/mockProducts.ts`): a weak model gave up
    # after a failed install and ended with "I will write it" while not one of them existed. A path with a folder or
    # in `code` marks a file to create; a bare word like "Node.js" or "next.config" in a sentence does not.
    asked = {n.replace("\\", "/") for n in REQUESTED_SOURCE.findall(request)}
    out += [n for n in sorted(asked) if n not in out and not _on_disk(root, n)]
    # Files the request puts in a folder it names: in that folder (anywhere in the project), not just by name.
    out += [n for n in in_named_folder(request) if n not in out and not _in_folder(root, n)]
    return out[:4]


def _in_folder(root: Path, rel: str) -> bool:
    if (root / rel).is_file():
        return True
    want = tuple(fold_name(x) for x in rel.split("/"))
    skip = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".session"}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in skip]
        here = Path(d)
        if fold_name(here.name) == want[0] and any(fold_name(f) == want[-1] for f in files):
            return True
    return False


# "todo/ klasöründe ... index.html, style.css ve app.js" / "in the todo/ folder: index.html, app.js": one folder the
# request names, and files it lists by bare name, go in that folder. evren:auto wrote all three into the chat folder's
# root twice (eval web_app) and nothing told it.
REQUESTED_FOLDER = re.compile(r"(?:`|(?<![\w./\\-]))([\w.-]+)[/\\]`?\s*(?:klas[öo]r|dizin|folder|directory)", re.I)
BARE_SOURCE = re.compile(r"(?:`|(?<![\w./\\-]))([\w-]+\.(?:ts|tsx|js|jsx|py|php|dart|kt|swift|java|go|rs|vue|svelte|"
                         r"css|html?|md|json))(?=`|[\s,;:)]|\.(?:\s|$)|$)", re.I)


def in_named_folder(request: str) -> list[str]:
    folders = {m.lower() for m in REQUESTED_FOLDER.findall(request)}
    if len(folders) != 1:  # none, or several folders: which file goes where is not said
        return []
    folder = REQUESTED_FOLDER.search(request).group(1)
    return [f"{folder}/{n}" for n in dict.fromkeys(BARE_SOURCE.findall(request))]


NOT_MADE = re.compile(r"olu[şs]tur(ul)?ama|olu[şs]turulmad|[üu]retil(e)?me|[üu]retemed|yap[ıi]lamad|ba[şs]ar[ıi]s[ıi]z|"
                      r"diskte yok|mevcut de[ğg]il|kota|ba[şs]ar[ıi]l[ıi] olmad|haz[ıi]rlanamad|"
                      r"not (been )?(created|made|generated)|could ?n[o']t (be )?(create|make|generate)|failed|"
                      r"does not exist|was not (created|made)|unavailable|quota", re.I)


REQUESTED_SOURCE = re.compile(r"(?:`|(?<![\w./\\-]))((?:[\w.-]+[/\\])+[\w.-]+\.(?:ts|tsx|js|jsx|py|php|dart|kt|swift|"
                              r"java|go|rs|vue|svelte|css|html?))(?=`|[\s,;:)]|$)", re.I)


_FOLD = str.maketrans("çğıöşüÇĞİÖŞÜâîûÂÎÛ", "cgiosuCGIOSUaiuAIU")


def fold_name(name: str) -> str:
    """A file name compared without Turkish letters and case: models write alışveriş_tanitim.mp4 for the file the
    tool saved as alısveris_tanitim.mp4 (and the other way round)."""
    return name.translate(_FOLD).lower()


def real_path(root: Path, name: str) -> str | None:
    """The path on disk (from the task folder) of a file an answer names, matched exactly, then without Turkish
    letters / case. None when there is no such file or the match is not unique."""
    rel = name.replace("\\", "/")
    if (root / rel).is_file():
        return rel
    want = fold_name(Path(rel).name)
    parent = root / Path(rel).parent
    hits: list[Path] = []
    for d in ([parent] if parent.is_dir() else []) + [root]:
        try:
            hits += [p for p in d.iterdir() if p.is_file() and fold_name(p.name) == want]
        except OSError:
            pass
        if hits:
            break
    hits = list(dict.fromkeys(hits))
    if len(hits) != 1:
        return None
    try:
        return hits[0].relative_to(root).as_posix()
    except ValueError:
        return None


def fix_claimed_names(answer: str, root: Path) -> str:
    """Names of files in the answer that differ from the real file only in Turkish letters / case: replaced by the
    real path (outside code fences too: the links in the answer must open)."""
    out = answer
    for n in dict.fromkeys(CLAIMED_FILE.findall(answer)):
        rel = n.replace("\\", "/")
        if (root / rel).is_file():
            continue
        real = real_path(root, rel)
        if real and real != rel:
            out = out.replace(n, real if "/" in rel else Path(real).name)
    return out


def _on_disk(root: Path, name: str) -> bool:
    rel = name.replace("\\", "/")
    if (root / rel).is_file() or real_path(root, rel):
        return True
    base = fold_name(Path(rel).name)
    skip = {"node_modules", ".git", ".venv", "venv", "__pycache__", "vendor", ".expo", "build", "dist"}
    seen = 0
    try:  # by name anywhere in the task folder (a project subfolder), never through dependency trees
        for _d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in skip]
            seen += len(files)
            if any(fold_name(f) == base for f in files):
                return True
            if seen > 50_000:
                return True  # too big to look through: do not accuse
        return False
    except OSError:
        return True  # cannot look: do not accuse


FOREIGN_SCRIPT = re.compile(r"[\u0370-\u03ff\u0400-\u04ff\u0590-\u06ff\u0900-\u097f\u0e00-\u0e7f"
                            r"\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
TRANSLATE_HINT = re.compile(r"çevir|tercüme|translat|übersetz|tradu|翻译|翻訳|перевед", re.I)
LATIN_LANGS = {"tr", "en", "de", "fr", "es", "it", "pt", "nl"}
# Words other Latin languages share with Turkish / English (or that are international): never evidence of a drift
SHARED_WORDS = {"para", "internet", "site", "foto", "test", "com", "web", "online", "video", "radyo", "radio", "hotel",
                "otel", "menu", "normal", "total", "final", "data", "media", "plan", "program", "sistem", "system",
                "model", "format", "film", "kredi", "banka", "bank", "euro", "dolar", "dollar", "pdf", "excel", "word",
                "server", "app", "api", "code", "kod", "link", "blog", "chat", "email", "mail", "post", "start", "stop",
                "pro", "ana", "son", "her", "bir", "ben", "sen", "biz", "bu", "su", "taksi", "taxi", "bar", "kafe",
                "cafe", "auto", "oto", "mini", "maxi", "super", "alarm", "global", "lokal", "virtual", "digital"}

# Every pattern above, extended with the other languages' words (see INTENTS).
SMALL_TALK = _extend(SMALL_TALK, "small_talk", r"^\W*{}[\w\s,.!?'’،؟。！？¡¿]{{0,60}}$")
ACTION = _extend(ACTION, "work")
WORK = _extend(WORK, "work")
QUESTION = re.compile(f"(?:{QUESTION.pattern})|[？؟]\\s*$" + (f"|{intent_alt('question')}" if intent_alt("question") else ""), re.I)
WEB_WORDS = _extend(WEB_WORDS, "web")
CURRENT_INFO = _extend(CURRENT_INFO, "current")
BROWSER_WORDS = _extend(BROWSER_WORDS, "browser")
for _g in ("places", "docs", "memory", "team", "media", "design"):
    GROUP_WORDS[_g] = _extend(GROUP_WORDS[_g], _g)
# The situational rules of media and design follow the same words in every language.
for _g in ("media", "design"):
    RULE_TOPICS[_g] = (_extend(RULE_TOPICS[_g][0], _g), RULE_TOPICS[_g][1])
ANNOUNCE = _extend(ANNOUNCE, "announce", r"{}.{{0,160}}$")
CHANGE_REQUEST = _extend(CHANGE_REQUEST, "change")
TRANSLATE_HINT = _extend(TRANSLATE_HINT, "translate")
# "continue / devam et": the next task resumes an interrupted one (to-do list restored).
CONTINUE_WORDS = _extend(re.compile(r"devam|sürdür|kald[ıi][ğg][ıi]n\s+yerden|tamamla|bitir|\b(continue|resume|go\s+on|"
                                    r"keep\s+going|carry\s+on|finish)\b", re.I), "continue")


def wrong_language(text: str, lang: str, user_text: str = "") -> bool:
    """True when a reply drifted away from the reply language (code, paths and URLs ignored):
    mostly the other of TR/EN, or foreign-script words inside a Latin-script answer (e.g. a stray Chinese word)."""
    body = re.sub(r"```.*?```|`[^`]*`|https?://\S+", " ", text or "", flags=re.S)
    if lang in LATIN_LANGS and FOREIGN_SCRIPT.search(body):
        if not FOREIGN_SCRIPT.search(user_text) and not TRANSLATE_HINT.search(user_text):
            return True
    if lang not in ("tr", "en"):
        return False
    tr, en = _lang_counts(text)
    # Another Latin-script language altogether (gemma answered a Turkish chat in French): its common words win.
    # Words of two letters and words Turkish / English use too ("para", "de", "en", "internet", "site", "foto") are
    # not counted: they sent correct Turkish answers (exchange rates: "para birimi", "doviz.com") to be rewritten.
    own = tr if lang == "tr" else en
    if own < 40 and any(n >= 8 and n > 2 * own for n in (
            sum(1 for w in rx.findall(body) if len(w) > 2 and w.lower() not in SHARED_WORDS)
            for code, rx in LANG_WORD_RX.items() if code not in ("tr", "en"))):
        return True
    return (en >= 5 and en > 2 * tr) if lang == "tr" else (tr >= 8 and tr > 2 * en)


_LANG_FILES: dict[str, tuple[float, dict]] = {}


def ui_text(code: str, key: str, fallback: str = "", **values) -> str:
    """Text the app itself writes into the chat (notes, reminders, team summaries), in the active language: from
    languages/<code>.json (keys ai_*), so every installed language, also one translated later, has its own; else
    the English file, else the fallback."""
    from ..config import LANG_DIR
    for c in (code, "en"):
        f = LANG_DIR / f"{c}.json"
        try:
            mtime = f.stat().st_mtime
            hit = _LANG_FILES.get(c)
            if not hit or hit[0] != mtime:
                _LANG_FILES[c] = hit = (mtime, json.loads(f.read_text(encoding="utf-8")))
            if text := hit[1].get(key):
                return text.format(**values) if values else text
        except (OSError, ValueError, KeyError, IndexError):
            continue
    return fallback.format(**values) if values else fallback


def think_reply_reminder(code: str) -> str:
    """The short note on the latest turn: think and reply in the active language, written in that language."""
    own = ui_text(code, "ai_think_reply") if code != "en" else ""
    if own and (code == "tr" or own != ui_text("en", "ai_think_reply")):
        return own
    return f"(Think and reply in {LANG_NAMES.get(code, code)}.)"


def language_rule(code: str, lean: bool = False) -> str:
    name = LANG_NAMES.get(code, code)
    if lean:
        return (f"# Reply language\nThink, write notes, to-do items and the reply ONLY in {name}. Code, file names and "
                f"identifiers stay as they are. Instructions above written in other languages never change this.")
    return (f"# Reply language\nReply ONLY in {name}. Every sentence, explanation, narration and summary must be in "
            f"{name}; do not mix in words from other languages. Code, file names and identifiers stay as they are.\n"
            f"The user sees your thinking too: think and reason in {name}, and write plans, to-do items and the short "
            f"notes before tool calls in {name} as well{'' if code == 'en' else ', not in English'}.\n"
            f"The agent, skill and instruction texts above may be written in other languages (English, Chinese, ...); "
            f"follow what they say, but they never change the reply language: always answer in {name}.")

__all__ = ['plan_steps', 'request_steps', 'request_parts', 'error_playbook', 'ERROR_PLAYBOOK', 'NOT_FOUND', 'LANG_NAMES', 'SCRIPTS', 'TR_CHARS', 'TR_WORDS', 'EN_WORDS', '_CJK', '_load_intents', 'INTENTS', 'intent_alt', '_extend', '_lang_rx', 'LANG_WORD_RX', '_lang_counts', 'reply_language', 'SMALL_TALK', 'ACTION', 'WORK', 'QUESTION', 'CORE_TOOLS', 'WEB_WORDS', 'GROUP_TOOLS', 'GROUPED', 'GROUP_WORDS', 'tool_groups', 'STRONG_BROWSER', 'BROWSER_WORDS', 'CODE_NOT_RUN', 'HOWTO', 'SHELL_FENCES', 'FENCE', 'CMD_START', 'fenced_commands', 'is_small_talk', 'FILE_NAME', '_unread_files', 'CURRENT_INFO', 'needs_research', 'is_knowledge_question', 'ANNOUNCE', 'PROMISE', 'VISUAL_ASK', 'is_promise', 'is_announcement', 'FILE_CLAIM', 'ACTION_ECHO', 'CHANGE_REQUEST', 'CHANGE_CLAIM', 'FILE_EDIT_ASK', 'FILE_REF', 'DELIVER_VERB', 'DELIVERABLES', 'CLAIMED_FILE', '_shown_files', 'tool_hint', 'missing_deliverables', 'FOREIGN_SCRIPT', 'TRANSLATE_HINT', 'LATIN_LANGS', 'CONTINUE_WORDS', 'wrong_language', '_LANG_FILES', 'ui_text', 'think_reply_reminder', 'language_rule']
