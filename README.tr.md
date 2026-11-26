<p align="center"><img src="screenshots/banner.tr.png" alt="AI IQ 300 — Otonom AI Komuta Merkezi" width="100%"></p>

<p align="center">
  <b>Yerel ve bulut yapay zekâ modelleriyle çalışan, kendi kendine kod yazan, test eden ve çalıştıran otonom AI komuta merkezi.</b><br>
  <a href="README.md">English</a> · <a href="https://github.com/AppsTRDesign">GitHub</a> · <a href="https://wplugins.shop">wplugins.shop</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/sürüm-0.21.0-2563eb" alt="sürüm">
  <img src="https://img.shields.io/badge/python-3.12-3776ab" alt="python">
  <img src="https://img.shields.io/badge/node-20%2B-339933" alt="node">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-555" alt="platform">
  <img src="https://img.shields.io/badge/FastAPI-React-7c3aed" alt="stack">
  <img src="https://img.shields.io/badge/dil-TR%20%2F%20EN-db2777" alt="dil">
</p>

---

## ✨ AI IQ 300 nedir?

AI IQ 300, bilgisayarınızda çalışan ve ChatGPT/Claude tarzı sade bir sohbet arayüzüne sahip bir **yazılım geliştirme ve otomasyon merkezidir**. Ona bir hedef verirsiniz: klasörleri ve dosyaları oluşturur, PowerShell/CMD/Python/Node/PHP komutlarını çalıştırır, hataları ayıklar, uygulamayı tarayıcıda test eder ve sonucu size raporlar. Siz bir bulut sağlayıcı seçmedikçe verileriniz bilgisayarınızdan çıkmaz.

> "PHP ile tam bir e-ticaret sitesi kur" deyin; proje yapısı, veritabanı, arayüz ve test adım adım oluşur. Model işi bir yapılacaklar listesine böler, her adımı sohbette canlı izlersiniz.

## 📊 Benchmark: dokuz gerçek görev, gerçek çıktıdan puan

İki NVIDIA modeli AI IQ 300'de aynı dokuz görevi yaptı (v0.20.1, 2026-11-23, modeller sırayla). Modelin söyledikleri puanlanmadı. Her kontrol, görevden sonra gerçekten var olana bakar: diskteki dosyalar, gizli testler, sayfaya tıklayan gerçek bir tarayıcı, kendi okuyucularıyla açılan belgeler, git'in kendisi, şemayı çizen Mermaid ve tek tek açılan her kaynak sayfa.

| Model | Tam geçen | Kontrol | Süre | Uygulama hatası |
|---|---|---|---|---|
| `nemotron-3.5-super-vl-120b-a12b` | **9/9 (%100)** | 65/65 | 7,6 dk | yok |
| `nemotron-3-ultra-550b-a55b` | **9/9 (%100)** | 65/65 | 32,8 dk | yok |

<p align="center"><img src="eval/benchmark/heatmap.tr.svg" alt="Görev × model: geçen kontroller" width="100%"></p>
<p align="center"><img src="eval/benchmark/time.tr.svg" alt="Her görevin süresi nereye gitti" width="100%"></p>

