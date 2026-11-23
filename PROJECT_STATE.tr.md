# AI IQ 300 - PROJECT_STATE.md

**Türkçe** · [English](PROJECT_STATE.md)

## Proje Vizyonu
Otonom, çoklu ajan destekli, yerel ve bulut LLM'leri ile çalışan tam kapsamlı yazılım geliştirme ve komuta merkezi.

## Mevcut Durum (State)
- **Tarih:** 2026-11-20
- **Aktif Görev:** v0.16.0 tamamlandı (susan akışlarda bağlantı denetimi, ücretli + ücretsiz AI video, medya model seçiciler, gömme / kapatılmış modelsiz canlı listeler, MCP sekmeleri, kurulum ilerlemesi). v0.15.1 tamamlandı (internet kesintisi: algılanır, gösterilir, görev bekleyip aynı modelle kaldığı yerden sürer; kurulumda çevrimdışı / proxy desteği). v0.15.0 tamamlandı (adım kaydı düzeltmeleri, modüler orkestratör / registry, profesyonel kurulum). v0.12.0 tamamlandı (zayıf modeller: düz metin araç çağrıları çalıştırılır, istenen dosya diskte denetlenir, system_info, sohbet araması, model kaydı, LM Studio bellek koruması, test paketi, orkestratör bölündü); v0.11.0 tamamlandı (kapsamlı tarama: yalın istem, kopma ve model değişiminde süreklilik, modeli kapatmayan RAM / VRAM koruması, eksiksiz WebSocket yeniden bağlanma, yarış düzeltmeleri); v0.10.7 tamamlandı (toplu seçme/silme, ilk mesajda yetenekler, 14 dilde araç algılama, bölmeden yazım); v0.10.6 tamamlandı (web tasarımı + stock_photo, sayfa JS/kırık görsel testi, gerçek sayıya çapalı bağlam, yerel pencere büyütme, Markdown canlı yanıt); v0.10.5 tamamlandı (gerçek token verisi, görsel model, ayar denetimi); v0.10.4 tamamlandı (ayarlar, yerel GPU, MCP, araç zinciri, beceriler); v0.10.3 tamamlandı (canlı test: Evren auto, NVIDIA Nemotron 3 Ultra 550B, Groq)
- **Son Başarılı İşlem:** v0.10.0 — profesyonel belge motoru (Chromium PDF/HTML + KaTeX, tasarımlı DOCX/PPTX/XLSX), ayarlanabilir akış zaman aşımları ve parçalı yazma, run_state.json ile kesinti sonrası devam, paralel araç yürütme, canlı todos, çok dilli niyet tablosu, zengin mesaj kutusu, mesaj sayfalama/kopyala/sil/alıntı, sağ tık menüleri, gruplu değişiklik kartı, medya oynatıcılar, servis kartları, kota/bakiye ekranı.
- **Önceki:** v0.6 — kesintisiz orkestrasyon (devam ettirme, sessiz araç yazımında heartbeat, görev içi bağlam kırpma/özetleme, canlı bağlam sayımı, takılı adım temizliği, tekrar eden çağrı koruması, asılsız dosya iddiası koruması), todo aracı + canlı yapılacaklar listesi, otomatik yetenek algılama (use_skill), bilgi sorularında salt-okuma araçlar, arama alaka filtresi + Bing URL çözümü, canlı gruplu adımlar, model seçiciden bağlam düzenleme (ayarlarla senkron), aç/kapat popover'lar, çizim ekranı, klasör yükleme, hedef modu, belge kartları ve önizleme (xlsx/docx/pdf/pptx), kökteki gereksiz docs/ kaldırıldı.

## v0.18.7 (2026-11-23): Mermaid şemaları, akış şeması yeteneği, bölünmüş sistem araçları, kayıt düzeltmeleri
pytest 318. Sohbet şeması tarayıcıda denetlendi (satır içi, genişletme, kod düzenleme, koyu tema, konsol hatası yok).
- **Şemalar:** `frontend/src/components/Diagram.jsx` (satır içi şema, üzerine gelince menü, yakınlaştırma / kaydırma /
  sığdırmalı tam ekran görüntüleyici, canlı önizlemeli Monaco düzenleme, PNG / SVG dışa aktarma);
  `lib/mermaidText.js` yapıştırılan Mermaid'i tanır; `lib/diagramTheme.js` tek tema kaynağıdır, arka uç da kullanır.
- **`render_diagram`** (`backend/app/tools/diagram.py`): başsız Chromium + uygulamanın Mermaid'i ve teması, PNG ya da
  SVG, dosya yazma onayından geçer. `generate_image` şema isteklerini reddeder.
- **Akış şeması yeteneği** (`skills/flowchart.md`): tür seçimi, şekiller, tırnaklar, alt gruplar, anlamlı renkler, denetim.
- **WORKFLOW.md / WORKFLOW.tr.md** şemalarla; `screenshots/workflow-*.png` README'lerde.
- **Sistem araçları:** `system_info` (özet / now / all), `hardware_info`, `software_info`, `mobile_info`; önce tarih;
  önbellekli (donanım 30 dk, yazılım 10 dk), açılışta ısıtılır; sürücü harfi -> fiziksel disk türü.
- **Kayıt düzeltmeleri:** yalnızca todo içeren son tur görevi bitirir (üçlü cevap yok); todo birleştirme yalnızca biten
  eski maddeleri tutar; yapıya duyarlı saçmalama kesimi ("Ak" kesilmesi); `<|close|>message` şablon belirteçleri
  gizlenir; benzer arama freni; kendi adıyla MCP araçları; `file_path` / `filename` takma adları; yapışık arama
  sonuçları ayrılır; kimlik depoyu ve sürümü bilir.

## v0.18.6 (2026-11-22): Google / GitHub entegrasyonu, başka araçların komutlarıyla beceri
Gerçek modelle test edildi (NVIDIA Nemotron, geçici AIIQ_DATA kopyası). pytest 284.
- **Google:** yerleşik `google` aracı (bağlı hesapla Google REST API'leri: Gmail ve taslaklar, Drive, Sheets, Docs,
  Takvim, Kişiler); google-* MCP sunucuları cevap verdiğinde kullanılır, Developer Preview reddinde bu araca
  geçilir; "API'leri etkinleştir" uyarısı gerçek denetimden gelir.
- **GitHub MCP:** issue / PR / commit / depo kelimeleri bağlı github sunucusuna yönlendirir; yanlış sahip -> get_me
  ipucu; olmayan araç adına "Bunu mu demek istediniz"; yanlış alana yazılan seçenek değeri doğru alana taşınır.
- **Zayıf model korumaları:** `<arguments>{...}</arguments>` / `<argument name="body">` sarmalayıcıları her araçta
  açılır; tırnaksız `argv=[...]` / `arguments={...}` okunur; mcp gövdesindeki iç içe araç etiketi bildirilir; 24 bin
  karakteri aşan google / mcp çağrısı üretim döngüsü olarak kesilir; hesap aracı çağrılmadan verilen hesap cevabı bir
  kez uyarılır; yapılacaklar listesi boşa dönme döngüsü kapatıldı.
- **Komutlarla beceri** (`catalog.skill_source`): `npx skills add sahip/depo`, sahip/depo, GitHub adresi,
  `hf skills add [ad]` (Hugging Face pazaryeri), `gradio skills add [kullanici/space]` (gradio becerisi ya da bir
  Space'in API'sinden üretilen beceri) MCP sunucusu olarak hata vermek yerine Beceriler sayfasında ya da MCP formunda
  seçim penceresini (RepoSkillsModal) açar. `source:` alanı sayesinde tekrar içe aktarma günceller; yerleşikler
  ezilmez; becerinin yanındaki dosyalar fetch_url bağlantısı olur; tek seferde en fazla 60 (her biri istemde ~40
  token). YAML blok açıklamalar (`description: >-`) okunur.
