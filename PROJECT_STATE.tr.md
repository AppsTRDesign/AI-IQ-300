# AI IQ 300 - PROJECT_STATE.md

**Türkçe** · [English](PROJECT_STATE.md)

## Proje Vizyonu
Otonom, çoklu ajan destekli, yerel ve bulut LLM'leri ile çalışan tam kapsamlı yazılım geliştirme ve komuta merkezi.

## Mevcut Durum (State)
- **Tarih:** 2026-11-17
- **Aktif Görev:** v0.12.0 tamamlandı (zayıf modeller: düz metin araç çağrıları çalıştırılır, istenen dosya diskte denetlenir, system_info, sohbet araması, model kaydı, LM Studio bellek koruması, test paketi, orkestratör bölündü); v0.11.0 tamamlandı (kapsamlı tarama: yalın istem, kopma ve model değişiminde süreklilik, modeli kapatmayan RAM / VRAM koruması, eksiksiz WebSocket yeniden bağlanma, yarış düzeltmeleri); v0.10.7 tamamlandı (toplu seçme/silme, ilk mesajda yetenekler, 14 dilde araç algılama, bölmeden yazım); v0.10.6 tamamlandı (web tasarımı + stock_photo, sayfa JS/kırık görsel testi, gerçek sayıya çapalı bağlam, yerel pencere büyütme, Markdown canlı yanıt); v0.10.5 tamamlandı (gerçek token verisi, görsel model, ayar denetimi); v0.10.4 tamamlandı (ayarlar, yerel GPU, MCP, araç zinciri, beceriler); v0.10.3 tamamlandı (canlı test: Evren auto, NVIDIA Nemotron 3 Ultra 550B, Groq)
- **Son Başarılı İşlem:** v0.10.0 — profesyonel belge motoru (Chromium PDF/HTML + KaTeX, tasarımlı DOCX/PPTX/XLSX), ayarlanabilir akış zaman aşımları ve parçalı yazma, run_state.json ile kesinti sonrası devam, paralel araç yürütme, canlı todos, çok dilli niyet tablosu, zengin mesaj kutusu, mesaj sayfalama/kopyala/sil/alıntı, sağ tık menüleri, gruplu değişiklik kartı, medya oynatıcılar, servis kartları, kota/bakiye ekranı.
- **Önceki:** v0.6 — kesintisiz orkestrasyon (devam ettirme, sessiz araç yazımında heartbeat, görev içi bağlam kırpma/özetleme, canlı bağlam sayımı, takılı adım temizliği, tekrar eden çağrı koruması, asılsız dosya iddiası koruması), todo aracı + canlı yapılacaklar listesi, otomatik yetenek algılama (use_skill), bilgi sorularında salt-okuma araçlar, arama alaka filtresi + Bing URL çözümü, canlı gruplu adımlar, model seçiciden bağlam düzenleme (ayarlarla senkron), aç/kapat popover'lar, çizim ekranı, klasör yükleme, hedef modu, belge kartları ve önizleme (xlsx/docx/pdf/pptx), kökteki gereksiz docs/ kaldırıldı.

## Proje Durumu — v0.12.0
Zayıf model turu: EVREN `auto` (bulut) ve Ollama Qwen2.5-Coder 7B (yerel CPU) ile gerçek testler; depoda 43 uçtan uca sahte model denetimi + 6 birim testi.
- **Dürüstlük denetimleri (`agents/checks.py`):**
  - `stream_parser.cli_calls`: komut satırı ya da fonksiyon biçiminde yazılmış araç çağrıları (`write_file path="a" content="..."`, `run(shell=..., command=...)`, kod bloğu içinde ya da dışında) gerçek çağrıya döner (`ai_note_cli_calls`). Yalnızca sohbet turlarında asla.
  - `missing_deliverables(request, answer, root, since)`: istenen PDF/DOCX/XLSX/PPTX (`DELIVERABLES`, `DELIVER_VERB`) görevde yazılmadıysa ya da cevapta adı geçen çıktı dosyası (`CLAIMED_FILE`) diskte yoksa model iki kez uyarılır (`deliver_retries`), sonra cevabın başına `ai_note_not_delivered_final` gelir (`flag_unresolved`).
  - `NOT_FOUND`: hiçbir aracın yazmadığı bir dosyayı adlandıran başarısız komut → web arama ipucu yerine "önce write_file ile oluştur".
  - `tool_hint(request)`: isteğe göre `system_info` / `make_doc` adını veren tek satır (saklanmaz). `TAG_PROTOCOL` doğru ve yanlış çağrı örneği gösterir.
