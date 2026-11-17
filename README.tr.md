<p align="center"><img src="screenshots/banner.tr.png" alt="AI IQ 300 — Otonom AI Komuta Merkezi" width="100%"></p>

<p align="center">
  <b>Yerel ve bulut yapay zekâ modelleriyle çalışan, kendi kendine kod yazan, test eden ve çalıştıran otonom AI komuta merkezi.</b><br>
  <a href="README.md">English</a> · <a href="https://github.com/AppsTRDesign">GitHub</a> · <a href="https://wplugins.shop">wplugins.shop</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/sürüm-0.12.0-2563eb" alt="sürüm">
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

## 🖼️ Ekran görüntüleri

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
| **PHP** | 8.2+ | İsteğe bağlı | PHP projelerini çalıştırma |
| **WSL2 + Docker** | güncel | İsteğe bağlı | Projeleri konteynerde çalıştırma; yol haritasındaki sandbox |
| **Tarayıcı** | Chrome / Edge / Firefox | ✅ Zorunlu | Arayüz |

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
tanitim/   Banner, ekran görüntüleri ve tanıtım metinleri
```

## 🆕 v0.12.0 ile gelenler (yalan "bitti" yok, zayıf modellere gerçek araç kullanımı, sohbet araması, model karnesi)

Zayıf modellerle gerçek testler yapıldı: bulutta EVREN `auto`, yerelde Ollama Qwen2.5-Coder 7B (CPU). Bulunan her sorun uygulamada giderildi ve sahte modelle 43 uçtan uca denetimle yeniden test edildi.

- **Yapmadığı işi "yaptım" diyemez:**
  - Zayıf modeller araç çağrısını çoğu zaman kod bloğunun içine düz metin olarak yazar (```` ```write_file path="rapor.py" content="..."``` ````, `run(command="...")`). Bunlar artık tanınıyor ve **gerçekten çalıştırılıyor**.
  - Cevap bir PDF, Word, Excel ya da PowerPoint dosyasını "hazır" diye sunuyorsa ya da adı geçen bir çıktı dosyası diskte yoksa, uygulama **diske bakar**. Dosya yoksa model iki kez gerçekten oluşturmaya zorlanır; yine olmazsa cevabın en başında açık bir uyarı görünür: "⚠️ Bu dosya oluşturulmadı, diskte yok".
  - Yazmadığı bir betiği çalıştırmaya kalkan model ("can't open file 'hesap.py'") web'de hata aramaya gönderilmez; "dosya yok, önce write_file ile oluştur" diye net bir uyarı alır.
- **Zayıf modellere doğru araç:**
  - Yeni `system_info` aracı: işlemci, ekran kartı ve VRAM, RAM modülleri, anakart, BIOS, diskler, ağ bağdaştırıcıları, monitörler ve işletim sistemi tek çağrıda (Windows, Linux, macOS). Türkçe Windows'ta bozulan `systeminfo | findstr "İşlemci"` komutlarına gerek kalmaz; seri numaraları rapora girmez.
  - İsteğe uygun araç modele tek satırla söylenir: "PDF rapor" → `make_doc`, "donanımım" → `system_info`. Elle fpdf/reportlab betiği yazma dönemi bitti.
  - Metin protokolündeki modellere doğru ve yanlış araç çağrısı örneği gösterilir.
  - Gerçek sonuç: EVREN `auto` "bilgisayarımın donanımını PDF rapor olarak yaz" isteğinde `system_info` + `make_doc` ile 22 saniyede gerçek bir PDF üretti. Yerel Qwen2.5 7B de aynı işi yaptı.
- **Bozuk çıktı cevap sayılmaz:** model metin yerine tek bir karakteri tekrarlamaya başlarsa (`@@@@…`, Ollama "token repeat limit"), bu çöp metin ne gösterilir ne kaydedilir. Aynı istek beş kez boşuna tekrarlanmaz: tekrar cezası ve daha düşük sıcaklıkla bir kez denenir, olmazsa nedenini söyleyen açık bir hata verilir (genellikle bozuk GPU arka ucu, ör. Vulkan).
- **Sohbetlerde tam metin araması:** sol menüdeki "Sohbetlerde ara" kutusu her sohbetin her mesajında arar (SQLite FTS5, Türkçe karakterlere duyarsız), eşleşen kelimeler vurgulanır, tıklayınca sohbet açılır.
- **Model karnesi:** Ayarlar > Çoklu model > "Model performansı" her modelin bu bilgisayarda ölçülen kaydını gösterir: görev sayısı, hata oranı (başka modele geçmek zorunda kalınan görevler dahil), ilk token süresi, tur süresi, istem okuma hızı. Havuz artık **hızlı ve güvenilir modeli öne alır** (kapatılabilir).
- **Daha hızlı açılan uzun sohbetler:** yazılan dosyaların tamamı ve uzun komut çıktıları sohbet açılırken kısaltılmış gelir; adıma tıklayınca tamamı yüklenir. Büyük ekler (resim, video) kopyalanırken diğer sohbetlerin akışı artık durmaz.
- **LM Studio için de modeli kapatmayan bellek koruması:** bellek kritik düşünce kullanılan model daha küçük bir pencereyle yeniden yüklenir; çalışan görev ilerlemesini özetleyip sürer.
- **Geliştiriciler için:** `orchestrator.py` bölündü (istem metinleri `prompts.py`, niyet ve dürüstlük denetimleri `checks.py`); depoda otomatik test paketi var: `python tests/e2e/run_e2e.py` (sahte modelle 43 uçtan uca denetim) ve `python -m pytest tests`.

## 🆕 v0.11.0 ile gelenler (tıkanma yok, unutma yok, yarı boyutta ilk istem, modeli kapatmayan RAM / VRAM koruması)

Arka uç ve ön yüz satır satır tarandı; bulunan her sorun giderildi ve hem sahte modelle (27 denetim) hem gerçek modellerle (EVREN `auto`, GLM 5.3, NVIDIA Nemotron 3 Ultra 550B) yeniden test edildi.

- **Yavaş modeller için yarı boyutta ilk istem:**
  - Önceki ölçüm: bir görevin ilk isteği yerel modelde 3,4-4,8K, bulut modelde 5,4-9,8K token taşıyordu (kurallar, yetenek metinleri, araç tanımları).
  - Yeni **yalın istem** aynı bilgiyi 1,9-2,9K (yerel) ve 3,1-6,1K (bulut, yerel araç çağrısı) ile verir; bir selamlaşma 1,3K yerine 0,6K ister.
  - Model yapabildiği her şeyi tek paragraflık bir dizinden bilir, gerekeni kendisi açar (`need_tools`, `use_skill`).
  - Bir sohbette kullanılan araç grupları ve beceriler o sohbetin sonraki görevlerinde açık kalır: tekrar tekrar yükleme yok.
  - İstemin değişmeyen kısmı en başta durur; yerel sunucu onu bir kez okur ve önbelleğinde tutar. Bir grup açılınca yalnızca sona ekleme yapılır.
  - Otomatik: yerel modellerde, küçük pencerelerde ve yavaş okuduğu ölçülen modellerde yalın. Ayarlar > Güvenlik > "İlk istem boyutu" ile Yalın ya da Tam seçilebilir.
- **Kopma, model değişimi ve elektrik kesintisi (hiçbir şey yeniden yapılmaz, hiçbir şey unutulmaz):**
  - Bağlantı koptuğunda yarıda kalan cevap **devam ettirilir**, baştan yazılmaz: yazılan kısım ekranda kalır, model son sözcükten sürdürür.
  - Her kesintide (kopma, meşgul sağlayıcı, başka modele geçiş, küçülen pencere, devam ettirilen görev) uygulama modele kendi kesin kaydını verir: yazılan ve okunan dosyalar, komutlar, aramalar, yapılacaklar listesi. İlk kim yapmış olursa olsun, hiçbir model aynı şeyi ikinci kez yazmaz, okumaz ya da çalıştırmaz.
  - Yarı yolda başka modele geçen görev, araç geçmişini her modelin kabul ettiği biçimde taşır (gerektiğinde yerel çağrılar metin protokolüyle gösterilir).
  - **Takımlar:** model değiştiren üye ilerlemesini korur; devam ettirilen takım bitmiş parçaları atlar, yarıda kalanı yazdığı dosyalardan sürdürür.
  - Uzun sohbetler: geçmiş penceresinden çıkan mesajlar iz bırakmadan düşüyordu (yerel modelde 12, bulutta 30 mesajdan sonra). Artık sohbet özetine katılır, o zamana kadar kısa bir döküm olarak kalır.
  - Başarısız olan bir özet artık görevi başlamadan bitirmez.
- **Modelinizi kapatmayan RAM / VRAM koruması:**
  - Bellek azaldığında: uygulamanın kendi önbellekleri boşaltılır, kullanılmayan modeller bellekten çıkarılır.
  - Hâlâ kritikse: çalışan modelin bağlam penceresi küçültülür (16K → 8K). Model yüklü kalır; görev ilerlemesini özetleyip sürer. Sohbet hafızası uygulamada tutulduğu için hiçbir şey kaybolmaz.
  - VRAM her ekran kartında izlenir (NVIDIA, AMD, Intel; Windows ve Linux); eşikler ve güvenlik payı bilgisayarın boyutuna göre ayarlanır (8 GB dizüstünden 128 GB iş istasyonuna).
  - Çalışan modeli bellekten çıkarmak varsayılan olarak kapalı bir seçenektir (Ayarlar > Güvenlik).
  - Yerel hız: yerel modele giden her istek artık aynı pencereyi taşır. Yan çağrılar (özet, dil düzeltme) modeli iki kez yeniden yükletiyordu; boş RAM'deki küçük oynamalar da artık pencereyi değiştirmez.
  - Yazarken penceresinin sonuna gelen yerel model, istemin başını sessizce atmak yerine durdurulup devam ettirilir.
- **Canlı bağlantı (WebSocket):**
  - Yavaş ya da askıya alınmış bir tarayıcı sekmesi çalışan görevi çökertebiliyordu (dolan olay kuyruğu görevin içinde hata veriyordu). Giderildi: üretici taraf asla bloklanmaz ve hata almaz.
  - Uygulama yeniden başlatıldığında açık sekme, sayfa yenilenene kadar hiç olay almıyordu. Giderildi: sekme bunu fark edip durumunu yeniden yükler.
  - Yeniden bağlanan sekme çalışan her görevi anlık görüntü olarak alır (metin, adımlar, yapılacaklar, bekleyen onaylar); kısa kopmada yalnızca kaçırdığı olayları alır.
  - Canlı tutma sinyalleri; kapanmadan ölen bağlantı kendiliğinden yeniden açılır. Bekleyen metin parçaları tek mesajda gönderilir.
- **Yarış durumları ve takılmalar:**
  - Görev cevabını kaydederken ikinci kez durdurmak (çift tıklama), sohbeti silmek ya da uygulamayı kapatmak sohbeti sonsuza dek "çalışıyor" bırakabiliyor ve cevabı kaybettiriyordu. Giderildi.
  - Görevi çalışırken silinen sohbetin klasörü geri geliyordu. Giderildi.
  - Sonlandırılamayan bir süreç artık görevi sonsuza dek bekletmez.
  - Modelin yazdığı sohbet başlıkları yeniden çalışıyor (yalnızca ek mesaj gönderilince üretiliyordu).
- **Hız:**
  - Sohbet mesajları için veritabanı dizini: sohbet açmak ve görev başlatmak artık tüm geçmişi taramaz.
  - Ayarlar her adımda diskten okunmaz; uzun canlı cevaplar her karede değil saniyede birkaç kez çizilir.
- **Artık dediğini yapan ayarlar:**
  - Sağlayıcının "paralel istek" değeri anında uygulanır (yalnızca ilk kullanımda okunuyordu).
  - Yedek model yalnızca "bulut yedeği" açıkken kullanılır.
  - Hata veren tek bir sağlayıcı artık tüm model listesini boşaltmaz.

## 🆕 v0.10.7 ile gelenler (toplu seçme ve silme, ilk mesajda tüm yetenekler, çok dilli araç algılama, bölmeden yazım)

- **Toplu seçme ve silme:**
  - **Sohbet listesi:** "Yakın zamanlar" başlığındaki "Seç" ile sohbetler tek tek ya da "Tümünü seç" ile işaretlenip birlikte silinir. Her sohbet mesajları, özetleri, kayıtları ve çalışma klasörüyle birlikte gider.
  - **Sohbetin içi:** her mesajın altındaki seçme düğmesi seçme modunu açar.
    - Mesajlar tek tek ya da toplu seçilir; "Seçilenleri sil" ve "Tüm mesajları sil" düğmeleri vardır.
    - Silinen mesajlarla birlikte onlardan oluşan geçmiş de gider: sohbet kaydındaki satırları, onları içeren özet, yarıda kalan görevin kayıt noktası. Sohbet boşalırsa tüm kayıt klasörü temizlenir. Çalışma klasöründeki dosyalar korunur.
  - Canlı gönderilen mesajlar kaydedilince gerçek kimliklerini alır; artık hemen seçilebilir ve silinebilir.
  - Sayfa yenilenince biten görevlerin cevapları iki kez görünüyordu; bu düzeltildi.
- **Model ilk mesajda tüm yeteneklerini biliyor:**
  - Sohbet mesajında (araçsız tur) da yetenek haritası, tüm beceriler ve ajanlar (@researcher, @writer, @tester...) istemde yer alır. "Neler yapabilirsin?" sorusuna dosya, komut, web, medya, ses, görsel üretimi, belge, beceri ve ajanlarla eksiksiz cevap verilir (testte 6 sn).
  - Ajan listesi görev istemlerinde de var.
  - İstem boyu: sohbet 1,3K, görev ~4,7K token.
- **Çok dilli araç algılama:** medya (görsel, video, ses, seslendirme, altyazı) ve web tasarımı istekleri 14 ek dilde tanınır (de, fr, es, it, pt, nl, ru, uk, ar, fa, zh, ja, ko, hi). Örneğin "Erstelle eine Landingpage", "この動画の字幕を作って" ve "做一个咖啡店网站" doğru araçları açar.
- **Büyük dosyalar bölünmeden yazılır:**
  - Araç tanımındaki "40K üstünü parçalara böl" kuralı kaldırıldı; model büyük dosyayı bölüp parçaları hatalı sanarak döngüye giriyordu. Dosya boyutu ne olursa olsun tek çağrıda yazılır.
  - İstenirse Ayarlar > Ajan > "Büyük dosyaları bölerek yaz" ile bir sınır seçilebilir (varsayılan: kapalı).
  - Sağlayıcının çıktı sınırı bir dosyayı keserse yazılan kısım kaydedilir ve model kaldığı yerden devam eder; önceden aynı 40K baştan yazılıp yine kesiliyordu.
- **Düzeltmeler:**
  - Ayarlar > Web araştırması açılmıyordu: React #185 (sonsuz yeniden çizim) hatası giderildi.
  - "Hazırlanıyor" satırında karakter sayısı ve model adı iki kez yazılmıyor.
  - Ekler `attachments/` altında çalışma klasörüne kopyalanıyor.
  - Görsel üretiminde Pollinations token desteği var: logosuz görsel.
  - "kadın sesine çevir" gibi istekler ilk mesajda çalışıyor; açılmamış bir grubun aracı çağrılınca grup otomatik açılıyor.

## 🆕 v0.10.6 ile gelenler (profesyonel web tasarımı, gerçek stok fotoğraflar, test edilen JavaScript, gerçek sayılara çapalı bağlam)

- **Profesyonel web tasarımı:** sayfa yapma isteğinde (bir yapma fiili ve bir sayfa sözcüğü birlikte geçince) modele kıdemli tasarımcı kuralları eklenir:
  - Tasarım sistemi: iki Google Fonts yazı tipi, CSS değişkenleriyle palet (kontrast ≥ 4.5:1), 8 px boşluk ölçeği.
  - Yerleşim: sticky menü, hero, işletmenin ihtiyaç duyduğu bölümler, çalışan mobil menü.
  - Gerçek içerik (lorem ipsum yok), hover/focus durumları, IntersectionObserver ile görünme animasyonları.
  - Ayrıntılı adımlar `/web-design` becerisinde. Başka bir sitenin ekran görüntüsünü almak bu kuralları yüklemez.
- **Gerçek stok fotoğraflar (`stock_photo`):**
  - Openverse ve Wikimedia Commons'ta ticari kullanıma açık lisanslı fotoğrafları arar; anahtar gerekmez.
  - Fotoğrafları 1600 px JPEG'e küçültüp çalışma klasörüne indirir; yazar, lisans ve kaynak bağlantısını döndürür.
  - Model sayfada göreli yolu kullanır ve altbilgiye kaynak satırı ekler. Fotoğraf URL'si bağlamak (hotlink) ve uydurma dosya adı yasak.
  - Ölçüm: 3 fotoğraf 4 sn.
- **Sayfalar gerçekten test ediliyor:** `web_screenshot` sayfanın JavaScript'ini çalıştırır ve şunları listeler:
  - JS hataları ve konsol hataları,
  - yüklenemeyen istekler ve HTTP 4xx/5xx yanıtları,
  - kırık görseller.
  Model bunları düzeltip yeniden görüntü alır; sorun yoksa sonuçta "JavaScript hatasız çalıştı, tüm görseller yüklendi" yazar.
- **Bağlam sayacı sağlayıcının gerçek sayılarına çapalı:**
  - Her tur, sağlayıcının bir önceki isteğin gerçek boyutu için bildirdiği sayıdan başlar ve yalnızca aradaki değişikliği tahmin eder. Kırpma, özetleme ve sınırlar da bu sayıyı kullanır.
  - Ollama'nın `prompt_eval_count` değeri, önbellekten yeniden kullandığı kısmı saymaz. Önceden bu küçük sayı yanlış (düşük) bir oran öğretiyordu. Artık alt sınır olarak işaretleniyor: oran görülen en büyük değer oluyor, önbellek isabetleri bu oranla boyutlanıyor.
  - Düşünme metni bir sonraki isteğe gönderilmediği için sayılmıyor. Önceden canlı sayaç onu da ekliyor, sonra 6K → 5K gibi geri düşüyordu.
- **Yerel pencerede taşma yok:** kısa bir görevde tek büyük bir dosya pencereyi doldurduğunda sıkıştırılacak bir şey kalmıyordu ve Ollama istemin başını sessizce kesiyordu (8K'da %92). Artık kırpma ve özetten sonra hâlâ sığmıyorsa yerel pencere sığacak boyuta büyütülür ve sohbette bildirilir.
- **Yerel modeller için RAM koruması (donma veya mavi ekran yok):**
  - Bir yerel modelin bellek ihtiyacı, ağırlıkları artı bağlam penceresi × paralel yuva × token başına KV belleğidir. KV boyutu Ollama'dan GGUF bilgisiyle alınır: katman, KV başı ve baş boyutu.
  - Her istekten önce pencere boş RAM'e sığan boyutla sınırlanır; sistem için 3 GB pay bırakılır. Otomatik pencere büyütme de bu sınırı aşmaz.
  - Ağırlıkları bile sığmayan bir model hiç yüklenmez; sohbette ne yapılacağı yazılır.
  - Arka planda bir RAM bekçisi 3 sn'de bir kontrol eder:
    - boş RAM %8'in altına inerse boştaki yerel modelleri boşaltır,
    - %4'ün altına inerse çalışan modeli de boşaltır.
    Bunu bir bildirimle haber verir.
  - Ollama paralel istek ayarı varsayılan olarak **1**. Daha yüksek bir değer seçilirse RAM maliyeti TR/EN açıklamayla onaya sunulur ve ayarın altında kalıcı bir uyarı görünür. Önceden 4 olan değer, 35B'lik modelle 32 GB RAM'i aşıyordu.
- **Profesyonel canlı yanıt:**
  - Akan metin her an biçimli Markdown olarak görünür: açık kod bloğu, yarım kalın veya italik yazı ve yarım bağlantı ekranda kapatılır, ham simgeler yanıp sönmez.
  - Düşünme satırı ayrı bir ikon ve italik stille, en fazla iki satır olarak gösterilir; son tamamlanmış cümle, `)*` gibi artıklar olmadan.
- **Hızlı stok fotoğraf:**
  - Bir sayfanın tüm görselleri tek çağrıda gelir: konular virgülle ayrılır ve paralel aranır. Ölçüm: 6 fotoğraf 5,5 sn; aynı sorgu önbellekten 0,1 sn.
  - Türkçe sorgular otomatik İngilizceye çevrilir.
  - Sonuçlar başlık ve etiket uyumuna göre sıralanır, böylece alakasız fotoğraflar elenir.
  - Uzun bir ifade sonuç vermezse otomatik olarak kısaltılmış hâlleri denenir.
  - Her konuya 30 sn süre sınırı vardır.
  - Önceden her fotoğraf ayrı bir model turu harcıyordu ve uzun ifadeler "No usable photo" hatası veriyordu; deepseek görevi 815 sn sürdü.
- **Tekrar döngüsü koruması:** model aynı cümleyi 4 kez ya da daha fazla yazmaya başlarsa akış kesilir, tekrarlar silinir ve sohbette bir not gösterilir. Önceden aynı paragraf dakikalarca onlarca kez yazılıyordu.
- **Sızıntı yok:**
  - Ekran görüntüsü adımında ve sorun listesinde kullanıcının tam `file://` klasör yolu yerine yalnızca dosya adı ya da göreli yol görünür.
  - Eksik bir yerel dosya, ne yapılacağını söyleyen bir mesajla raporlanır: "missing file: images/x.jpg – indir ya da başvuruyu kaldır".
