<p align="center"><img src="screenshots/banner.tr.png" alt="AI IQ 300 — Otonom AI Komuta Merkezi" width="100%"></p>

<p align="center">
  <b>Yerel ve bulut yapay zekâ modelleriyle çalışan, kendi kendine kod yazan, test eden ve çalıştıran otonom AI komuta merkezi.</b><br>
  <a href="README.md">English</a> · <a href="https://github.com/AppsTRDesign">GitHub</a> · <a href="https://wplugins.shop">wplugins.shop</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/sürüm-0.6.0-2563eb" alt="sürüm">
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

| Sohbet ve adımlar | Görev sürerken: canlı adımlar ve yapılacaklar |
|---|---|
| ![Sohbet](screenshots/tr-01-chat.png) | ![Canlı görev](screenshots/tr-07-live-run.png) |
| **Belge kartları** | **Excel önizleme** |
| ![Belgeler](screenshots/tr-08-docs.png) | ![Excel önizleme](screenshots/tr-09-preview-excel.png) |
| **Word önizleme** | **Model seçiciden bağlam ayarı** |
| ![Word önizleme](screenshots/tr-10-preview-word.png) | ![Model ve bağlam](screenshots/tr-11-model-context-dark.png) |
| **Bağlam analizi** | **Çizim ekranı** |
| ![Bağlam](screenshots/tr-02-context-dark.png) | ![Çizim](screenshots/tr-13-drawing.png) |
| **Dosya yöneticisi** | **Sağlayıcılar** |
| ![Dosyalar](screenshots/tr-03-files.png) | ![Sağlayıcılar](screenshots/tr-04-providers-dark.png) |
| **Artı menüsü** | **Hakkında** |
| ![Artı menüsü](screenshots/tr-12-plus-menu.png) | ![Hakkında](screenshots/tr-05-about.png) |

<p align="center"><img src="screenshots/tr-06-mobile-dark.png" width="300" alt="Mobil"><br><i>Mobil görünüm (koyu tema)</i></p>

## 🚀 Özellikler

**Ajan ve orkestrasyon**
- **Gerçek araç kullanımı:** Ollama, OpenAI uyumlu API'ler ve Anthropic için native function calling. Qwen-XML, Hermes-JSON ve Mistral biçimlerini tanıyan evrensel ayrıştırıcı; ham araç sözdizimi sohbete sızmaz.
- **Çoklu ajan:** Asistan, Planlayıcı, Kodlayıcı, Hata ayıklayıcı ve Test uzmanı. Komut hata verince otomatik hata ayıklama döngüsü devreye girer. `@ajan` ile rol değiştirilir.
- **Kesintisiz görevler:** Uzun işler bitene kadar sürer. Model bir sonraki adımı söyleyip durursa, boş cevap verirse ya da listede açık madde kalırsa görev devam ettirilir. Yarıda kalan iş "devam et" ile kaldığı yerden sürer.
- **Canlı yapılacaklar listesi:** Çok adımlı işlerde model gerektiğinde listeyi kendisi açar, maddeleri ilerledikçe işaretler; liste sohbetle senkron kalır.
- **Otomatik yetenek algılama:** Model, isteğe uyan yeteneği (web uygulaması, belge, git…) kendisi seçip yükler; `/yetenek` ile elle de çağrılır. Yetenek çağrıldığında son istek hedeflenir, önceki sohbet konusuna kayılmaz.
- **Hedef ve plan modları:** Hedef modunda model, hedefe ulaşana kadar kendi başına çalışır; plan modunda önce plan çıkarır.
- **Akıllı korumalar:** Aynı sayfanın tekrar tekrar indirilmesi, asılsız "dosya oluşturdum" iddiaları, uydurma mutlak yollar ve yanlış dilde cevap otomatik düzeltilir. Bilgi sorularında yalnızca okuma araçları verilir, istenmeyen dosya yazılmaz.

**Bağlam ve modeller**
- **Canlı bağlam:** Bağlam görev sürerken her adımda sayılır. Uzun görevlerde eski dosya içerikleri kırpılır, gerekirse adımlar özetlenir; görev pencere dolduğu için kopmaz. Kategori bazlı istatistikler, %80 eşikte sıkıştırma ve kalıcı oturum özetleri.
- **Model seçiciden bağlam ayarı:** Yerel modellerin bağlam boyutu model seçicideki etiketten kaydırıcıyla ya da hazır düğmelerle (8K–262K) değiştirilir; Ayarlar ve bağlam paneliyle anında senkron kalır.
- **29 sağlayıcı:** Ollama, LM Studio, OpenAI, Anthropic, Gemini, OpenRouter, Groq, DeepSeek, Mistral, xAI, Together, EVREN ve diğerleri. Modeller sağlayıcı bazında paralel ve anlık yüklenir; araç/görsel/düşünme rozetleri görünür.
- **VRAM dostu:** Yerel modele geçince diğer yerel modeller otomatik boşaltılır.
- **Yavaş donanıma dayanıklı:** Model bir dosyayı sessizce yazarken "Hazırlanıyor · N sn" göstergesi çıkar; uzun üretimler zaman aşımına düşmez.