- **Donanım raporu -> Drive görevi (tüm modeller için düzeltildi):** `google file=` yerel dosyayı gerçekten yükler
  (5 MB'a kadar multipart, üstünde 8 MB'lık parçalarla resumable; düz Drive adresi yükleme adresine çevrilir;
  /files/<id> = PATCH; Drive'ın bildirdiği boyut denetlenir). `save=` yalnızca indirme içindir, JSON cevap asla .pdf'in
  üstüne yazılmaz (önceki görev sağlam PDF'i 128 baytlık JSON ile ezmişti). fetch_url save= bir web sayfasını .pdf /
  .zip / resim adıyla kaydetmez. Beceri `tools:` listeleri temel araçları (run, list_dir, read/write/edit_file,
  system_info...) artık engellemez. Ayrıştırıcı: kapanmamış açılış etiketi ilk `<`'de biter; `<parameter name=…>` /
  `<parameter=…>` / `<path>` / `<arguments>` blokları argüman olur (adım etiketine "…Raporu</h1>" sızıyordu). Sonuna
  eklenen işaretlemede eklem yerindeki yetim kapanış parçası atılır, açık tablo / liste kapatılır. Yolu verilmeyen
  make_doc dosya adını başlıktan çıkarır. use_skill adı her argümandan alır. Canlı: NVIDIA Nemotron 4 tur / 24 sn'de
  yaptı, geçerli 3 sayfalık PDF boyutu eşleşerek yüklendi; evren:auto da yaptı (446 sn, sağlayıcı bir kez durdu,
  kaydedilen kısımdan devam edilerek kurtarıldı). pytest 291.
- **Geçmiş işle ilgili sorularda yanıt artık silinmiyor:** "…test ettin?" / "çalıştırdın mı" / "did you run it"
  çalıştırma isteği sayılıyordu; önceki komutları kod bloklarında anlatan bitmiş yanıt "bir komut yazılmış ama
  çalıştırılmamıştı" notuyla siliniyordu. `checks.asks_for` geçmiş / bitmiş zaman kiplerini (Türkçe "test et-"
  çekimleri dahil) yanıtı yeniden yazdıran tüm korumalarda yok sayar (yazdırılmış kod, çalıştırılmamış komut,
  değişiklik iddiası, eksik teslim, yazılmamış kod); "sadece yazdırdı" koruması yapıştırılmış çıktı değil gerçek kod
  (kaynak bloğu ya da komut satırı) ister. pytest 294.
- **Durum sorgusu nihai yanıtı artık durdurmuyor:** döngü koruması aynı sonucun 3. tekrarını, model yön değiştirsin
  diye hataya çeviriyor; exit 0 dönen bir sorgu (`ruflo task status`, 6 kez) böylece "son komut başarısız" sayıldı,
  bitmiş yanıt silindi ("…model bitti diyordu; önce düzeltmesi isteniyor") ve hata ayıklama rolü başladı. Bu
  sonuçlar artık `repeat_ok` taşır: model için yine döngü notu, ama asla çözülmemiş hata ya da hata ayıklama turu
  değil. Bir adımın başarısız olduğunu / bitmediğini kendisi söyleyen yanıt (`admits_failure`) çözülmemiş hata,
  teslim edilmeyen dosya (bir denemeden sonra) ve açık yapılacaklar (bir hatırlatmadan sonra) korumalarında korunur.
- **Arka planda süreç bırakan komutlar hemen döner:** `ruflo daemon start` (miras aldığı boruları açık tutan
  daemon) bittikten sonra her seferinde tam 10 sn bekliyordu; borular artık yalnızca çıktı gelirken okunuyor (1,2 sn
  sessizlikte biter). pytest 297.
- **Bir aracı kaldırmak artık bir dizi "hata" değil:**
  - Son komut `Remove-Item … -ErrorAction SilentlyContinue` ya da `2>$null` ise çıkış kodu 0 olur. PowerShell bu
    durumda da `$?` değerini false yapıyordu.
  - Hiçbir şey bulamayan sorgular (`Get-Command x`, `where`, `npm ls -g x`, `pip show`, `Test-Path`, `grep` …)
    hata değil, sonuç sayılır.
  - İki durum sorgusu arasında durumu değiştiren başka bir çağrı varsa döngü sayacı sıfırlanır.
  - Komut olarak yazılan uygulama aracı (`run list_dir`) aracı çalıştırır.
  - Hata rehberine iki kayıt eklendi: boşluklu yolun iki argümana bölünmesi ve `@latest` kaynaklı npm EUSAGE.
  - Çalışma klasörü dışındaki bir dosyayı açmak konsolda yakalanmamış 403 yerine bildirim gösterir.
- **8300 geçmiş taramasından:**
  - Ham satır sonu içeren ya da nesneden sonra cümle gelen MCP argümanları (uzun Linear / Notion metinleri)
    okunur.
  - PowerShell'de `head` / `tail` çalışır.
  - Tarayıcıda en üstte `return` olan ya da IIFE biçimindeki JS kodu çalışır.
  - İki akış parçasına bölünen satıcı çağrı sarmalayıcısı (`</minimax:` + `tool_call>`, NVIDIA'da nemotron) not
    olarak görünüyordu. Artık etiket biçimindeki her kısa kuyruk tamamlanana kadar tutulur ve `<x:tool_call>`
    sarmalayıcıları atılır.
  - pytest 305.

## Proje Durumu: v0.18.5
Dev dosyalar ve sonrası (2026-11-21), model bazında değil tüm sağlayıcılar için. Canlı: NVIDIA Nemotron 3 Ultra
152.690 karakterlik oyunu tek çağrıda yazdı (660 sn, kopmasız, tek doctype), tarayıcıda test etti, tek hatayı
edit_file ile düzeltti. pytest 199.
- **Diske canlı yazım:** akan write_file 2 sn'de bir gerçek dosyaya yazılır (tam satırlar); kopmada yazılan kısım
  kalır, model oradan devam eder (append), baştan yazılan içerik sona eklenmez (tek belge, asla iki doctype). Kurtarma
  işsiz işaretlenen todo maddelerini geri alır.
- **İstek süre sınırı:** bazı sağlayıcılar istek başından ~300 sn sonra bağlantıyı kapatmadan veri göndermeyi
  bırakıyor. NVIDIA Nemotron 3 Ultra'da uygulama mantığı olmadan ölçüldü: max_tokens=32000 ile veri 302 ve 308 sn'de
  durdu (2/2); onsuz düz akış 360 sn'yi geçti, yerel araçlı akış 697 sn'de normal bitti, uygulamanın kendi görevi 660
  sn aktı (0/3). Uygulama max_tokens'ı yalnızca yerel modellere gönderiyor; kullanıcının önceki kopmaları onsuz da
  oldu, bu yüzden sınır modele değil sağlayıcıya ait davranış sayılır: sağlayıcı başına öğrenilir (request_caps.json),
  akış 90 yerine 12 sn sonra kesilir, dosyalar sınıra sığan parçalarla yazılır.
- **Yerel araç çağrısı yalnızca argümanları akıtan sağlayıcıda** (yoksa sessiz "hazırlanıyor"); diğerlerinde metin
  protokolü. Kullanıcı notları arayüz dilinde.
- **Kendini öldürme koruması:** bir model port boşaltmak için `taskkill /f /im python.exe` çalıştırıp uygulamanın
  kendisini kapattı. python / node / uygulama yorumlayıcısını adla öldürmek ve uygulamanın kendi PID'i her kipte
  reddedilir; tek PID ya da stop aracı serbest.
- **Portlar:** `python -m http.server 8080` (çıplak port) artık görülüyor: eski sunucumuz değiştirilir, başka
  programınki için boş port önerilir.
- **Tarayıcı araçları (tam tarama):**
  - tıklama önce bakar: yanıp sönen buton beklemeden tıklanır, üstü örtülü butonda örten katman adıyla söylenir
    (`covered by <div#cover>`); tıklama başına 6 sn yerine 0,2-0,3 sn;
  - basılı tutma (`hold=800`), sürükleme (`drag="120,0"`, `to:x,y`, bir ref'in üstüne; küçük adımlarla), tuşu basılı
    tutma (`hold=1500`); batch'te drag / swipe / longpress;
  - js birden çok ifade çalıştırır, `undefined`'ı öyle söyler (null değil), öğe / liste HTML olarak döner;
  - yakalanmayan hatalar türü ve yeriyle gelir (`ReferenceError: ... (at index.html:3106:21)`);
  - favicon / kaynak haritası / .well-known sayfa hatası sayılmaz; önceki başarısız açılış sonraki sayfada raporlanmaz;
  - browser_batch çit, ham satır sonu ve sondaki virgülü kabul eder, JSON'un nerede bozulduğunu söyler;
  - "3s", "200px", "1.5s" (= 1500 ms) gibi değerler adımı durdurmaz;
  - opaklığı 0 olan ekranlar (başlık ekranının altındaki HUD) görünür sayılmaz;
  - geçmişi olmayan sekmede back sayfayı korur (about:blank'e gidiyordu);
  - ERR_EMPTY_RESPONSE / bağlantı sıfırlama / sertifika hataları açıklanır; eskimiş ref ile kaydırma / ekran görüntüsü
    yeniden bulunur; wait görünür kopyayı bekler;
  - browser_check hiç durulmayan sayfalarda (oyun) zaman aşımına düşmez ve Chromium'u her zaman kapatır; kullanıcının
    kapattığı pencere Playwright sürücüsünü açık bırakmaz; kapanan sekmelerin kayıtları silinir; indirmeler üst üste
    yazılmaz, başarısız olanlar bildirilir.
- **Todo:** başlatılan sunucu "tarayıcıda test et ve hataları düzelt" maddesini artık kapatmaz; düzelt / tarayıcıda
  denetle maddelerini yalnızca model kapatır.
- **Hata rehberi:** `timeout /t` -> Start-Sleep; ERR_EMPTY_RESPONSE -> portu eski bozuk bir sunucu tutuyor.
- Bu turun önceki düzeltmeleri: system_info clean_text, MCP _read_stderr çökmesi, MCP arama kutularının çizgiye
  bitişmesi, 404 HEAD yerine /fs/exists.

## Proje Durumu: v0.18.4
MCP kütüphanesi (16 hazır sunucu, kategori ve arama), kayıt defterinde arama, Dene penceresi ve Sohbette kullan;
mesaj kutusunda # ile MCP aracı seçme, yapıştırınca çipler korunuyor; seçilen araç modele ilk sırada, yoksa açıkça
bildiriliyor. Web / fotoğraf araması kartları; geçen sürenin yanında canlı ve ortalama token/sn; dışa aktarılan
adımlarda süre ve hız. Todo "done" düzeltmesi, Openverse lisans filtresi düzeltmesi.

## Proje Durumu: v0.18.3
Düşüncede ve mesaj kutusunda LaTeX; tur başına token/sn; yanıtta kesme en az 90 sn ve kesmeden önce yeniden
denetim; biten düşünce 30.000 karakter; WebSocket ping zaman aşımı 60 sn.

## Proje Durumu: v0.18.2
Düşünce görünümü, şablon tasarımları, galeri (2026-11-21). Ham düşünce ölçüldü; düz bloklar paragraflara bölünüyor,
HTML / Markdown / kod render ediliyor. Excel tasarımları (pano, bütçe, huni, Gantt'lı takip, takvim, karne, stok),
format başına çizilen küçük resimler, belge türüne uygun örnek içerik. Galeride Tümünü gör modalı ve pasif oklar.
make_doc şablon adını başlık yapmayı reddediyor; antet / altbilgi belgeye özel.

## Proje Durumu: v0.18.1
Akışlar, gerçek tasarımlı şablonlar, zayıf model korumaları (2026-11-21). pytest 173, mock e2e geçti; canlı: evren
qwen3-vl / auto / deepseek-v4.1-flash / qwen3.8-flash, NVIDIA Nemotron 3.5 Super, Gemini, Groq, Cloudflare.
- **Akış kesmeleri:** Evren dosya argümanlarını 5-12 sn'lik parçalarla gönderiyor; bağlantı denetimi sağlıklı
  akışları 48 sn'de kesiyordu. Artık en az 90 sn (8 x boşluk), canlı tutma sinyali gelirken hiç; dosya ortasında 150 sn;
  cümle ortasında duran düşünce 45 sn'de sürdürülür; "veri yok" uyarısı ve canlı düşüncenin kapanması akışın kendi
  temposundan sonra.
- **Düşünce görünümü (ThinkText):** hafif ayrıştırıcı (satır sonu, temel HTML, Markdown, tablo, liste) + kod Monaco'da;
  saniyede 10 güncelleme.
- **Şablonlar:** 35 hazır şablon, 8 düzen; yazı tipi, kenar boşluğu, antet / altbilgi, logo ve özel CSS; PDF, DOCX,
  PPTX ve XLSX'te farklı görünümler; galeri önizlemesi belge motorunun kendisiyle. doc_template inspect / create /
  preview ile referans birebir kopyalanır. Şablon yalnızca tasarımdır; dolgu ve örnek başlıklar reddedilir.
- **Bozuk PDF yazı tipi haritası:** OCR oylamasıyla her dilde onarılır.
- **Zayıf modeller:** yetenek araç listesine eşlikçiler, yetenek içinde de teslimat denetimi, kelimesi kelimesine tekrar
  ve liste döngüsü yakalanır, yapılacaklara uygulama talimatı girmez.
- **Arayüz:** gönderilen / kopyalanan mod mesajlarında çipler, yalnızca var olan dosyalar için dosya çipi, yenilemede aynı
  sohbet ve görüntüleyici, model seçiciler seçili modelde açılır.
- **Diğer:** system_info `now` (tarih, saat, gün, saat dilimi); MiniMax / Moonshot / Z.ai / Requesty / Vercel / Poe /
  Baseten doğrudan adresler.

## Proje Durumu — v0.18.0
Belge şablonları, mod çipleri, üretim/arama adımları, okunur hatalar (2026-11-20). pytest 158, e2e 54/54.
- **Belge şablonları** (tools/doc_templates.py): 14 hazır şablon (PDF / DOCX: tasarım raporu, deney analizi,
  yatırım notu, proje teklifi, toplantı notları, özgeçmiş; XLSX: analitik panosu, finansal bütçe, çalışma takvimi,
  proje takibi; PPTX: iş değerlendirmesi, pazar trendleri, haftalık operasyon, yatırımcı sunumu) + kullanıcının
  kendi şablonları (data/doc_templates). Şablon kimliği aynı zamanda make_doc teması (renkler docs_gen.THEMES'e,
  yazı tipi / kapak CSS'i TEMPLATE_CSS'e) ve bir bölüm taslağı. make_doc `template=`, `doc_template` aracı (list /
  create / delete; Template Creator). API: GET /api/doc-templates, GET /api/doc-templates/{id}/preview (gerçek HTML
  küçük resim), DELETE.
- **Mod çipleri** (ComposerModes.jsx): (+) girdileri (görsel, tanıtım videosu, AI klip, resimden video, ekran
  görüntüsü, Word / PDF / Excel / PowerPoint) renkli çiplerdir; talimat mesajla gider. Belge modları şablon galerisini
  açar (iframe önizlemeler, Şablon oluştur = Template Creator çipi + açıklama). Resimden video, sohbet klasöründeki
  resimleri, ekleri ve yüklemeyi gösteren bir seçici açar.
- **Adım türleri**: generate_image = image_gen, generate_video / animate_image = video_gen, edit_video = video_edit,
  inspect_media = inspect, text_to_speech = speech, speech_to_text = transcribe ("Fotoğraf aranıyor" / "Görsel test"
  yerine); biten düşünce adımı "Düşündü" der.
- **Düşünce gösterimi**: tek satır sonları korunur, <br> ve kaçışlı \n satır sonu olur.
- **Hatalar**: `providers.message_of` her hata biçimini okur (Gemini'nin JSON dizisi, Python gösterimi, Cloudflare
  hataları, iç içe) - arayüzde JSON yok; servisler de kullanır. Arayüz: nedene göre çevrilmiş açıklama (yoğunluk,
  dakikalık sınır, günlük kota, GPU kotası, ödeme, olmayan / kapatılan model, zaman aşımı, güvenlik, yetki); ham metin
  "teknik ayrıntı" altında.
- **Model listeleri**: Gemini yalnızca sohbet adlandırmasıyla (gemini-4-hydrogen gibi kod adlı modeller gizli:
  dakikalarca yanıt vermiyordu); `_chat_by_meta` listelerin kendi alanlarını kullanır (Together type, Mistral
  capabilities.completion_chat, Groq active, kind); NOT_CHAT_EXTRA (davinci / babbage, moderation, sora, dall-e, tts,
  whisper...).
- **AI video yedeklemesi**: ücretli servisin bulunamayan modeli yerine servisin diğer modelleri denenir; zorunlu
  argüman ekleyen Space'lere (last_image) boş değer gönderilir; klipler sırayla üretilir (paralel çağrılar ücretsiz
  GPU kotası için yarışıyordu).
- **Sohbette medya**: kartlar tam video oynatıcıyı ve dalga formlu ses oynatıcıyı kullanır (otomatik oynatma yok,
  kısayollar yalnızca üzerindeyken); görüntüleyici parçaları önceden yüklenir (güncellemeden sonra açınca sayfa
  yenilenmez); stüdyonun render sonucu birkaç saniyede bir baştan başlıyordu (src'de Date.now()) - düzeltildi.
- **Dosyanın sesi**: "Bu sesi kullan" sonrası ton paneli açılır (hız, perde, duygu, stüdyo) ve dosya yeniden yazılır.
- **Teslim kontrolü**: bir dosyanın oluşturulamadığını söyleyen satırlar iddia sayılmaz.

## Proje Durumu — v0.17.1
Gerçek kullanımdan düzeltmeler (2026-11-20). pytest 147, e2e 54/54.
- **Sohbet başına taslak** (lib/drafts.js, Composer): her sohbetin yazı kutusundaki metin + ekler localStorage'da
  tutulur; sohbet yeniden açılınca, sayfa yenilenince ya da elektrik kesilince geri gelir; resimler base64'ünü
  GET /api/sessions/{sid}/upload/raw ile geri alır. İlk yüklemeyle oluşan yeni sohbet taslağını korur.
- **Düşünce gösterimi** (lib/thinkfmt.js): düşüncede çitsiz HTML / kod dil etiketli kod bloğuna, ayraçsız tablo
  |---| satırlı tabloya dönüşür; canlı kutu ve kayıtlı "Düşünüyor" adımı Markdown olarak çizilir (adım <pre> idi).
- **edit_video**: nesne / metin / .mp3 olarak verilen `narration` tek seslendirmeye dönüşür (nesne KeyError 0 =
  "Missing required argument: 0" ile çöküyor ve ses düşüyordu); seslendirme yoksa sonuç "NO voice-over" der.
  KeyError mesajı artık bir değerin biçiminin yanlış olabileceğini söyler.
- **speech_to_text**: ses ffmpeg ile çözülür (faster-whisper'ın PyAV okuyucusu PyAV 19'da metadata_errors ile bozuldu).
- **Teslim kontrolü**: cevaptaki dosya adları Türkçe harf / büyük-küçük harf farkı gözetmeden eşleşir
  (`checks.real_path`, `fold_name`); son cevaba yanlış "oluşturulmadı" notu yerine gerçek yol yazılır
  (`fix_claimed_names`).
- **Sesler**: önizleme düğmesi ikinci basışta durdurur; Chatterbox kurulum ilerlemesi paket ve model klasörü
  boyutunu izler (3 GB model inerken %60'ta duruyordu).

## Proje Durumu — v0.17.0
Yerel stüdyo sesleri ve pro seçiciler (2026-11-20). pytest 144; gerçek testler: 4 Türkçe Piper sesi + Kokoro
kuruldu ve ölçüldü, her motor API üzerinden çalıştı (önizleme Piper 0,7 sn, Kokoro 1,2 sn, Edge 6,7 sn), altyazısı
yakılmış seslendirmeli video (-15,3 LUFS). Chatterbox (3 GB model) gerçek testi: Türkçe 10 sn konuşma işlemcide
33-45 sn; kendi ses referansı izlendi (çıkış 97 Hz, referans 103 Hz; varsayılan ses kadın). resemble-perth
Windows'ta PerthImplicitWatermarker'ı None bırakıyordu ("'NoneType' object is not callable"): işçi işlem yapmayan
filigrana geçer.
- **backend/app/voice/** (yeni): `catalog.py` (Piper dizini + ek Türkçe sesler fahrettin / fettah / 99eren99,
  Kokoro v1.0 int8, Chatterbox dilleri, ilerlemeli kurma / kaldırma, perdeden cinsiyet: otokorelasyon F0, < 160 Hz
  erkek; ölçülen dfki 97, fahrettin 108, 99eren99 83 = erkek, fettah 182 = kadın), `engines.py` (Piper, Kokoro,
  Chatterbox KENDİ uv ortamında data/tts/chatterbox/venv tek kalıcı işçiyle - chatterbox-tts numpy<2 / torch 2.6
  sabitler; Edge ffmpeg ile çözülür), `studio.py` (tek ffmpeg geçişi: none/natural/podcast/broadcast/video/warm,
  tempo korunarak perde, oda yankısı, loudnorm), `render.py` (cümle bölme, kırpılmış duraklamalar, zamanlamalar ->
  .srt, "İsim: satır" diyalogları, dil + cinsiyet + motor sırasına göre yedek zinciri; ayar `voice`).
- **Bağlantılar:** `tts.synthesize` (sesli yanıt / önizleme) ve `speech.text_to_speech` render'dan geçer;
  text_to_speech aracına pitch / emotion / pause / studio / speakers / srt eklendi; edit_video sesi "video" işlemesi
  alır, `subtitles: true` seslendirme cümlelerini videoya yakar (`_burn_subs`, libass, yanına .srt).
- **API:** GET /api/voices, POST /api/voices/install (arka planda, ilerleme), DELETE /api/voices/{id},
  POST /api/voices/preview (ton), POST /api/voices/reference (kendi ses, onay zorunlu); /api/tts/voices birleşik.
- **Kurulum:** "voices" adımı (backend/voice_setup.py: fettah + 99eren99 + Kokoro, PROGRESS satırları);
  gereksinimler: piper-tts, kokoro-onnx (Chatterbox Ayarlar'dan kurulur, asla .venv'e değil).
- **Arayüz:** Ayarlar > Sesler sekmesi (VoicesPane.jsx), yeni VoicePicker (filtreler, indirme, motor / kalite
  rozetleri, ton kaydırıcıları), lib/voices.js; `Select`'e telefonda alttan sayfa, size="sm", nokta / ikon
  seçenekleri eklendi; tüm yerel <select>'ler değiştirildi (görsel/video modeli, Video Stüdyo, Logo, STT); range /
  checkbox / radio / color / file için ortak CSS, telefonda 16 px alanlar.

## Proje Durumu — v0.16.1
Ortak ayar senkronu ve komutlarda Android araç zinciri (2026-11-20). pytest 137.
- **Cloudflare senkronu (arayüz):** görsel kartına yazılan Hesap Kimliği sağlayıcının model listesini hemen yeniler
  (sağlayıcı kartında eski "Account ID is not set" hatası kalıyordu); bir anahtar ya da anahtar düğmesi herhangi bir
  yerde değişince servis rozetleri yenilenir; görsel kartındaki alan kayıttan sonra kayıtlı değeri gösterir. Yeni hata
  kodu `missing_account` (TR/EN).
- **Komutlarda Android / Kotlin:** `mobile.add_to_run_env`, data/mobile içindeki Gradle, adb, emulator, sdkmanager,
  Maestro ve JDK'yı her `run` komutunun PATH'ine ekler (kullanıcının kendi PATH'inden sonra; ANDROID_HOME/JAVA_HOME
  tanımlı değilse). `system_info` araç zincirini listeler (`android_kotlin_toolchain`). Bir model "Gradle yok, Kotlin
  yok" demişti.
- **PowerShell 5.1 gürültüsü:** `tidy_ps_errors`, `2>&1` ile bir programın stderr satırlarına eklenen hata kaydı
  satırlarını (At ...ps1, + CategoryInfo, NativeCommandError) siler; `java -version` artık hata gibi görünmez.

## Proje Durumu — v0.16.0
Medya servisleri, canlı model listeleri, bağlantı denetimi (2026-11-20). pytest 133, mock uçtan uca 54/54; kullanıcının
anahtarlarıyla yalıtılmış geçici klasörde gerçek testler (8 bulut sağlayıcı, 6 Cloudflare görsel modeli, stok, ücretsiz
Wan 2.2 klip).
- **Bağlantı denetimi (streaming.py `_liveness`, router.ping):** 20 sn susan bulut akışına yeni bağlantıdan 1 token'lık
  yoklama: yanıt var -> akış 30 sn'de (aracı bütün gönderen sağlayıcılarda 90 sn) kaldığı yerden sürer, yavaş ->
  beklenir, hata -> sunucu hatası, ulaşılamıyor -> internet / sağlayıcı. Arayüz: hazırlanıyor adımında `probe_*` metinleri.
- **Video servisleri (animate.py, services.CATALOG video türü):** Veo (Gemini anahtarı), fal.ai, Replicate, Runway, sonra
  ücretsiz HF Space'leri; her biri açılıp kapatılır, aynı anda biri çalışır. `/api/video/test/{sid}` (ücretsiz anahtar
  denetimi, `?real=true` klip üretir). (+) > Resimden video. Ayarlar > Web > AI video eski motor kartının yerini aldı.
- **Medya modelleri (tools/mediamodels.py):** servis başına varsayılan + yalnızca o türden seçenekler (Gemini /
  Cloudflare canlı); media.models / video.models ayarları; Cloudflare FLUX.2 multipart; Imagen predict.
- **Ortak anahtarlar:** medya kartına girilen anahtar sağlayıcıyı da açar, tersi de; tek Cloudflare hesap kimliği.
- **Model listeleri:** Gemini kendi API'sinden (pencere, düşünme, görsel, araç); `NOT_CHAT` gömme / ses / koruma /
  yalnızca görsel modelleri her yerde gizler; `infer_caps` adlardan; kapatılan modeller (`model_retired`) gizlenir ve
  istek önerilen yeni modele gider; OpenRouter "reasoning is mandatory" düşünme açık tekrar denenir.
- **MCP:** hazır sunucular tek tıkla eklenir, açılıp kapatılır, silinir; kendi sunucular ayrı sekmede.
- **Kurulum:** konsol uyumlu işaretler, Android kurulumunda canlı ilerleme (`Meter`, `PROGRESS` satırları), gerçek hıza
  göre kalan süre.

## Proje Durumu — v0.15.1
İnternet kesintileri ve kurulum (2026-11-20).
- **Ağ izleyici (`backend/app/netwatch.py`):** her 10 sn'de (çevrimdışıyken 3 sn) DNS + TCP (ya da sistem proxy'si)
  denenir; iki başarısız denemede çevrimdışı, bir başarılıda çevrimiçi sayılır. Değişiklik arayüze gider
  (`system`/`net` olayı, `hello` içinde de): kalıcı "bağlantı kesildi", sonra "geri geldi (N sn kesik kaldı)" bildirimi.
- **Görevler:** bulut modelde ağ hatası `check_now()` ile denetlenir; bilgisayar çevrimdışıysa görev süre sınırı
  olmadan (durdurulabilir) bekler, kotadan deneme harcamaz, model değiştirmez, "parçalı yaz" ipucu almaz; bağlantı
  gelince aynı model ve konuşmayla sürer (`ai_note_back_online`). İzleyici çevrimdışı derken susan akış, takılma
  sınırına kadar beklemek yerine 6 sn'de kesilir.
- **Araçlar:** web araçları (arama, yerel olmayan adres okuma, görsel/video üretimi, seslendirme...) hata vermek yerine
  bağlantıyı bekler; tekrar koruması kesintiden sonra aynı çağrıyı reddetmez (`tooling._run_tool`).
- **Arayüz:** sohbette geçen süreyle "İnternet yok — bağlantı bekleniyor" kutusu; TR/EN metinler; rehber bölümü.
- **Kurulum:** önce bağlantıyı denetler (3 deneme), Windows proxy'sini pip/npm/playwright'a geçirir, çevrimdışıyken
  kurulu olanlarla sürer (`pip --no-index`) ve eksik paketin adını söyler; kayıtta boş satır yok.
- **Temiz zip:** `chat/`, `data/`, `workspace/`, önbellek ve nokta klasörleri yok.
- Testler: `tests/test_netwatch.py`; uçtan uca `NETCUT` senaryosu (`AIIQ_NET_SIM` ile benzetilen kesinti).

## Proje Durumu — v0.15.0
2026-11-20 turu: uzun gerçek çalışmaların adım kayıtlarındaki (PHP mağaza, Kotlin hesap makinesi, Android SDK
güncelleme; `hatalar/`) her hata kök nedenine kadar izlendi ve düzeltildi, ayrıca kullanıcının bu turdaki istekleri
yapıldı. pytest 120, mock uçtan uca 43/43.
- **Etiket protokolü:** nitelik olarak gönderilen bütün dosya (`content="..."`, ayrıca `old=`/`new=`) gerçek sonuna
  kadar okunur (`stream_parser.big_attr_call`); önceden her app.js yazımı `cart: '<svg viewBox=` noktasında (ilk tırnak)
  kesiliyordu. DeepSeek `<｜DSML｜invoke>` çağrıları ayrıştırılır; `</parameter>`, `</tool>`, DSML artıkları notlara
  sızmaz (parçalar arasında tutulur). `todo` sondaki virgülü, tek tırnağı, çitli JSON'u ve düz satırları kabul eder.
- **edit_file:** SEARCH/REPLACE işaretleri kendi satırında olmalı - JS `===` ayırıcı sanılıp dosyalara `=======`
  yazılıyordu. İşaret bırakacak düzenleme / yazma reddedilir.
- **write_file:** boş yeni dosya, bozuk yol (`b u i l d . g r a d l e`), uygulama kayıt satırları (`[To-do ...]`)
  reddedilir / çıkarılır; bozuk karakter (U+FFFD) ve geçici dosya adları bildirilir.
- **Zorunlu 8K bölme yok:** "~8.000 karakter, bu sağlayıcı uzun çağrıları düşürüyor" notları Ayarlar > Ajan > bölerek
  yazma ayarına uyar (kapalı = tek çağrı). 75 sn'lik "araç çağrısını ancak bitince gönderiyor" kesmesi kaldırıldı
  (yazılmakta olan çağrıyı atıyordu); EVREN'in araç argümanlarını akıttığı bilinir.
- **Döngüler:** tekrar, kelime salatası (`_salad_cut`) ya da eyleme geçmeden 48K karakter düşünme kesilir ve tur sağlam
  kısımdan yeniden yapılır (taşınan düşünce, düşünmesiz istek, tekrar cezası); cevap orada bitirilmez.
- **Görevin hafızası:** okunup sonra değişmeyen dosyalar geçmişte bütün kalır (pencerenin dörtte biri,
  `_kept_reads`); todo listesi (`todo_board`) her model devrinde, devam ettirmede ve açık madde notunda gider; birden
  çok dosya adlayan madde hepsi yazılınca işaretlenir; sunucu başlatma kendi maddesini işaretler; `dosya:satır`
  bildiren başarısız komuta o satırlar diskten eklenir (`error_context`).
- **Yönlendirme:** görev sürerken gelen mesajlar birlikte, kullanıcının sözü olarak çitlenmiş, todo listesi ve kısa bir
  kuralla (düzeltme / yeni yön / soru) iletilir; eski taşınan plan düşürülür.
- **Anahtar kelime değil seçim:** yetenekler tetikleyici kelimelerle yüklenmez; model tüm yetenek ve ajanları
  amaçlarıyla görür ve seçer (takım üyeleri ajan rolü alabilir). "Soru" için salt-okuma sınırı yumuşaktır: model
  need_tools ile kaldırır.
- **Android:** `mobile_env status` tüm yolları, kurulu platform / build-tools / imajları, doğrulanmış sürüm setlerini
  (compileSdk 36 = AGP 8.11.1 + Kotlin 2.1.21 + Gradle 8.13 + JDK 17/21) ve kuralları verir; yeni `gradle` ve `sdk`
  eylemleri; Maestro çalışma klasöründe koşar; makinede zaten olan SDK / JDK (Android Studio) kullanılır, sadece
  güncellenir.
- **Kabuk UTF-8:** PowerShell çıktısı, `Get-Content` ve Java araçları (Maestro) UTF-8 okur ve yazar.
- **Arayüz:** canlı düşünce sabit yükseklikte, sonu izleyen bir kutuda akar ve düşünme bitince kapanır; uzun kullanıcı
  ve yönlendirici mesajları Markdown ve kodla katlanır (Daha fazla / az göster); Vite parça uyarıları yok.
- **Kurulum / çalıştırma:** `installer.py` (install.bat çağırır): adımlar, ilerleme çubuğu, geçen / kalan süre, kayıt,
  Türkçe Windows'ta Türkçe diğerlerinde İngilizce, mevcut olanı kullanan mobil kurulum. `run.bat` / başlatıcı: başlık
  kutusu ve okunaklı renkli log (sık yoklamalar gizli, `--verbose` hepsini gösterir).
- **Kod düzeni:** `orchestrator.py` 4.288 -> 1.988 satır (learning, runstate, guards, history, continuity, prompting,
  streaming, tooling); `registry.py` 2.924 -> 459 satır (shell_tools, file_tools, web_tools, media_tools, doc_tools,
  agent_tools). Her ad yeniden dışa aktarılır; TOOLS sırası korunur.

## Proje Durumu — v0.14.3
Süreklilik turu; `evren:qwen3.8-flash-next` ile 4 sa 16 dk süren gerçek testle kanıtlandı (BakkalX Expo + Express +
yönetim paneli + iyzico/PayTR görevi: 301 model turu, 9/9 yapılacak, API duman testi 24/24, iki tarafta `tsc --noEmit`
0 hata, tek bağlantı kopması 1 sn'de toparlandı). pytest 102, mock e2e 43/43.
- **Düşünce kopmada korunur:** `_carry_thinking`, kopan turun (duraklama, zaman aşımı, kopma, model değişimi)
  düşüncesini sonraki isteğe taşır (`THINK_CARRY`, en çok 14K karakter, tek mesaj, devam eden cevaptan önce) ve o
  istek düşünmeden gönderilir (`run.no_think`; EVREN: `chat_template_kwargs.enable_thinking=false`, ölçüldü: 0 düşünme
  tokenı; `reasoning_effort` orada yok sayılıyor). Önceden her yeniden deneme tüm görevi baştan düşünüyordu (birkaç
  kopmada 18 dakika "düşünüyor"). Zaman aşımı / takılmada aynı model iki kez denenir, sonra değiştirilir.
- **Akıtan sağlayıcı "sessiz yazar" sayılmaz:** ölçümler EVREN'in araç argümanlarını parça parça akıttığını gösterdi
  (2.289 parça, en uzun boşluk 2,7 sn). `router.mark_streams_tool_args` bunu sağlayıcı başına öğrenir
  (data/streams_args.json); böyle bir sağlayıcı 75 sn'de "araç çağrısını sonda gönderiyor" diye kesilmez, metin
  protokolüne geçirilmez, stream_tools.json'daki yanlış kayıtlar silinir. "Düşünme bitti" bekleme metni artık
  sağlayıcının sonda gönderdiğini söylemiyor.
- **Anlık silme:** sohbetler hemen kaybolur (iyimser liste, siliniyor / silindi bildirimi); sunucu görevlerini paralel
  durdurur, geliştirme sunucularını kapatır, satırları siler, `session.deleted` yayınlar, klasörü arka planda siler
  (node_modules tüm uygulamayı kilitliyordu). Çalışan sohbetin mesajları silinince 409 yerine görev durdurulur.
  `db.add_message` silinmiş sohbete yazmaz.
- **İstek seli yok:** `/api/models/health` değişiklik olunca `_health_watch` ile WebSocket'ten itilir (sayfa açılışta,
  odakta en fazla 30 sn'de bir ve dakikada bir sorar); bağlam paneli görev sırasında 4 sn yerine 30 sn'de bir yenilenir.
- **system_info part=software:** çalışma klasörü ve bağımlılık dosyaları, kabuklar, CLI araçları, uygulama Python
  paketleri, global npm paketleri, MCP sunucuları ve araçları, etkin arama motorları, kullanılabilir stok / görsel
  servisleri, GitHub bulma ve indirme yolları, yetenekler, ajanlar, komutlar, sağlayıcılar.
- **Adımlar Markdown olarak:** her görevin adım listesinde kopyala / .md indir düğmeleri (`stepsMarkdown`).
- **Canlı testten düzeltmeler:** geçmişteki eski dosya gövdeleri tek satır olur (`_gone_body`) - model "ilk 300
  karakter + kısaltma notu" kalıbını yeni dosyalara kopyalıyordu, dört yazım reddedildi; path'siz write_file append
  yazılmakta olan dosyaya gider; search_code `regex=` içinde gönderilen deseni alır; browser_wait (en çok 60 sn) boş
  kalan ve hata veren sayfada hemen biter; browser_navigate yerel SPA'nın çizilmesini 20 sn'ye kadar bekler; konsol
  kayıtları URL'leri ve başarısız isteklerle gelir; HTML JS kontrolü file:// altında yalnız sunucuda çalışan
  referansları atlar; hazırlanıyor adımı dosya adını (ya da henüz gelmediğini) gösterir.

## Proje Durumu — v0.14.2
Kod taraması (ruff, pyflakes, ön yüzde ESLint, pytest 87, mock e2e 43/43) ve büyük gerçek model testi: Expo +
TypeScript "market süper uygulaması" evren glm-5.3 (503 -> evren auto) ve gemma-4-31b ile uçtan uca kuruldu.
- **Dürüst bitiş:** `missing_deliverables` isteğin adını verdiği kaynak dosyaları da denetler (`REQUESTED_SOURCE`,
  ör. `data/mockProducts.ts`); `_on_disk` node_modules / build klasörlerine girmez. Düzeltme notları uygulamadan
  geldiğini ve sonraki cevabın tam son cevap olması gerektiğini söyler (rapor "düzelttim" ile değişiyordu).
- **Yazımda sözdizimi denetimi:** `write_file` / `edit_file` sonrası `syntax.syntax_errors` (Python `compile`, diğer
  diller tree-sitter; `_syntax_note`); bozuk dosya ayrıştırılana kadar `unresolved` kalır (`track_syntax`).
- **Sorun başına hata ayıklama sınırı:** `max_debug_attempts`, çalışan bir komuttan ya da daha az hata satırından
  sonra yeniden başlar (`ran_ok`, `last_err_count`); yakınsayan tsc döngüsü 5'te kesiliyordu.
- **Kabuk argv:** `argv` + `shell=powershell|bash|cmd` ile programı PATH'te olmayan komut (`Move-Item`, `mv`) o kabukta
  çalışır (`_shell_join`), "kurulu değil" denmez.
- **Takılma sınırı:** `_heartbeat`'in uyarlamalı 45 sn sınırı düşünmenin hemen ardından uygulanmaz (EVREN araç
  çağrısını ancak bitince gönderir); mesaj, sınırın akışın hızından geldiğini söyler.
- **Devre kesici yok (kullanıcı isteği):** hata sayısı artık araçları kapatmaz (`max_debug_attempts` aynı hata
  eşiği oldu, varsayılan 3; `STUCK_STOP` kaldırıldı, `fail_streak` her 4'te uyarır). Aynı hata yeniden gelirse model
  araştırıp denenmemiş bir yol seçer; yalnızca birebir tekrarlanan çağrılar (`round_sigs`) durdurulur.
- **Her şeyi kurabilme:** `mobile.install_java` / `mobile_env action=java` (Adoptium API'den taşınabilir Temurin 17,
  data/mobile/jdk; MSI yok, yönetici yok; `setup` kendisi çağırır); MSI 1618 için `ERROR_PLAYBOOK` (taşınabilir / bekleme).
- **Her sayfada denetim:** `BrowserAgent.news()` her sayfa işleminden sonra console hatalarıyla birlikte başarısız
  istekleri (4xx/5xx, yüklenemeyenler) bildirir ve önce düzeltilmesini ister; `browser_check` ağ hatalarını da listeler.
- **Uzun görevler:** ilerleme özeti görevde yazılan tüm dosyaları listeler (diskte var; düzenlenir, yeniden yazılmaz);
  çalışma kuralları: adımın dosyalarını planla, hepsini tek cevapta yaz, sonra bir kez denetle.
- **Bekleme:** "sağlayıcı yoğun olabilir" yerine `after_think` aşaması ("düşünmeyi bitirdi, cevabını yazıyor").
- **Arayüz:** en alta git butonu ve video göstergesi artık yana kaymıyor (animasyon Tailwind 4 `translate`'ine ikinci
  bir -50% ekliyordu).
- **Gerçek tarayıcıda son test:** `_verified` başlatılmış sunucuyu artık test saymaz; yalnızca sayfayı açmak
  (tarayıcı araçları, web_screenshot, mobile_env) sayılır. Çalışma kuralları / SYSTEM_CONTRACT / mobil beceri: web ve
  Expo web uygulamaları browser_navigate ile açılır, her console / ağ hatası giderilir. `PAGE_ERR`, `HTTP 5xx`,
  `JS error`, 404 js/css, reddedilen paketleri ve sayfa denetimi notunu tutar. Başarısız istekler yanıt anında
  kaydedilir (`BrowserAgent.bad`); 404 / 500 istek kayıtlarında önceden durum kodu yoktu.
- **edit_file:** tutan bloklar kaydedilir, tutmayanlar güncel dosyayla bildirilir (7K altıysa tamamı).
- **todo:** kısa güncellemeler `advance` / `done` / `start` / `add` (`todo_patch`); her sonuçtaki hatırlatma artık tüm
  listeyi yeniden göndermeyi istemiyor (bir Expo görevinde 26 kez tam liste yazılmıştı).
- **Tur 6 sonrası düzeltmeler:** `todo_patch` sayıları her biçimde okur ("4,5,6", "4-8"); `_babble_cut` farklı dillerde art arda gelen minik satırları ("BOOM.", "LFG.", "火.") keser, sonraki istek tekrar cezasıyla gider; edit_file her anahtar yazımını alır (`oldText`, `old_str`, iç içe `changes` / `replacements`); olmayan dosya için klasörün gerçek içeriği listelenir; yerel sayfalar tarayıcı önbelleği kapalı yüklenir; canlı alan son notu yalnızca ondan sonra iş yapılmadıysa gösterir; döngü imzası defter tutma çağrılarını (`BOOKKEEPING`) saymaz, araçları yalnızca 6 birebir aynı tur kapatır.
- **Sohbet medyası:** cevaplardaki yerel dosya bağlantıları (`[x](screenshots/a.png)`) uygulamada açılır (düz bağlantı olarak uygulamanın kendi sayfasına gidiyor, sohbet yenilenmiş gibi görünüyordu); cevap resimleri 460×256 ile sınırlı; görev ekran görüntüleri kompakt kaydırmalı sıra (telefon görüntüleri telefon çerçevesinde, masaüstü tarayıcı çerçevesinde). `wrong_language` diğer Latin dillerini de yakalar (Türkçe sohbette Fransızca cevap); Windows uzun yol hataları için `ERROR_PLAYBOOK`.
- **Tanıtım videosu:** tanitim/video (TR/EN, 16:9 ve 9:16), gerçek panel sahneleri, Gemini seslendirme, CC BY fragman müziği.
- **Diğer:** zaten bitmiş süreçte `stop` hata değil; yeniden derlenmiş paketin dosyaları yoksa ön yüz bir kez kendini
  yeniler (`vite:preloadError`, 404 stil dosyası).
- **Expo:** `create-expo-app --template typescript` (TypeScript paketini iskele yapar) ve `@types/*` 404 için
  `ERROR_PLAYBOOK`; `mobile-app-test` becerisine iskele bölümü (`blank-typescript` / `tabs`, `npx expo install`).
- **Diğer düzeltmeler:** projesiz sohbetin çatalı klasörünü de kopyalar; `messages.jsonl` temizliği yarım satırı
  atlar; `process_manager` 64 KB üstü `\r` ilerleme çubuklarını boşaltır, öldürülen süreci sonsuza dek beklemez;
  `mobile.py` (log satırsız AVD listesi, adb yok, zaman aşımında kill); PROJECT_STATE / summary.md başlıkları
  İngilizce; başlatıcı ve e2e çalıştırıcı Windows konsolunda UTF-8 yazar.

## Proje Durumu — v0.14.1
- **Mobil test:** `tools/mobile.py` (durum / kurulum / başlatma / adb / ekran görüntüsü / Maestro; Android SDK, emülatör, Pixel AVD data/mobile altında; `java_home()` PATH dışındaki JDK 17+'yı bulur), `mobile_env` aracı (`mobile` grubu), install.bat / install.sh'in istenince çağırdığı `backend/mobile_setup.py` (`AIIQ_MOBILE`), `mobile-app-test` yeteneği.
- **AI video:** `generate_video` (`imagegen.generate` ile ilk kare, sonra `animate.animate`), `/api/video/engines` (HF Space çalışma durumu), Ayarlar `VideoEnginesCard`, (+) > Oluştur > AI klip.
- **Araçlar:** `venv_pip` / `PIP_CALL` her pip çağrısını uygulama Python'una yönlendirir (argv dahil); `_unquote_arg`; PATH'te olmayan program için `INSTALL_HINT`; `fetch_url save=` + `_download`; `_github_repo` (dosya dosya 4. okuma -> ZIP); görev klasöründen `cd`; `start` içinde `_port_of` / `_port_busy`; `ERROR_PLAYBOOK` (+ gh auth, yanlış bayraklar); make_doc'ta `placeholder_marks`; stok fotoğraf için `_provider_of`.
- **Orkestratör:** `_auto_todo` yalnızca devam eden maddeyi kapatır; todo birleştirme bitmiş maddeyi yeniden açmaz ve tek "devam ediyor" bırakır; başlık yalnızca `title_auto == 1` iken; `_step` `ACTION_ECHO` satırlarını (tam satır) temizler; bağlantı kopmasında 1 sn sonra yeniden deneme; yetenekler `triggers:` ile otomatik yüklenir (docs, video-studio, localhost-project, mobile-app-test).
- **Ön yüz:** `RangeField` ∞ / Kapalı / Otomatik düğmeleri; `Markdown` resim çözümleyici (sohbet klasörü); `stripActionEcho`; `RichInput` ertelenmiş execCommand; `DocPreview` slayt yerleşimi (`tools/slides_view.py`: konumlu yazı / resim / tablo / grafik, yer tutucu varsayılanları) ve Excel ızgarası (formül çubuğu, birleşik hücreler, genişlikler, dolgular); rehber bölümleri create / testing / settings-buttons.
- **Son düzeltmeler (canlı paket evren auto ve gemma-4-31b ile 9/9):** `editing.parse_blocks` blok türevlerini, JSON düzenleme listelerini ve unified diff'i kabul eder, `edit_file` old/new takma adlarını ya da dosyanın tamamını alır; `stream_parser.attrs` tek tırnaklı öznitelikleri okur; `mcp` aracı `arguments`'ı JSON metni ve üst düzey alanlar olarak alır, eksik zorunluları söyler; `PLACEHOLDER` HTML etiketlerini yakalamaz; `meta.docs` betikle üretilen belgeleri listeler (önizleme kartları); `_make_title` akıl yürüten modellerde geniş bütçeyle, sonra yardımcı modelle yeniden dener; `request_steps` numaralı isteklerden yapılacaklar listesini açar; kaynaklı cevap ajanlarına bir kez araştırma hatırlatılır.
- **Büyük görev düzeltmeleri (evren auto / gemma-4-31b / glm-5.3 ile 15-20 dk gerçek testler):**
  - Model değişimi ve devir: dosya ortasındaki takılmada `_busy_alternative` için `retries >= 2` gerekir; bulut sağlayıcılarda `_heartbeat(adaptive=True)`; quota / payment / plan_required havuz olmadan da başka modele geçer; her geçiş noktasında `HANDOVER` notu.
  - Döngü ve üzerine yazma koruması: yazma / ekleme / kurtarmada `editing.collapse_repeats`, akış sırasında `_file_loop_check` (ProviderError `looping`, `run.file_loops` -> `frequency_penalty`); kurtarılan yolun düz yazımı eklemeye döner; okunmadan üzerine yazılan 1.500 karakterden büyük dosyalar `.session/backups`'a yedeklenir.
  - Yapılacaklar ve test: `todos_auto` + modelin listesiyle birleştirme; yazılı plandan `plan_steps`; `tool_turns == 4` iken tek seferlik liste hatırlatması; `VERIFY_ASK` / `VERIFY_TOOLS` test edilmemiş çalıştır-ve-test yanıtını bir kez geri gönderir (`ai_note_not_verified`).
  - Araçlar: `read_file` `ctx.read_limit`'e (pencerenin %15'i, 12K-40K) kadar tam satır ve sonraki aralığı verir, aynı aralığın tekrarı `read_seen`'den yanıtlanır; `SERVER_CMD` `npm run web/preview`, `expo start`, `flutter run`, `artisan serve`'ü kapsar; başarısız yazım adımının ayrıntısı araç çıktısıdır; `JAVA_HINT` ve `mobile-app-test` önce tarayıcıyı, kurulumda yalnız paket yöneticisini kullanır.
  - Ön yüz: `ProviderIssue` ve `toolErrorLine` (`te_*`, `te_binary` dahil).
  - Tarayıcı: `BrowserAgent.target()` (eskiyen ref -> `remember_refs`'teki rol + ad, etiket / placeholder / tam metin önceliği, ilk görünür eşleşme, gizli eleman hemen bildirilir), örtülü elemanda betikle tıklama, yerel sitelerde ve model işlem yaptıktan sonra `dismiss_popups(cookie_only)` (`acted`), `_batch_step` / `BATCH_ALIASES`; `start` sohbetin kendi sunucusunun portunu betik dosyasından okur; `stop` port veya tek sunucuyu kabul eder; tekrarlanan etkisiz `edit_file` hata sayılır.
  - `fail_streak` model turu başına bir sayılır (`turn_idx` / `fail_turn`); `_summarize_progress` özeti yerine geçtiği metnin dörtte biriyle sınırlar; `verify.MAKERS` resim retinde `stock_photo` / `generate_image` önerir; `CD_ONLY` satır sonunda durur; `FIELD_NEAR_JS` (for= olmayan etiket -> alanı); `_target_keys` (element / target / locator).
  - `SCRIPT_ONLY` tek başına betik adını yorumlayıcısıyla çalıştırır; `read_file` SQLite dosyasını (tablolar, satırlar) açıklar, diğer ikili dosyaları reddeder; `Run.outcomes` aynı çağrının üçüncü aynı sonucunu hataya çevirir; `request_parts` model liste açmazsa 3. turda listeyi açar; açılır liste seçenekleri metin/değerle eşlenir, `browser_form` `{etiket: değer}` alır.
  - `local_page_instead` (web_screenshot, browser_check, browser_navigate): ölü localhost portunda sayfanın HTML dosyası açılır; `_verified` / `TEST_CMD` (kurulum test sayılmaz); `files_nudged` (yazılmayıp cevaba dökülen kod); `todo` kullanıcının dilini ister; `shell=php|python|node` ile dosya adı dosyayı çalıştırır.

  - Son tur: her çalışma isteminde `SYSTEM_CONTRACT` (prompts); `PLAN_GATED` + `plan_refusals` (plan kapısı, request_parts yedeği); `_photo_for` kaldırıldı (resim yazımı stock_photo çağrısıyla reddedilir); `round_sigs` döngü dedektörü, `counted` (yalnız sayı değişen döngüler), `MEDIA_CAP`, `tools_off`; `failure_signature`; `shrink_old_steps` (eski araç trafiği kısaltılır, KEEP_RECENT=6); `ctx_peak` -> `context_stats._peak` (ContextPanel `ctx_peak`); make_doc'ta `_anchor_images`, `docs_gen._image_bytes` file: URI; yorumlayıcı bayrakları (`shell=php -S ...`) `php -S ...` olarak çalışır; alt süreçlerde `PYTHONUTF8`; `_wait_online`; `test_every_tool_runs_its_own_function`.
  - Sonra: `APP_MARKS` / `app_placeholder` uygulamanın kısaltma notlarını dosya içeriği olarak reddeder; `page_state` / `PAGE_ERR` sayfası hata gösteren görevi açık tutar; `<option>` tıklaması üst select'te seçer; yerel sitelerde confirm() kabul edilir; `OLD_STEP_MARK` (`SHRUNK` ile çakışıyordu).

## Proje Durumu — v0.13.0
Medya ve araç turu; EVREN `auto` ve GLM 5.3 ile canlı test edildi; 49 birim testi (`tests/test_checks.py`, `test_media_services.py`, `test_studio.py`, `test_tools.py`) + 43 uçtan uca denetim.
- **Servisler (`tools/services.py`):** anahtarlı görsel (HF, Together, OpenAI, Gemini, Stability, Cloudflare) ve stok (Pexels, Pixabay, Unsplash) servisleriyle sistem servislerinin (Pollinations, Openverse, Commons) `CATALOG`'u; `run()` kullanılabilenleri sırayla dener, `QuotaError` servisi sıfırlanana kadar engeller, en son sistem servisi cevap verir; kullanım `data/service_usage.json`'da; `/api/services`, `/api/media/test/{id}`, `/api/stock/test/{id}`.
- **Video motoru (`tools/video_edit.py`):** zaman çizelgesi JSON'u (sahneler, klipler, müzik, ses, logo, efektler, görünüm, oran), yama biçimi (`scenes{"n":…}`, `clips{"n":…}`, `add_*`, `remove_*`), `numbered_view` (modelin gördüğü: `#` + klip türü), yazı stilinin yazı olmayan klibe gitmesini reddeden koruma, serbest biçimli yazı (`free_text`), `EFFECTS` + `effect_chain`, zoompan/xfade, loudnorm + sidechain kısma, `-/filter_complex` ile filtre grafiği; projeler `<ad>.timeline.json`.
- **Stüdyo API'si (`main.py`):** `/video/media`, `/video/project` GET/PUT, `/video/render`, `/video/ai` (hatayla beslenen bir yeniden denemeli model yaması), `/video/voice`, `/api/video/music` (`tools/music.py`, 8 çevrimdışı stil), `/api/music/library` (yeniden deneme/yedek sorgulu Openverse), `/music/download` (+ CREDITS.txt), `/api/stt`, logo uç noktaları (`tools/logo.py`). `tools/animate.py`: `gradio_client` ile HF ZeroGPU Space'lerinde resimden video.
- **Ön yüz:** `VideoStudio.jsx` (sürüklenip boyutlanan yazı ve katmanlı sahne, denetçi, zaman çizelgesi, `focus()` = neye tıklanırsa ayarlarını açıp oraya gider, müzik kütüphanesi, seslendirme, efekt önizlemesi, canlı AI günlüğü; telefon düzeni: sabit sahne / araç çubuğu / zaman çizelgesi + kayan panel, `pointer:coarse` dokunma tutamaçları), `VoiceLibrary.jsx`, `LogoMaker.jsx`, (+) menüsünde renkli Oluştur bölümü, `lib/errors.js`; backend'deki her `fail()` kodunun TR/EN `err_<kod>` çevirisi var.
- **MCP (`mcp_client.py`):** OAuth 2.1 (bilgi keşfi, DCR, PKCE, `/api/mcp/{id}/oauth`, geri dönüş), `split_command` (npx `-y`), `mcp_search` aracının arkasında `search_servers` (kayıt, npm, GitHub; resmiler önce).
- **Yetenekler:** `video-studio`, `localhost-project` (her yığını localhost'ta: tanı, Win/macOS/Linux'ta çalışma ortamı/paket/veritabanı kur, başlat, test et, raporla). Yetenek dosyasında isteğe bağlı yeni `triggers:` regex'i (`catalog.matching_skills`): eşleşen isteğin sistem istemine "önce use_skill X" satırı eklenir.
- **Döngüler ve hata ayıklama (PHP projesinde gerçek EVREN çalışması):** `checks.ERROR_PLAYBOOK` / `error_playbook()` (yaygın hatalar için yollar); hata ayıklama dalı `same_rounds` sayar ve ikinci aynı hatada pes etmek yerine denenmiş komutları listeleyip farklı yol ister (3'te, sınırsız modda 6'da bırakır); `Run.fail_streak` (`STUCK_WARN`=4 not, `STUCK_STOP`=10 araçlar durur, cevap istenir); `Run.fs_epoch` hiçbir şey değişmeden tekrarlanan `list_dir` / `read_file` / `search_code`'u reddeder; okuma araçları `run.blocked`'a asla girmez. `fetch_url` `save=` + arşiv/kurulum dosyalarını otomatik indirme (`_download`, `DOWNLOAD_EXT`), `_github_repo` bir deponun dosya dosya 4. okumasını ZIP talimatına çevirir, GitHub API 403/429 açıklanır; `list_dir` yolları çalışma klasöründen, olmayan yollar için `_did_you_mean`. Yetenekler `triggers:` ile otomatik yüklenir (araçları daraltmadan), `ai_note_skill_auto`.
- **Testler:** `tests/conftest.py`, herhangi bir test modülü yüklenmeden `AIIQ_DATA`'yı geçici klasöre yönlendirir; gerçek `data/` kullanılacaksa çalışmayı durdurur (önceki bir sıralama bir testin gerçek bir anahtarı silmesine yol açmıştı; geri yüklendi). `run_e2e.py` `AIIQ_E2E_KEEP=1` ile geçici klasörünü saklar.

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
