// About page content (TR/EN; the Guide lives in guide.js). Other languages fall back to English.
export const AUTHOR = {
  name: "Onur Öztaş",
  github: "https://github.com/AppsTRDesign",
  site: "https://wplugins.shop",
};
export const VERSION = "0.8.3";

const tr = {
  about: {
    title: "Hakkımızda",
    tagline: "Yerel ve bulut yapay zekâ modelleriyle çalışan, kendi kendine kod yazan, test eden ve çalıştıran otonom AI komuta merkezi.",
    what_title: "AI IQ 300 nedir?",
    what: "AI IQ 300; bilgisayarınızda çalışan, ChatGPT/Claude tarzı sade bir sohbet arayüzüne sahip bir yazılım geliştirme ve otomasyon merkezidir. Ona bir hedef verirsiniz; klasörleri ve dosyaları oluşturur, komutları çalıştırır, hataları ayıklar, uygulamayı tarayıcıda test eder ve sonucu size raporlar. Verileriniz, siz bulut sağlayıcı seçmedikçe bilgisayarınızdan çıkmaz.",
    features_title: "Öne çıkan yetenekler",
    features: [
      ["Çoklu model", "Ollama, LM Studio, OpenAI, Anthropic, Gemini, OpenRouter, Groq, NVIDIA NIM, Cloudflare Workers AI, DeepSeek, EVREN ve 25+ sağlayıcı; tek tıkla geçiş."],
      ["Gerçek araç kullanımı", "Native function calling + evrensel ayrıştırıcı: araç çağrıları güvenilir çalışır, ham sözdizimi sohbete sızmaz."],
      ["Çoklu ajan", "Asistan, Planlayıcı, Kodlayıcı, Hata ayıklayıcı ve Test uzmanı rolleri; hata olursa otomatik hata ayıklama döngüsü."],
      ["Kesintisiz görevler", "Uzun işler bitene kadar sürer; canlı adım grubu, yapılacaklar listesi ve otomatik yetenek seçimi."],
      ["Akıllı bağlam", "Gerçek token sayımı (gömülü tokenizer + sağlayıcının kendi sayısı, araç tanımları dahil), model düşünürken ve yazarken canlı sayaç, görev içi kırpma/özetleme (yapılan adımların kesin listesiyle, tekrar ve uydurma yok), eşik bazlı sıkıştırma ve kalıcı oturum özetleri."],
      ["Güvenlik", "Üç kademeli izin modu, yıkıcı komutlar için akıllı güvenlik çiti, kısıtlı alt süreç ortamı."],
      ["Profesyonel IDE", "Monaco editör, dosya yöneticisi, süreç paneli, git zaman makinesi, gece/gündüz teması, tam mobil uyum."],
      ["Web araştırması", "Önce sizin API'leriniz (Google, Yandex, Bing, Brave, Tavily, SearXNG), yoksa ücretsiz ddgs ile Google/Yahoo/Bing/Yandex/Brave paralel arama, sonuç birleştirme, arka plan tarayıcısı, yapısal veri ve arşiv kopyasıyla sayfa okuma, kaynaklı özetler."],
      ["Sürüme uygun komutlar", "İşletim sistemi derlemesini, kabukları ve araç sürümlerini bilerek komut yazar; argv ile kabuksuz çalıştırma, heredoc yönlendirme, hazır olunca dönen arka plan süreçleri."],
      ["Belge araştırması", "PDF, Word, Excel, PowerPoint, OpenDocument, CSV ve resimleri sayfa numaralı alıntılarla okur; taranmış sayfalarda yerleşik OCR."],
      ["İnceleme kartı ve süre", "Bir görevin klasörde yaptığı tüm değişiklikler (komutlar dahil) farklarıyla; görevin süresinin model, araç ve uygulama arasındaki dağılımı."],
      ["Harita ve mekânlar", "Semt, adres veya koordinat çevresinde mekân arama (OpenStreetMap ücretsiz; Google/Yandex Places ile puan ve yorum), etkileşimli harita, mekân karşılaştırma, pazar ve rakip analizi, ürün kataloğu."],
      ["Belge üretimi ve önizleme", "Word, Excel, PDF ve PowerPoint üretir; belgeler sohbette kart olarak açılır ve uygulama içinde önizlenir."],
      ["Çoklu model ve kotalar", "Kota dolunca otomatik model değişimi, ajan başına model, modelin başka modele iş vermesi; 5 saatlik ve haftalık kota takibi."],
      ["Proje hafızası", "Proje başına kurallar (AIIQ.md) ve genel kurallar her sohbete eklenir; \"bunu hatırla\" denince model kuralı kendisi kaydeder."],
      ["Akıllı kod düzenleme", "Kısmi dosya düzenleme, proje içi kod arama ve fonksiyon/sınıf haritası; büyük projelerde bile hızlı değişiklik."],
      ["Onaydan önce fark", "Onay isteyen her dosya değişikliğinde eklenecek ve silinecek satırları önceden görürsünüz."],
      ["Model profilleri", "Model başına düşünme, görsel girdi, akış, araç çağrı biçimi, sıcaklık ve çıktı uzunluğu ayarı."],
      ["Çaba ayarı", "Düşünme çabası modelin API bilgisinden gelen gerçek seviyelerle ayarlanır; desteklemeyen modellere talimatla iletilir."],
      ["MCP istemcisi", "GitHub, PostgreSQL, dosya sistemi gibi MCP sunucularını bağlayın; araçları modele otomatik sunulur."],
      ["Söz dizimi ağacı", "Tree-sitter ile kesin tanımlar ve etki analizi: bir değişikliğin hangi dosyaları etkileyeceğini önceden görür."],
      ["Ajan takımları", "Büyük işleri parçalara bölüp farklı bulut modellerde çalıştırır: bağımsız parçalar aynı anda, birbirine bağlı parçalar aşama aşama (1. takımın çıktısı 2. takıma). Üyeler mesajlaşır, ortak görev listesi kullanır; canlı görev panosu."],
      ["Ses ile yönetim", "Cevapları sesli okuma ve sesli komutlar: \"gönder\", \"durdur\", \"onayla\", \"reddet\", \"yeni sohbet\"."],
      ["Çizim ve ekler", "Çizim ekranı, dosya ve klasör yükleme, hedef ve plan modları."],
    ],
    adv_title: "Avantajlar",
    advantages: [
      "Yerel öncelikli: kod ve dosyalarınız bilgisayarınızda kalır; bulut yalnızca siz seçerseniz kullanılır.",
      "Sağlayıcıdan bağımsız: model değiştirmek için kod değil, tek tık yeter.",
      "Şeffaf: her adım, komut ve dosya değişikliği izlenebilir; her proje git ile geri alınabilir.",
      "Genişletilebilir: yeni ajan, yetenek ve sağlayıcı eklemek için kod yazmanız gerekmez.",
    ],
    roadmap_title: "Yol haritası",
    roadmap: [
      "İsteğe bağlı Docker (WSL2) sandbox ile yalıtılmış komut çalıştırma",
      "Tam zaman çizelgeli video düzenleyici (ffmpeg): kırpma, kesme, birleştirme, yazı ve logo, müzik, geçişler, format dönüştürme; altyazı konuşmadan otomatik (faster-whisper) veya verilen metinden; sohbette önizleme",
      "Güçlü resim üretimi: varsayılan ücretsiz Pollinations (FLUX), anahtar girilirse Hugging Face, Together, OpenAI, Gemini, Stability; istenen format ve ölçüyü (hikâye, kapak, A4, banner) algılama, yazıların resmin üstüne keskin basılması",
      "Stok resim ve video servisleri: Pexels, Pixabay, Unsplash, Openverse, Wikimedia (ücretsiz) ve Shutterstock, Getty, Adobe Stock, Storyblocks (ücretli; her indirmede fiyatıyla onay); lisans ve kaynak kaydı",

    ],
    dev_title: "Geliştirici",
    dev_desc: "Yazılım geliştirici; WordPress eklentileri, yapay zekâ araçları ve otomasyon çözümleri üretiyor.",
  },
};