- **Değişiklik kartı işlem işlem toplar (Claude Code gibi):**
  - Her `write_file` ve `edit_file` kendi +/− sayısını taşır. Kart, gruplar ve başlık bu sayıları toplar; örneğin yazılan +597 ve iki düzenleme (+2 −2, +2 −2) birlikte +601 −4 eder.
  - Görsel grubunda +0 −0 yerine toplam boyut görünür.
  - Görev sürerken aynı gruplu kart "Canlı" etiketiyle görünür ve her işlemde anında güncellenir; bitince son inceleme kartına dönüşür.
- **Yerinde "Tüm farkları aç" (modal yok):**
  - Kart içinde açılır.
  - Dosyalar Kod / Belge / Görsel... gruplarında ve her dosya açılıp kapanan bir akordeon.
  - Dosya adı ve kod içinde arama yapılabilir.
  - "Toplam fark" ile "İşlem işlem" görünümleri arasında geçiş yapılabilir.
- **Yazının ortasında tıkanma:** dosya akarken sağlayıcı 120 sn veri göndermezse yazılan kısım kaydedilir ve model oradan devam eder. Önceden 300 sn'lik genel zaman aşımı bekleniyordu (evren/deepseek).
- **Doğru sıralı paralel işler:** aynı cevapta yazılan bir dosyaya bakan ekran görüntüsü ya da okuma, yazmanın bitmesini bekler. Fotoğraf ve medya incelemesi okumalarla paralel çalışır.
- **Görsel model sohbet modeliyle aynıysa da betimleme gelir:** önceden deepseek hem sohbet hem görsel model seçiliyken sayfa hiç betimlenmiyordu.
- **Her model görür ve duyar (`inspect_media`):** resim göremeyen, ses duyamayan modeller bile bir görsel, video ya da ses dosyasını eksiksiz inceler. Hepsi yerel kütüphanelerle yapılır; görsel model betimlemesi isteğe bağlıdır.
  - **Görsel:**
    - boyut ve EXIF bilgisi (kamera, tarih, konum verisi var mı),
    - baskın renkler, parlaklık ve kontrast,
    - netlik ve yüz sayısı (OpenCV),
    - içindeki yazı (OCR: Windows OCR / Tesseract / RapidOCR).
  - **Video:**
    - süre, çözünürlük, fps ve codec bilgisi (ffprobe),
    - sahne değişimlerinden anahtar kareler (ffmpeg) ve numaralı kare sayfası (kullanıcıya da gösterilir),
    - karelerdeki yazılar (OCR),
    - kare sayfasının görsel model betimlemesi,
    - konuşmanın metni.
  - **Sohbete eklenen resimler:** görsel model yoksa ya da hata verirse uygulama resmi kendisi inceler ve bilgileri isteğe ekler.
- **Konuşmayı yazıya çevirme (`speech_to_text`):** ses ve videolarda, çevrimdışı faster-whisper ile (CPU, int8). Zaman damgalı metin döner, `.srt` altyazı ve `.txt` dosyası yazılır. Dil otomatik algılanır; model boyutu tiny, base, small ya da medium seçilebilir.
- **Yazıyı konuşmaya çevirme (`text_to_speech`):** ücretsiz Microsoft sinir ağı sesleriyle `.mp3` üretir. Dil, cinsiyet, ses ve hız seçilebilir, metin uzunluğu sınırsızdır. Seslendirme ffmpeg ile videoya eklenebilir.
- **Yerel modeller için yalın tasarım (hızlı, az RAM):**
  - **Metin protokolü varsayılan:** Ollama, native araç çağrısını dosya tamamen bitince gönderiyordu; 535 sn boyunca sessizlik oluyordu. Artık dosya canlı akar: karakter sayısı görünür ve kopmada kalınan yerden devam edilir. Model profilinden "native" seçilerek eski davranış geri açılabilir.
  - **Daha küçük pencere:** varsayılan bağlam penceresi 32K yerine 16K. Pencere yalnızca gerektiğinde ve RAM'in izin verdiği kadar büyür.
  - **Erken özet:** yerel görevde kırpma ve özet %65'te başlar. Büyütmeden önce özet denenir, çünkü pencere boyutu değişince model yeniden yüklenir ve KV belleği büyür.
  - **Kısa geçmiş:** 30 yerine son 12 mesaj gönderilir. Eskisi sohbet özetinde ve durum dosyasında durur; kesintiden sonra kayıt noktasından devam edilir.
- **Meşgul sağlayıcıda anında geçiş (devre kesici):**
  - 503, hız sınırı ya da tıkanma ikinci kez gelince aynı modelde 15–30 sn'lik beklemeler yapılmaz. Görev sırayla şunlardan birinde sürer:
    1. Ayarlar > Modeller'deki yedek model,
    2. çoklu model havuzunun en müsait modeli,
    3. sağlayıcının kendi yönlendiricisi (`evren:auto`).
  - Görev hiçbir zaman yerel modele taşınmaz (RAM korunur).
  - Meşgul model 90 sn dinlenir; o sırada başlayan görevler de doğrudan alternatifle başlar.
  - İlk meşgul yanıtta tek bir kısa (5 sn) deneme yapılır.