- **Görevler:** tarayıcıda test edilen yapılacaklar uygulaması, gizli testlere karşı düzeltilen bozuk Python, beş modülde yeniden adlandırma, Word + PDF rapor, görevin ortasında gerçekten kesilen bağlantı, her kaynağı denetlenen web araştırması, güvenlik odaklı kod incelemesi, Mermaid akış şeması ve git dalları.
- **Ölçüt başarı oranı ve uygulama hatası olmamasıdır.** Süre çoğunlukla sağlayıcıya bağlı: 550B koşusunun %80'i NVIDIA'nın ücretsiz kuyruğunda geçti (her isteğin ilk token'ından önce ortalama 26 sn). Uygulamanın kendi payı sürenin %0-1'i.
- Üzerine gelince ayrıntı gösteren tam rapor: [eval/benchmark/report.tr.html](eval/benchmark/report.tr.html) (indirip açın) · veri: [results.json](eval/benchmark/results.json) · yöntem ve geçmiş: [eval/BENCHMARK.tr.md](eval/BENCHMARK.tr.md) · kendiniz çalıştırın: [eval/README.tr.md](eval/README.tr.md).

## 🎬 Tanıtım videosu

<p align="center"><a href="https://www.youtube.com/watch?v=IxbYD4iCyb0"><img src="https://img.youtube.com/vi/IxbYD4iCyb0/maxresdefault.jpg" alt="AI IQ 300 tanıtım videosu" width="100%"></a></p>

<p align="center"><b>▶ <a href="https://youtube.com/shorts/fsrAsy4j84M?feature=share">Tanıtım videosunu izle (YouTube 16:9)</a></b> · 🇬🇧 <a href="https://www.youtube.com/watch?v=gSqQ8b9ssGs">English</a></p>

Tek cümleden çalışan uygulamaya: komut yazılır, ajan planlar, bütün dosyaları tek turda yazar, `tsc` ile derler, uygulamayı **gerçek tarayıcıda** açıp console + network denetimini yapar, yakaladığı hatayı anında düzeltir ve test edilmiş sonucu teslim eder. Videoda gerçek AI IQ 300 paneli, tüm ayar ekranları, donanım taraması ve sistem onarımı, web araştırması, sesten yazı / yazıdan ses, belge ve video stüdyosu yer alıyor.

<sub>Müzik: “Epic Trailer” · Soundrider/Dope ([Jamendo](https://www.jamendo.com/track/1670474)) · [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/)</sub>

## 🖼️ Ekran görüntüleri

| **PowerPoint önizleme: gerçek slayt yerleşimi, resimler, küçük resimler** | **Excel önizleme: formül çubuğu, birleşik hücreler, sayfa sekmeleri** |
|---|---|
| ![PowerPoint önizleme](screenshots/tr-51-pptx-preview.png) | ![Excel önizleme](screenshots/tr-52-excel-preview.png) |
| **Ücretsiz AI video motorları (yazıdan / resimden video)** | **Kaydırıcıların yanında ∞ / Kapalı / Otomatik düğmeleri** |
| ![AI video motorları](screenshots/tr-53-video-engines.png) | ![Ayar düğmeleri](screenshots/tr-54-setting-buttons.png) |

| **Video Stüdyosu: resimdeki her yazıyı sürükle ve biçimlendir, zaman çizelgesi, canlı AI düzenleme** | **Stüdyo müziği: 8 stilde özgün parça veya telifsiz kütüphane** |
|---|---|
| ![Video Stüdyosu](screenshots/tr-44-video-studio.png) | ![Stüdyo müziği](screenshots/tr-45-studio-music.png) |
| **Logo yapıcı: AI yönleri, AI sembolleri, saydam PNG** | **400+ ücretsiz doğal sesten oluşan kütüphaneyle yazıdan ses** |
| ![Logo yapıcı](screenshots/tr-47-logo-maker.png) | ![Ses kütüphanesi](screenshots/tr-48-voice-library.png) |
| **Renkli (+) menüsü: Oluştur bölümü** | **Anahtar, kota ve ücretsiz yedekli görsel üretim servisleri** |
| ![Oluştur menüsü](screenshots/tr-46-create-menu.png) | ![Görsel servisleri](screenshots/tr-49-image-services.png) |

<p align="center"><img src="screenshots/tr-50-studio-mobile-dark.png" width="300" alt="Telefonda Video Stüdyosu"><br><i>Telefonda Video Stüdyosu: resimde veya zaman çizelgesinde neye dokunursanız ayarları altta açılır</i></p>

| **Yalan "bitti" yok: istenen PDF diskte yoksa cevabın başında uyarı** | **Zayıf model bile gerçek PDF üretir: `system_info` + `make_doc`** |
|---|---|
| ![Sahte "hazır" yakalandı](screenshots/tr-41-false-ready-caught.png) | ![Donanım raporu PDF](screenshots/tr-40-hardware-pdf.png) |
| **Sohbetlerde tam metin araması** | **Model karnesi: hız ve hata oranı** |
| ![Sohbet araması](screenshots/tr-42-chat-search.png) | ![Model performansı](screenshots/tr-43-model-performance.png) |
| **Tarayıcı ajanı: gerçek pencerede siteye girip form dolduruyor, kendi ekran görüntüsünü alıyor** | **Rehber: tarayıcı ajanı makalesi** |
| ![Tarayıcı ajanı canlı iz](screenshots/tr-39-browser-agent-trace.png) | ![Rehber: tarayıcı ajanı](screenshots/tr-38-guide-browser.png) |
| **Ayarlar: tarayıcı ajanı (görünür pencere, kayıtlı oturumlar)** | |
| ![Ayarlar: tarayıcı ajanı](screenshots/tr-37-browser-settings.png) | |
| Harita: detay kartları, size uzaklık, yol tarifi, koyu tema | Tüm değişikliklerin inceleme kartı (araç ve komut) ve görevin süre dağılımı |
| ![Harita: detay kartları, size uzaklık, yol tarifi, koyu tema](screenshots/tr-32-map-cards.png) | ![Tüm değişikliklerin inceleme kartı (araç ve komut) ve görevin süre dağılımı](screenshots/tr-33-changes-timing.png) |
| **Rehber: belge okuma, OCR ve sayfa numaraları** | **Rehber: sürüme uygun komutlar (koyu)** |
| ![Rehber: belge okuma, OCR ve sayfa numaraları](screenshots/tr-34-guide-documents.png) | ![Rehber: sürüme uygun komutlar (koyu)](screenshots/tr-35-guide-commands-dark.png) |
| **Aşamalı ajan takımı: HTML → analiz → Word, 3 bulut modeli** | **Bir semtteki mekânlar etkileşimli haritada** |
| ![Aşamalı ajan takımı (3 bulut modeli)](screenshots/tr-30-staged-team.png) | ![Harita ve mekânlar](screenshots/tr-31-map.png) |
| **Modeller arası takım mesajları ve ortak görev listesi (gerçek çalıştırma)** | |
| ![Modeller arası takım mesajları ve ortak görev listesi (gerçek çalıştırma)](screenshots/tr-36-team-messages.png) | |
| **Wiki rehber: konu ağacı, arama, tam çoklu model sayfaları** | **Web araması: önce API'leriniz, sonra ücretsiz motorlar; her motorun durumu** |
| ![Wiki rehber](screenshots/tr-28-guide.png) | ![Web arama motorları](screenshots/tr-29-web-search-dark.png) |
| **Sohbet ve adımlar** | **Görev sürerken: canlı adımlar ve yapılacaklar** |
| ![Sohbet](screenshots/tr-01-chat.png) | ![Canlı görev](screenshots/tr-07-live-run.png) |
| **Ajan işini ekran görüntüsüyle kendisi kontrol eder** | **Resme göndermeden önce çizim ve yazı ekleme** |
| ![Ajanın ekran görüntüleri](screenshots/tr-23-agent-screenshots.png) | ![Resim düzenleyici](screenshots/tr-22-image-editor.png) |
| **Dosyaları sohbetin her yerine bırakın** | **Doğal sesler, kadın / erkek** |
| ![Dosya bırakma](screenshots/tr-21-drop-files.png) | ![Sesler](screenshots/tr-24-voices-dark.png) |
| **Hazır yetenekler (/)** | **Hazır ajanlar (@)** |
| ![Yetenekler](screenshots/tr-25-skills.png) | ![Ajanlar](screenshots/tr-26-agents-dark.png) |
| **Onaydan önce fark (diff)** | **Paralel ajan takımı ve görev panosu** |
| ![Onaydan önce fark](screenshots/tr-14-approval-diff.png) | ![Ajan takımı](screenshots/tr-18-agent-team.png) |
| **Modelin API'sinden gelen çaba seviyeleri** | **Model profilleri** |
| ![Çaba](screenshots/tr-15-effort-dark.png) | ![Model profilleri](screenshots/tr-16-model-profiles.png) |
| **MCP sunucuları** | **Çoklu model havuzu ve kotalar** |
| ![MCP](screenshots/tr-17-mcp-dark.png) | ![Çoklu model](screenshots/tr-19-multi-model-dark.png) |
| **Proje kuralları (AIIQ.md)** | **Model seçiciden bağlam ayarı** |
| ![Proje kuralları](screenshots/tr-20-project-rules.png) | ![Model ve bağlam](screenshots/tr-11-model-context-dark.png) |
| **Belge kartları** | **Excel önizleme** |
| ![Belgeler](screenshots/tr-08-docs.png) | ![Excel önizleme](screenshots/tr-09-preview-excel.png) |
| **Word önizleme** | **Bağlam analizi** |
| ![Word önizleme](screenshots/tr-10-preview-word.png) | ![Bağlam](screenshots/tr-02-context-dark.png) |
| **Dosya yöneticisi** | **Çizim ekranı** |
| ![Dosyalar](screenshots/tr-03-files.png) | ![Çizim](screenshots/tr-13-drawing.png) |
| **Sağlayıcılar** | **Artı menüsü** |
| ![Sağlayıcılar](screenshots/tr-04-providers-dark.png) | ![Artı menüsü](screenshots/tr-12-plus-menu.png) |
| **Hakkında** | |
| ![Hakkında](screenshots/tr-05-about.png) | |

<p align="center"><img src="screenshots/tr-06-mobile-dark.png" width="280" alt="Mobil"> &nbsp; <img src="screenshots/tr-27-mobile-jump-dark.png" width="280" alt="Mobil, en son mesaja in"><br><i>Mobil görünüm (koyu tema); yukarı kaydırınca yuvarlak düğme en son mesaja indirir</i></p>

## 🚀 Özellikler

**Ajan ve orkestrasyon**
- **Gerçek araç kullanımı:** Ollama, OpenAI uyumlu API'ler ve Anthropic için native function calling. Qwen-XML, Hermes-JSON ve Mistral biçimlerini tanıyan evrensel ayrıştırıcı; ham araç sözdizimi sohbete sızmaz.
- **Çoklu ajan:** Asistan, Planlayıcı, Kodlayıcı, Hata ayıklayıcı ve Test uzmanının yanında hazır profesyonel ajanlar: `@researcher` (kaynaklı web araştırması), `@comparer` (tablo ve net öneriyle ürün karşılaştırma), `@writer` (makale; mevcut Word/Markdown dosyasına da yazar), `@prompt-wizard`, `@skill-maker` ve `@agent-maker`. Komut hata verince otomatik hata ayıklama döngüsü devreye girer. `@ajan` ile rol değiştirilir.
- **Kesintisiz görevler:** Uzun işler bitene kadar sürer. Model bir sonraki adımı söyleyip durursa, boş cevap verirse ya da listede açık madde kalırsa görev devam ettirilir. Yarıda kalan iş "devam et" ile kaldığı yerden sürer.
- **Canlı yapılacaklar listesi:** Çok adımlı işlerde model gerektiğinde listeyi kendisi açar, maddeleri ilerledikçe işaretler; liste sohbetle senkron kalır.
- **Otomatik yetenek algılama:** Model, isteğe uyan yeteneği kendisi seçip yükler; yüklenene kadar her yetenekten talimatta yalnızca bir satır bulunur. Hazır olanlar: `/web-research`, `/web-summary`, `/web-report`, `/web-to-doc` (mevcut Word/Excel/Markdown belgesine yazar), `/compare`, `/article`, `/prompt`, `/docs`, `/webapp`, `/git`. Yetenek çağrıldığında son istek hedeflenir, önceki sohbet konusuna kayılmaz.
- **Token tasarruflu araç setleri:** bir ajan ya da yetenek kendi araçlarını listeleyebilir (dosyasında `tools:`); kullanılırken modele yalnızca bu araçların tanımı gider, %60–85 daha küçük; küçük modeller daha az yanlış araç çağırır.
- **Yetenek ve ajan üreticiler:** `@skill-maker` / `@agent-maker` anlattığınızı profesyonel bir yetenek ya da ajana dönüştürür, doğrular (biçim, araçlar, uzunluk) ve onayınızla `skills/` ya da `agents/` klasörüne ekler; hemen `/` veya `@` ile kullanılır.
- **Web sayfası ekran görüntüsü:** Claude'daki gibi model gerektiğinde görüntü alır: bir sayfayı yapınca ya da değiştirince (masaüstü ve telefon görünümü) veya bir sitenin nasıl göründüğü sorulunca. Cihaz, tam sayfa, tek öğe, koyu tema, PNG/JPEG/PDF seçilebilir. Görüntü adımların altında küçük resim olarak çıkar, tıklayınca görüntüleyicide açılır; resim göremeyen modellere sayfanın gerçek metni verilir, sayfada olmayanı uydurmazlar.
- **Hedef ve plan modları:** Hedef modunda model, hedefe ulaşana kadar kendi başına çalışır; plan modunda önce plan çıkarır.
- **Ajan takımları (paralel ve aşamalı):** Çoklu model havuzu açıkken model büyük bir işi 1–6 parçaya böler; her üye farklı bir bulut modelde çalışır. Bağımsız parçalar aynı anda, birbirine bağlı parçalar aşama aşama çalışır; sonraki aşama öncekilerin sonucunu alır (kendi araç döngüsüyle okur, yazar, düzenler, komut çalıştırır). Üyeler birbirine mesaj atar ve ortak görev listesini kullanır (ekler, üstlenir, bitirir). Canlı görev panosu her üyenin modelini, durumunu, adımlarını, dosyalarını, raporunu, mesajları ve ortak listeyi gösterir.
- **MCP istemcisi:** Ayarlar > MCP'den Model Context Protocol sunucularını (stdio komutu ya da Streamable HTTP) bağlayın: GitHub, PostgreSQL, dosya sistemi, tarayıcı… Araçları her sohbette modele sunulur. Salt okunur araçlar onaysız, diğerleri onayla çalışır; tokenlar gizli anahtar deposunda kalır. Çöken sunucu bir sonraki çağrıda yeniden başlar.
- **Akıllı kod düzenleme:** Dosyanın tamamını yeniden yazmak yerine kısmi düzenleme (`edit_file`, SEARCH/REPLACE blokları, girinti toleranslı eşleşme), proje içi kod arama ve satır aralığıyla okuma.
- **Söz dizimi ağacı (Tree-sitter):** 20'den fazla dilde kesin fonksiyon/sınıf/metot bilgisi, her proje sohbetinde kod haritası ve etki analizi: model bir değişiklikten önce dokunduğu şeyi kullanan dosyaları görür (yorum ve metin içindeki eşleşmeler sayılmaz). Gramer çevrimdışı indirilemezse regex'e döner.
- **Akıllı korumalar:** Aynı sayfanın tekrar tekrar indirilmesi, asılsız "dosya oluşturdum" iddiaları, uydurma mutlak yollar ve yanlış dilde cevap otomatik düzeltilir. Bilgi sorularında yalnızca okuma araçları verilir, istenmeyen dosya yazılmaz.

**Bağlam ve modeller**
- **Canlı bağlam:** Bağlam görev sürerken her adımda sayılır. Uzun görevlerde eski dosya içerikleri kırpılır, gerekirse adımlar özetlenir; görev pencere dolduğu için kopmaz. Kategori bazlı istatistikler, %80 eşikte sıkıştırma ve kalıcı oturum özetleri.
- **Model seçiciden bağlam ayarı:** Yerel modellerin bağlam boyutu model seçicideki etiketten kaydırıcıyla ya da hazır düğmelerle (8K–262K) değiştirilir; Ayarlar ve bağlam paneliyle anında senkron kalır.
- **31 sağlayıcı:** Ollama, LM Studio, OpenAI, Anthropic, Gemini, OpenRouter, Groq, NVIDIA NIM, Cloudflare Workers AI, DeepSeek, Mistral, xAI, Together, EVREN ve diğerleri. Modeller sağlayıcı bazında paralel ve anlık yüklenir; araç/görsel/düşünme rozetleri görünür.
- **Çoklu model ve kotalar:** Yetenek etiketli bulut modeli havuzu. Kota, kredi ya da hız sınırı dolunca görev en müsait modelle sürer; ajanlara ayrı model atanabilir; model bir alt işi başka modele verebilir (`ask_model`). Yenilenme zamanlarıyla 5 saatlik ve haftalık kullanım, kendi sınırlarınız. Yerel modeller havuza girmez.
- **Çaba ayarı:** Model seçicinin yanındaki gösterge menüsü, modelin gerçekten desteklediği düşünme seviyelerini API verisinden alır: OpenRouter `reasoning.effort`, OpenAI `reasoning_effort`, Anthropic düşünme bütçesi, Gemini `thinkingBudget`, Ollama `think`. API'si bunu sunmayan modellere (çoğu yerel model) seviye talimat olarak iletilir. Anthropic'te genişletilmiş düşünme araç kullanan görevlerde de çalışır (imzalı düşünme blokları araç turları boyunca korunur).
- **Model profilleri:** Model başına düşünme, görsel girdi, akış ve araç çağrı biçimi (yerel / etiket) açma-kapama; sıcaklık ve en fazla çıktı ayarı.
- **Yeniden deneme:** Meşgul (503) ya da hız sınırına takılan sağlayıcılar artan bekleme süreleriyle yeniden denenir, gerekirse model değişir; görev tek hatada ölmez.
- **VRAM dostu:** Yerel modele geçince diğer yerel modeller otomatik boşaltılır.
- **Yavaş donanıma dayanıklı:** Model bir dosyayı sessizce yazarken "Hazırlanıyor · N sn" göstergesi çıkar; uzun üretimler zaman aşımına düşmez.

**Çalışma alanı**
- **Profesyonel IDE:** Monaco editör, klasör ağaçlı ve türe göre filtreli dosya yöneticisi, süreç paneli, git zaman makinesi.
- **Belge üretimi ve önizleme:** Word, Excel, PDF ve PowerPoint. Üretilen belgeler sohbette türüne göre renkli kart olarak görünür; karta ya da cevaptaki belge yoluna tıklayınca uygulama içinde önizlenir (Excel: SheetJS, Word: docx-preview, PDF: tarayıcı görüntüleyicisi, PowerPoint: slayt kartları).
- **Çizim ekranı ve resim düzenleyici:** Kalem, çizgi, ok, dikdörtgen, elips, yazı, silgi, renkler, geri al/yinele. Eklenen bir resme tıklayıp üzerine işaret koyun; düzenlenen resim orijinal çözünürlükte ekin yerine geçer (silgi fotoğrafa dokunmaz).
- **Ekler:** Dosya ve klasör yükleme (klasör yapısı korunur), sohbetin her yerine tam ekran bırakma alanıyla sürükle-bırak, yapıştırma ve sesle yazma.
- **Web araştırması:**
  - Önce sizin arama API'leriniz kullanılır: Google, Yandex, Bing, Brave, Tavily, SearXNG.
  - Yoksa ücretsiz ddgs (Google, Yahoo, Bing, Yandex, Brave) Wikipedia ve Wikidata ile birlikte çalışır; en son çare arka planda hazır bekleyen tarayıcıdır.
  - Sonuçlar motorlar arasında birleştirilir, konu dışı olanlar elenir. Sorun çıkaran motor dinlendirilir.
  - Sayfalar yapısal verileriyle okunur; okunamayan sayfa için arşiv kopyası kullanılır.
  - Cevaplar kaynaklıdır. Bot doğrulamaları çözülmez.
- **Harita ve mekânlar:**
  - `places` aracı semt, adres ya da koordinat çevresindeki mekânları bulur: mesafe, adres, telefon, web sitesi ve saatler.
  - Ücretsiz OpenStreetMap ile çalışır; anahtar girilirse Google/Yandex Places ile puan ve yorum da gelir.
  - Etkileşimli harita sayfaları çizer.
  - Yetenekler: `/place-research`, `/place-compare`, `/map-market` (rakipler, boşluklar, SWOT, pazarlama stratejisi) ve `/catalog`.
- **Proje hafızası:** Proje başına `AIIQ.md` kuralları (proje menüsü > Proje kuralları) ve Ayarlar'daki genel kurallar her sohbete eklenir; "bunu hatırla" dediğinizde model kuralı kendisi kaydeder.
- **Resim ve sayfalar:** Üretilen resimler yakınlaştırılabilir görüntüleyicide, HTML sayfaları uygulama içi tarayıcıda açılır.
- **Ses ile yönetim:** Cevaplar otomatik ya da her cevabın altındaki hoparlörle okunur. Doğal Microsoft sinir ağı sesleri (edge-tts, ücretsiz, anahtarsız) kadın/erkek etiketiyle listelenir ve her dil için ayrı seçilir; çevrimdışıyken tarayıcı sesleri kullanılır. Emojiler, semboller ve metin ifadeleri okunmaz. Sesli komut modunda konuşma kutuya yazılır, sesli komutlar uygulamayı yönetir: "gönder", "durdur", "onayla", "reddet", "yeni sohbet", "oku", "sus".
- **Yerel Türkçe ses paketleri:** 18 açık kaynak Türkçe TTS motoru (Seda, Supertonic 3, Pocket-TTS, XTTS v2, Kızagan, Fish S2 Pro ...) Ayarlar > Sesler'den ya da kurulumdan, her biri kendi ortamına kuruluyor; uygulama bilgisayarın onları çalıştırıp çalıştıramayacağına bakıyor. Sesler kurulumda ölçülüyor (kadın/erkek gerçek perdeden), bazılarında duygu ya da referans sesten klonlama var, lisanslar görünüyor. Ölçülmüş sonuçlar: [eval/TTS_BENCHMARK.tr.md](eval/TTS_BENCHMARK.tr.md). Aynı anda en fazla üç ses modeli yüklü kalıyor; en uzun süredir boşta olan önce kapatılıyor.
- **Bulut sesleri:** kendi anahtarınızla ElevenLabs, OpenAI TTS, Google Cloud TTS, Gemini TTS ve Azure AI Speech (sohbet sağlayıcıları gibi anahtar, test ve model). Sesleri tüm ses seçicilere katılıyor ve yalnızca seçildiğinde kullanılıyor. Her seçici motora göre süzüyor: her yerel motor, her kurulu ses paketi ve her bulut servisi, ses sayılarıyla.
- **Ses klonlama stüdyosu:** sesinizi kaydedin ya da yükleyin, kalite puanını görün (gürültü, kırpılma, süre, perde), temizleyin (gürültü, uğultu, tık, sert s, sessizlikler, seviye), orijinalle temizlenmişi karşılaştırın, her klonlama motorunda dinleyin, sonra seslendirici olarak saklayın ya da varsayılan ses yapın.
- **Oturum sistemi:** Her sohbet için `chat/<id>-session/` klasöründe transcript, özetler, durum dosyası ve yüklemeler.
- **Güvenlik:** Üç izin modu (Onay iste / Benim için onayla / Tam erişim). Tam erişimde bile yıkıcı komutlar için akıllı güvenlik çiti. **Onaydan önce fark:** bir dosya değişikliği onay istediğinde kart, karar vermeden önce tam olarak neyin değişeceğini gösterir (eklenecek satırlar yeşil, silinecekler kırmızı; yeni dosyada tüm içerik, silmede silinecek içerik).
- **Arayüz:** Gece/gündüz teması, tam mobil uyum (ayarlar ve paneller kendi sütun genişliğine göre düzenlenir; dar pencerede metin sıkışmaz), tıklayınca açılıp kapanan menüler, yukarı kaydırınca en son mesaja indiren düğme ve otomatik düzen denetimi (4 genişlik × TR/EN: taşma, üst üste binme ve yapışık düğme yok); TR/EN hazır, yeni diller tek tıkla otomatik çevrilir (ajan ve yetenek metinleri dahil).

## 📦 Gereksinimler

| Bileşen | Sürüm | Durum | Ne için? |
|---|---|---|---|
| **Python** | 3.12 | ✅ Zorunlu | Backend (FastAPI) |
| **Node.js** (npm dahil) | 20+ (22 LTS önerilir) | ✅ Zorunlu | Arayüzün derlenmesi |
| **Git** | 2.40+ | ⭐ Önerilir | Zaman makinesi, otomatik commit |
| **Ollama** veya **LM Studio** | güncel | ⭐ Yerel model için (biri yeterli) | Modelleri bilgisayarda çalıştırma |
| **FFmpeg** | 7+ (yoksa uygulama indirir) | ⭐ Önerilir | Video Stüdyosu, video araçları, sesten yazı |
| **PHP** + Composer | 8.2+ | İsteğe bağlı | PHP projelerini çalıştırma (`localhost-project` yeteneği istenince kurar) |
| **.NET SDK** | 8+ | İsteğe bağlı | ASP.NET projeleri (klasik ASP / ASP.NET Framework: Windows + IIS) |
| **WSL2 + Docker** | güncel | İsteğe bağlı | Projeleri konteynerde çalıştırma; yol haritasındaki sandbox |
| **Tarayıcı** | Chrome / Edge / Firefox | ✅ Zorunlu | Arayüz |

> Medya özelliklerinin Python paketleri `requirements.txt` ile gelir: `gradio_client` (ücretsiz AI ile resimden video), `uv` (`uvx` ile Python MCP sunucuları), `edge-tts` (sesler), `faster-whisper` (sesten yazı), `numpy` + `Pillow` (müzik üreteci, logo arka plan temizleme). Video yazıları sistem yazı tiplerini kullanır (Windows ve macOS'ta Arial / Georgia / Impact; Linux'ta `install.sh` DejaVu kurar). Yeni npm paketi gerekmez.

> Söz dizimi ağacı gramerleri ilk kullanımda otomatik iner (bir kez internet gerekir). Birçok MCP sunucusu `npx` (Node.js) ya da `uvx` (Python) ile başlatılır.
> Yerel model kurmak istemiyorsanız Ayarlar > Sağlayıcılar'dan bir bulut API anahtarı (OpenRouter, OpenAI, Anthropic, Gemini, EVREN…) girmeniz yeterli.
> Önerilen donanım: 16 GB+ RAM. GPU ile 7B–14B modeller için 8 GB+ VRAM, 30B+ modeller için 16–24 GB VRAM. GPU'su desteklenmeyen sistemlerde 30B MoE modeller (ör. `qwen3-coder:30b`) 32 GB RAM ile işlemcide de çalışır; yalnızca daha yavaştır.

### 🪟 Windows 10 / 11

Komutlar PowerShell'de çalışır. [winget](https://learn.microsoft.com/windows/package-manager/winget/) Windows 11'de hazır gelir; isterseniz bağlantılardan kurulum dosyasını indirin.

| Bileşen | İndirme | winget ile kurulum |
|---|---|---|
| Python 3.12 | [python.org/downloads/windows](https://www.python.org/downloads/windows/) — kurulumda **"Add python.exe to PATH"** işaretleyin | `winget install Python.Python.3.12` |
| Node.js LTS | [nodejs.org/en/download](https://nodejs.org/en/download) | `winget install OpenJS.NodeJS.LTS` |
| Git | [git-scm.com/download/win](https://git-scm.com/download/win) | `winget install Git.Git` |
| Ollama | [ollama.com/download/windows](https://ollama.com/download/windows) | `winget install Ollama.Ollama` |
| LM Studio | [lmstudio.ai](https://lmstudio.ai/) | `winget install ElementLabs.LMStudio` |
| PHP 8.2+ | [windows.php.net/download](https://windows.php.net/download/) — zip'i açıp klasörü PATH'e ekleyin | — |
| Docker Desktop | [docs.docker.com/desktop/setup/install/windows-install](https://docs.docker.com/desktop/setup/install/windows-install/) | `winget install Docker.DockerDesktop` |

Kurulumdan sonra terminali kapatıp açın ve sürümleri kontrol edin:

```bash
python --version
```
```bash
node --version
```

**WSL2 + Docker (isteğe bağlı):**

1. PowerShell'i **yönetici olarak** açın, WSL2'yi kurun ve bilgisayarı yeniden başlatın:
   ```bash
   wsl --install
   ```
2. WSL'i güncelleyin ve varsayılan sürümün 2 olduğunu doğrulayın:
   ```bash
   wsl --update
   ```
   ```bash
   wsl --status
   ```
3. Docker Desktop'ı kurun (yukarıdaki tablo), açın ve **Settings > General > Use the WSL 2 based engine** seçeneğinin işaretli olduğunu kontrol edin.
4. Çalıştığını doğrulayın:
   ```bash
   docker run hello-world
   ```

> BIOS'ta sanallaştırma (Intel VT-x / AMD-V) açık olmalıdır. Ayrıntılar: [learn.microsoft.com/windows/wsl/install](https://learn.microsoft.com/windows/wsl/install)

### 🐧 Linux (Ubuntu / Debian / Fedora)

**Ubuntu 24.04 / Debian 13** (Python 3.12 depoda hazır):

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git curl
```

**Ubuntu 22.04** (Python 3.12 için deadsnakes deposu):

```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt update && sudo apt install -y python3.12 python3.12-venv git curl
```

**Fedora:**

```bash
sudo dnf install -y python3.12 git curl nodejs npm
```

**Node.js 22 LTS** (Ubuntu/Debian, [NodeSource](https://github.com/nodesource/distributions)):

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs
```

**Ollama** ([ollama.com/download/linux](https://ollama.com/download/linux)):

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**LM Studio:** [lmstudio.ai](https://lmstudio.ai/) adresinden AppImage'i indirip çalıştırılabilir yapın.

**PHP (isteğe bağlı):**

```bash
sudo apt install -y php-cli php-sqlite3 php-mbstring
```

**Docker Engine (isteğe bağlı,** [docs.docker.com/engine/install](https://docs.docker.com/engine/install/)**):**

```bash
curl -fsSL https://get.docker.com | sh
```
```bash
sudo usermod -aG docker $USER
```

Oturumu kapatıp açtıktan sonra doğrulayın:

```bash
docker run hello-world
```

### 🍎 macOS

[Homebrew](https://brew.sh/) ile: `brew install python@3.12 node git` · Ollama: [ollama.com/download/mac](https://ollama.com/download/mac) · Docker: [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/)

## 🛠️ Kurulum

`install.bat` / `install.sh` şunları otomatik yapar: Python sanal ortamı (`.venv`), `requirements.txt` bağımlılıkları (FastAPI, Uvicorn, httpx, Playwright, python-docx, openpyxl, reportlab, python-pptx…), Playwright Chromium, arayüz paketleri ve derleme.

### Windows

```bash
install.bat
```
```bash
run.bat
```

### Linux / macOS

```bash
chmod +x install.sh run.sh
```
```bash
./install.sh
```
```bash
./run.sh
```

Playwright'ın sistem kütüphaneleri eksikse (Linux):

```bash
sudo .venv/bin/python -m playwright install-deps
```

Uygulama `http://127.0.0.1:8300` adresinde açılır (farklı port: `run.bat 9000` / `./run.sh 9000`). İlk açılışta arayüz sistem dilinizde başlar (çeviri yoksa İngilizce).

**İlk model:** Ollama kuruluysa bir model indirin:

```bash
ollama pull qwen3-coder:30b
```

ya da Ayarlar > Sağlayıcılar'dan bir bulut sağlayıcı ekleyip **Test**'e basın.

## 🧭 Kullanım

1. Sol menüde **+** ile proje oluşturun ve bir klasör seçin; ajanın çıktıları oraya yazılır.
2. Mesaj kutusunun altından modeli ve izin modunu seçin; bağlam boyutunu model seçicideki etiketten ayarlayın.
3. İsteğinizi yazın. Ajan için `@coder`, `@tester`; yetenek için `/webapp`, `/docs` kullanabilirsiniz ya da modelin kendisinin seçmesine bırakın.
4. **+** menüsünden dosya/klasör ekleyin, çizim yapın, Hedef veya Plan modunu açın.
5. Görev sürerken adım grubuna tıklayıp ayrıntıları görün; yapılacaklar listesinden ilerlemeyi izleyin. Bağlam halkasından kullanım, çıktılar ve arka plan görevleri görünür.
6. Üretilen belgelerin kartına tıklayarak uygulama içinde önizleyin.
7. Düşünme seviyesini model seçicinin yanındaki gösterge menüsünden ayarlayın; model başına ayrıntılar Ayarlar > Modeller > Model profilleri'nde.
8. Araçları Ayarlar > MCP'den bağlayın; Ayarlar > Çoklu model'den bulut modeli havuzu kurun, böylece model kota dolunca geçiş yapabilir ve ajan takımı kurabilir.
9. Sesli yanıtı Ayarlar > Genel'den açıp sesi seçin (kadın/erkek) ya da cevabın altındaki hoparlöre tıklayın.
10. Dosyaları sohbetin herhangi bir yerine bırakın; eklenen resme tıklayıp göndermeden önce üzerine çizin ya da yazın.
11. Bir sayfanın nasıl göründüğünü sorun (ya da modelin kendi sayfalarını kontrol etmesine bırakın): görüntüler adımların altında çıkar, tıklayınca açılır.
12. Kendi yetenek ve ajanlarınızı `@skill-maker` / `@agent-maker` ile ekleyin.
13. Kurulumda yalnızca Ollama açıktır; bir bulut sağlayıcının API anahtarını kaydedince o sağlayıcı açılır.

Ayrıntılı kullanım için uygulamadaki **Rehber** bölümüne bakın.

## 🏗️ Mimari

> Klasör yapısı ve tam özellik geçmişi: [PROJECT_STATE.tr.md](PROJECT_STATE.tr.md) · [English](PROJECT_STATE.md)

```
backend/   FastAPI · ajan orkestratörü · ajan takımları · sağlayıcı adaptörleri · MCP istemcisi · Tree-sitter · süreç yöneticisi · politika
           Playwright ekran görüntüleri · edge-tts sesleri
frontend/  React + Vite + Tailwind · Monaco · Zustand · SheetJS · docx-preview
agents/    Ajan rolleri (Markdown)        skills/    Yetenekler (Markdown)
languages/ tr.json · en.json
chat/      Her sohbete bir klasör: chat/<sohbet kimliği>/ (dosyaları) + .session/ (kaydı); chat/projects/ (klasör seçilmeden açılan projeler)
screenshots/ Bu README'deki banner ve ekran görüntüleri
```

### 🔀 Bir mesaj nasıl işlenir

> Tur tur sıralama şeması ve ajan ekibi akışıyla tam çalışma şeması (GitHub şemaları çizer):
> [WORKFLOW.tr.md](WORKFLOW.tr.md) · [English](WORKFLOW.md)

<p align="center"><img src="screenshots/workflow-tr.png" width="640" alt="AI IQ 300 çalışma şeması"></p>

## 🧩 Başka araçların komutlarıyla beceri ekleme (npx skills, hf skills, gradio skills)

Beceri kurulum komutları `SKILL.md` talimatlarını bir ajanın beceri klasörüne kopyalayıp kapanır; bunlar **MCP sunucusu değildir**, o yüzden sunucu olarak başlatılamaz. AI IQ 300 bu komutları tanır ve **Beceriler** olarak içe aktarır:

| Komut | Ne içe aktarılır |
|---|---|
| `npx skills add sahip/depo` (`npx -y`, `bunx`, `pnpm dlx`, `yarn dlx` da olur) | O GitHub deposundaki tüm `SKILL.md` dosyaları, seçmeniz için (`--skill ad` seçili gelir) |
| `sahip/depo`, `https://github.com/sahip/depo`, `…/tree/main/klasor` | Aynısı: tüm depo ya da bir klasörü |
| `hf skills add [ad]` | Hugging Face beceri pazaryeri (25 beceri); ad yoksa `hf` komutundaki gibi `hf-cli` |
| `gradio skills add` | Gradio'nun kendi becerisi (Gradio arayüzleri kurmak) |
| `gradio skills add kullanici/space` | O Hugging Face Space'in API'sinden üretilen beceri: her uç nokta, parametreleri ve hazır Python çağrısı |

**Nerede:** Komutu **Beceriler** sayfasındaki içe aktarma kutusuna ya da MCP sunucu formuna yapıştırın; formda Kaydet yerine **Becerileri içe aktar** düğmesi çıkar. Böyle bir komutla "Başlatılamadı" olan sunucu kartında da aynı düğme vardır (içe aktarmadan sonra işe yaramayan sunucu kaydı silinebilir).

**Nasıl çalışır:** Bir seçim penceresi becerileri listeler (gruplu, aranabilir, açıklamalı; daha önce aktarılanlar işaretli). Seçilen her beceri kaynağıyla kaydedilir; tekrar içe aktarmak kopya oluşturmaz, günceller. Aynı adlı yerleşik bir beceri asla ezilmez (yenisinin önüne sahibinin adı eklenir). Becerinin yanındaki dosyalar (referanslar, betikler) bağlantı olarak eklenir; beceri onlara yönlendirince model açar. Her beceri modelin istemine kısa bir satır ekler (~40 token); pencere toplamı gösterir ve tek seferde en fazla 60 beceriye izin verir - yalnızca kullanacaklarınızı seçin. `--global`, `--force`, `--cursor`, `--claude`, `--dest` gibi bayraklar yok sayılır: beceriler her zaman uygulamanın kendi Beceriler bölümüne gider.

## 🆕 Sürüm notları

Son sürüm: **v0.21.0 ile gelenler (18 yerel Türkçe ses paketi, bulut sesleri, ses klonlama stüdyosu, sonuna kadar çalışan dil çevirici, ölçülmüş ses benchmark'ı)**

v0.6'dan bugüne her sürümün getirdikleri: **[CHANGELOG.tr.md](CHANGELOG.tr.md)**. İndirmeler: [GitHub sürümleri](https://github.com/AppsTRDesign/AI-IQ-300/releases).

## 📌 Proje durumu

Projenin tam durumu iki dilde tutuluyor: vizyon, mimari ve klasör yapısı, sürüm sürüm tamamlanan tüm özellikler, açık görevler, önemli kararlar ve sonraki adım.

- 🇹🇷 **Türkçe:** [PROJECT_STATE.tr.md](PROJECT_STATE.tr.md)
- 🇬🇧 **English:** [PROJECT_STATE.md](PROJECT_STATE.md)

**Şu an:** v0.14.1 tamamlandı (Android emülatörü ve Maestro ile mobil uygulama testi, yazıdan / resimden AI klip, HTML öncelikli belgeler, pro PowerPoint / Excel önizleme, daha sağlam araçlar: .venv'e pip, döngü yok, sıralı yapılacaklar; büyük görev düzeltmeleri: devir teslimli dikkatli model değişimi, görev ortasında kota geçişi, döngü ve üzerine yazma koruması, bütün dosya okuma, çevrilmiş hatalar). v0.13.0 tamamlandı (sürüklenip biçimlendirilen yazılarla Video Stüdyosu, canlı AI düzenleme, efektler, AI ile resimden video, özgün ve kütüphane müziği, mobil düzen; logo yapıcı; yazıdan ses ve sesten yazıyla ses kütüphanesi; kota yedekli anahtarlı görsel ve fotoğraf servisleri; MCP OAuth ve kendi kendine kurulum; `localhost-project` yeteneği). v0.12.0 tamamlandı (yalan "bitti" yok: düz metin araç çağrıları çalıştırılır, istenen dosya diskte denetlenir; zayıf modellere `system_info` ve doğru araç ipucu; sohbetlerde tam metin araması; model karnesi; LM Studio bellek koruması; depoda test paketi). v0.11.0 tamamlandı (kapsamlı tarama: tıkanma yok, kopma ve model değişiminde unutma yok, yarı boyutta ilk istem, modeli kapatmayan RAM / VRAM koruması, eksiksiz yeniden bağlanma). v0.10.7 tamamlandı (toplu seçme ve silme, ilk mesajda tüm yetenekler, 14 dilde araç algılama, bölmeden yazım). v0.10.6 tamamlandı (gerçek stok fotoğraflarla profesyonel web tasarımı, JS hatası ve kırık görsel için test edilen sayfalar, sağlayıcının gerçek sayılarına çapalı bağlam sayacı, yerel pencerede taşma yok, Markdown olarak akan canlı yanıt). v0.10.5: gerçek token verisiyle bağlam, ekran görüntülerinde görsel model, ayar denetimi. v0.10.4: Ayarlar, yerel GPU ayarları, canlı senkron, npm / PyPI / GitHub'dan MCP, otomatik araç kurulumu ve sekiz yeni beceri canlı test edildi.

| Alan | Durum |
|---|---|
| Ayarlar | Tüm model seçicilerde yetenek ikonları; tüm sayısal alanlarda kaydırıcı + sayı |
| Yerel modeller | Ollama / LM Studio anlık algılama; Ollama ortam ayarları (Vulkan, FP16, flash attention, KV önbellek) ve LM Studio yükleme seçenekleri |
| MCP | `mcp_add`: npm, PyPI, GitHub'dan derlenen ve uzak sunucular; uçtan uca test edildi |
| Araç zinciri | ffmpeg, git, gh, php, composer otomatik kurulur (winget / brew / apt) |
| Beceriler | site-test, remote-server, social-media, ads-manager, graphics, mcp-servers, packages, code-review |
| Sıradaki | Zaman çizelgeli video düzenleyici, görsel üretimi, stok servisleri, isteğe bağlı Docker sandbox |

## 🗺️ Yol haritası

1. **Tam zaman çizelgeli video düzenleyici (ffmpeg):** kırpma, kesme, birleştirme, yazı ve logo, müzik, geçişler, format dönüştürme; altyazı konuşmadan otomatik (faster-whisper) ya da verilen metinden; sohbette önizleme.
2. **Güçlü resim üretimi:** varsayılan ücretsiz Pollinations (FLUX), anahtarla Hugging Face, Together, OpenAI, Gemini, Stability; istenen format ve ölçüyü algılar, yazıları resmin üstüne keskin basar.
3. **Stok resim ve video servisleri:** Pexels, Pixabay, Unsplash, Openverse, Wikimedia (ücretsiz) ve Shutterstock, Getty, Adobe Stock, Storyblocks (ücretli; her indirmede fiyatıyla onay).
4. **İsteğe bağlı Docker (WSL2) sandbox:** Komutları yalıtılmış konteynerde çalıştırma.

## 👤 Geliştirici

**Onur Öztaş** · [GitHub/AppsTRDesign](https://github.com/AppsTRDesign) · [wplugins.shop](https://wplugins.shop)

> ⚠️ Komutlar bilgisayarınızda doğrudan çalışır; komut filtresi bir yalıtım (sandbox) değildir. Gerçek kontrol onay modudur. Hassas ortamlarda **Onay iste** modunu kullanın.