// Long-form Guide and About content (TR/EN). Other languages fall back to English.
export const AUTHOR = {
  name: "Onur Öztaş",
  github: "https://github.com/AppsTRDesign",
  site: "https://wplugins.shop",
};
export const VERSION = "0.6.0";

const tr = {
  guide: {
    title: "Rehber",
    intro: "AI IQ 300'ü birkaç dakikada verimli kullanmak için bilmeniz gereken her şey.",
    sections: [
      { icon: "rocket", title: "1. Hızlı başlangıç", items: [
        "install.bat ile kurun, run.bat ile başlatın. Uygulama http://127.0.0.1:8300 adresinde açılır.",
        "Ayarlar > Sağlayıcılar'dan bir model kaynağı hazırlayın: yerel Ollama/LM Studio anahtar istemez; bulut API'leri için anahtarı girip Test'e basın.",
        "Mesaj kutusunun altındaki model seçiciden çalışmak istediğiniz modeli seçin. Yerel modele geçince diğer yerel modeller bellekten boşaltılır.",
      ] },
      { icon: "folder", title: "2. Projeler ve sohbetler", items: [
        "Sol menüde + ile proje oluşturun; bilgisayarınızdan bir klasör seçebilir veya yeni klasör açabilirsiniz. Ajanın tüm çıktıları o klasöre yazılır.",
        "Projesiz sohbetler workspace/ klasöründe çalışır. Her sohbetin oturum kaydı chat/<id>-session/ altında tutulur ve sohbet silinince tamamen silinir.",
        "Sohbet ve projelere sağ tıklayarak sabitleyebilir, yeniden adlandırabilir, arşivleyebilir veya silebilirsiniz.",
      ] },
      { icon: "bot", title: "3. Ajanlar (@) ve yetenekler (/)", items: [
        "Varsayılan asistan sohbete göre davranır: sohbet ederseniz sohbet eder, iş isterseniz araçlarla gerçekten yapar.",
        "@coder, @tester, @debugger, @planner yazarak rolü değiştirin. /webapp, /docs, /git gibi yetenekler talimat ekler.",
        "Yetenek yazmanız şart değil: model, isteğinize uyan yeteneği kendisi seçip yükler.",
        "Yetenekler ve Ajanlar sayfalarından yenilerini oluşturabilir, Monaco ile düzenleyebilir, dosyadan veya GitHub adresinden içe aktarabilirsiniz.",
      ] },
      { icon: "wrench", title: "4. Araçlar ve otonom çalışma", items: [
        "Model; dosya yazma/okuma, PowerShell/CMD/Python/Node/PHP komutları, arka plan süreçleri, web araştırması, tarayıcıda görsel test ve Word/Excel/PDF/PPT üretimi yapabilir.",
        "Komut hata verirse hata ayıklayıcı rolü devreye girer, hatayı okuyup düzeltir ve yeniden dener.",
        "Arka planda olan her şey tek bir adım grubunda toplanır; iş sürerken yalnızca o anki adım görünür, tıklayınca hepsi açılır.",
        "Çok adımlı işlerde model gerektiğinde canlı bir yapılacaklar listesi açar ve maddeleri ilerledikçe işaretler.",
        "Uzun görevler bitene kadar sürer; model bir sonraki adımı söyleyip durursa devam ettirilir. Yarıda kalan işi \"devam et\" ile kaldığı yerden sürdürebilirsiniz.",
        "Artı menüsü: dosya ve klasör yükleme, Hedef modu (hedefe ulaşana kadar kendi başına çalışır), Plan modu, Çizim ekranı (çizip resim olarak gönderin) ve belge kısayolları.",
      ] },
      { icon: "shield", title: "5. İzin modları ve güvenlik", items: [
        "Onay iste: proje dışı dosya ve internet işlemlerinden önce sorar. Benim için onayla: yalnızca riskli işlemleri sorar. Tam erişim: sınırsız erişim.",
        "rm -rf, format, os.remove gibi yıkıcı komutlar tam erişimde bile onay ister; disk biçimlendirme gibi işlemler hiç çalıştırılmaz.",
        "Komutlar bilgisayarınızda doğrudan çalışır; filtre bir yalıtım (sandbox) değildir. Gerçek kontrol onay modudur.",
      ] },
      { icon: "gauge", title: "6. Bağlam yönetimi", items: [
        "Mesaj kutusundaki halka bağlam doluluğunu gösterir; tıklayınca hangi kalemin ne kadar yer kapladığını, çıktıları ve arka plan görevlerini görürsünüz.",
        "Bağlam ayarlanan eşiğe (varsayılan %80) ulaşınca eski mesajlar otomatik özetlenir; Şimdi sıkıştır ile elle de yapabilirsiniz.",
        "Bağlam iş sürerken de canlı sayılır; uzun görevlerde eski dosya içerikleri kırpılır ya da adımlar özetlenir, böylece görev kopmaz.",
        "Yerel modellerde bağlam boyutunu model seçicideki boyut etiketinden veya Ayarlar'dan ayarlayın; ikisi anında senkron kalır."
      ] },
      { icon: "files", title: "7. Dosyalar ve zaman makinesi", items: [
        "Dosyalar bölümü klasör ağacı, türe göre filtre, önizleme, yükleme, yeniden adlandırma ve sağ tık menüsü olan tam bir dosya yöneticisidir.",
        "Proje klasörlerinde her çalışmadan sonra otomatik git anlık görüntüsü alınır; Zaman makinesi ile istediğiniz noktaya geri dönebilirsiniz.",
        "Üretilen Word, Excel, PDF ve PowerPoint belgeleri sohbette kart olarak görünür; karta tıklayınca uygulama içinde önizlenir.",
      ] },
      { icon: "globe", title: "8. Web araştırması", items: [
        "research aracı birden çok arama motorunu birleştirir, en iyi kaynakları paralel okur ve kaynak adresleriyle özetler.",
        "Bot korumasıyla erişimi engelleyen siteler açıkça raporlanır; model başka kaynaklara yönelir ve uydurmaz. Daha güçlü sonuç için Ayarlar > Web'den Brave, Tavily veya SearXNG ekleyebilirsiniz.",
      ] },
      { icon: "help", title: "9. Sık sorulanlar", items: [
        "Model listesi boş: sağlayıcı etkin mi, anahtar kayıtlı mı? Ayarlar > Sağlayıcılar > Test sonucunu kontrol edin.",
        "EVREN 403 veriyor: kullanım şartlarını Test > Şartları oku ve kabul et ile onaylayın.",
        "Arayüz eski görünüyor: güncellemeden sonra tarayıcıda bir kez Ctrl+F5 yapın.",
      ] },
    ],
  },
  about: {
    title: "Hakkımızda",
    tagline: "Yerel ve bulut yapay zekâ modelleriyle çalışan, kendi kendine kod yazan, test eden ve çalıştıran otonom AI komuta merkezi.",
    what_title: "AI IQ 300 nedir?",
    what: "AI IQ 300; bilgisayarınızda çalışan, ChatGPT/Claude tarzı sade bir sohbet arayüzüne sahip bir yazılım geliştirme ve otomasyon merkezidir. Ona bir hedef verirsiniz; klasörleri ve dosyaları oluşturur, komutları çalıştırır, hataları ayıklar, uygulamayı tarayıcıda test eder ve sonucu size raporlar. Verileriniz, siz bulut sağlayıcı seçmedikçe bilgisayarınızdan çıkmaz.",
    features_title: "Öne çıkan yetenekler",
    features: [
      ["Çoklu model", "Ollama, LM Studio, OpenAI, Anthropic, Gemini, OpenRouter, Groq, DeepSeek, EVREN ve 25+ sağlayıcı; tek tıkla geçiş."],
      ["Gerçek araç kullanımı", "Native function calling + evrensel ayrıştırıcı: araç çağrıları güvenilir çalışır, ham sözdizimi sohbete sızmaz."],
      ["Çoklu ajan", "Asistan, Planlayıcı, Kodlayıcı, Hata ayıklayıcı ve Test uzmanı rolleri; hata olursa otomatik hata ayıklama döngüsü."],
      ["Kesintisiz görevler", "Uzun işler bitene kadar sürer; canlı adım grubu, yapılacaklar listesi ve otomatik yetenek seçimi."],
      ["Akıllı bağlam", "Görev sürerken canlı sayım, görev içi kırpma/özetleme, eşik bazlı sıkıştırma ve kalıcı oturum özetleri."],
      ["Güvenlik", "Üç kademeli izin modu, yıkıcı komutlar için akıllı güvenlik çiti, kısıtlı alt süreç ortamı."],
      ["Profesyonel IDE", "Monaco editör, dosya yöneticisi, süreç paneli, git zaman makinesi, gece/gündüz teması, tam mobil uyum."],
      ["Web araştırması", "Çok motorlu arama, gerçek tarayıcıyla sayfa okuma, engel tespiti ve kaynaklı özetler."],
      ["Belge üretimi ve önizleme", "Word, Excel, PDF ve PowerPoint üretir; belgeler sohbette kart olarak açılır ve uygulama içinde önizlenir."],
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
      "Kısmi dosya düzenleme ve proje içi kod arama (yerel modellerde çok daha hızlı değişiklik)",
      "Tree-sitter ile fonksiyon/sınıf haritası: değişikliğin etkileyeceği dosyaları önceden görme",
      "MCP istemcisi: GitHub, PostgreSQL ve binlerce hazır MCP sunucusunu araç olarak bağlama",
      "Onaydan önce değişiklik farkı (diff) görünümü ve proje başına kalıcı kurallar",
      "İsteğe bağlı Docker (WSL2) sandbox ile yalıtılmış komut çalıştırma",
      "Bulut modellerde paralel ajan takımları ve görev panosu; sesli yanıt",
    ],
    dev_title: "Geliştirici",
    dev_desc: "Yazılım geliştirici; WordPress eklentileri, yapay zekâ araçları ve otomasyon çözümleri üretiyor.",
  },
};