const en = {
  about: {
    title: "About",
    tagline: "An autonomous AI command center that writes, tests and runs code with local and cloud AI models.",
    what_title: "What is AI IQ 300?",
    what: "AI IQ 300 is a software development and automation hub that runs on your computer behind a clean ChatGPT/Claude-style chat. Give it a goal: it creates folders and files, runs commands, debugs errors, tests the app in a browser and reports back. Your data never leaves your computer unless you choose a cloud provider.",
    features_title: "Highlights",
    features: [
      ["Multi-model", "Ollama, LM Studio, OpenAI, Anthropic, Gemini, OpenRouter, Groq, NVIDIA NIM, Cloudflare Workers AI, DeepSeek, EVREN and 25+ providers; one-click switching."],
      ["Real tool use", "Native function calling + a universal parser: tool calls work reliably and raw syntax never leaks into the chat."],
      ["Multi-agent", "Assistant, Planner, Coder, Debugger and Tester roles; automatic debugging loop on failures."],
      ["Uninterrupted tasks", "Long jobs run to the end, with live grouped steps, a to-do list and automatic skill selection."],
      ["Smart context", "Real token counting (bundled tokenizer + the provider's own count, tool definitions included), a live meter while the model thinks and writes, in-task trimming/summarizing (with an exact list of the steps already done, so nothing is repeated or invented), threshold compression and persistent session summaries."],
      ["Safety", "Three permission modes, a smart fence for destructive commands and a restricted child-process environment."],
      ["Pro IDE", "Monaco editor, file manager, process panel, git time machine, light/dark themes, fully responsive."],
      ["Web research", "Your APIs first (Google, Yandex, Bing, Brave, Tavily, SearXNG), else free ddgs search over Google/Yahoo/Bing/Yandex/Brave in parallel; result fusion, a background browser, structured data and archived copies for reading pages, cited summaries."],
      ["Version-aware commands", "Writes commands knowing the OS build, the shells and the tool versions; argv runs without a shell, heredocs are routed, background processes return when ready."],
      ["Document research", "Reads PDF, Word, Excel, PowerPoint, OpenDocument, CSV and images with page-numbered quotes; built-in OCR for scanned pages."],
      ["Review card and timing", "Every change a task made in its folder (commands included) with diffs; where the task's time went between model, tools and the app."],
      ["Maps and places", "Find places around a district, address or coordinates (free OpenStreetMap; ratings and reviews with Google/Yandex Places), interactive maps, place comparison, market and competitor analysis, product catalogs."],
      ["Documents with preview", "Generates Word, Excel, PDF and PowerPoint files; they appear as cards and preview inside the app."],
      ["Multi-model and quotas", "Automatic model switch on quota, per-agent models, models handing work to each other; 5-hour and weekly quota tracking."],
      ["Project memory", "Per-project rules (AIIQ.md) and global rules are added to every chat; say \"remember this\" and the model saves the rule itself."],
      ["Smart code editing", "Partial file edits, project-wide code search and a function/class map: fast changes even in big projects."],
      ["Diff before approval", "For every file change that needs approval you see the lines to be added and removed beforehand."],
      ["Model profiles", "Per-model thinking, image input, streaming, tool-call format, temperature and output length."],
      ["Effort setting", "Reasoning effort uses the real levels from the model's API data; models without it get an instruction."],
      ["MCP client", "Connect MCP servers such as GitHub, PostgreSQL or the file system; their tools are offered to the model."],
      ["Syntax trees", "Exact definitions and impact analysis with Tree-sitter: see which files a change affects beforehand."],
      ["Agent teams", "Splits big jobs into parts on different cloud models: independent parts at the same time, dependent parts stage by stage (team 1's output goes to team 2). Members message each other and share a task list; live task board."],
      ["Voice control", "Answers read aloud and spoken commands: \"send\", \"stop\", \"approve\", \"deny\", \"new chat\"."],
      ["Drawing and attachments", "Drawing pad, file and folder upload, goal and plan modes."],
    ],
    adv_title: "Advantages",
    advantages: [
      "Local-first: your code and files stay on your computer; the cloud is used only when you choose it.",
      "Provider-agnostic: switching models is a click, not a code change.",
      "Transparent: every step, command and file change is traceable; every project can be rolled back with git.",
      "Extensible: add agents, skills and providers without writing code.",
    ],
    roadmap_title: "Roadmap",
    roadmap: [
      "Optional Docker (WSL2) sandbox for isolated command execution",
      "Full timeline video editor (ffmpeg): trim, cut, join, text and logo, music, transitions, format conversion; subtitles automatic from speech (faster-whisper) or from given text; preview in the chat",
      "Stronger image generation: free Pollinations (FLUX) by default, Hugging Face, Together, OpenAI, Gemini, Stability with a key; detects the wanted format and size (story, cover, A4, banner) and prints text sharply over the image",
      "Stock image and video services: Pexels, Pixabay, Unsplash, Openverse, Wikimedia (free) and Shutterstock, Getty, Adobe Stock, Storyblocks (paid; approval with the price on every download); licence and source recorded",

    ],
    dev_title: "Developer",
    dev_desc: "Software developer building WordPress plugins, AI tools and automation solutions.",
  },
};

export const PAGES = { tr, en };
export const pagesFor = (lang) => PAGES[lang] || PAGES.en;