- **Ses stüdyosu:** `text_to_speech` ile üretilen her ses, sohbette oynatıcılı bir kart olarak görünür. "Sesi değiştir" o dildeki tüm sesleri kadın/erkek etiketiyle listeler:
  - ▶ metnin ilk cümlesini o sesle anında okur (canlı önizleme),
  - "Bu sesi kullan" ses dosyasını seçilen sesle yeniden üretir ve oynatıcı yenilenir.
- **Ses ve video kartları:** üretilen mp3/wav ve mp4/webm dosyaları belgeler gibi kart olarak listelenir: gerçek oynatıcı, indirme ve açma düğmeleri.
- **Profesyonel transkript:** `speech_to_text` sonucu zaman aralıklı bir tablo (Zaman | Metin) olarak verilir; konuşma süresi, dil ve dosya adları da yazılır. `inspect_media` aynı whisper modelini kullanır, bellekte tek kopya tutulur.
- **Ücretsiz yerel görsel model:** görsel model yoksa ya da yanıt vermezse, RAM'e sığdığı sürece küçük bir yerel Ollama görsel modeli kullanılır (ör. `ollama pull moondream`, 1,7 GB). OCR, renk adları (ör. "#8b4513 brown"), yüz ve netlik analizi her durumda çalışır.
- **Yerel modeller için daha güçlü koruma:**
  - Windows'ta boş RAM'e ek olarak bellek taahhüt sınırı (RAM + sayfa dosyası) da izlenir. 32 GB RAM ve 5 GB sayfa dosyası olan bir makine, "boş RAM" yeterli görünürken bu sınır yüzünden kapanmıştı.
  - Bekçi 2 sn'de bir kontrol eder: %12'nin altında boştaki modeli, %6'nın altında çalışan modeli boşaltır. Whisper modeli de serbest bırakılır.
  - Ollama, fiziksel çekirdek sayısının bir eksiğiyle çalışır (ör. 6 çekirdekte 5); böylece aşırı ısınma ve donma olmaz.
  - Boşta bekleyen model 10 dk sonra bellekten çıkar.
  - Durdurulan görev kayıt noktasından "devam et" ile sürdürülür; hiçbir şey unutulmaz.
- **Akış darboğazları giderildi:**
  - Uzun düşünce her parçada baştan birleştirilip 6 KB'lık olay olarak gönderiliyordu; artık saniyede en fazla 4 kez güncellenir.
  - Metin protokolünde yazılan dosya her parçada baştan taranıyordu; artık kalınan yerden aranır. 40 KB'lık dosya 1'er karakterle beslendiğinde 274 ms sürüyor, süre dosya boyuyla doğrusal artıyor.
- **Görsel üretimi (`generate_image`):**
  - Açıklamadan yeni bir resim üretir: gerçekçi fotoğraf, ürün çekimi, 3B görünüm ya da illüstrasyon. Ücretsiz FLUX modeli Pollinations üzerinden çalışır; anahtar gerekmez, bir görsel birkaç saniyede gelir.
  - "Buna benzer bir resim" isteğinde model önce `inspect_media` ile orijinali inceler, betimlemeyi istem olarak kullanır.
  - Kesin grafik ve diyagramlar için kod (matplotlib/skia) önerilir.
  - Ücretsiz katman köşeye küçük bir pollinations.ai logosu koyar; bu, hizmetin atıf şartıdır ve silinmez. Ayarlar > Web araştırması > Görsel üretimi bölümüne auth.pollinations.ai'den ücretsiz kayıtla alınan token girilirse görseller resmi olarak logosuz üretilir. Test düğmesi görselin logosuz gelip gelmediğini gösterir.
- **Model yeteneklerini ilk mesajda bilir:**
  - "kadın sesine çevir", "sesli oku", "benzer bir resim oluştur" gibi ifadeler doğru araç grubunu açar ve bilgi sorusu gibi yalnızca okuma moduna düşmez.
  - Model, açılmamış bir grubun aracını çağırırsa grup otomatik açılır ve çağrı çalışır. Önceden "böyle bir aracım yok" deyip vazgeçiyordu.
- **Ekler çalışma klasöründe:** sohbete eklenen resim ve dosyalar `attachments/` altına kopyalanır ve yolu modele bildirilir; sonraki mesajlarda da kullanılabilir. Önceden "resmi analiz ettim ama dosya yok" deniyordu.
- **Okunabilir canlı düşünme:** "Daha iyi:" gibi tek kısa satır yerine son tamamlanmış cümleler (~160 karakter) ve yazılmakta olan cümlenin başı gösterilir, en fazla 3 satır.
- **Mobilde izin düğmesi:** dar ekranda yalnızca ikon görünür, etiket iki satıra bölünmez.
- **Tek seferde yazım, parça parça istek yok:**
  - Kurtarılan dosyanın geri kalanı tek çağrıda istenir. Önceki "parçalara böl" yönergesi her parçayı ayrı bir model turuna çeviriyordu ve deepseek'te görev 17 dk sürdü.
  - `write_file` tanımı da tam dosyayı tek çağrıda yazmayı söylüyor; yalnızca 40K karakterin üstünde 2–3 parçaya izin var.
  - Ölçüm: landing page 145 sn (4 tur). Deepseek meşgulken görev alternatife geçerek 292 sn'de bitti; önceden 1200 sn'lik zaman aşımına düşüyordu.
- **Akış ortasında durma:**
  - Yazarken 75 sn veri gelmezse yazılan kısım kaydedilir. Native araç kullanan model bundan sonra kesintisiz akan metin protokolüne geçer (kalıcı).
  - Bu durum "Sağlayıcı meşgul" diye değil, "Akış durdu, kaldığı yerden sürüyor" diye gösterilir.
  - Aynı görevde ikinci duruşta model alternatife geçer.
- **Doğru sayaçlar:** devam yazımları (append) ve kurtarılan kısım da +N satır olarak sayılır; canlı kart "+0 −0" göstermez.
- **Görsel adları ve eksik dosya önerisi:**
  - İlk fotoğraf ek olmadan kaydedilir (`latte-art.jpg`, sonra `-2`, `-3`); modellerin tahmin ettiği ad tutar.
  - Eksik bir dosya için klasördeki en yakın dosya önerilir: "bunu mu demek istedin: images/latte-art-cup.jpg?".
- **Fark görünümü:**
  - Birden çok işlemi olan dosyada varsayılan görünüm "İşlem işlem": düzenlemelerin + ve − satırları hemen görünür, büyük ilk yazım katlı başlar.
  - Açılan her dosyada "Kod editöründe aç" düğmesi var; dosyayı tarayıcıda değil Monaco editörde açar.
  - Ses seçici gerçekten kullanılan sesi işaretler; seçim mesaja kaydedilir.
- **Hatalar:** `speech_to_text` artık resim dosyasında "IndexError" yerine `inspect_media` önerir. OpenCV 5.x, yüz modelleri olmadan geldiği için `<5` ile sabitlendi.
- **Çökmeye dayanıklı kayıt:** ayarlar ve gizli anahtarlar önce geçici dosyaya yazılıp diske işleniyor, sonra yerine konuyor. Mavi ekran anında VERSION dosyası 8 sıfır bayta dönmüştü; ayarlar ve anahtarlar artık böyle bozulamaz.
- **Kod taraması:** ölü kod ve kullanılmayan global kaldırıldı; tüm arka uç pyflakes'ten temiz geçiyor, ön uç derleniyor.

## 🆕 v0.10.5 ile gelenler (2,4 kat hızlı yerel görevler, yarı boyutta istem, gerçek token verisiyle bağlam, hızlı görsel model)

- **Bağlam yönetimi sağlayıcının gerçek sayılarıyla:** her turda sağlayıcının bildirdiği gerçek istem boyutu okunur: Ollama `prompt_eval_count`, OpenAI uyumlularda `include_usage` ile `usage.prompt_tokens`, Anthropic `input_tokens`, artık Gemini `usageMetadata` da. Bu değerle yerel tahmin arasındaki oran model başına öğrenilir ve kaydedilir (`data/ctx_ratio.json`). Kırpma, özetleme ve görev başı sıkıştırma artık bu gerçek boyutlara göre karar verir. Önceden oran yalnızca sayacı değiştiriyor, kararlar ham tahminle veriliyordu.
- **Bağlam taşması doğru ele alınıyor:** Ollama'nın "request (9297 tokens) exceeds the available context size (8192 tokens)" hatası tanınmıyordu. Hata "model araç çağrısını desteklemiyor" sanılıyor ve görev sıkıştırma yerine metin protokolüne geçiyordu. Artık bağlam taşması sayılıyor; mesajdaki gerçek sayı modelin oranını düzeltiyor.
- **Talimatlara yetmeyen yerel pencere:** sabit istem (kurallar + araç tanımları) tek başına yerel pencereye sığmıyorsa (ör. 8K), pencere bir kez çalışan en küçük boyuta (en az 16K) çıkarılır. Bu, model seçicideki seçim gibi kaydedilir ve sohbette bildirilir.
- **Görsel model ekran görüntülerine gerçekten bakıyor:** sohbet modeli resim göremiyorsa `web_screenshot` ve `browser_screenshot` görüntüyü Ayarlar > Modeller'deki görsel modele (ör. deepseek-v4.1-flash) gönderir. Model yalnızca sayfa metni yerine gerçek bir betimleme alır. Bir modelin resim görüp göremediği artık yalnızca adından değil, sağlayıcının API verisinden (Ollama capabilities, OpenRouter modalities) anlaşılıyor.
- **Ayar denetimi (her ayarın gerçek kullanımı kontrol edildi):**
  - Ollama kartındaki "Akış" anahtarı artık uygulanıyor.
  - Anthropic ve Gemini kartlarında hiçbir şey değiştirmeyen anahtar yerine "Her zaman akışlı" yazıyor.
  - Sıkıştırma eşiği aralığı %40-95 oldu.
  - Bulut yedeği açıklaması gerçekte ne yaptığını anlatıyor (her sağlayıcı, yalnızca erişilemez/aşırı yük hatalarında).

- **Katmanlı sistem istemi (ihtiyaç anında ayrıntı, önbellek dostu):**
  - Her istekte tüm sistemlerin kısa bir **yetenek haritası** bulunur (araç grupları, programlar, adlarıyla beceriler); model uygulamanın yapabildiği her şeyi bilir.
  - Tam tanımlar yalnızca gerektiğinde gelir: bir grubun araçları `need_tools` ile, bir becerinin talimatları `use_skill` ile, kurulum / video-ses / Markdown kuralları ise istek o konudaysa.
  - Hiç değişmeyen kısım başta, klasör, tarih ve ortam sonda durur; böylece Ollama ve bulut istem önbellekleri her turda başı yeniden kullanır.
  - Tek bir URL ya da "ekran görüntüsü al" artık 14 tarayıcı aracını yüklemiyor; bu araçlar sayfada işlem yapma sözcükleriyle geliyor.
  - Aynı ekran görüntüsü isteği **9.1K'dan 4.5K istem token'ına** indi. Yalnızca işlemcide çalışan yerel modelde görevin tamamı **433 sn'den 180 sn'ye** düştü (ilk yanıt 147 sn → 57 sn).