**Çalışma alanı**
- **Profesyonel IDE:** Monaco editör, klasör ağaçlı ve türe göre filtreli dosya yöneticisi, süreç paneli, git zaman makinesi.
- **Belge üretimi ve önizleme:** Word, Excel, PDF ve PowerPoint. Üretilen belgeler sohbette türüne göre renkli kart olarak görünür; karta ya da cevaptaki belge yoluna tıklayınca uygulama içinde önizlenir (Excel: SheetJS, Word: docx-preview, PDF: tarayıcı görüntüleyicisi, PowerPoint: slayt kartları).
- **Çizim ekranı:** Kalem, çizgi, dikdörtgen, elips, silgi, renkler, geri al/yinele; çizim resim olarak sohbete eklenir.
- **Ekler:** Dosya ve klasör yükleme (klasör yapısı korunur), sürükle-bırak, yapıştırma ve sesle yazma.
- **Web araştırması:** Çok motorlu arama, alaka filtresi (konu dışı sonuçlar elenir), gerçek tarayıcıyla sayfa okuma, engel tespiti ve kaynaklı özetler. Bot korumaları aşılmaya çalışılmaz.
- **Oturum sistemi:** Her sohbet için `chat/<id>-session/` klasöründe transcript, özetler, durum dosyası ve yüklemeler.
- **Güvenlik:** Üç izin modu (Onay iste / Benim için onayla / Tam erişim). Tam erişimde bile yıkıcı komutlar için akıllı güvenlik çiti.
- **Arayüz:** Gece/gündüz teması, tam mobil uyum, tıklayınca açılıp kapanan menüler; TR/EN hazır, yeni diller tek tıkla otomatik çevrilir (ajan ve yetenek metinleri dahil).

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

Ayrıntılı kullanım için uygulamadaki **Rehber** bölümüne bakın.

## 🏗️ Mimari

```
backend/   FastAPI · ajan orkestratörü · sağlayıcı adaptörleri · süreç yöneticisi · politika
frontend/  React + Vite + Tailwind · Monaco · Zustand · SheetJS · docx-preview
agents/    Ajan rolleri (Markdown)        skills/    Yetenekler (Markdown)
languages/ tr.json · en.json              chat/      Oturum klasörleri
workspace/ Projesiz sohbetlerin çalışma alanı (üretilen belgeler workspace/docs/ altında)
tanitim/   Banner, ekran görüntüleri ve tanıtım metinleri
```

## 🆕 v0.6 ile gelenler

- Kesintisiz orkestrasyon: devam ettirme, canlı bağlam sayımı, görev içi kırpma/özetleme, takılı adım temizliği, sessiz araç yazımında canlı gösterge.
- Canlı yapılacaklar listesi, Hedef modu ve otomatik yetenek algılama.
- Canlı gruplu adımlar; model seçiciden bağlam düzenleme (ayarlarla senkron); tıklayınca açılıp kapanan menüler.
- Belge kartları ve uygulama içi önizleme (Excel, Word, PDF, PowerPoint).
- Çizim ekranı ve klasör yükleme.
- Web aramasında alaka filtresi; bilgi sorularında salt okuma araçları; tekrar eden çağrı ve asılsız iddia korumaları.
- Windows komut çıktılarında Türkçe karakter düzeltmesi; kökte gereksiz `docs/` klasörü oluşmuyor.

## 🗺️ Yol haritası

1. **Kısmi dosya düzenleme ve proje içi kod arama:** Model küçük değişiklikler için dosyanın tamamını yeniden yazmaz; yerel modellerde çok daha hızlı.
2. **Tree-sitter sembol haritası:** Fonksiyon ve sınıf haritasıyla bir değişikliğin hangi dosyaları etkileyeceğini önceden görme.
3. **MCP istemcisi:** GitHub, PostgreSQL ve binlerce hazır MCP sunucusunu araç olarak bağlama.
4. **Onaydan önce değişiklik farkı (diff) ve proje kuralları:** Onay ekranında neyin değiştiğini görme; proje başına kalıcı kurallar dosyası.
5. **İsteğe bağlı Docker (WSL2) sandbox:** Komutları yalıtılmış konteynerde çalıştırma.
6. **Paralel ajan takımları ve görev panosu** (bulut modeller için) ve sesli yanıt.

## 👤 Geliştirici

**Onur Öztaş** · [GitHub/AppsTRDesign](https://github.com/AppsTRDesign) · [wplugins.shop](https://wplugins.shop)

> ⚠️ Komutlar bilgisayarınızda doğrudan çalışır; komut filtresi bir yalıtım (sandbox) değildir. Gerçek kontrol onay modudur. Hassas ortamlarda **Onay iste** modunu kullanın.