const en = {
  guide: {
    title: "Guide",
    intro: "Everything you need to use AI IQ 300 productively in a few minutes.",
    sections: [
      { icon: "rocket", title: "1. Quick start", items: [
        "Install with install.bat and start with run.bat. The app opens at http://127.0.0.1:8300.",
        "Set up a model source in Settings > Providers: local Ollama/LM Studio need no key; for cloud APIs enter the key and press Test.",
        "Pick the model from the selector under the message box. Switching to a local model unloads other local models from memory.",
      ] },
      { icon: "folder", title: "2. Projects and chats", items: [
        "Create a project with + in the sidebar; choose a folder on your computer or create a new one. All agent output is written there.",
        "Chats without a project work in workspace/. Every chat keeps its session record in chat/<id>-session/, deleted completely with the chat.",
        "Right-click chats and projects to pin, rename, archive or delete them.",
      ] },
      { icon: "bot", title: "3. Agents (@) and skills (/)", items: [
        "The default assistant adapts to the conversation: it chats when you chat and does the work with tools when you ask for it.",
        "Type @coder, @tester, @debugger or @planner to switch roles. Skills such as /webapp, /docs or /git add instructions.",
        "You don't have to type a skill: the model picks and loads the one that matches your request.",
        "Create new ones on the Skills and Agents pages, edit them with Monaco, or import them from a file or a GitHub URL.",
      ] },
      { icon: "wrench", title: "4. Tools and autonomous work", items: [
        "The model can write/read files, run PowerShell/CMD/Python/Node/PHP commands, start background processes, research the web, test UIs in a browser and produce Word/Excel/PDF/PPT files.",
        "When a command fails, the debugger role reads the error, fixes it and retries.",
        "Everything that happens in the background is grouped under one header; while a task runs only the current step shows, and a click opens them all.",
        "For multi-step work the model opens a live to-do list when needed and ticks items off as it goes.",
        "Long tasks run to the end; a model that announces the next step and stops is made to continue. Type \"continue\" to resume an interrupted task where it stopped.",
        "Plus menu: upload files and folders, Goal mode (works on its own until the goal is reached), Plan mode, the Drawing pad (sketch and send it as an image) and document shortcuts.",
      ] },
      { icon: "shield", title: "5. Permission modes and safety", items: [
        "Ask for approval: asks before external file and internet actions. Approve for me: asks only for risky actions. Full access: unrestricted.",
        "Destructive commands such as rm -rf, format or os.remove always ask, even in full access; disk formatting never runs.",
        "Commands run directly on your computer; the filter is not a sandbox. The approval mode is the real control.",
      ] },
      { icon: "gauge", title: "6. Context management", items: [
        "The ring in the message box shows context usage; click it to see which category uses how much, plus outputs and background tasks.",
        "Old messages are summarized automatically at the threshold (default 80%); use Compress now to do it manually.",
        "Context is counted live while a task runs; in long tasks old file bodies are trimmed or steps summarized so the task does not break.",
        "For local models, set the context size from the size chip in the model picker or in Settings; both stay in sync instantly."
      ] },
      { icon: "files", title: "7. Files and time machine", items: [
        "Files is a full file manager: folder tree, type filters, preview, upload, rename and right-click menus.",
        "Project folders get an automatic git snapshot after each run; restore any point with the Time machine.",
        "Generated Word, Excel, PDF and PowerPoint files appear as cards in the chat; click one to preview it inside the app.",
      ] },
      { icon: "globe", title: "8. Web research", items: [
        "The research tool merges several search engines, reads the best sources in parallel and summarizes with source URLs.",
        "Sites that block automated access are reported clearly; the model moves on to other sources instead of guessing. Add Brave, Tavily or SearXNG in Settings > Web for stronger results.",
      ] },
      { icon: "help", title: "9. FAQ", items: [
        "Model list is empty: is the provider enabled and the key saved? Check Settings > Providers > Test.",
        "EVREN returns 403: accept the terms via Test > Read & accept terms.",
        "The UI looks outdated: press Ctrl+F5 once after an update.",
      ] },
    ],
  },
  about: {
    title: "About",
    tagline: "An autonomous AI command center that writes, tests and runs code with local and cloud AI models.",
    what_title: "What is AI IQ 300?",
    what: "AI IQ 300 is a software development and automation hub that runs on your computer behind a clean ChatGPT/Claude-style chat. Give it a goal: it creates folders and files, runs commands, debugs errors, tests the app in a browser and reports back. Your data never leaves your computer unless you choose a cloud provider.",
    features_title: "Highlights",
    features: [
      ["Multi-model", "Ollama, LM Studio, OpenAI, Anthropic, Gemini, OpenRouter, Groq, DeepSeek, EVREN and 25+ providers; one-click switching."],
      ["Real tool use", "Native function calling + a universal parser: tool calls work reliably and raw syntax never leaks into the chat."],
      ["Multi-agent", "Assistant, Planner, Coder, Debugger and Tester roles; automatic debugging loop on failures."],
      ["Uninterrupted tasks", "Long jobs run to the end, with live grouped steps, a to-do list and automatic skill selection."],
      ["Smart context", "Live counting during tasks, in-task trimming/summarizing, threshold compression and persistent session summaries."],
      ["Safety", "Three permission modes, a smart fence for destructive commands and a restricted child-process environment."],
      ["Pro IDE", "Monaco editor, file manager, process panel, git time machine, light/dark themes, fully responsive."],
      ["Web research", "Multi-engine search, real-browser page reading, block detection and cited summaries."],
      ["Documents with preview", "Generates Word, Excel, PDF and PowerPoint files; they appear as cards and preview inside the app."],
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
      "Partial file edits and project-wide code search (much faster changes with local models)",
      "Tree-sitter function/class map: see which files a change will affect before making it",
      "MCP client: connect GitHub, PostgreSQL and thousands of ready MCP servers as tools",
      "Diff view before approval and persistent per-project rules",
      "Optional Docker (WSL2) sandbox for isolated command execution",
      "Parallel agent teams and a task board for cloud models; spoken replies",
    ],
    dev_title: "Developer",
    dev_desc: "Software developer building WordPress plugins, AI tools and automation solutions.",
  },
};

export const PAGES = { tr, en };
export const pagesFor = (lang) => PAGES[lang] || PAGES.en;