- **Hızlı ve kendini onaran görsel model:**
  - Ekran görüntüleri **bilinen en hızlı görsel modele önce** gider (ayarlı modele küçük bir öncelik verilir); yavaş, meşgul ya da boş dönen model saniyeler içinde sıradakine devreder. Her seferinde tek istek gider, yarışan istek yoktur: bir sağlayıcı aynı anahtarın isteklerini sıraya koyar (iki istek birlikte gönderilince 4 sn'lik model yavaş olanın arkasında 55 sn bekledi).
  - Her modelin hızı öğrenilir (`data/vision_speed.json`); görsele özel modeller (qwen-vl, llava, pixtral...) önce denenir.
  - Betimleme kısa ve odaklıdır. Ölçüm: önce 60-90 sn ya da zaman aşımı, şimdi **3,5-4 sn**.
- **Yerel modelde yan iş yok:** sohbet başlığını ayarladığın bir bulut modeli (görsel/yedek/havuz) yazar ya da başlık isteğin ilk sözcüklerinden alınır. Önceden işlemcide 20-40 sn süren başlık çağrısı bir sonraki mesajını bekletiyor ve sohbeti Ollama'nın istem önbelleğinden çıkarıyordu.
- **Bağlantıyı açık tutan sinyalleri ayırt eden takılma algısı:** araç çağrısını yazarken ping gönderen bir sağlayıcı (evren) sessizlik sayacını her seferinde sıfırlıyordu; takılan bir istek 6 dakikadan fazla bekledi. Artık sayacı yalnızca gerçek veri sıfırlıyor ve 75 sn sonra akışlı metin protokolüne geçiş orada da çalışıyor.
- **Sessiz dosya yazımı bitti (kopmaların yaşandığı yer):**
  - Bazı bulut sağlayıcılar araç çağrısını (bütün bir dosyayı) ancak bitince gönderiyor: dakikalarca sessizlik oluyor ve kopmada her şey kayboluyor.
  - Bir model bunu büyük bir çağrıda ilk kez yaptığında sistem hemen öğrenir ve o modeli kalıcı olarak akışlı metin protokolüne geçirir: dosyalar canlı akar, kopmada kaldığı yerden devam edilir.
  - 75 sn koruması aynı turda önce kısa bir çağrı (todo) gelse de çalışır; önceden orada kapalı kalıyordu.
- **Claude Code gibi koordineli: plan, toplu iş, yarış yok:**
  - Her model cevabı bir çağrıdır. Bu yüzden modelden planı ilk adımlarla birlikte göndermesi ve bağımsız her işi aynı cevaba koyması istenir (birkaç okuma, arama, farklı dosyalara yazma); bunlar paralel çalışır.
  - Model isteklerinin kendisi asla yarışmaz: görev başına aynı anda tek istek gider.
  - Yan işler (sohbet başlığı) aynı sağlayıcıda görev akarken bekler.
- **Sayfa açık değilken browser_screenshot** artık boş sayfanın fotoğrafını çekmek yerine önce sayfanın açılmasını söylüyor.

## 🆕 v0.10.4 ile gelenler (pro ayarlar, yerel GPU ayarları, GitHub'dan MCP, yeni beceriler, otomatik araç kurulumu)

- **Model yetenekleri her yerde:** Ayarlar'daki tüm model seçiciler (aktif, görsel, yedek, profiller, çoklu model havuzu ve ajanlar) sohbetteki seçici gibi araç / görsel / düşünme ikonlarını, bağlam boyutunu ve model boyutunu gösterir. Yedek model veya profil modeli seçilince tam yetenek kartı (sağlayıcı, bağlam, native araç, görsel, düşünme) listelenir.
- **Tüm sayısal ayarlarda kaydırıcı + sayı:** sıcaklık, çıktı sınırı, istek ve eşzamanlılık sınırları, kotalar, zaman aşımları, bağlam penceresi ve diğerleri tek bir kaydırıcı, elle yazılabilen sayı kutusu (`32k`, `1.5m` yazılabilir), otomatiğe dön düğmesi ve geniş aralıklarda logaritmik ölçekle ayarlanır.
- **Yerel ve bulut modellerinde anlık senkron:** uygulama açıldıktan sonra başlatılan veya kapatılan Ollama / LM Studio 5 saniye içinde, sayfa yenilemeden algılanır; başarılı Test eski hatayı hemen kaldırır; başka pencerede değişen ayarlar canlı uygulanır.
- **Ollama çalışma ayarları (Ayarlar > Sağlayıcılar > Ollama):** Vulkan GPU desteği (`OLLAMA_VULKAN`), RX 580 gibi eski kartlar için Vulkan FP16 kapatma (`GGML_VK_DISABLE_F16`), flash attention, KV önbellek türü Tam / Yarı / Az (`f16` / `q8_0` / `q4_0`), paralel istek ve en fazla yüklü model. Ollama'nın okuduğu yere kaydedilir (Windows kullanıcı ortam değişkenleri, `setx` ile aynı; "Otomatik" değişkeni `reg delete` gibi siler), yeniden başlat düğmesiyle uygulanır, yüklü modellerin GPU payı gösterilir ve komut karşılıkları listelenir. Hepsi Otomatik başlar.
- **LM Studio yükleme seçenekleri:** GPU'ya yükleme (tam / %75 / %50 / %25 / kapalı), flash attention, KV önbelleği GPU'da veya RAM'de, değerlendirme grubu ve boşta kalma süresi; her model yüklemesinde gönderilir (REST `/api/v1/models/load` veya `lms` komutu).
- **Ajan npm, PyPI veya GitHub'dan MCP ekler:** yeni `mcp_add` aracı bir MCP sunucusunu bağlar (npx paketi, uvx/pip paketi, GitHub'dan klonlanıp derlenen depo veya uzak URL), anahtarlarını gizli depoda saklar ve araçlarını döndürür; bozuk paket takılmadan yaklaşık bir saniyede hatasını bildirir. Resmi filesystem sunucusu (npm), GitHub'dan klonlanıp derlenen weather örneği ve mcp-server-time (PyPI) ile uçtan uca test edildi. Düzeltme: Windows'ta boşluklu klasördeki `npx` (`D:\Program Files\nodejs`) MCP sunucularını başlatamıyordu.
- **Çalışma klasörüne paket kurulumu:** Composer (PHP), npm, pip, Go, Cargo ve GitHub projeleri; sistem programları winget / brew / apt ile (yeni `packages` becerisi). PHP varsa Composer otomatik kurulur (sağlama toplamı doğrulanmış composer.phar); php.ini'siz PHP'de (winget sürümü) openssl, curl, mbstring, zip, intl, gd, pdo... açılır, böylece `composer require` doğrudan çalışır.
- **Otomatik araç kurulumu:** `install.bat` eksikse ffmpeg, Git, GitHub CLI ve PHP'yi winget ile kurar; `install.sh` ffmpeg, git, gh, php ve composer'ı brew / apt / dnf / pacman ile kurar. Uygulama kendisi de `static-ffmpeg` ile (Windows, macOS, Linux için ffmpeg + ffprobe) yedek kurar ve PATH'e ekler; algılanan araçlar modelin ortam satırında görünür.
- **Profesyonel grafik ve medya kütüphaneleri:** Python'da `skia-python` (Skia motoru), `drawsvg`, `vtracer` (bitmap'ten vektöre), `qrcode`, `static-ffmpeg`, `paramiko` (SSH/SFTP); Node'da ajanın betikleri için NODE_PATH üzerinde `sharp`, `@resvg/resvg-js`, `opentype.js`.
- **Yeni beceriler (Claude Code tarzı yetenekler):** `site-test` (hata raporlu uçtan uca site testi), `remote-server` (SSH / SFTP / FTP: yedekli dosya bulma, okuma, test, yükleme), `social-media` (X, Instagram, LinkedIn, TikTok; resmi API'ler veya oturum açık tarayıcı, yayın yalnızca onayla), `ads-manager` (Meta, Google Ads, Yandex Direct rapor ve kampanya; yeni kampanyalar duraklatılmış, bütçe yalnızca onayla), `graphics` (logo, ikon, banner, SVG/PNG paketleri), `mcp-servers`, `packages`, `code-review` (hatalar, OWASP güvenliği, testler ve lint).

## 🆕 v0.10.3 ile gelenler (sahte dosya yok, döngü yok, profesyonel video oynatıcı)

- **Kod bloğu değil iş:** model işi yapmak yerine komutu kod bloğu olarak yazarsa (```bash ffmpeg ...```), o komut onun yerine gerçekten çalıştırılır ve sonucu modele döner. "Komutu çalıştır" hatırlatması en fazla iki kez yapılır; sonsuz döngü yok.
- **Sahte dosya yok (tüm türler):** metin, ikili biçimli bir dosyaya (mp4, png, pdf, docx, xlsx, zip, exe…) yazılamaz; model dosyayı gerçek programıyla üretmeye yönlendirilir. Komutların yazdığı her dosya türüne göre denetlenir (boş mu, gerçek PDF/ZIP/resim/video/JSON mı); bozuk çıktı "başarılı" sayılmaz.
- **Başarısız adım "bitti" diye sunulmaz:** son komut başarısızken model bitti derse önce düzeltmesi istenir; düzeltemezse cevabın başında açık bir uyarı görünür.
- **ffmpeg:** var olan dosyanın üzerine yazma sorusu (`-y`) otomatik; artık dosya silme ya da onay gerekmez. MP4 altyazısı için `mov_text`, yakma için `subtitles=` yönergesi.
- **Tam erişim gerçekten tam:** "Tam erişim" kipinde dosya silme ve riskli komutlar için onay istenmez (yalnızca disk biçimlendirme gibi sistemi bozan komutlar her kipte engelli). "Otomatik" kipte görevin kendi oluşturduğu dosyalar onaysız silinir.
- **Profesyonel video oynatıcı:** gizlenen özel kontroller, sürüklenebilir ilerleme çubuğu (ara bellek ve üzerine gelince zaman), ses (hatırlanır), hız menüsü, döngü, yan altyazılar (.vtt/.srt otomatik bulunur, SRT dönüştürülür), resim içinde resim, tam ekran, kareyi PNG kaydetme, çözünürlük rozeti, klavye kısayolları (boşluk/k, ←/→, j/l, ↑/↓, m, f, c, 0-9, < >) ve bozuk/desteklenmeyen dosyada açık hata mesajı.
- **Tam erişimde kendi sitende üyelik/giriş:** isteğinde adını verdiğin sitede (ör. "siteadi.com'a şu bilgilerle üye ol") model şifreyi yazar ve kayıt/giriş düğmelerine onaysız basar. Kart/banka bilgisi gerçek sitelerde yine yazılmaz.
- **CAPTCHA'da otomatik devir:** CAPTCHA çıkınca tarayıcı gizliyse görünür pencere açılır, sayfa öne gelir; sen çözdüğün anda algılanır ve görev kendiliğinden devam eder ("bitti" demen gerekmez). Model CAPTCHA'yı kendisi çözmez.
- **Düzeltme:** boşluk içeren klasördeki yerel dosyalar (`file:///…%20…`) tarayıcı aracında açılamıyordu.
- **Açılır pencereler kapanır (tüm siteler):** sayfanın önüne çıkan modallar (bülten, kampanya, cinsiyet seçimi, uygulama reklamı…) algılanıp kapatma düğmesiyle ya da Escape ile kapatılır; çerez bandında her zaman "Tümünü Reddet" seçilir; şifre/kart alanı olan pencerelere dokunulmaz. Ayarlardan kapatılabilir.
- **workspace/ kaldırıldı, her şey chat/ altında:** projesiz her sohbetin klasörü artık `chat/<sohbet kimliği>/` (dosyaları) ve içindeki gizli `.session/` (kaydı); klasör seçilmeden açılan projeler `chat/projects/`. Eski `workspace/` ve `chat/<id>-session` içeriği ilk açılışta otomatik taşınır, hiçbir şey silinmez. Sohbet silinince klasörünün tamamı silinir. Yeni sohbetin Dosyalar ekranı artık boş bir "workspace" ve dönen simge yerine "klasör ilk mesajla oluşur" der.
- **Görev sürerken gönderilen mesajlar:** model nihai cevabı yazarken gelen mesaj artık o cevabı silmez; cevap korunur, mesaj ardından işlenir ve ikisi tek mesajda gösterilir. Görev biterken gelen mesaj kaybolmaz, kendiliğinden yeni görev olur. Bu mesajlar sohbette "Görev sürerken eklendi" etiketi ve "sırada / işlendi" durumuyla, adımlarda "Yönlendirmen işlendi" satırıyla belirgin görünür.
- **Sessiz sağlayıcıda tıkanma yok:** araç çağrısını ancak bitince gönderen bulut sağlayıcılarda (ör. evren deepseek) dosya yazarken dakikalarca hiçbir şey gelmiyor, 300 sn sonunda kopup baştan yazılıyordu. Artık 75 sn sessizlikte tur akışlı metin protokolüyle yeniden yapılır (dosya canlı akar, kopmada kaldığı yerden sürer) ve bu tercih modele kalıcı kaydedilir (`data/stream_tools.json`): sonraki görevler baştan hızlı protokolle başlar.
- **Yenilemede süre sıfırlanmaz:** sayfa yenilenince çalışan görevin toplam süresi sunucudaki başlangıç zamanından devam eder.
- **Model ortamını bilir:** her istemde kısa bir ortam bölümü var: işletim sistemi (sürüm/derleme/mimari), çalışma klasörü ("çalışma alanı") ve tek satırlık yetenek özeti; ayrıntılı kabuk/araç sürümleri yalnızca komut çalıştırılacağında eklenir (sohbet isteminde toplam ~740 token).
- **Bulut sağlayıcılarda eşzamanlılık sınırı (meşgul/503 hataları):** uygulama aynı sağlayıcıya aynı anda birçok istek atabiliyordu (başlık, özet, görsel model, ekip üyeleri, ikinci sohbet ya da ikinci kurulum); evren gibi sağlayıcılar bunu "Model şu anda dolu" (HTTP 503) ile reddediyordu. Artık her bulut sağlayıcı için bir istek kuyruğu var: fazla istekler hata yerine sırada bekler, "meşgul" veya 429 yanıtından sonra o sağlayıcıya 5 dakika tek tek istek gider. Belgelenmiş sınırlar varsayılan olarak girildi (Ollama Cloud 1, DeepSeek 8, Mistral 60/dk ve 2, SambaNova 20/dk, OpenRouter `:free` 20/dk, Hugging Face 2, Cerebras 2, evren 3); sağlayıcı kartındaki "Eşzamanlı istek" alanından değiştirilebilir.
- **Küçük düzeltmeler:** dosya kartı 0 baytlık dosyayı "0 B" gösterir (eskiden "1 KB"); dosya önizlemesinde video küçük resmi ve oynat düğmesi.

## 🆕 v0.10.2 ile gelenler (kopmada kaybolmayan dosyalar, tek kaynaklı sürüm, hızlı ve düzenli belgeler)

- **Kopmada yazılan kaybolmaz:** model bir dosya veya belge yazarken bağlantı koparsa, o ana kadar yazılan kısım (tam satırlar) dosyaya kaydedilir ve model yalnızca kalanını `append` ile ekler; baştan yazmaz. Yazılan kısım birkaç saniyede bir diske de kaydedilir: elektrik kesintisinden sonra "devam et" ile aynı noktadan sürer. Araç çağrısını ancak bitince gönderen sağlayıcılarda kopmadan sonra akışlı metin protokolüne geçilir.
- **Tekrar okuma yok:** görevde okunmuş ve değişmemiş dosya yeniden okunmaz; içine gömülü base64 resim verisi modele gönderilmez (megabaytlarca gereksiz token).
- **Yapılacaklar kendini günceller:** PDF/Word/sunum üretilince ilgili "rapor/PDF hazırla" maddesi ve ondan önce açık kalan adımlar otomatik tamamlanır.
- **Paralel yazma:** farklı dosyalara yazan çağrılar (ör. aynı turda PDF ve Word) aynı anda çalışır; sonuçlar sırayla bağlama girer.
- **HTML sayfaları:** her sayfaya `<meta charset="utf-8">` eklenir ve önizleme sunucusu UTF-8 bildirir (Türkçe harfler bozulmaz); betik içeren sayfalar yazılınca başsız Chromium'da açılıp JavaScript hataları modele bildirilir.
- **Belgeler:** Word'de dolgulu kapak bloğu (başlık, giriş, tarih), alt çizgili bölüm başlıkları, 2. sayfadan itibaren başlık satırı ve "sayfa x / y"; PowerPoint'te numaralı bölüm başlık bandı.
- **Ayarlar:** görsel model artık ana model resim göremediğinde ekli resimleri betimler; arayüz dili arka uca da kaydedilir; bulut yedek modeli meşgul/sunucu hatalarında da devreye girer.
- **Sürüm tek yerden:** kökteki `VERSION` dosyası; `python set_version.py 0.12.0` sürümü package.json ve README rozetlerine de yazar; Hakkında sayfası ve `/api/health` dosyadan okur.
- **Mesaj kutusu:** satır içi kod aç/kapa (iç içe olmaz, seçim korunur), her şey silinince biçim kalmaz, menüden kod bloğu/alıntı seçilince imleç alt satıra geçer.
- **Canlı testte bulunanlar:** ekran görüntüsü aracıyla alınan PDF artık tek uzun sayfa değil A4 sayfalar; `shell` belirtilmeden gönderilen Python kodu PowerShell yerine Python ile çalışır; model sonraki maddeyi işaretleyince açık kalan önceki madde de tamamlanır (dosya adı farklı yazılsa bile).
- **Tarayıcı performansı:** uzun görevlerde adım listesi son 60 adımı gösterir (öncekiler isteğe bağlı), adım satırları yalnız değişince yeniden çizilir, uzun düşünme metni kısaltılır. Joker yollu (`gorseller/01…05-*.png`) sahte dosya çipleri artık oluşmaz.

## 🆕 v0.10.1 ile gelenler (söz değil iş, doğrulanmış belgeler, yönlendirme, hızlı ekipler)

- **Söz verip yapmama biter:** model "şimdi başlatacağım / oluşturuluyor…" yazıp araç çağırmazsa görev bitmez; gerçekten yapması istenir, yine yapmazsa "hiçbir şey çalıştırılmadı" diye açıkça yazılır.
- **Doğrulanmış belgeler:** var olmayan resim belgeye girmez ve modele bildirilir; grafik istenip belgede yoksa model üretip eklemeye zorlanır; belgedeki ondalıklı rakamlar görevde okunan kaynaklarla karşılaştırılır. Veri XML'leri (TCMB kurları gibi) alan adlarıyla ve eksiksiz okunur.
- **HTML rapor bileşenleri:** KPI kartları, çubuk grafik, bilgi kutusu, rozet, iki sütun — resim dosyası gerekmez; Word ve PowerPoint'te otomatik görsele dönüşür. Her belgenin kaynağı `.doc-sources/` altında saklanır; sonradan "grafik ekle" denince aynı belge düzenlenir.
- **Çalışırken yönlendirme:** görev sürerken yazdığınız mesaj görevi durdurmaz; çalışan göreve yönlendirme olarak iletilir.
- **Model değişse de devam:** yarıda kalan görevin araç sonuçları da saklanır; "devam et" başka modelde bile aynı şeyleri yeniden aramadan sürer.
- **Canlı ayrıntı ve süre:** "Hazırlanıyor" adımı modelin ne yaptığını söyler (istemi okuyor / yanıt yazıyor / araç çağrısı yazıyor, token ve model adıyla); adım başlığında toplam süre anlık akar (1 dk 30 sn).
- **Hızlı çoklu model:** uzun hız sınırı beklemesinde hemen havuzdaki müsait modele geçilir; ekip üyeleri sağlayıcılara dağıtılır, sağlayıcının dakikalık token hakkı seçimde hesaba katılır, araç çağrısı desteklemeyen modeller de üye olabilir, üyeler birbirinin işini baştan bilir, biten ekipte açık ortak görev kalmaz. Aynı görev 346 sn yerine 58 sn.
- **Sohbet başlığını model yazar** (kullanıcının verdiği başlığa dokunulmaz); başlıkta Markdown olmaz, uzun başlık üzerine gelince kayar.
- **Mesaj kutusu:** Başlık 1-3, alıntı ve kod bloğu gerçekten çalışır; blok altına otomatik boş satır, boş satırda Enter veya aşağı ok ile çıkış; biçim menüsü yukarı açılır ve dışarı tıklayınca kapanır.
- **Ayarlar:** anahtarı olmayan servis ve sağlayıcılar kapalı görünür; düşünme düğmesine basınca efor/düşünme düğmeleri kaybolmaz; akış kopma varsayılanı 300 sn.

## 🆕 v0.10.0 ile gelenler (pro belgeler, kesintisiz görevler, paralel çalışma, zengin mesaj kutusu)

- **Profesyonel belge motoru:** PDF ve HTML Chromium ile tasarımlı şablondan üretilir (renkli kapak bandı, vurgu çubuklu bölümler, zebra tablolar, sayfa numarası). Türkçe dahil her dil ve yazı sistemi (Arapça, Çince, Kiril, Hintçe...) gerçek fontlarla, bağlantılar tıklanabilir, **LaTeX formüller dizilir**. Word: gerçek stiller, tablolar, numaralı/madde listeler, köprüler, formüller. PowerPoint: dekoratif başlık slaydı, bölüm slaytları, yerel tablolar, metin + görsel iki sütun. Excel: JSON veya Markdown tablolarından biçimli sayfalar, gerçek sayılar. Uzun içerik dosyaya parça parça yazılıp `source=` ile dönüştürülür.
- **Kopmayan model bağlantısı:** akış kopma (180 sn), ilk yanıt ve yerel model zaman aşımları ile yeniden deneme sayısı Ayarlar'da. Takılan istek yapılan adımlar korunarak yeniden denenir; dosya yazarken kopan/kesilen çağrıda model parça parça yazmaya yönlendirilir (`write_file append=true`). Akış ortası sağlayıcı hataları ve bozuk SSE satırları görevi bitirmez.
- **Elektrik kesintisinde bile devam:** görevin gerçek ilerlemesi (araç çağrıları, sonuçlar, yapılacaklar, dosyalar) her adımda diske yazılır. Uygulama kapanırsa görev "yarıda kaldı" olarak görünür; "Kaldığı yerden devam et" ile tamamlanan adımlar tekrarlanmadan sürer. Bağlam sıkıştırmada yapılacaklar durumu korunur.
- **Paralel çalışma:** bir adımdaki bağımsız araştırma, sayfa ve dosya okumaları aynı anda çalışır (tek model ve ekip). Ekip üyeleri geçici hatada aynı modeli bekleyerek yeniden dener, bağlamları taşmaz. Sınırsız adım / sınırsız hata ayıklama anahtarları.
- **Canlı yapılacaklar:** yazılan dosya veya başarılı komut ilgili maddeyi otomatik tamamlar; liste durumu her adımda modele hatırlatılır.
- **Çok dilli orkestratör:** niyet algılama 14+ dilde (`agents/intents.json`, dil dosyaları `ai_intents` ile genişletebilir); Almanca, Fransızca, İspanyolca... yanıt dili algılanır.
- **Zengin mesaj kutusu:** seçince biçim araç çubuğu (bağlantı, kalın, italik, üstü çizili, kod, başlık, listeler, alıntı), Ctrl+B/I/E/K kısayolları, satır başı Markdown kısayolları, satır sonları korunur. `/` ve `@` listesi mesaj kutusu genişliğinde, aramalı ve kaydırdıkça yüklenir.
- **Sohbet:** mesajlara kopyala/sil, seçili metni "Sohbete ekle" (yorumlu alıntı; tıklayınca kaynağı yanıp söner), uzun sohbetlerde sayfalı yükleme, LaTeX formüller sohbette de dizilir.
- **Kenar çubuğu menüleri:** projeye taşı, ayrı kopya oluştur, okunmadı işaretle, paylaş (Markdown), kopyala, yeni pencerede aç; projeyi sabitle, sohbetleri arşivle, Dosya Gezgininde aç.
- **Dosyalar:** değişiklik kartı türüne göre gruplu; görev sürerken yazılan dosyalar canlı görünür; video oynatıcı ve dalga formlu ses oynatıcı, resimler görüntüleyicide.
- **Ayarlar:** arama motorları ve harita servisleri sağlayıcı kartı tasarımında (aç/kapa, tek tek test), sağlayıcı başına dakikalık istek sınırı (NVIDIA ücretsiz 40), hesap bakiyesi/kredi (OpenRouter, DeepSeek, EVREN), model bazında kullanım tablosu, "Şimdi dene" gerçek deneme isteği atar. Düşünme anahtarı (API destekliyorsa).
- Nemotron 3 ailesinin 1M bağlamı, Gemini `retryDelay`, sızıntı kalıpları (`<tools ="...">`, `[tool="..."]`) ve aynı dosyayı baştan yazma koruması.

## 🆕 v0.9.0 ile gelenler (cevaplar doğrudan sohbete, zayıf modellere araç, yakınlaştırılabilir resim düzenleyici)

- **Sohbet cevapları doğrudan sohbete yazılıyor:**
  - Selamlaşma veya düz bir soruya verilen cevap doğrudan cevap olarak akıyor. Önceden önce adımların altındaki not alanında görünüyor, sonra sohbete zıplıyordu.
  - Araç kullanan işler yine adımların altındaki sabit alanda yürüyor.
  - Asistanın kendisiyle ilgili sorular ("kaç yılında modellendin", "hangi modelsin", "seni kim yaptı") sohbet sayılıyor.
- **Zayıf modeller artık araç kullanabiliyor:** yerel araç çağrısı yapamayan modeller aracı çoğu zaman kendi etiketiyle yazıyor: `<research query="PHP 2026 açıkları"></research>`, `<web_search query="x"/>` veya `<run shell="powershell">php -v</run>`. Bu metin önceden sohbete düşüyor ve hiçbir şey çalışmıyordu. Bu şekilde yazılan her araç artık gerçek çağrı olarak çalışıyor:
  - nitelikler argüman oluyor;
  - içteki metin ya da ana nitelik ana argüman oluyor;
  - kendiliğinden kapanan veya kapanmamış ama nitelikli etiket de sayılıyor.

  Metin içindeki sıradan etiketlere (HTML, cümle içinde geçen `<places>`) dokunulmuyor. Aynısı ajan takımı üyeleri için de geçerli.
- **Kaydırma ve yakınlaştırmalı resim düzenleyici** (büyük ekran görüntüleri ve fotoğraflar):
  - el aracı, boşluk tuşu basılıyken ya da orta fare tuşuyla sürükleme;
  - fare tekerleği imlecin olduğu noktaya yakınlaştırıyor (%5–%800);
  - −, resmi sığdıran yüzde düğmesi, +, sığdır ve 1:1 düğmeleri;
  - + / − / 0 (sığdır) / 1 (%100) kısayolları.

  Çizimler her yakınlaştırmada resme bağlı kalıyor ve resmin kendi çözünürlüğünde kaydediliyor.

## 🆕 v0.8.9 ile gelenler (ajanın başlattığı sunucular her zaman kapatılır)

- **Model açtığını kapatıyor:** ajana, başlattığı her sunucu veya izleyiciyi (php -S, npm run dev, python -m http.server...) kontrolü biter bitmez `stop` ile durdurması söyleniyor. `start` sonucu da süreç kimliğiyle bunu hatırlatıyor. Bir sunucuyu yalnızca kullanıcı kullanmak istediğinde açık bırakıyor ve bunu cevabında söylüyor.
- **Kapatmazsa güvenlik ağı devreye giriyor:** ajanın başlatıp açık bıraktığı sunucular, görev bittikten birkaç dakika sonra otomatik kapatılıyor.
  - Süre Ayarlar > Güvenlik > *Ajan sunucularını otomatik kapat* altında ayarlanıyor: varsayılan 10 dakika, 0 = kapatma.
  - Sohbete bir not düşülüyor ve Bağlam > Arka plan görevleri sunucunun yanında "N dk sonra kapanır" gösteriyor.
  - Aynı sohbette yeni bir görev çalışırken geri sayım duraklıyor.
- **`run` ile başlatılan sunucu artık görevi kilitlemiyor:** bir sunucu hiç "bitmez", bu yüzden `run` komut zaman aşımına (5 dakika) kadar bekliyordu. Sunucu komutları (http.server, php -S, npm/yarn/pnpm dev veya start, vite, next dev, uvicorn, flask run, runserver...) artık arka planda başlatılıyor ve hazır olduğu anda dönüyor. 240 sn süren bir test artık 14 sn sürüyor.
- **Durdurulan görevden geriye çalışan bir şey kalmıyor:** görev durdurulduğunda veya hata verdiğinde hâlâ çalışan komutu da onunla birlikte sonlandırılıyor. Önceden açık kalıyordu.
- **Sert kapatmanın kalıntıları açılışta temizleniyor:** önceki çalışmadan hâlâ çalışan süreçler durduruluyor; yalnızca o süreç kimliği hâlâ aynı programa aitse.

## 🆕 v0.8.8 ile gelenler (sakin canlı görünüm, dürüst çalıştırma, tamamlanan yapılacaklar)

- **Görev sürerken sohbet artık yanıp sönmüyor:**
  - Modelin görev sırasında yazdığı her şey (araç çağrısından önceki notlar, akan cevap, yazılmakta olan düşünce) adımların altındaki tek ve sabit bir alanda gösteriliyor.
  - Bir not adım listesine geçtiğinde bu alan aynı metni göstermeye devam ediyor. Önceden metin cevap gibi görünüp kayboluyor ve başka yerde yeniden çıkıyordu; bu sızıntı gibi görünüyor, hızlı modellerde titriyordu.
  - "Düşünüyor" göstergesi yalnızca ilk adımdan önce görünüyor; artık adımlar arasında açılıp kapanmıyor.
  - Uygulamanın kendi eylem kaydı ("[Tool actions in this turn ...]") bir model kopyalasa bile gösterilmiyor.
  - Cevap görev bitince tam yerini alıyor.
- **"Yaz ve çalıştır" gerçekten çalıştırılıyor:** kullanıcı bir şeyin çalıştırılmasını veya ölçülmesini istediğinde (ya da dosya adı verdiğinde) model yalnızca kodu yazarsa, ondan bir kez daha dosyayı yazıp çalıştırması ve gerçek çıktıyla cevap vermesi isteniyor. Önceden yalnızca paket kurma ve ağ kodları yakalanıyordu.
- **Sahipsiz sunucu kalmıyor:** uygulama sert kapatıldıktan sonra çalışmaya devam eden ve ajanın başlattığı geliştirme sunucuları (ör. `php -S localhost:8000`) bir sonraki açılışta durduruluyor. Yalnızca o kimlikteki süreç hâlâ aynı programsa; başka hiçbir şeye dokunulmuyor.
- **Tamamlanan yapılacaklar listesi:** görev gerçek bir nihai cevapla bitince modelin işaretlemeyi unuttuğu maddeler tamamlandı sayılıyor. Önceden biten bir görev 1/3 gösterebiliyordu. Kullanıcıya soru soran cevaplarda maddeler açık kalıyor.

## 🆕 v0.8.7 ile gelenler (anlık hatalar, iş teslim eden ajanlar, gerçek kurulum, görünür ilerleme)

- **Hatalar anında görünüyor:** uygulamanın beklediği hız sınırı, meşgul sağlayıcı veya sunucu hatası artık hemen sohbette görünüyor: neden, sağlayıcının mesajı ve bir sonraki denemeye canlı geri sayım. Önceden ancak adım listesi açılınca görünüyordu.
- **Dakikalık token sınırı (Groq ücretsiz 413 "TPM: Limit 8000, Requested 11733"):** uygulama sınırı hatadan okuyor, kısa araç tanımlarına geçiyor, konuşmayı sınırın altına kırpıyor ve bir kez daha gönderiyor; artık hata verip bırakmıyor.
- **Ajanlar ve skill'ler istendiği gibi çalışıyor:**
  - Ajan çağrısı (`@agent-maker ...`) artık modele o ajanın sonucunu aynı görevde teslim etmesini söylüyor. Zayıf modeller önceden soru listesiyle cevap veriyordu.
  - Ajan üretici, skill üretici ve prompt sihirbazı talimatları varsayılanları kendisi çıkarıyor; yalnızca soru sorarak cevap vermiyor.
  - **Tek mesajda birden çok ajan** (`@coder yaz, @debugger kontrol et`): ilki ana rol oluyor, diğerlerinin talimatları ve araçları verilen sırayla ekleniyor. Önceden yalnızca ilki kullanılıyordu.
  - Ajan/skill dosyasında YAML liste olarak yazılmış `tools:` artık okunuyor. Üretilen bir ajan önceden araç sınırlarını kaybediyordu.
- **Gerçek ve doğrulanmış kurulumlar:**
  - Komutlar güncel sistem PATH'ini görüyor; bir önceki komutun kurduğu program (winget, kurulum dosyası) hemen bulunuyor.
  - Modele eksik bir aracın gerçek kurulum yolu öğretildi: önce kesin kimliği bul (`winget search php --source winget` → `PHP.PHP` değil `PHP.PHP.8.4`), sonra `--source winget` ile kur. msstore kaynağı şart ve bölge isteyip başarısız oluyordu. Ardından `--version` ile doğrula.
  - Güncel paket adı veya sürüm belirsizse model önce kısa bir web araması yapıyor.
  - Bir komut hata verince web araçları açılıyor ve modelden düzeltmeyi tahmin etmeden önce o hatayı bir kez aratması isteniyor.
  - `Start-Process URL` yalnızca kullanıcının tarayıcısını açar. Uygulama bunu araç sonucunda açıkça yazıyor; model artık bir şeyi "indirip kurdum" diye iddia edemiyor.
  - `shell=python` ile gönderilen tek satırlık bir komut (ör. `python --version`) Python kodu gibi hata vermek yerine sistem kabuğunda çalışıyor.
- **Görünür ilerleme:**
  - Görev sürerken modelin son notu o anki adımın üstünde görünür kalıyor ve o anki düşüncenin son satırları gösteriliyor; hangi aşamada olduğu her zaman görülüyor.
  - Bir komut adımı açıldığında çıktının üstünde çalıştırılan tam komut görünüyor (kabuk, klasör, komutun tamamı).
- **Markdown düzenleyicide:** Markdown ya da .md dosyası istendiğinde içerik dosyaya yazılıyor ve hemen düzenleyicide (Monaco) açılıyor.
- **Sağlayıcı önekli model seçici:** her model sağlayıcısıyla görünüyor (`ollama:`, `ollama-cloud:`, `openrouter:`, `nvidia:`...). Arama öneki, sağlayıcı adını ve birden çok kelimeyi eşleştiriyor ("cloud qwen", "openrouter: free").

## 🆕 v0.8.6 ile gelenler (yalın istem, sıkıştırma döngüsü yok, kararlı arka plan tarayıcısı)

- **Araçlar sohbeti takip ediyor:**
  - Model artık her mesajda bütün araçları almıyor. Çekirdek set hep var (okuma, listeleme, arama, yazma, düzenleme, silme, komut, başlatma, durdurma, yapılacaklar, yetenekler).
  - Diğer gruplar yalnızca istek veya son konuşma onlarla ilgiliyse ekleniyor: web, tarayıcı, mekan, belge, hafıza, proje, takım, MCP.
  - Model bir grubu küçük `need_tools` aracıyla kendisi açabiliyor ("web,docs"); hiçbir yetenek kaybolmuyor.
  - Küçük pencerelerde (≤32K, yerel modellerde tipik) araç tanımları kısa gönderiliyor.
  - Dosya/komut çalışma kuralları ve web kuralları yalnızca o araçlar sunulduğunda isteme ekleniyor.
  - Ölçüm (gerçek tokenizer, Ollama'nın kendi sayımıyla %5–9 içinde uyumlu):

    | İstek | Önce | Şimdi |
    |---|---|---|
    | Basit kod görevi | ~9,1K token istem + araç | ~3,7K |
    | Bilgi sorusu | 5,2K | 2,6K |
    | Selam / "kendinden bahset" | 1,6K | 0,6K |

  - Asistanın kendisiyle ilgili sorular sohbet sayılıyor: hiç araç gönderilmiyor.
- **Sıkıştırma döngüsü yok:**
  - Sabit kısım (sistem istemi + araç tanımları) bütçeyi tek başına doldurduğunda eski sıkıştırma yer açamıyor ve tekrar tekrar çalışıyordu (%80 → %69 → %80...). Artık yalnızca konuşma sıkıştırılıyor ve ona adil bir pay bırakılıyor.
  - Kırpma sınırın belirgin altına iniyor; böylece bir sonraki araç sonucu onu hemen yeniden tetiklemiyor.
  - "Bağlam sıkıştırıldı" adımı yalnızca gerçekten yer açıldığında (en az %8) gösteriliyor.
  - Görev içi özetten sonra araç tanımlarının iki kez sayılması düzeltildi.
  - 16K pencereyle 40 ağır araç turunda test edildi: istem pencereyi hiç aşmadı ve birkaç kırpmada bir gerçek özet çalıştı.
- **Ollama "No user query found in messages":** pencereden uzun istemde Ollama en eski mesajları, kullanıcının isteğiyle birlikte, kendisi kesiyordu; Qwen şablonu da kalanı reddediyordu. Sıkıştırma artık pencere dolmadan çalışıyor. Bu hata (ve llama.cpp'nin "truncating input" uyarısı) "bağlam çok uzun" olarak ele alınıyor: beş kez sunucu hatası denemesi yerine kırp, özetle, yeniden gönder.
- **Arka plan tarayıcısı (Playwright), tam profil, çökme döngüsü yok:**
  - Gizli pencere, GPU birleştirme kapalı olarak tam Chromium'un yeni headless modunu kullanıyor. Eski headless kabuk ağır sayfalarda çöküyordu ("Target crashed" döngüsü).
  - Arka plan profili: masaüstü görüntü alanı ve ekran, kullanıcının dili ve `Accept-Language`, sistem saat dilimi, "Headless" işareti çıkarılmış gerçek kullanıcı ajanı. Bot doğrulamaları yine çözülmüyor; bildiriliyor ve kullanıcıya bırakılıyor.
  - Çöken sekmenin yerine yenisi açılıyor. İki kez çöken site o oturumda tarayıcıda tekrar açılmıyor; model `fetch_url` / `web_screenshot`'a yönlendiriliyor.
  - Sekmeyi sıfırlamak için `about:blank` çalışıyor.
  - Araştırma okuyucusu tarayıcısı da aynı modu ve gerçek tarayıcı sürümünü kullanıyor.
  - **Görünür** tarayıcı penceresi, onu kullanan görev bitince kapanıyor. Girişler profilde kalıyor; gizli pencere 5 dakika boşta kalınca kapanıyor.
- **Yeni tarayıcı seçeneği: "Hızlı okuyucu (gizli, resimsiz)".** Sayfaları arka planda resim, video ve yazı tipi yüklemeden açar. Okuma, tıklama ve form doldurma daha hızlıdır; engellenen resimlerin hata gürültüsü modele gitmez.
- **Ayarlar > Tarayıcı ajanı > Kayıtlı oturumlar** yeniden tasarlandı: profil boyutu kendi kutusunda, "Pencereyi kapat" ve kırmızı "Tüm girişleri unut" (silinecek bir şey yokken pasif) yan yana.

## 🆕 v0.8.5 ile gelenler (sızıntısız sohbet, kesin bağlam, hız, güçlü araştırma)

Gerçek bulut modelleriyle (NVIDIA NIM, Cloudflare Workers AI, Groq, Gemini, EVREN, OpenRouter, DeepSeek, Ollama Cloud)
tam bir test turu yapıldı: tek sohbet, aynı anda 8 sohbet, çok modelli ajan takımları, sıkıştırma ve web araştırması.
Bulunan her hata uygulamada düzeltildi.

- **Sohbete sızıntı yok:**
  - Modellerin metin olarak yazdığı düşünceler artık her zaman gizleniyor: `<thinking>`, `<reasoning>`, tek başına gelen `</think>` (DeepSeek-R1/QwQ tarzı: o ana kadar gösterilen metin geri alınıp düşünme adımına taşınır) ve gpt-oss "harmony" kanal belirteçleri (`<|channel|>analysis…`).
  - Yeni araç çağrısı biçimleri kaybolmak yerine tanınıyor: GLM (`<tool_call>ad<arg_key>…`), harmony (`to=functions.x`) ve `<tool>{json}</tool>`.
  - Düz metindeki `<tool>` kelimesi (HTML, belge) artık cevabın geri kalanını yutmuyor.
  - Düşüncenin içine yazılmış araç çağrısı (Cloudflare'de GLM) boş cevapla bitmek yerine çalıştırılıyor. Boş cevap asla yanıt sayılmıyor; modelden bir kez daha isteniyor.
  - Tek seferlik çağrılar (özet, dil düzeltme, `ask_model`) da aynı şekilde temizleniyor.
  - Politika, onay, süreç ve model hatası adımları ham JSON yerine okunur satırlar gösteriyor.
- **Anahtar ve dosya sızıntısı yok:**
  - Kayıtlı API anahtarları her araç çıktısında, ana ajan ve takım üyeleri için, modele ya da iz kaydına ulaşmadan maskeleniyor (`[secret hidden]`).
  - Dosya araçları tam yetki modunda bile `data/secrets.json` ve sohbet veritabanını açmıyor.
  - Projesiz her sohbetin artık kendi çalışma klasörü var (`workspace/chats/<sohbet kimliği>`). Bir sohbet başka sohbetin dosyalarını veya proje klasörlerini görmüyor ve üzerine yazmıyor. Sohbet silinince klasörü de siliniyor.
- **Kesin bağlam hesabı (gerçek tokenizer + sağlayıcının gerçek değerleri):**
  - Bağlam panelindeki her kategori (sistem, araç tanımları, yetenekler, mesajlar, araç trafiği) "karakter ÷ 3" yerine gömülü tokenizer ile sayılıyor. Yerel araç tanımları artık iki kez sayılmıyor.
  - Sağlayıcının kendi istem sayısı tahminin yerini alıyor. Önbellekli istem (Ollama yalnız yeni token'ları bildirir) artık sayacı küçültmüyor.
  - Cloudflare her parçada kullanım sayısı gönderiyor; artık yalnız son toplam kullanılıyor (sayaç ~2 token'a düşüyordu, model başına kullanım da yanlıştı).
  - Dairesel bağlam göstergesi ile bağlam kartı artık hep aynı sayıyı gösteriyor. Görev sürerken kart canlı değeri ve o an çalışan modeli gösteriyor (önceden kırmızı halkayı kayıtlı eski, düşük değere sıfırlıyordu). Geç gelen bir yanıt daha yeni canlı değeri ezmiyor.
  - İstemin sabit kısmı görev sonunda iki kez ölçeklenmiyor (cevaptan sonra sayaç sıçrıyordu). Sıkıştırmadan sonra sayaç sistem istemini ve araçları koruyor (küçük bir değere düşüp sonraki mesajda geri sıçrıyordu).
  - Canlı sayaç, model yazarken yalnız yeni metni sayıyor (önceden tüm cevabı saniyede iki kez yeniden token'lıyordu).
- **Çoklu model, senkron:**
  - Gemini araç çağrıları düşünce imzasını koruyor (sonraki istek HTTP 400 ile düşüyordu).
  - Her takım üyesinin kartı, sağlayıcının gerçek değerlerinden kendi bağlamını ve toplam token'ını gösteriyor.
  - Her modelin 5 saatlik/haftalık kullanımı ve hız sınırı başlıkları o modelin altında tutuluyor. Bir modele geri dönülünce kendi değerlerinden devam ediliyor.
  - Takım üyeleri ana ajanla aynı sızıntı temizliğini ve araç çağrısı kurtarmayı alıyor.
- **Halüsinasyonsuz sıkıştırma:**
  - Özet artık yalnız cevapları değil, uygulamanın kesin eylem kaydını da görüyor (yazılan dosyalar, komutlar, aramalar, takım üyeleri ve modelleri). Yalnız bu gerçekleri koruması ve yarım kalan işi belirtmesi isteniyor.
  - Özet sohbetin dilinde yazılıyor.
- **Daha hızlı:**
  - Görev artık model bilgisi için 0,3–0,5 sn beklemiyor: bilgiler açılışta yükleniyor ve arka planda yenileniyor.
  - Klasör taramaları ve sistem istemi oluşturma ayrı iş parçacığında çalışıyor; diğer sohbetler akmaya devam ediyor.
  - Ölçüm: karışık sağlayıcılarda aynı anda 8 sohbet, sunucu sağlık yanıtı p95 = 13 ms; ilk token öncesi uygulama hazırlığı ~50 ms.
- **Daha güçlü web araştırması** (bot doğrulaması çözülmez; engelli siteler önceki gibi bildirilir):
  - Kaynaklar farklı sitelere yayılıyor.
  - 300 karakterden kısa sayfalar atlanıp sıradaki sonuçla değiştiriliyor.
  - Okuma bir süre sınırında gelenlerle bitiyor; sonuçlar arama sırasına diziliyor.
  - Az sayfa okunabildiğinde arama özetleri ekleniyor.
  - Kısa statik sayfalar artık tarayıcıda yeniden açılmıyor (1,6 sn → 0,5 sn).
  - HTTP hataları açıkça bildiriliyor.
  - Arşiv kopyası olmayan sayfada okuyucu artık çökmüyor.
  - Tipik bir araştırma 9 sn'den 5 sn'ye indi.

## 🆕 v0.8.4 ile gelenler (tarayıcı ajanı: siteye girip gerçek kullanıcı gibi test)

- **Gerçek, görünür bir tarayıcı penceresi:** Model artık sayfa açabilir, elemanları okuyabilir, tıklayabilir, form doldurabilir, tuşa basabilir, bekleyebilir ve ekran görüntüsü alabilir — tıpkı bir kullanıcı gibi.
  - **Kalıcı profil:** Pencere `data/browser-profile` adlı kendi profiliyle açılır. Bir siteye bir kez elle giriş yapın; çerezler orada kalır ve sonraki görevlerde model sizi zaten giriş yapmış bulur. Ayarlar > Web > Tarayıcı ajanı'ndan görünür/gizli yapılabilir, kapatılabilir veya tüm girişler tek tıkla unutturulabilir.
  - **Piksel değil yapı:** Sayfa ekran görüntüsünden tahmin edilmez; erişilebilirlik ağacı olarak okunur — her elemanın rolü, adı, değeri ve kısa bir referansı (`[e12]`) ile. Bu referansla tıklanır/yazılır; tasarım değişse de bozulmaz. Her eylemden sonra sayfa yeniden okunur ve gerçekten olan doğrulanır.
  - **Araçlar:** `browser_navigate`, `browser_snapshot`/`browser_find`, `browser_click`/`browser_type`/`browser_key`/`browser_form`, `browser_scroll`/`browser_wait`, `browser_inspect` (konsol hataları, başarısız istekler, çerezler), `browser_screenshot`, `browser_tabs`, `browser_batch` (birkaç adımı tek seferde).
- **Güvenlik kuralları gömülü:**
  - Şifre ve kart bilgisini model kendisi asla yazmaz; gerçek bir sitede giriş/ödeme gerekince **browser_handoff** çağırır, pencereyi size bırakır, siz tamamlayınca devam eder.
  - Test şifreleri yalnızca localhost/127.0.0.1 veya isteğinizde adını verdiğiniz bir test ortamında yazılabilir.
  - Gönder, sil, satın al, yayınla gibi geri dönüşü olmayan bir düğmeden önce onay ister.
  - CAPTCHA veya bot doğrulaması asla çözülmeye çalışılmaz; durur, browser_handoff ile size bırakır.
- **"Projeyi test et" artık gerçek kullanıcı gibi test eder:** Projeyi başlatır, gerçek tarayıcı penceresinde açar, formları doldurur, düğmelere tıklar, sonucu kontrol eder, konsol hatalarına ve başarısız isteklere bakar. @tester ajanı bu akışı izler; bir takımın test aşaması da aynı araçları kullanabilir.
- **Küçük modeller için akıllı araç kapısı:** 14 yeni araç tanımı her görevin isteminin boyutunu artırabileceğinden, tarayıcı araçları yalnızca görev metni bunu gerektirdiğinde (site, sayfa, tıkla, giriş yap, test et…) ya da görev zaten bir tarayıcı adımı kullandığında sunulur — zayıf/dar bağlamlı yerel bir model gereksiz araç kalabalığıyla karşılaşmaz.
- **Üç kök sorun giderildi:**
  - Model, konum/mekân gibi bir araçla doğrudan yapılabilecek bir işi bazen `pip install` + elle yazılmış bir komutla "çözüyormuş gibi" yapıp hiç çalıştırmadan bırakıyordu; artık böyle bir cevap algılanıp araç gerçekten çağrılana kadar görev yeniden denettiriliyor.
  - Bağlam sıkıştırma adımının "önce/sonra" token sayıları, üstteki bağlam göstergesiyle aynı ölçeklemeyi kullanmadığından farklı görünebiliyordu (ayrıca ham JSON olarak sızıyordu); artık okunabilir bir özet olarak gösteriliyor ve aynı sayılar her yerde tutarlı.
  - Bağlamın dairesel ilerleme halkası, görev sırasında model değişince (kota geçişi gibi) bayat bir üst sınırla kırmızı görünüp panel açılınca maviye dönebiliyordu; artık görev sürerken birkaç saniyede bir kendiliğinden tazeleniyor.
- **Test edildi:** 9 regresyon dosyası (208 kontrol) ve tarayıcı ajanına özel 15 uçtan uca kontrol (gerçek navigasyon, referansla tıklama/yazma, şifre maskeleme, ekran görüntüsü, durum/kapatma/unutma uç noktaları).

## 🆕 v0.8.3 ile gelenler (komutlar, belgeler, inceleme, süre, konum)

- **Komutlar tam hızda ve sürüme uygun:**
  - Uygulama açılırken işletim sisteminin sürümünü ve derlemesini (ör. Windows 10 22H2 build 19045), her kabuğu sürümüyle (Windows PowerShell 5.1, PowerShell 7, cmd, Git Bash) ve kurulu araçları (git, Node, npm, Python, Java…) tespit edip modele verir; model bu bilgisayarda gerçekten var olan komutları yazar.
  - Yeni `argv=[...]` programı kabuksuz, doğrudan çalıştırır (git 0,05 sn'de başlar).
  - Yeni kabuklar: `powershell5`, `pwsh` ve `bash` (Windows'ta Git Bash; asla WSL değil).
  - Çok satırlı betikler betik dosyası olarak çalışır.
- **PowerShell katmanı yerel anlamı korur:**
  - `rm -rf`, `mkdir -p a b`, `ls -la`, `del /s /q` ve `touch` yalnızca bu biçimde yazıldığında yakalanır.
  - `ls -Filter *.txt`, `Remove-Item -Recurse` ve `dir | Where-Object` gerçek cmdlet'e olduğu gibi gider; düz `rm klasör` artık sessizce özyinelemeli silmez.
  - Hatalar gerçek çıkış koduyla döner.
- **Heredoc sorunu kalıcı olarak çözüldü:**
  - PowerShell'e giden bash heredoc'u Git Bash'te çalışır. Git Bash yoksa dosyaya yazmaya ya da girdi aktarmaya çevrilir.
  - İçeriden yazılmış PowerShell here-string kapanışları düzeltilir.
- **Arka plan süreçleri:**
  - `start`, sunucu hazır olduğunu yazdığı anda döner (sabit 6 sn yerine 0,3 sn).
  - Geliştirme sunucuları normal komutların sırasını kapatmaz; 9 sunucu açıkken bile komutlar hemen başlar.
- **Yeni `/host-commands` yeteneği:**
  - Emin olunmayan sözdizimini kullanmadan önce yerel yardıma, sonra o sürümün resmî belgesine bakar (Microsoft Learn, git-scm, docs.python.org, nodejs.org).
  - Bilinen sürüm tuzaklarını bilir ve her sonucu doğrular.
- **Süre nereye gidiyor:**
  - Her görev toplam süresini gösterir. Açınca dağılımı görünür: ilk yanıt, model (ilk token beklemesi), araç türüne göre süreler, takım, ek çağrılar, yeniden deneme beklemesi ve uygulamanın kendi işi.
  - `/api/perf` son görevlerin p50/p95/en yüksek değerlerini, `/api/health` özetini verir.
  - MCP sunucuları ilk yanıtı artık 25 sn'ye kadar bekletmiyor.
- **Değişiklik inceleme kartı:**
  - Görevin klasörde eklediği, değiştirdiği ya da sildiği her dosya cevabın altında listelenir. Yalnızca araçların değil; komutların, betiklerin, biçimlendiricilerin ve paket yöneticilerinin değişiklikleri de.
  - Her satırda kaynak, +/− satır sayısı ve renkli fark vardır; dosya editörde açılabilir.
  - Görüntü, model ilk cevabını yazarken arka planda alınır; zaman kaybettirmez.
- **Belge araştırması:**
  - `read_document` ve `fetch_url` PDF, Word, Excel, PowerPoint, OpenDocument (odt/ods/odp), CSV, metin ve resimleri okur. Her alıntıda sayfa, slayt, tablo satırı ya da paragraf etiketi bulunur.
  - Taranmış sayfalar Windows'un yerleşik OCR'ı ile okunur (çevrimdışı, sayfa başına ~0,1 sn, Türkçe karakterler korunur). Linux/macOS'ta Tesseract ya da RapidOCR kullanılır.
  - Uzun belgelerde soruya uyan en iyi pasajlar sayfa numaralarıyla gelir.
  - Web araştırması belgeleri de kaynak olarak paralel okur. Engellenen bir belgenin tarihli Wayback kopyası belge olarak okunur.
- **Konumla çalışan harita:**
  - "Yakınımda" aramaları gerçek konumunuzu kullanır: tarayıcının konum servisi (Wi-Fi/GPS, bir kez izin ister). Konum alınamazsa internet adresinden yaklaşık konum kullanılır ve bu açıkça belirtilir.
  - Harita sayfasında profesyonel detay kartları var: puan yıldızları, size uzaklık, adres, bugünkü saatler ve telefon.
  - Her kartta konumunuzdan Yol tarifi, Ara, Web ve Haritada düğmeleri bulunur.
  - Ayrıca filtre, sıralama, doğruluk çemberli "buradasınız" işareti, numaralı iğneler ve koyu tema.
- **Test edildi:** 21 komut katmanı kontrolü, 15 yeni uçtan uca kontrol ve önceki tüm sahte model paketleri.

## 🆕 v0.8.2 ile gelenler (takımlar, web araması, harita, rehber)

- **Aşamalı ajan takımları (iş akışı):** takım artık sırayla da çalışabiliyor. Aynı aşamadaki üyeler aynı anda çalışır. Sonraki aşama, öncekiler bitince başlar ve onların raporlarını, modellerini ve dosya adlarını alır. Örnek: 1. takım HTML sayfası yazar, 2. takım onu analiz eder, 3. takım analizi Word'e yazar; her biri farklı bir bulut modelinde. Model aşama vermeyi unutsa bile bir parça açıkça diğerine dayanıyorsa ("1. takımın HTML'ini analiz et") parçalar yine sırayla çalışır. Görev panosunda her üyede *Aşama 1, 2, 3* etiketi görünür. Üyeler belge (Word/Excel/PDF) üretebilir, web araştırması ve harita araması da yapabilir.
- **Kim ne yaptı, dürüstçe:** sonraki turlar hangi ajanın hangi modelde çalıştığını tam olarak bilir. *Başka modele soruldu* adımının takım değil danışma olduğunu da bilir. Böylece model sonradan "aslında takım çalışması yapmadık" demez. Takım, grup ya da çoklu ajan istendiğinde model işi kendisi yapmak yerine takım aracını kullanır.
- **Uydurma bilgi yok:** güncel bilgi ya da kaynak isteyen bir soruyu (fiyat, haber, hava durumu, "kaynaklı") model ezberden cevaplarsa bir kez geri gönderilir ve önce araştırma yapması sağlanır; fiyat ve adresler uydurulmaz.
- **Dil kaymaları ucuz düzeltiliyor:** cevapta başka dilde bir sözcük çıkarsa (ör. Çince bir kelime) yalnızca cevap kısa bir istekle düzeltilir. Model ikinci kez düşünmez, cevap iki kez yazılmaz, bağlam büyümez.
- **Çok daha güçlü web araması:**
  - Önce sizin kurduğunuz API'ler kullanılır: Google Programmable Search, Yandex Search API, Bing Web Search API, Brave, Tavily, SearXNG.
  - API yoksa ücretsiz **ddgs** kütüphanesi Google, Yahoo, Bing, Yandex ve Brave'i Wikipedia ve Wikidata ile birlikte paralel arar.
  - En son çare olarak arka planda hazır bekleyen bir tarayıcı (Playwright) aynı aramayı yapar.
  - Birden çok motorun bulduğu sonuç öne geçer, konu dışı sonuçlar elenir. Alakasız sonuç ya da doğrulama sayfası veren motor bir süre dinlendirilir. Aramalar önbelleğe alınır.
  - Sayfalar yapısal verileriyle (fiyat, puan, adres, çalışma saatleri) okunur. Okunamayan sayfa Wayback Machine arşiv kopyasından alınır.
  - Ayarlar > Web'de aramayı test ettiğinizde her motorun durumu görünür.
- **Harita ve mekânlar:**
  - Yeni `places` aracı bir semt, adres ya da koordinat çevresindeki mekânları bulur: mesafe, adres, telefon, web sitesi ve çalışma saatleriyle.
  - Ücretsiz OpenStreetMap ile çalışır; anahtar girilirse Google Places / Yandex Places kullanılır (puan, yorum sayısı ve fiyat seviyesi eklenir).
  - Uygulama içinde açılan etkileşimli bir harita sayfası çizer.
- **Yeni yetenekler:**
  - `/place-research`: mekânları bulur, yorum ve fiyatlarını araştırır.
  - `/place-compare`: iki veya daha fazla mekânı karşılaştırır.
  - `/map-market`: bir konum için rakip yoğunluğu, boşluklar, SWOT ve pazarlama stratejisi çıkarır.
  - `/catalog`: Excel, Word/PDF ya da aranabilir web sayfası olarak ürün kataloğu hazırlar.
- **Rehber artık gerçek bir wiki:**
  - Konular ağaç yapısında; arama yapılabiliyor, eşleşmeler vurgulanıyor.
  - "Bu sayfada" listesi ve önceki/sonraki bağlantıları var.
  - Çoklu model, takımlar, iş akışları, kotalar, arama API'leri ve harita için tam sayfalar TR/EN olarak hazır.
- **Test edildi:**
  - Sahte model paketleri: 51 senaryo, 53 API kontrolü ve yeni 5. tur kontrolleri.
  - Gerçek bulut çalıştırmaları: NVIDIA NIM, Groq, Cloudflare Workers AI ve EVREN ile aşamalı takım, mekân ve araştırma.

## 🆕 v0.8.1 ile gelenler (güvenilirlik ve test)

- **Gerçek token sayımı:** gömülü (çevrimdışı) tokenizer ve sağlayıcının kendi sayımı kullanılıyor; araç tanımları da sayılıyor. Bağlam sayacı model düşünürken veya uzun bir dosya yazarken canlı ilerliyor, gerçek sayı geldiğinde artık sıçramıyor.
- **Güvenilir bağlam sıkıştırma:** az sayıda çok uzun mesajlı sohbetler de sıkıştırılıyor. Görev içi özetler yapılmış adımların kesin listesini taşıyor; model ilerlemeyi tekrarlamıyor ve uydurmuyor. Özetler her turda değil, aralıklı yapılıyor.
- **Profesyonel hata yönetimi:**
  - Hız limitinde sağlayıcının istediği süre (`Retry-After`) kadar bekleniyor.
  - "Bağlam çok uzun" hatasında görev bitmiyor; kırpılıp yeniden deneniyor.
  - Takılan bulut isteği 3 dakikada kesilip yeniden deneniyor.
  - Kota hatasında havuzdaki sonraki modele geçilip aynı adımdan devam ediliyor.
  - Yeni TR/EN hata metinleri eklendi.
- **Sorunsuz Windows komutları:**
  - Windows PowerShell 5.1'de `&&` / `||` zincirleri çalışıyor.
  - Unix/cmd alışkanlıkları anlaşılıyor (`rm -rf`, `del a b`, `rmdir /s /q`, `mkdir -p`, `ls -la`, `touch`).
  - Tek başına `cd` sonraki komutlar için hatırlanıyor.
  - Çıkış kodları gerçek: önceden başarısız bir derleme başarılı görünüyordu.
- **Yeni sağlayıcılar:** NVIDIA NIM (build.nvidia.com) ve Cloudflare Workers AI (yalnız Hesap kimliği ve API token girilir; modeller bağlam boyutu, araç ve akıl yürütme bilgisiyle listelenir). Hata kodları tek tek eşlendi; örneğin Cloudflare'in günlük ücretsiz nöronu (3036) bitince UTC gece yarısına kadar beklenir, "ücretli plan gerekli" (5035) hatasında başka modele geçilir.
- **Daha temiz sohbet:** modelin araç çağrıları arasında yazdığı metin, kaybolan bir cevap gibi değil, küçük bir çalışma notu olarak görünüyor.
- **Ajan ekipleri:** ayrı çağrılarla gönderilen parçalar tek ekipte çalışıyor. Aynı şekilde sürekli başarısız olan çağrı durduruluyor, böylece sonsuz döngü olmuyor.
- **Sızıntılar giderildi:**
  - Biten süreç kayıtları artık sınırlı.
  - Örtülen pencerede canlı sohbet artık donmuyor (olay kuyruğu sınırsız büyüyebiliyordu).
- **Test edildi:** sahte model paketleri ve gerçek modellerle (EVREN, OpenRouter, NVIDIA NIM, Cloudflare Workers AI, Groq; hata yolları Gemini 503 ve 402 kredi hatalarıyla canlı). Kapsam: sızıntı, darboğaz, paralel sohbet, çoklu model ekibi, modeller arası mesajlaşma, sıkıştırma, istem enjeksiyonu, iptal ve güvenlik senaryoları.

## 🆕 v0.8 ile gelenler

- Model gerektiğinde aldığı **web sayfası ekran görüntüleri**; sohbette küçük resim, tıklayınca görüntüleyici.
- Eklerde **resim düzenleyici** (ok, yazı, şekil, silgi) ve dosya/klasörler için **sohbet geneli bırakma alanı**.
- Kadın/erkek etiketli, dile göre seçilen **doğal sesler** (edge-tts); emoji ve semboller okunmaz.
- **13 profesyonel yetenek ve ajan** (araştırmacı, karşılaştırıcı, yazar, prompt sihirbazı, yetenek ve ajan üretici, web araştırma/özet/rapor, web'den belgeye, makale, prompt, belge) ve **token tasarruflu araç setleri**; doğrulamalı `save_catalog` aracı.
- İş sürerken **en son mesaja in** düğmesi; 360 px telefona sığan mesaj kutusu; sıfır bulgulu düzen denetimi.
- **Varsayılanda yalnız Ollama açık**; anahtar kaydedilince sağlayıcı açılır. Uygulama her portta çalışır (`run.bat 8400`).

## 🆕 v0.7

- Onay kartında **onaydan önce fark (diff)**; değişiklik onay beklerken adım satırı şimdiki zamanla görünür.
- **Model profilleri** ve her modelin API verisine dayanan gerçekçi **çaba ayarı** (yerel modellerde talimatla).
- Ayarlar sayfası, salt okunur/onay kuralları ve gizli depoda tokenlarla **MCP istemcisi** (stdio + Streamable HTTP).
- **Tree-sitter söz dizimi ağacı:** kesin semboller, kod haritası ve `impact` etki analizi.
- Bulut havuzunda **paralel ajan takımları** ve canlı **görev panosu**.
- **Ses ile yönetim:** sesli yanıt ve sesli komutlar (gönder, durdur, onayla, reddet, yeni sohbet).
- Ajan takımları için **takım içi mesajlaşma ve ortak görev listesi**; **Anthropic'te araçlarla genişletilmiş düşünme**.
- **Her yerde etkin dil:** düşünme, planlar, notlar, takım raporları ve uygulamanın kendi notları etkin dili izler (metinler dil dosyalarından gelir; yeni diller de alır).
- Düzeltmeler: python kabuğuna gönderilen betik çağrıları betik olarak çalışır (hata ayıklama döngüsü yok); yapılmadan "yaptım" denen düzenlemeler yakalanıp gerçekten yapılır; klasörü yazılmamış dosya bağlantıları doğru dosyayı açar; takım adımı üye adlarını gösterir (ham JSON yok); araç çağrısından önceki kısa notlar artık görünüp kaybolmaz; hata mesajla birlikte saklanır; ulaşılamayan sağlayıcı dakikalar yerine saniyeler içinde sonuçlanır.
- Otomatik geçişli çoklu model havuzu, ajan başına model, `ask_model`, 5 saatlik/haftalık kotalar; kısmi dosya düzenleme ve kod arama; proje hafızası (`AIIQ.md`); resim görüntüleyici ve uygulama içi tarayıcı; meşgul sağlayıcılar için yeniden deneme.
- Dar pencereye uyan düzen; daha hızlı model listesi (400 model: 92 → 0,5 ms), önbellekli sembol haritası ve büyük projelerde ~10 kat hızlı etki analizi.

v0.6: kesintisiz orkestrasyon, canlı yapılacaklar listesi, hedef modu, otomatik yetenek algılama, belge kartları ve önizleme, çizim ekranı.

## 📌 Proje durumu

Projenin tam durumu iki dilde tutuluyor: vizyon, mimari ve klasör yapısı, sürüm sürüm tamamlanan tüm özellikler, açık görevler, önemli kararlar ve sonraki adım.

- 🇹🇷 **Türkçe:** [PROJECT_STATE.tr.md](PROJECT_STATE.tr.md)
- 🇬🇧 **English:** [PROJECT_STATE.md](PROJECT_STATE.md)

**Şu an:** v0.12.0 tamamlandı (yalan "bitti" yok: düz metin araç çağrıları çalıştırılır, istenen dosya diskte denetlenir; zayıf modellere `system_info` ve doğru araç ipucu; sohbetlerde tam metin araması; model karnesi; LM Studio bellek koruması; depoda test paketi). v0.11.0 tamamlandı (kapsamlı tarama: tıkanma yok, kopma ve model değişiminde unutma yok, yarı boyutta ilk istem, modeli kapatmayan RAM / VRAM koruması, eksiksiz yeniden bağlanma). v0.10.7 tamamlandı (toplu seçme ve silme, ilk mesajda tüm yetenekler, 14 dilde araç algılama, bölmeden yazım). v0.10.6 tamamlandı (gerçek stok fotoğraflarla profesyonel web tasarımı, JS hatası ve kırık görsel için test edilen sayfalar, sağlayıcının gerçek sayılarına çapalı bağlam sayacı, yerel pencerede taşma yok, Markdown olarak akan canlı yanıt). v0.10.5: gerçek token verisiyle bağlam, ekran görüntülerinde görsel model, ayar denetimi. v0.10.4: Ayarlar, yerel GPU ayarları, canlı senkron, npm / PyPI / GitHub'dan MCP, otomatik araç kurulumu ve sekiz yeni beceri canlı test edildi.

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
