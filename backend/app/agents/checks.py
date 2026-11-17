"""How a request and a reply are read: reply language, intents (small talk, work, web, browser...), tool groups,
and the checks that keep weak models honest (code printed instead of run, promises, false file claims,
missing deliverables). Moved out of orchestrator.py; it re-exports every name."""
from __future__ import annotations

import json
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


def _extend(rx: re.Pattern, intent: str, wrap: str = "{}") -> re.Pattern:
    alt = intent_alt(intent)
    return re.compile(f"(?:{rx.pattern})|{wrap.format('(?:' + alt + ')')}", rx.flags) if alt else rx


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
    "design": {"stock_photo", "web_screenshot", "generate_image"},
    "browser": set(BROWSER_TOOLS),
    "places": {"places", "my_location"},
    "docs": {"make_doc", "read_document"},
    "memory": {"remember", "save_catalog"},
    "project": {"impact", "symbols"},
    "team": {"team", "ask_model"},
    "mcp": {"mcp"},
    "mcp_setup": {"mcp_add"},
    "media": {"inspect_media", "speech_to_text", "text_to_speech", "generate_image"},
    "system": {"system_info"},
}
GROUPED = set().union(*GROUP_TOOLS.values())
GROUP_WORDS = {
    "system": re.compile(r"donan[ıi]m|sistem\s*(bilgi|[öo]zellik)|bilgisayar[ıi]m|pc'?\s*(m|nin|imin)|[öo]zellikler|"
                         r"i[şs]lemci|ekran\s*kart|anakart|\bram\b|bellek|\bgpu\b|\bcpu\b|\bvram\b|disk|hardware|specs?\b|"
                         r"system\s*info|my\s*(pc|computer|machine)|processor|graphics\s*card|motherboard", re.I),
    "places": re.compile(
        r"yak[ıi]n|nerede|harita|konum|mekan|restoran|kafe|cafe|otel|eczane|ma[ğg]aza|adres|semt|il[çc]e|mahalle|"
        r"\bnear|\bmap|location|venue|restaurant|hotel|pharmacy|store|address|place|rakip|competitor", re.I),
    "docs": re.compile(r"pdf|word|docx|excel|xlsx|pptx|powerpoint|sunum|belge|d[öo]k[üu]man|rapor|tablo|slayt|"
                       r"document|report|spreadsheet|presentation|slide", re.I),
    "memory": re.compile(r"hat[ıi]rla|unutma|her\s*zaman|bundan\s*sonra|kural|remember|always|from\s*now\s*on|rule|"
                         r"skill|yetenek|ajan|agent|katalog|catalog", re.I),
    "team": re.compile(r"tak[ıi]m|ekip|paralel|ajanlar|ba[şs]ka\s*model|team|parallel|agents|another\s*model|"
                       r"b[üu]y[üu]k\s*proje|kapsaml[ıi]|large\s*project", re.I),
    "project": re.compile(r".", re.S),  # a project chat: always (availability decides)
    "mcp": re.compile(r".", re.S),
    "design": RULE_TOPICS["design"][0],
    "mcp_setup": re.compile(r"\bmcp\b|model\s*context\s*protocol|ara[çc]\s*sunucu|tool\s*server", re.I),
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
ACTION_ECHO = re.compile(r"\s*\[Tool actions in this turn[^:\]]*:[^\]]*\]\s*")
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
        hints.append("system_info returns this computer's hardware and OS in one call")
    if DELIVER_VERB.search(request):
        for rx, _exts, kind in DELIVERABLES:
            if rx.search(request):
                hints.append(f"make the .{kind} with make_doc (type=\"{kind}\", path=\"name.{kind}\", content as "
                             "Markdown/HTML) - no fpdf/reportlab/python-docx script")
                break
    return f"\n[Tool hint: {'; '.join(hints)}.]" if hints else ""


def missing_deliverables(request: str, answer: str, root: Path, since: float) -> list[str]:
    """What the answer presents as produced but is not on disk: a requested file kind no file of this task has, and
    output files the answer names that do not exist. Empty for questions and how-to answers."""
    if not WORK.search(request) or HOWTO.search(request) or not DELIVER_VERB.search(request):
        return []
    out = []
    for rx, exts, kind in DELIVERABLES:
        if rx.search(request) and not workspace.files_since(root, exts, since - 2):
            out.append(f"*.{kind}")
    prose = re.sub(r"https?://\S+", " ", FENCE.sub(" ", answer))
    names = {Path(n.replace("\\", "/")).name: n for n in CLAIMED_FILE.findall(prose)}
    if names:
        there = {Path(p).name.lower() for p in workspace.files_since(root, (), 0, set(names))}
        out += [n for base, n in names.items() if base.lower() not in there and base not in request]
    return out[:4]


FOREIGN_SCRIPT = re.compile(r"[\u0370-\u03ff\u0400-\u04ff\u0590-\u06ff\u0900-\u097f\u0e00-\u0e7f"
                            r"\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
TRANSLATE_HINT = re.compile(r"çevir|tercüme|translat|übersetz|tradu|翻译|翻訳|перевед", re.I)
LATIN_LANGS = {"tr", "en", "de", "fr", "es", "it", "pt", "nl"}

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

__all__ = ['NOT_FOUND', 'LANG_NAMES', 'SCRIPTS', 'TR_CHARS', 'TR_WORDS', 'EN_WORDS', '_CJK', '_load_intents', 'INTENTS', 'intent_alt', '_extend', '_lang_rx', 'LANG_WORD_RX', '_lang_counts', 'reply_language', 'SMALL_TALK', 'ACTION', 'WORK', 'QUESTION', 'CORE_TOOLS', 'WEB_WORDS', 'GROUP_TOOLS', 'GROUPED', 'GROUP_WORDS', 'tool_groups', 'STRONG_BROWSER', 'BROWSER_WORDS', 'CODE_NOT_RUN', 'HOWTO', 'SHELL_FENCES', 'FENCE', 'CMD_START', 'fenced_commands', 'is_small_talk', 'FILE_NAME', '_unread_files', 'CURRENT_INFO', 'needs_research', 'is_knowledge_question', 'ANNOUNCE', 'PROMISE', 'VISUAL_ASK', 'is_promise', 'is_announcement', 'FILE_CLAIM', 'ACTION_ECHO', 'CHANGE_REQUEST', 'CHANGE_CLAIM', 'FILE_EDIT_ASK', 'FILE_REF', 'DELIVER_VERB', 'DELIVERABLES', 'CLAIMED_FILE', '_shown_files', 'tool_hint', 'missing_deliverables', 'FOREIGN_SCRIPT', 'TRANSLATE_HINT', 'LATIN_LANGS', 'CONTINUE_WORDS', 'wrong_language', '_LANG_FILES', 'ui_text', 'think_reply_reminder', 'language_rule']