- **Bozuk çıktı:** `providers.stream_error` "token repeat limit" hatasını `degenerate` koduna çevirir; görev döngüsü görünen metni atar, `repeat_penalty=1.18, repeat_last_n=256, temperature=0.4` ile (Ollama seçeneklerine geçer) bir kez yeniden dener, sonra `err_degenerate_detail` verir. Tek karakter tekrarından oluşan son cevap boş sayılır.
- **Yeni araç `system_info` (`tools/sysinfo.py`, `system` grubu):** işlemci, ekran kartı + VRAM, RAM modülleri, anakart, BIOS, diskler, ağ, monitörler, işletim sistemi; Windows'ta PowerShell CIM JSON, Linux'ta lscpu/lspci/lsblk/DMI, macOS'ta system_profiler; seri numaraları atılır.
- **Model kaydı (`llm/modelstats.py`, `data/model_stats.json`):** görev, başarılı, başarısız (`fallback` adımları = başka modele geçilen dahil), ilk token ve tur süresi (EMA); `GET/DELETE /api/models/stats` (`SPEED` okuma hızıyla); Ayarlar > Çoklu model > Model performansı; `multi_model.prefer_fast` açıkken (varsayılan) `router.pick` `rank_key` ile sıralar.
- **Arama:** `messages_fts` (FTS5, `unicode61 remove_diacritics 2`, tetikleyiciler, bir kerelik yeniden kurma; yoksa LIKE), `GET /api/search`, kenar çubuğunda vurgulu `ChatSearch`.
- **Hafif sohbet sayfaları:** `_light_steps` sayfalı mesaj cevaplarında 2000 karakteri aşan adım ayrıntılarını keser (`lazy: {mid, i, chars}`); `GET /api/messages/{mid}/steps/{i}`; `ActivityTrace.Step` açılınca tamamını yükler. Ekler iş parçacığında okunur/kopyalanır (`_with_attachments`).
- **LM Studio bellek koruması:** `router.reload_local(model_id, num_ctx)` (REST unload + load, yoksa `lms` CLI); görevin bellek dalında ve kritik bellekte `memguard.watchdog(..., other_local)` ile kullanılır.
- **Yeniden düzenleme ve testler:** `orchestrator.py` `prompts.py` (istem metinleri) ve `checks.py` (dil, niyetler, denetimler) olarak bölündü; adlar yeniden dışa aktarılır. `tests/e2e/run_e2e.py` + `mock_llm.py` (yalıtılmış veri klasörü, `AIIQ_TEST_PORT`), `tests/test_checks.py`.
- **Gerçek sonuçlar:** EVREN `auto`: sohbet, dosya yazma + çalıştırma, düzenleme, donanım PDF'i (`system_info` + `make_doc`, 22 sn) geçti. Qwen2.5 7B: sohbet ve donanım PDF'i geçti (CPU'da ≈7 dk); dosya görevi önce yazmadığı betiği çalıştırarak başarısız oldu (artık `NOT_FOUND` ipucu bunu karşılıyor). Ollama yeniden başlatıldıktan sonra GPU'da çalıştı (ilk token 40 sn yerine 2,8 sn) ve yalnızca "@@@@" üretti; yeni `degenerate` işleyişi bunu beş deneme ve kaydedilen çöp cevap yerine 14 sn'de açık bir hatayla durdurdu. Sağlıklı bir Qwen çalışmasında dosya görevi tekrarlanamadı.

## Proje Durumu — v0.11.0
Kapsamlı tarama (arka uç ve ön yüz, satır satır); sahte modelle (27 denetim) ve EVREN `auto`, EVREN `glm-5.3`, NVIDIA `nemotron-3-ultra-550b-a55b` ile test edildi.
- **Yalın istem:**
  - `WORK_RULES_LEAN`, `CAPABILITIES_LEAN`, `RULE_TOPICS_LEAN`, `BROWSER_GUIDE_LEAN`, `CHAT_NOTE`; `language_rule(code, lean)`; `hostinfo.prompt_section(short=)`; `tools_prompt(.., lean)` / `tool_schemas(.., lean)`.
  - `lean_for(model, info, mode)`: `agent.prompt_mode` (auto | lean | full); auto = yerel model, pencere ≤ 32K ya da `is_slow` (`data/model_speed.json`: 1K istem tokeni başına ilk tokene kadar geçen ms, `_stream_turn` içinde öğrenilir).
  - İstem sırası: değişmeyen kısım başta (kurallar, dizin, çekirdek araçlar); açılan grupların araçları, ortam ve durum sonda. Yalın istem bir grubu yalnızca o isteğin sözcükleriyle açar; tarayıcı araçları `STRONG_BROWSER` ister.
  - Sohbet yetenek hafızası: `.session/abilities.json` (`_abilities_load/_open/_save`): son 6 görevde kullanılan gruplar açık başlar; "Already open in this chat" bölümü.
  - Ölçüm (token): selamlaşma 1333 → 587; yerel dosya görevi 3361 → 1885; yerel büyük görev 4825 → 2910; bulut 4732 → 3129 ve 9809 → 6133.
- **Süreklilik:**
  - `broke()`: geçici hata, model değişimi ya da bellek rahatlatmada cevabın yazılan kısmı korunur (`CONTINUE_TAG`) ve devam ettirilir; `need_record` bir kez `_ledger(run)` ekler (`RECORD_TAG`: yazılan/okunan dosyalar, komutlar, aramalar, yapılacaklar, devralınan adımlar).
  - `_for_model(messages, model, native)`: metin protokollü modele yerel araç çağrıları etiket olarak; `thinking_blocks` / `extra` yalnızca onları yazan modele (`by`).
  - `_history`: pencereden eski mesajlar için `DIGEST_TAG` dökümü; `_overflow` + `compress(keep_recent=window)` onları özete katar. Başlangıçtaki sıkıştırma hatası artık görevi bitirmez.
  - Takımlar: kayıt noktasında `_team_board`, `ctx.team_prior`; `run_team` bitmiş parçaları atlar; `_member` model değişiminde `log` tutar.
  - Yeni denetim: dosya değişikliği istendi ama dosya değişmedi (`FILE_EDIT_ASK`, `ai_note_no_edit`).
- **Bellek koruması (`llm/memguard.py`):**
  - `reserve(total)`, `limits(total)`, `vram_limits(total)`: makineye göre ölçeklenir. `vram()`: nvidia-smi, Windows kayıt defteri + PDH sayacı (her GPU, her dil), Linux sysfs.
  - `watchdog(state, busy, notify, relief)`: uygulama önbellekleri (`release_app_memory`) → kullanılmayan modeller → küçük pencere (`shrink`, taban 8K; `_CAPS`) → bellekten çıkarma yalnızca `local_guard.emergency_unload` ile.
  - Çalışan görev `_stream_turn` içinde `pressure(model)` görür (ProviderError `memory`), yazılanı kurtarır, pencereyi küçültür ve sürer. `steady()` istekler arasında num_ctx'i sabit tutar.
  - `router.stream_chat` her yerel isteğe aynı `num_ctx`'i verir; yerel turlar `max_tokens` = kalan yer alır; Ollama `done_reason: length` → `truncated`.
- **Olaylar:** `EventBus` dolu kuyrukta hata vermez (birikim atılır + `gap`), `boot` kimliği, `last_seq`. `/ws/events`: `hello` (reset), görev başına `snapshot` (bekleyen onaylarla), `process` tekrarı, 15 sn sinyal, `_coalesce`. İstemci: `socket.js` izleyici, `store.resync`, `boot`.
- **Yarışlar:** `execute` bitişi sarıldı (`run.finishing`, RUNS her zaman boşalır); `cancel_run` tekrar çağrılabilir; `cancel_session` bekler; `orchestrator.shutdown`; `ProcessManager.stop` zaman aşımı.
- **Diğer:** mesaj dizini (`idx_messages_session`), `db.checkpoint`, ayar dosyası önbelleği (`config._read`), `changes` metin önbelleği sınırları, canlı `_Slots.limit`, `_busy_alternative` `cloud_fallback`'e uyar, hataya dayanıklı `list_all_models`, `_make_title` çağrısı düzeltildi.

## Proje Durumu — v0.10.7
- **Toplu silme:**
  - `POST /api/sessions/delete` silinen sohbetler için `delete_session` mantığını kullanır.
  - `POST /api/sessions/{sid}/messages/delete` ({ids} veya {all}) şunları temizler: messages.jsonl satırları, özet (summary_upto kapsıyorsa), run_state/partial; sohbet boşalınca `.session` klasörü.
  - store: `chatSel`/`msgSel`, `toggleSel`, `deleteChats`, `deleteMessages`, `startSelect`, `syncIds` (canlı kimlik → kayıtlı kimlik).
  - Yeniden oynatılan "done" olayı, son 3 mesajda kayıtlı aynı cevap varsa eklenmez.
  - UI: Sidebar "Seç", ChatView `Selectable` / `SelectBar`.
- **Yetenekler:**
  - `CAP_HEAD`; araçsız turda "What you can do" bölümü, beceriler ve `# Agents` listesi (görev istemlerinde de).
  - intents.json `media` ve `design` (14 dil); GROUP_WORDS ve RULE_TOPICS genişletildi.
- **Yazım:**
  - `write_file` tanımı bölmeyi istemez; `agent.split_write_chars` (0 = kapalı) bölme kuralını istemin sonuna ekler.
  - Çıktı sınırı kesmesinde `_salvage` ve append ile devam edilir; kesilen çağrının kısmi argümanları korunur.
- **Düzeltmeler:** `NO_CONF` sabit seçici (React #185); `media` ayar bölümü; hazırlık etiketinde tekrar yok.

## Proje Durumu — v0.10.6
- **Tasarım:** `RULE_TOPICS["design"]` (yapma fiili + sayfa sözcüğü birlikte geçince) ve `design` araç grubu (`stock_photo`, `web_screenshot`); `skills/web-design.md`; CAPABILITIES ve need_tools'ta `design` grubu.
- **stock_photo:** `tools/stock.py`: Openverse (ticari/değiştirilebilir lisans), sonra Wikimedia Commons. Pillow ile 1600 px JPEG; klasör `images/`; yazar/lisans/kaynak döner.
- **Sayfa testi:** `shot.capture` pageerror, console error, requestfailed, HTTP ≥400 ve kırık `<img>` (naturalWidth 0) toplar; `web_screenshot` sonucunda "Problems found" listesi.
- **Bağlam:** Ollama usage `partial: True` (önbellek öneki sayılmaz), oran yalnızca büyüyerek öğrenilir, düşük sayı önbellek isabeti sayılır. `Run.anchor` (model, tahmin, gerçek) ile `real_of(est)`; sınırlar etkin orana (eff) göre. Düşünme metni canlı sayaçtan ve çıktı sayısından düşülür. Kırpma/özetten sonra yerelde hâlâ sığmıyorsa `_grow_local_window(need=...)` ve `ai_note_ctx_grown_conv`.
- **Canlı yanıt:** `closeMarkdown` (açık fence, `**`, `*`, `` ` ``, `~~`, yarım bağlantı); `LiveNote thought` (Brain ikonu, `.note-thought` iki satır); `lastSentence` artık sarmalayıcıları atıyor.
- **RAM koruması:** `llm/memguard.py`:
  - `kv_per_token` (GGUF model_info) ve `safe_window` (psutil boş RAM + yüklü modeller − 3 GB pay − ağırlık) / (KV × paralel × KV türü).
  - `router.context_info` local max/current'ı keser ve `ram` döndürür.
  - `execute` ağırlık sığmazsa `no_memory` hatası verir; paralel > 1 ise not ekler.
  - `watchdog` (main lifespan `_ram_guard`): %8 altında boştaki, %4 altında çalışan Ollama modelini boşaltır ve `model/memory` bildirimini yayınlar.
  - `OLLAMA_NUM_PARALLEL` varsayılanı 1; arayüzde onay ve uyarı (TR/EN).
- **Stok hızlandırma:**
  - `stock.find` virgülle ayrılmış konuları paralel arar (`_find_one`).
  - `_english` sorguyu çevirir; `_score` başlık ve etiketlere göre sıralar; `_simpler` kısaltılmış yedek sorguları dener.
  - Konu başına 30 sn `wait_for` sınırı.
  - `data/stock_cache` (`_from_cache` / `_to_cache`).
- **Döngü koruması:** `_loop_cut`: son 4000 karakterde aynı cümle 4 kez veya daha fazla geçerse akış `break` ile kesilir. Akış `stream.aclose()` ile kapatılır; `ai_note_loop` notu eklenir.
- **Sızıntı:** web_screenshot etiketinde file:// yerine dosya adı; shot `missing file: <göreli>` döner.
- **Değişiklik kartı:** `lib/changes.js` (`opsByFile`, `fileCounts`, `liveFiles`); write_file artık diff, added ve removed taşır; ChangesCard yerinde inceleme (modal yok: akordeon, gruplar, arama, toplam/işlem işlem); LiveChanges aynı kartı `live` ile kullanır; `photo` adım türü; `MIDCALL_STALL=120` (akış ortasında tıkanmada kurtar ve devam et); `_run_jobs` yazmadan sonra bakışı bekletir.
- **Görsel:** `describe_for` görsel model sohbet modeliyle aynı olsa da çalışır.
- **Medya:**
  - `tools/media_inspect.py`, `inspect_media` aracı.
    - Görsel: EXIF, palet, parlaklık, Laplacian netlik, Haar yüz, `docread.ocr_images`.
    - Video: ffprobe, sahne anahtar kareleri, `_sheet`, kare OCR'ı, `describe_for("")`, whisper.
  - Ekli resimler için görsel model yoksa yerel inceleme yapılır.
  - `tools/speech.py`: `speech_to_text` (faster-whisper, .srt/.txt) ve `text_to_speech` (edge-tts, parçalı mp3).
  - `media` grubu ve RULE_TOPICS media genişletildi.
- **Yerel yalın mod:**
  - `router.native_tools` yerelde False döner (profil "native" ile açılır).
  - `LOCAL_DEFAULT_CTX` 16K.
  - `_budget` yerelde en fazla %65.
  - `LOCAL_HISTORY=12`.
  - Taşmada büyütmeden önce `_summarize_progress` çalışır.
- **Devre kesici:**
  - `BUSY_CODES` ve `_busy_alternative` (sıra: fallback_model → havuz → `<sağlayıcı>:auto`, yerel model asla).
  - Geçiş, ikinci meşgul yanıtta ya da `run.stalls >= 2` olunca yapılır; ilk yeniden deneme 5 sn.
  - Görev başında `usage_cooldown` kontrol edilir; meşgul soğuması 90 sn.
  - `MIDCALL_STALL=75`.
- **Ses stüdyosu ve medya kartları:**
  - `/api/sessions/{sid}/tts-file` dosyayı yeniden üretir ve mesaj meta'sındaki `tts.voice` alanını günceller.
  - `OutputGallery`: `MediaCard` (audio/video oynatıcı) ve `VoicePicker` (`/api/tts` ile canlı önizleme).
  - `workspace.OUTPUT_EXTS` ses ve video uzantılarını içerir.
- **Transkript:** `speech.table` (Zaman | Metin); `media_inspect` aynı whisper'ı kullanır.
- **Görsel:** RAM'e sığan küçük yerel Ollama görsel modelleri son aday; renk adları; OpenCV `<5`.
- **RAM koruması 2:**
  - `memguard.commit_free` (GetPerformanceInfo) ve `free_memory`; bekçi 2 sn'de bir, %12/%6 eşikleri; whisper boşaltılır.
  - `threads()` = fiziksel çekirdek − 1, Ollama `num_thread` olarak gönderilir.
  - `KEEP_ALIVE` 10 dk.
- **Akış performansı:**
  - Düşünme adımı en fazla 4 kez/sn gönderilir (`think_at`).
  - `StreamSplitter` `_scan` ile kapanış etiketini kaldığı yerden arar.
  - `PREP_NAME` yalnızca ilk 600 karakterde aranır.
- **Tek çağrı ve duruş:**
  - Kurtarma notu kalanı tek çağrıda ister; `write_file` tanımında parçalama sınırı 40K; SPLIT_HINT en fazla iki parça (25K).
  - `stalled` kodu: native araçla çalışan model metin protokolüne geçer (`silent_writer`); `run.stalls` sayılır.
  - Etiket: `step_retry_stalled` / `cd_stalled`.
  - Append ve kurtarma adımları added/diff taşır.
  - `stock._photo_name`: ilk görsel eksiz kaydedilir.
  - shot eksik dosyada en yakın eşleşmeyi önerir (difflib).
- **Fark görünümü:** `OpDiff`, birden çok işlemde varsayılan görünüm "ops"; "Kod editöründe aç" `openFile(path, true)` çağırır; VoicePicker güncel sesi kullanır.
- **Görsel üretimi ve yetenekler:**
  - `generate_image` (Pollinations FLUX) media ve design gruplarında; `tools/imagegen.py`: token varsa logosuz üretim, `save` görseli yazar; test uç noktası `/api/media/test`.
  - Media sözcükleri genişletildi; media isteği bilgi sorusu (salt okuma) sayılmaz.
  - `_run_tool`, açılmamış grubun aracını grubu açarak çalıştırır (`run.restricted` değilse).
  - Ekler `attachments/` altına kopyalanır.
  - `lastSentence` ~160 karakter ve yazılmakta olan cümleyi gösterir; düşünme satırı en fazla 3 satır.
  - İzin düğmesi `md` altında yalnızca ikon.
- **Atomik yazma:** `config.atomic_write` (settings/secrets). VERSION mavi ekranda NUL olmuştu, düzeltildi.
- **Tarama:** pyflakes temiz (ölü `target` ve gereksiz `global` kaldırıldı); vite build başarılı.

## Proje Durumu — v0.10.5
- **Gerçek token verisi:** `usage` (Ollama prompt_eval_count, OpenAI include_usage, Anthropic input_tokens, Gemini usageMetadata). Model başına oran `_learn_ratio` ile `data/ctx_ratio.json`'a yazılır. Kırpma/özet sınırları bu oranla gerçek token birimine çevrilir. Görev başı sıkıştırmada `LAST_REAL` (sohbetin son gerçek istem boyutu) kullanılır.
- **Taşma:** providers BODY_PATTERNS'e "exceeds the available context size" eklendi. NATIVE_REJECT yalnızca araçla ilgili 400'lerde metin protokolüne geçer. OVERFLOW_SIZES gerçek boyutu okur. `_grow_local_window` pencereyi en az 16K'ya çıkarır ve model olayıyla arayüzü günceller.
- **Görsel model:** `visual.describe_for` (görmeyen modelde web_screenshot / browser_screenshot betimlemesi). `router.supports_images` önce profil, sonra API önbelleği, en son ada bakar.
- **Ayar denetimi:** Ollama `streaming`, Anthropic/Gemini "her zaman akışlı", sıkıştırma eşiği %40-95, cloud_fallback açıklaması.

- **Hız ve katmanlı istem:**
  - SYSTEM_CORE (kimlik + davranış) ve CAPABILITIES (yetenek haritası) sabit kısımdır.
  - RULE_TOPICS (install, media, markdown) `rule_topics` ile görev başına bir kez seçilir; SCREENSHOT_RULE ayrıca eklenir.
  - ENV_SECTION + hostinfo istemin sonuna taşındı. Beceriler ad ve başlıkla listelenir.
  - BROWSER_WORDS'ten URL ve "ekran görüntüsü al" çıkarıldı.
  - Ölçüm: 9.1K → 4.5K token; yerel görev 433 → 180 sn.
- **Takılma:** `_heartbeat` keep-alive ping'lerinde sessizlik saatini sıfırlamaz (evren'de 6 dk takılma giderildi).
- **Görsel:** `visual.describe_for` adayları ölçülen hıza göre sıralar, uyarlamalı süre sınırıyla sırayla dener; aynı anda tek istek (yarışan istek yok); hızlar vision_speed.json'da tutulur, VISION_NAMES önceliklidir, 180 kelimelik betimleme 3,5-4 sn sürer.
- **Koordinasyon:** `whole_calls` (sonda tek parça gelen büyük çağrı → kalıcı metin protokolü), `_call_open` (tamamlanmış çağrı korumayı kapatmaz), toplu iş kuralı + todo ilk adımlarla, `lane="side"` + `_MAIN_ACTIVE` (yan işler ana istekle çakışmaz).
- **Yan işler:** `router.side_model`; yerel modelde başlık bulut modeline gider ya da model çağrılmaz. `browser_screenshot` about:blank'ta hata verir.

## Proje Durumu — v0.10.4
- **Ayarlar:** tüm model seçicilerde yetenek ikonları; yedek ve profil modelinde yetenek kartı; tüm sayısal alanlar kaydırıcı + sayı kutusu (RangeField, logaritmik ölçek, otomatiğe dön).
- **Senkron:** /api/models/health her 5 sn (gizli sekmede durur): yerel sunucu açılıp kapanınca model listesi ve hata durumu güncellenir; ayar dosyası değişince ayarlar yeniden okunur; Test başarılıysa önbellek temizlenir.
- **Yerel çalışma ayarları:** llm/local_runtime.py (Ollama ortam değişkenleri: Windows HKCU\Environment + WM_SETTINGCHANGE, macOS launchctl, Linux data/ollama_env.json; yeniden başlatma; LM Studio REST /api/v1/models/load veya lms --gpu/--ttl).
- **MCP:** mcp_add aracı (mcp_setup grubu); Windows .cmd boşluklu yol düzeltmesi; npm + GitHub + PyPI sunucularıyla uçtan uca test.
- **Araç zinciri:** toolchain.py (static-ffmpeg yedeği, composer.phar + SHA-256, php.ini/PHPRC, data/bin ve NODE_PATH); install.bat winget, install.sh brew/apt/dnf/pacman.
- **Beceriler:** site-test, remote-server, social-media, ads-manager, graphics, mcp-servers, packages, code-review.
- **Sıradaki:** zaman çizelgeli video düzenleyici, görsel üretimi, stok servisleri, isteğe bağlı Docker (WSL2) sandbox.

## Mimari ve Klasör Yapısı
- `/backend` (FastAPI, Process Manager, LLM Router, Agents)
- `/frontend` (React, Vite, Monaco, i18n)
- `/agents` (Planner, Coder, Debugger, Tester)
- `/skills` (Markdown skill tanımları)
- `/languages` (tr.json, en.json)
- `/chat/<sohbet kimliği>/` (projesiz her sohbetin çalışma klasörü: dosyalar, indirilenler, docs/ altında üretilen belgeler)
- `/chat/<sohbet kimliği>/.session/` (gizli oturum kaydı: session.json, messages.jsonl, summary.md, PROJECT_STATE.md, uploads/, scripts/)
- `/chat/projects/` (klasör seçilmeden oluşturulan projeler); `workspace/` v0.10.3'te kaldırıldı (ilk açılışta otomatik taşınır)
- `/tanitim` (GitHub README TR/EN, ekran görüntüleri, banner, R10 BBCode ve HTML tanıtım)

## Tamamlanan Özellikler (Done)
- [x] install.bat / run.bat / requirements.txt (Mevcut)
- [x] Python 3.12 & Node 26 uyumu
- [x] LLM Router (Ollama, LM Studio, OpenAI, Anthropic, Evren API)
- [x] Background Process Manager (Asyncio, WebSocket Log akışı)
- [x] Monaco Editor Entegrasyonu
- [x] i18n (tr/en) ve Otomatik Çeviri

## Devam Eden / Planlanan Görevler (TODO)
- [x] Multi-Agent Swarm Mimarisi (Ajanların birbiriyle chatleşmesi)
- [x] Self-Debugging Loop (Traceback yakalama ve otomatik düzeltme)
- [x] Görsel Geri Bildirim (Playwright + Base64 vision model)
- [x] Git Otomasyonu ve Zaman Makinesi (Smart Rollback)
- [x] Ofis Belge Üretimi (PDF, Word, Excel, PPT)
- [x] v0.6: kesintisiz orkestrasyon, canlı yapılacaklar listesi, otomatik yetenek algılama, belge önizleme, çizim ekranı

### Yol haritası (revize, öncelik sırasıyla)
- [x] Kısmi dosya düzenleme aracı (`edit_file`) + proje içi kod arama (`search_code`) + `read_file` satır aralığı
- [x] Resim görüntüleyici, uygulama içi tarayıcı, geçici sağlayıcı hatalarında yeniden deneme, sabit sistem istemi (önbellek)
- [x] Sembol haritası (regex: fonksiyon/sınıf/metot, `symbols` aracı, proje sohbetinde kod haritası)
- [x] Çoklu model: kota dolunca otomatik geçiş, 5 saatlik/haftalık kota takibi, ajan başına model, `ask_model`; yerel modeller havuza girmez
- [x] Tree-sitter söz dizimi ağacı: kesin tanımlar, `impact` etki analizi (gramerler ilk kullanımda iner; yoksa regex)
- [x] MCP istemcisi: stdio + Streamable HTTP, Ayarlar > MCP, `mcp` aracı, tokenlar secrets.json'da
- [x] Proje hafızası: proje başına AIIQ.md kuralları, genel kurallar, `remember` aracı
- [x] Rehber/Ayarlar/Hakkında sayfaları geniş ekrana göre büyütüldü
- [x] Onaydan önce diff görünümü (onay kartında yeni dosya / düzenleme / üzerine yazma / silme farkı)
- [x] Model profilleri: model başına düşünme, görsel girdi, akış, araç çağrı biçimi, sıcaklık, en fazla çıktı (Ayarlar > Modeller)
- [x] v0.10.0: belge motoru yeniden yazıldı (docs_gen.py: Markdown/HTML -> ortak HTML; Chromium+KaTeX PDF/HTML, python-docx, python-pptx iki sütun, openpyxl; ReportLab+DejaVu yedek), make_doc source=/theme/landscape
- [x] v0.10.0: Ayarlar > Güvenlik: stream_timeout / first_token_timeout / local_stream_timeout / provider_retries, paralel çalışma, sınırsız adım ve hata ayıklama
- [x] v0.10.0: run_state.json kontrol noktası, açılışta yarıda kalan görev kurtarma, resume_note; aynı sohbette çift görev engeli (409)
- [x] v0.10.0: agents/intents.json (14+ dil), SSE keep-alive, akış ortası hata sınıflandırma, kesilen araç çağrısı algılama, write_file append ve tekrar yazma koruması, sızıntı kalıpları
- [x] v0.10.0: sağlayıcı rpm hız sınırı (NVIDIA 40), hesap bakiyesi (OpenRouter/DeepSeek/EVREN), gerçek "Şimdi dene", Nemotron 3 1M bağlam; harita/arama API anahtarı geç bağlama hatası düzeltildi
- [x] v0.10.1: söz/duyuru koruması (is_promise), görsel istendi-belgede yok koruması, resim doğrulama, rakam kanıt denetimi (ctx.evidence), XML alan adlı okuma, belge kaynağı .doc-sources/
- [x] v0.10.1: HTML bileşenleri (kpis, bars, callout, badge, cols) + DOCX/PPTX için görselleştirme, çalışırken yönlendirme (run.steer), devamda araç sonuçları (results), model başlığı (title_auto), canlı süre ve hazırlık aşaması
- [x] v0.10.1: havuz seçimi (sağlayıcı TPM, sağlayıcı dağıtımı, aşama bazlı rezervasyon), etiket protokollü ekip üyeleri, hız sınırında anında model geçişi, ortak görevlerin kapanması
- [x] v0.10.2: kopmada kısmi dosya kurtarma (_salvage, partial_call.json, save_partial), sessiz sağlayıcıda metin protokolüne geçiş, read_file tekrar okuma önbelleği ve base64 kırpma, make_doc ile todo ilerletme, farklı dosyalara paralel yazma
- [x] v0.10.2: HTML utf-8 meta + önizleme charset, JS hata denetimi (js_check), joker yol çipi yok, DOCX kapak/başlık/sayfa x/y, PPTX bölüm bandı, VERSION + set_version.py, görsel model betimleme, dil senkronu, yedek model kapsamı, adım penceresi (60)
- [x] v0.10.2 canlı test: web_screenshot PDF A4 sayfa, looks_python (shell'siz Python kodu), todo'da sonraki madde önceki açık maddeyi kapatır
- [x] v0.10.3: fenced_commands (kod bloğundaki komutu çalıştır), code_nudges sınırı, tools/verify.py (ikili biçime metin yazma engeli + komut çıktısı denetimi), unresolved (başarısız adımı bitti sayma), ffmpeg -y, tam erişimde onaysız silme/riskli komut, VideoPlayer.jsx
- [x] v0.10.3: _own_site (Tam erişimde adı verilen sitede şifre/onaysız düğme; kart hariç), CAPTCHA devrinde görünür pencere + çözülünce otomatik devam (CAPTCHA_STATE_JS), file:// %20 düzeltmesi
- [x] v0.10.3: DISMISS_JS + AGENT.dismiss_popups (her sitede modal/çerez bandı kapatma, çerezde hep Reddet, şifre/kart pencereleri hariç), ayar browser.dismiss_popups
- [x] v0.10.3: workspace/ kaldırıldı -> chat/<id>/ (+ .session/), chat/projects/, workspace.migrate_layout (ilk açılışta taşıma, DB proje yolları), yeni sohbet Dosyalar boş durumu
- [x] v0.10.3: kept_answers (yönlendirmede cevap korunur), biten göreve gelen mesaj -> otomatik takip görevi (skip_user_msg/steer_parts), SILENT_TOOL_LIMIT=75 + kalıcı stream_tools.json, store started yarışı, SteerMessage/steer adım tasarımı, hostinfo.os_line + ortam/yetenek özeti
- [x] v0.10.3: router._Slots (bulut sağlayıcı başına eşzamanlılık kuyruğu, meşgul/429 sonrası 5 dk seri), providers_default concurrency/free_rpm (Ollama Cloud 1, DeepSeek 8, Mistral rpm60/2, SambaNova rpm20, OpenRouter free_rpm20, HF 2, Cerebras 2, evren 3), ayar kartında Eşzamanlı istek
- [x] v0.10.4: model seçicilerde yetenek ikonları, RangeField kaydırıcıları, /api/models/health canlı senkron, Ollama/LM Studio çalışma ayarları, mcp_add + Windows npx düzeltmesi, toolchain (static-ffmpeg, composer, php.ini), install.bat/install.sh araç kurulumu, 8 yeni beceri
- [x] v0.10.5: gerçek usage verisiyle bağlam (oran kaydı, LAST_REAL), Ollama taşma tanıma + pencere büyütme, görsel model ekran görüntüsünde, ayar denetimi
- [ ] İsteğe bağlı Docker (WSL2) sandbox
- [ ] Tam zaman çizelgeli video düzenleyici (ffmpeg, faster-whisper altyazı)
- [ ] Güçlü resim üretimi (Pollinations + anahtarlı servisler, format/ölçü algılama)
- [ ] Stok resim/video servisleri (ücretsiz + ücretli, ücretlide onay)
- [x] Paralel ajan takımları (`team` aracı, bulut havuzu) ve canlı görev panosu
- [x] Sesli yanıt (tarayıcı konuşma sentezi, otomatik okuma) ve sesli komut modu (gönder/durdur/onayla/reddet)
- [x] Takım üyeleri arası mesajlaşma ve ortak görev listesi (team_message / team_tasks)
- [x] Anthropic: araçlarla genişletilmiş düşünme (imzalı düşünme blokları korunur)
- [x] Etkin dil her yerde: düşünme/not/plan/takım raporu; uygulama metinleri languages/*.json `ai_*` anahtarlarından
- [x] Çaba ayarı: API verisinden gerçek seviyeler, yoksa talimatla
- [x] Dar ekran düzeni (container query, kenar çubuğu 1024px altında katman)
- [x] v0.8: web sayfası ekran görüntüsü aracı (`web_screenshot`, sohbette küçük resim + görüntüleyici, görmeyen modele sayfa metni)
- [x] v0.8: sohbet geneli dosya/klasör bırakma alanı, eklenen resme çizim/yazı düzenleyici (orijinal çözünürlük)
- [x] v0.8: edge-tts doğal sesler (kadın/erkek, dile göre ayrı seçim), emoji/sembol okunmaz, tarayıcı sesi yedek
- [x] v0.8: 13 profesyonel skill/ajan, `tools:` ile token tasarruflu araç seti, `save_catalog` (skill/ajan üretici)
- [x] v0.8: en son mesaja in düğmesi, 360 px mesaj kutusu düzeni, otomatik düzen denetimi (sıfır bulgu)
- [x] v0.8: varsayılanda yalnız Ollama açık; anahtar kaydedilince sağlayıcı açılır; her portta çalışır (origin kontrolü)
- [x] v0.8.1: gerçek token sayımı (gömülü tokenizer, araç tanımları dahil), canlı bağlam sayacı, yapılan adımları koruyan sıkıştırma
- [x] v0.8.1: PowerShell 5.1 uyumu (&&/||, rm -rf, del, kalıcı cd, gerçek çıkış kodu), not görünümü, ekip çağrısı birleştirme, döngü kilidi
- [x] v0.9.0: sohbet cevabı doğrudan sohbete (reply_mode), kimlik soruları sohbet sayılır, araç adını etiket yapan zayıf model çağrıları (<research .../>, <run>..</run>) çalışır, resim düzenleyicide el/boşluk/orta tuş ile kaydırma ve imlece yakınlaştırma
- [x] v0.8.1: Retry-After, bağlam aşımı kurtarma, takılan bulut isteği kesme, okumadan cevap kilidi, NVIDIA NIM ve Cloudflare Workers AI sağlayıcıları (hata kodları eşlendi)
- [x] v0.8.5: sızıntısız akış (thinking/reasoning/lone </think>/harmony, GLM ve harmony araç çağrıları, düşünce içi çağrı, boş cevap tekrarı), araç çıktısında anahtar maskeleme + secrets.json koruması, sohbet başına çalışma klasörü, okunur adım ayrıntıları (ham JSON yok)
- [x] v0.8.5: tokenizer ile kategori bazlı bağlam, önbellekli istem/Cloudflare parça kullanımı düzeltmesi, halka-kart senkronu (canlı değer + çalışan model), çift ölçekleme ve sıkıştırma sonrası sayaç düzeltmesi, artımlı canlı sayım, takım üyesi bağlam/token, Gemini düşünce imzası
- [x] v0.8.5: eylem kayıtlı ve dil uyumlu halüsinasyonsuz sıkıştırma; model bilgisi önbelleği (arka planda yenileme), iş parçacığında klasör/istem; araştırmada site çeşitliliği, kısa sayfa eleme, süre sınırı, gereksiz tarayıcı render'ı yok, arşiv hatası düzeltmesi
- [x] v0.8.6: dinamik araç grupları + need_tools, küçük pencerede kısa araç tanımları, araca göre kural bölümleri, sıkıştırma döngüsü düzeltmesi (sabit kısım payı, histerezis, gerçek kazançta adım), Ollama 'No user query found' = bağlam aşımı
- [x] v0.8.6: arka plan tarayıcısı yeni headless + tam profil (UA, dil, ekran), çökme kurtarma ve iki çökmede engel, görünür pencere görev sonunda kapanır, 'Hızlı okuyucu' seçeneği, Kayıtlı oturumlar kartı yeniden tasarım
- [x] v0.8.7: bekleme/rate limit hatası sohbette anında (geri sayım), TPM 413 sınırına sığdırma, ajan çağrısı teslim notu, çoklu ajan (@a @b), YAML tools listesi, güncel PATH, gerçek winget/indirme kuralları, hata sonrası web araması, Start-Process URL notu, shell=python komut satırı düzeltmesi, canlı not/düşünce görünümü, komut detayı, md -> Monaco, sağlayıcı önekli model seçici
- [x] v0.8.8: canlı görev tek sabit alanda (titreme/sızıntı görüntüsü yok), eylem kaydı yankısı gizli, 'çalıştır' isteğinde yalnız kod basılırsa gerçekten çalıştırma, görev sonunda yapılacaklar tamamlanır
- [x] v0.8.9: ajan sunucuları: stop kuralı + start hatırlatması, görev sonrası süreli otomatik kapatma (ayar, geri sayım, yeni görevde duraklatma), run ile sunucu -> arka plan, durdurulan görevin komutu kapanır, açılışta sahipsiz süreç temizliği

## Önemli Kararlar ve Notlar
- **Güvenlik:** PowerShell komutları çalıştırılırken "Tam Yetki" modunda dahi akıllı güvenlik filtresi kullanılacak.
- **VRAM Yönetimi:** 30B/35B modeller yüklenirken FFmpeg gibi arka plan işlemleri otomatik duraklatılacak veya model unload mekanizması devreye girecek.
- **Anti-Bot:** Bot korumaları aşılmaz; engellenen site raporlanır, model başka kaynağa yönelir.
- **Token Tasarrufu:** Ajanlar arası iletişimde gereksiz context şişirilmesi engellenecek, sadece "diff" (fark) ve "traceback" gönderilecek.

## Sıradaki Adım
Önerilen sıradaki işler (değer sırasıyla):
1. Depoda otomatik test paketi (sahte model sunucusu + bu turdaki 27 uçtan uca denetim) ve CI çalıştırması.
2. `agents/orchestrator.py` (3.500 satır) modüllere bölünsün: istem, bağlam, süreklilik, denetimler, görev döngüsü.
3. Adım ayrıntıları ve büyük diff'ler mesaj satırının dışında saklansın (arayüzde gerektiğinde yükleme), sohbetlerde SQLite FTS araması.
4. Model başına okuma hızı ve hata oranı Ayarlar > Modeller'de gösterilsin; havuzdaki en hızlı model otomatik seçilsin.
5. LM Studio: Ollama'daki gibi KV tahmini ve pencere küçültme (bugün koruma yalnızca Ollama modellerini yeniden boyutlandırıyor).
6. İsteğe bağlı Docker (WSL2) sanal ortamı, zaman çizelgeli video düzenleyici, güçlü görsel üretimi, stok servisleri.
