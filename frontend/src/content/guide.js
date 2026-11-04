// Wiki-style Guide (TR/EN): categories -> articles written in Markdown. Other languages fall back to English.
// Article ids are shared by both languages, so the open article stays the same when the language changes.

const tr = {
  title: "Rehber",
  intro: "AI IQ 300'ün her özelliği konu konu: soldan bir başlık seçin ya da arayın.",
  search: "Rehberde ara…",
  results: "{n} sonuç",
  empty: "Sonuç bulunamadı. Başka bir sözcük deneyin.",
  toc: "Bu sayfada",
  prev: "Önceki",
  next: "Sonraki",
  topics: "Konular",
  cats: [
    { id: "start", icon: "rocket", title: "Başlarken", articles: [
      { id: "install", title: "Kurulum ve ilk çalıştırma", summary: "install.bat, run.bat ve ilk açılış.", md: `
## Kurulum
1. Proje klasöründe **install.bat** dosyasını çalıştırın. Python ve Node bağımlılıkları (tokenizer dahil) kurulur.
2. **run.bat** ile uygulamayı başlatın. Tarayıcıda **http://127.0.0.1:8300** açılır.
3. Güncellemeden sonra install.bat'ı bir kez daha çalıştırın ve tarayıcıda **Ctrl+F5** yapın.

## Klasörler
| Klasör | İçerik |
|---|---|
| \`data/\` | Ayarlar, sohbet veritabanı, gizli anahtarlar |
| \`workspace/\` | Projesiz sohbetlerin çalışma alanı |
| \`chat/<id>-session/\` | Her sohbetin oturum kaydı (sohbet silinince silinir) |
| \`skills/\`, \`agents/\` | Yetenek ve ajan dosyaları |
| \`languages/\` | Arayüz dil dosyaları (tr.json, en.json…) |

> Anahtarlar yalnızca \`data/secrets.json\` içinde tutulur ve arayüze hiçbir zaman açık olarak gönderilmez.
` },
      { id: "providers", title: "Sağlayıcı ekleme", summary: "Yerel ve bulut model kaynakları, anahtarlar, Test.", md: `
## Yerel modeller
- **Ollama** ve **LM Studio** anahtar istemez; uygulama açıkken modeller otomatik listelenir.
- Yerel bir modele geçildiğinde diğer yerel modeller bellekten boşaltılır.

## Bulut API'leri
1. **Ayarlar > Sağlayıcılar**'ı açın, sağlayıcıyı etkinleştirin.
2. API anahtarını girin ve **Test**'e basın. Test model listesini ve hata varsa nedenini gösterir.
3. Desteklenenler: OpenAI, Anthropic, Gemini, OpenRouter, Groq, DeepSeek, Hugging Face, **NVIDIA NIM**, **Cloudflare Workers AI**, EVREN, Ollama Cloud ve 20'den fazlası.

## Cloudflare Workers AI
- API anahtarının yanında **Hesap kimliği (Account ID)** gerekir: Cloudflare panelinde sağ üstteki 32 karakterlik onaltılık kod.
- Ücretsiz plan günde 10.000 nöron verir; bitince (hata 3036) gece yarısına kadar beklenir. Bazı modeller ücretli plan ister (hata 5035): bu model 24 saat atlanır.

## NVIDIA NIM
- \`nvapi-\` ile başlayan anahtarı girin; 80'den fazla model listelenir. Hız sınırında uygulama bekleyip yeniden dener.

## EVREN
- İlk kullanımda 403 alırsanız **Test > Şartları oku ve kabul et** ile kullanım şartlarını onaylayın.
` },
      { id: "models", title: "Model seçimi ve profiller", summary: "Model seçici, bağlam boyutu, çaba, model profilleri.", md: `
## Model seçici
Mesaj kutusunun altındaki seçiciden modeli seçin. Yanındaki boyut etiketi (ör. **33K**) modelin bağlam penceresidir; yerel modellerde buradan değiştirilebilir.

## Çaba
Gösterge simgeli **Çaba** menüsü modelin desteklediği düşünme seviyelerini gösterir. OpenRouter, OpenAI, Anthropic, Gemini ve Ollama'da API'nin kendi ayarı kullanılır; desteklemeyen modellere seviye talimat olarak iletilir.

## Model profilleri
**Ayarlar > Modeller > Model profilleri**: model başına düşünme, görsel girdi, akış, araç çağrı biçimi, sıcaklık ve en fazla çıktı uzunluğu. **Otomatik** sağlayıcının bildirdiğini kullanır.
` },
      { id: "tour", title: "Arayüz turu", summary: "Kenar çubuğu, sohbet, adım listesi, paneller.", md: `
- **Sol menü:** projeler, sohbetler, Dosyalar, Yetenekler, Ajanlar, Ayarlar, Rehber, Hakkımızda.
- **Sohbet:** cevabın üstünde **adım grubu** (düşünme, notlar, araçlar), altında yapılacaklar listesi, üretilen dosya kartları ve görev panosu yer alır.
- **Mesaj kutusu:** + menüsü, izin modu, model seçici, bağlam halkası, çaba, sesli komut, mikrofon ve gönder.
- **Sağ paneller:** kod editörü, uygulama içi tarayıcı, belge önizleme, süreç paneli.
` },
    ] },
    { id: "chat", title: "Sohbet ve projeler", icon: "folder", articles: [
      { id: "projects", title: "Projeler ve sohbetler", summary: "Proje klasörü, sabitleme, arşiv.", md: `
- Sol menüde **+** ile proje oluşturun; bilgisayarınızdan bir klasör seçin veya yeni klasör açın. Ajanın tüm çıktıları o klasöre yazılır.
- Projesiz sohbetler \`workspace/\` klasöründe çalışır.
- Sohbet ve projelere **sağ tıklayarak** sabitleyin, yeniden adlandırın, arşivleyin veya silin.
- Proje menüsündeki **Proje kuralları** o projedeki her sohbetin uyacağı kuralları yazar (bkz. *Proje hafızası*).
` },
      { id: "files", title: "Dosyalar ve zaman makinesi", summary: "Dosya yöneticisi, git anlık görüntüleri, önizleme.", md: `
- **Dosyalar**: klasör ağacı, türe göre filtre, önizleme, yükleme, yeniden adlandırma ve sağ tık menüsü.
- Proje klasörlerinde her çalışmadan sonra otomatik **git anlık görüntüsü** alınır; **Zaman makinesi** ile istediğiniz noktaya dönün.
- Model mevcut dosyada yalnızca değişen kısmı düzenler; adımı açınca eklenen satırlar yeşil, silinenler kırmızı görünür.
- HTML sayfaları ve localhost adresleri **uygulama içi tarayıcıda** açılır (masaüstü/tablet/mobil görünüm).
` },
      { id: "attachments", title: "Ekler, çizim ve resim düzenleme", summary: "Dosya/klasör ekleme, çizim ekranı, resim üstüne çizim.", md: `
- Dosya ve klasörleri sohbetin herhangi bir yerine **sürükleyip bırakın** ya da + menüsünden yükleyin.
- **Çizim ekranı** (+ menüsü): çizip resim olarak gönderin.
- Eklediğiniz bir resme tıklayın: kalem, çizgi, ok, dikdörtgen, elips, yazı ve silgi. **Uygula ve ekle** resmi orijinal çözünürlükte değiştirir.
` },
      { id: "documents", title: "Belgeler ve önizleme", summary: "Word, Excel, PDF, PowerPoint üretimi.", md: `
- Model **make_doc** aracıyla Word, Excel, PDF ve PowerPoint üretir.
- Belgeler sohbette **kart** olarak görünür; karta tıklayınca uygulama içinde önizlenir.
- **/web-to-doc** yeteneği web araştırmasını mevcut bir Word/Excel/Markdown belgesine yazar.
` },
    ] },
    { id: "agents", title: "Ajanlar ve yetenekler", icon: "bot", articles: [
      { id: "roles", title: "Ajanlar (@)", summary: "Hazır roller ve rol değiştirme.", md: `
Varsayılan asistan sohbete göre davranır: sohbet ederseniz sohbet eder, iş isterseniz araçlarla gerçekten yapar.

| Ajan | Görevi |
|---|---|
| @coder | Kod yazar ve düzenler |
| @tester | Test eder |
| @debugger | Hataları ayıklar |
| @planner | Plan çıkarır |
| @researcher | Web araştırması |
| @comparer | Ürün karşılaştırma |
| @writer | Makale yazar |
| @prompt-wizard | Prompt hazırlar |
| @skill-maker / @agent-maker | Yeni yetenek / ajan üretir |

Bir komut hata verirse **hata ayıklayıcı** rolü kendiliğinden devreye girer.
` },
      { id: "skills", title: "Yetenekler (/)", summary: "Hazır yetenekler ve otomatik seçim.", md: `
- **/web-research, /web-summary, /web-report, /web-to-doc, /compare, /article, /prompt, /docs, /webapp, /git**.
- Harita ve pazarlama: **/place-research, /place-compare, /map-market, /catalog** (bkz. *Web ve entegrasyonlar*).
- Yetenek yazmanız şart değil: model isteğinize uyan yeteneği kendisi seçip yükler. Yetenekler yalnızca gerektiğinde yüklenir.
` },
      { id: "custom", title: "Kendi ajan ve yeteneğiniz", summary: "Oluşturma, içe aktarma, tools: satırı.", md: `
- **Yetenekler** ve **Ajanlar** sayfalarından yenilerini oluşturun, Monaco ile düzenleyin, dosyadan veya GitHub adresinden içe aktarın.
- Dosyaya bir **tools:** satırı eklerseniz o seçildiğinde modele yalnızca bu araçlar gönderilir: araç tanımları %60–85 küçülür, küçük modeller daha az yanlış çağrı yapar.
- @skill-maker ve @agent-maker yeni dosyayı doğrular ve onayınızla ekler; hemen / veya @ ile kullanılabilir.
` },
    ] },
    { id: "auto", title: "Otonom çalışma", icon: "wrench", articles: [
      { id: "tools", title: "Araçlar", summary: "Modelin kullanabildiği araçlar.", md: `
| Araç | Ne yapar |
|---|---|
| write_file / edit_file / read_file | Dosya yazar, kısmen düzenler, okur |
| run / start / stop | Komut çalıştırır, arka plan süreci başlatır/durdurur |
| search_code / symbols / impact | Kod arama, tanım haritası, etki analizi (Tree-sitter) |
| research / web_search / fetch_url | Web araştırması |
| places | Harita ve mekân araması, etkileşimli harita sayfası |
| web_screenshot / browser_check | Sayfa görüntüsü ve görsel test |
| make_doc | Word/Excel/PDF/PPT üretimi |
| todo | Canlı yapılacaklar listesi |
| ask_model / team | Başka modele sorma, ajan takımı (bkz. *Çoklu model ve takımlar*) |
| remember | Kalıcı kural kaydetme |
| mcp | Bağlı MCP sunucularının araçları |
` },
      { id: "review", title: "Değişiklik inceleme kartı", summary: "Bir turun klasörde bıraktığı tüm farklar.", md: `
Her görevin altında **N dosya değişti** kartı çıkar: görev başladığından beri çalışma klasöründe eklenen, değişen ve silinen **her** dosya.

- Kaynak her satırda yazar: **araç** (yaz, düzenle, belge) ya da **komut** (terminal komutu, betik, biçimlendirici, \`npm install\`, kod üreticileri).
- Satıra tıklayınca renkli fark açılır; **Tüm farkları aç** hepsini gösterir; ok simgesi dosyayı editörde açar.
- İkili ya da çok büyük dosyalarda boyut değişimi gösterilir.
- Klasörün görüntüsü görev başlarken arka planda alınır (model ilk cevabını yazarken), değişmeyen dosyalar önbellekten gelir; bu yüzden görev yavaşlamaz. \`node_modules\`, \`.git\`, \`dist\` gibi klasörler sayılmaz.
` },
      { id: "timing", title: "Süre ve performans", summary: "Bir görevin süresi nerede geçti.", md: `
Biten her görevin adım başlığında toplam süre görünür; açınca dağılımı:

| Kalem | Anlamı |
|---|---|
| İlk yanıt | Mesajı gönderdiğiniz andan modelin ilk düşünce/metin/araç çağrısına kadar |
| Model | Modelin tüm turlarının süresi; *ilk token beklemesi* sağlayıcının cevaba başlamadan geçirdiği süre |
| Araçlar | Araç türüne göre (run, write_file, research…), kaç kez çağrıldığıyla |
| Takım | Ajan takımının toplam süresi |
| Ek çağrılar | Özetleme, dil düzeltme, sıkıştırma |
| Uygulama | Geri kalan: uygulamanın kendi işi |

Son görevlerin yüzdelik değerleri (p50 / p95 / en yüksek) \`/api/perf\` adresinde, kısa özeti \`/api/health\` içinde. Böylece yavaşlığın modelde mi, bir araçta mı, takımda mı olduğu ayrı ayrı görülür.
` },
      { id: "steps", title: "Adımlar, notlar ve yapılacaklar", summary: "Adım grubu nasıl okunur.", md: `
- Arka planda olan her şey cevabın üstündeki **adım grubunda** toplanır; iş sürerken yalnızca o anki adım görünür, tıklayınca hepsi açılır.
- **Düşünüyor**: modelin düşünmesi. **Not**: model araçlar arasında yazdığı kısa açıklama; cevap değildir, soluk renkte görünür.
- Çok adımlı işlerde canlı bir **yapılacaklar** listesi açılır ve maddeler ilerledikçe işaretlenir.
- Model bir sonraki adımı söyleyip durursa devam ettirilir; yarıda kalan işi **devam et** ile sürdürün.
- **Hedef modu** (+ menüsü) hedefe ulaşana kadar kendi başına çalışır; **Plan modu** önce plan çıkarır.
` },
      { id: "commands", title: "Komutlar ve sistem sürümü", summary: "Sistem envanteri, kabuklar, argv, betikler, heredoc.", md: `
Komutlar bilgisayarınızda doğrudan, yalıtımsız çalışır; Codex ve Claude Code gibi. Hızlı ve doğru olmaları için model bilgisayarı tanır.

## Sistem envanteri
Uygulama açılırken bir kez (arka planda, yarım saniyede) şunları tespit eder ve modele verir:
- İşletim sistemi, sürümü ve derleme numarası (ör. *Windows 10 Pro 22H2, build 19045*), işlemci mimarisi
- Kabuklar ve sürümleri: Windows PowerShell 5.1, PowerShell 7, cmd, Git Bash
- Kurulu araçlar ve sürümleri: git, Node, npm, Python, PHP, Java, .NET, Docker, winget/brew…

Listede olmayan bir araç kurulu değildir; model önce kontrol eder ya da kurulum komutunu verir.

## Kabuk seçimi
| Kabuk | Ne zaman |
|---|---|
| \`argv=["git","status"]\` | Tek program, düz argümanlar: kabuk yok, tırnak sorunu yok, en hızlısı |
| \`powershell\` | PowerShell 7 kuruluysa o, değilse 5.1 |
| \`powershell5\` / \`pwsh\` | Belirli PowerShell sürümü |
| \`cmd\` | Toplu iş (.bat) ve cmd komutları |
| \`bash\` | Windows'ta Git Bash (WSL değil), Linux/macOS'ta bash |
| \`python\` / \`node\` | Çok satırlı betik: kaynak bir betik dosyasına yazılıp çalıştırılır |

## Windows PowerShell 5.1 uyumu
- \`&&\` ve \`||\` 5.1'de yoktur; uygulama soldan sağa anlamıyla çevirir.
- \`rm -rf\`, \`mkdir -p a b\`, \`ls -la\`, \`del /s /q\`, \`touch\` gibi alışkanlıklar yalnız bu biçimde yazıldığında yakalanır. Yerel kullanım (\`ls -Filter *.txt\`, \`Remove-Item -Recurse\`, \`dir | Where-Object …\`) gerçek cmdlet'e olduğu gibi gider; anlamı değişmez.
- Başarısız komut gerçek çıkış koduyla döner.

## Heredoc ve çok satırlı içerik
- \`cat > dosya <<'EOF'\` gibi bash heredoc'ları PowerShell'e gönderilirse Git Bash'te çalıştırılır. Git Bash yoksa dosyaya yazma ya da girdi olarak aktarmaya çevrilir.
- PowerShell here-string'inin içeriden yazılmış kapanışı (\`    '@\`) otomatik düzeltilir.
- Dosya içerikleri her zaman write_file ile yazılır, komutla değil.

## Arka plan süreçleri
- \`start\` (ör. \`npm run dev\`) sunucu "hazır" satırını yazdığı anda döner (ör. *Local: http://localhost:5173*); eskiden sabit 6 sn bekliyordu.
- Arka plan sunucuları normal komutların sırasını kapatmaz; 9 sunucu açıkken bile komutlar beklemeden çalışır.

## Sürüme uygun komut yeteneği
\`/host-commands\` (otomatik de seçilir): bir bayrak ya da cmdlet o sürümde var mı emin değilse, model önce yerel yardıma (\`--help\`, \`Get-Help\`, \`man\`), sonra o sürümün resmî belgesine bakar (Microsoft Learn, git-scm.com, docs.python.org, nodejs.org…). Eski sürümler için o sürümün belgesini seçer. Sonucu doğrular, hata tekrar ederse teşhis yazar.
` },
    ] },
    { id: "multi", title: "Çoklu model ve takımlar", icon: "users", articles: [
      { id: "multi-overview", title: "Genel bakış", summary: "Tek model, başka modele sorma, ajan takımı: farkları.", md: `
AI IQ 300'de birden fazla model üç şekilde birlikte çalışır:

| Yöntem | Ne zaman | Kim yapar | Araç kullanır mı? |
|---|---|---|---|
| **Otomatik model değişimi** | Kota/hız sınırı dolunca | Havuzdaki en müsait model kaldığı yerden sürdürür | Evet |
| **Başka modele sorma** (\`ask_model\`) | İnceleme, analiz, ikinci görüş | Havuzdan seçilen tek bir model | Hayır, yalnızca metin döner |
| **Ajan takımı** (\`team\`) | "takım", "ekip", "çoklu ajan" istendiğinde, büyük işlerde | Her üye ayrı bir modelde çalışan gerçek bir ajan | Evet: dosya, komut, belge, web |

Hepsi için önce bir **çoklu model havuzu** kurmanız gerekir (bkz. *Havuz kurulumu*). Yerel modeller havuza girmez.
` },
      { id: "pool", title: "Havuz kurulumu", summary: "Ayarlar > Çoklu model, etiketler, ajan başına model.", md: `
1. **Ayarlar > Çoklu model**'i açın ve **Etkin** yapın.
2. **Havuza** bulut modelleri ekleyin. Her modele yetenek etiketi verin: \`code\`, \`reasoning\`, \`fast\`, \`writing\`, \`vision\`, \`long_context\`.
3. **Otomatik geçiş**: kota dolunca görev en müsait modelle sürer. **Görev devri**: model işin bir kısmını başka modele verebilir (ask_model ve team bunu gerektirir).
4. **Ajan başına model**: örneğin @coder için bir model, @tester için başka bir model atayın.
5. **Kotalar** bölümü her sağlayıcının son 5 saatlik ve haftalık kullanımını gösterir; sınır girerseniz dolunca o sağlayıcı atlanır.

> Takım üyeleri için **yerel araç çağrısını destekleyen** modeller seçilir. Araç desteği olmayan modeller (ör. EVREN \`auto\`) üye olmaz, ama ana model ya da ask_model için kullanılabilir.
` },
      { id: "ask-model", title: "Başka modele sorma (ask_model)", summary: "Tek bir alt işi başka modele vermek.", md: `
Model, kendi içinde çözmek yerine bir alt işi havuzdaki başka bir modele verebilir: kod incelemesi, analiz, uzun metin, ikinci görüş.

- Yeteneğe (\`need\`) göre **en müsait model** seçilir (kota, hız sınırı, bağlam).
- Seçilen model meşgulse sıradakine geçilir (en fazla 3 deneme).
- Diğer model **yalnızca metin** döndürür; dosya yazamaz ve komut çalıştıramaz. Bu yüzden bu bir takım çalışması değil, **danışmadır**.
- Adım listesinde **Başka modele soruldu · model-adı** olarak görünür.

**Örnek:** *"index.html'i oku ve başka bir modele erişilebilirlik açısından incelet."*
` },
      { id: "team", title: "Ajan takımı (paralel)", summary: "Bağımsız parçaları aynı anda farklı modellerde çalıştırmak.", md: `
Model büyük bir işi parçalara böler; her parça **ayrı bir ajan** tarafından, **havuzdaki farklı bir modelde**, aynı anda yapılır.

## Nasıl çalışır
1. Ana model \`team\` aracını çağırır: her üyenin **başlığı**, **görevi** ve **yeteneği** (code, reasoning, fast, writing).
2. Her üye için farklı bir model ayrılır; havuz küçükse bir model paylaşılır.
3. Üyeler aynı klasörde dosya okur/yazar, komut çalıştırır, belge üretir, web'e bakar.
4. Bir model hata verirse (kota, hız sınırı) üye başka modele geçer.
5. Bitince ana model her üyenin **raporunu, dosyalarını ve modelini** alır ve size özetler.

## Görev panosu
Sohbette canlı bir **Ajan takımı** panosu açılır. Her kartta:
- üyenin adı ve durumu (sırada, çalışıyor, bitti, hata)
- kullandığı **model**
- adım sayısı ve son yaptığı iş
- değiştirdiği dosyalar ve tıklayınca açılan **rapor**

Alt kısımda ortak **görev listesi** ve üyeler arası **mesajlar** görünür.

**Örnek:** *"Takım kur: biri Flask API'yi (api/app.py), biri HTML arayüzü (web/index.html), biri README'yi yazsın."*
` },
      { id: "pipeline", title: "Aşamalı takım (sıralı iş akışı)", summary: "1. takımın çıktısını 2. takımın kullandığı zincirler.", md: `
Bazı işler birbirine bağlıdır: 2. takım 1. takımın çıktısına ihtiyaç duyar. Bunun için üyelere **aşama** (\`stage\`) verilir.

- Aynı aşamadaki üyeler **aynı anda** çalışır.
- Bir aşama, öncekiler **bitince** başlar.
- Sonraki aşamadaki üyeye önceki aşamaların **raporları, modelleri ve dosya adları** otomatik verilir; gerekirse dosyaları kendisi okur.
- Görev panosunda her kartın başında **Aşama 1, Aşama 2…** etiketi görünür.
- Model aşama vermeyi unutsa bile, bir parçanın görevi öncekine dayanıyorsa ("1. takımın yazdığı sayfayı analiz et") parçalar otomatik olarak sırayla çalıştırılır.

## Örnek: HTML → analiz → Word
İstem: *"Çoklu model ve ajanla takım çalışması yap: 1. takım basit bir HTML sayfası yazsın, 2. takım bu kodu analiz etsin, 3. takım analizi Word belgesine yazsın."*

| Aşama | Üye | Model (örnek) | Çıktı |
|---|---|---|---|
| 1 | HTML Kodlama | nvidia:nemotron… | ciktı/1_takim/index.html |
| 2 | Kod Analizi | groq:gpt-oss-120b | analiz raporu |
| 3 | Word Raporu | cloudflare:glm-4.7-flash | ciktı/3_takim/HTML_Analiz_Raporu.docx |

Üç üye üç farklı modelde çalışır ve her biri kendi araçlarını kullanır. Ana model yalnızca takımı kurar ve sonucu özetler.

> İpucu: İsteminizde "takım", "ekip", "grup" ya da "çoklu ajan" demeniz yeterli; aşamaları model kurar. Belirli bir sıra istiyorsanız "önce…, sonra…" diye yazın.
` },
      { id: "team-chat", title: "Takım içi haberleşme", summary: "Üyeler arası mesajlar ve ortak görev listesi.", md: `
- **team_message**: bir üye başka bir üyeye (adıyla) ya da herkese mesaj gönderir; örneğin API'nin adresini, dosya adını ya da biten bir parçayı bildirir.
- Mesajlar alıcının bir sonraki araç sonucuyla birlikte ona ulaşır.
- **team_tasks**: ortak görev listesi. Üyeler görev **ekler**, **üstlenir** (başkasının görevini alamaz) ve **bitirir**.
- Panoda mesajlar *gönderen → alıcı* biçiminde, görevler durumlarıyla canlı görünür.
` },
      { id: "verify", title: "Hangi model ne yaptı?", summary: "Takım sonucunu doğrulamak.", md: `
- **Görev panosu** her üyenin modelini gösterir. Adım listesinde takım adımı da tıklanınca aynı bilgiyi verir.
- Ana model raporunda modelleri araç sonuçlarındaki gibi yazmak zorundadır. Kendisi yaptığı işi takım işi gibi sunamaz.
- Sonraki mesajlarda da model önceki turda hangi ajanın hangi modelle çalıştığını bilir; "hangi takım hangi modeli kullandı?" diye sorabilirsiniz.
- **Başka modele soruldu** adımı bir **danışmadır**, takım değildir: o model dosya üretmez.
` },
      { id: "quota", title: "Kota, hız sınırı ve otomatik geçiş", summary: "Sınır dolunca ne olur?", md: `
| Durum | Uygulama ne yapar |
|---|---|
| Hız sınırı (429) | Sağlayıcının istediği süre kadar bekler (en fazla 2 dk) ve yeniden dener |
| Aşırı yük (503), ağ hatası, zaman aşımı | 5, 15, 30, 60, 90 sn arayla yeniden dener |
| Bulut model 3 dk sessiz | İsteği keser ve yeniden dener |
| Kota bitti / kredi yok (402) | Çoklu model açıksa havuzdaki en müsait modelle **kaldığı yerden** sürer |
| Bağlam aşıldı | Eski içeriği kırpar veya özetler, yeniden dener |
| Ücretli plan gerekli | Modeli 24 saat atlar |

Bütün hata mesajları etkin dilde gösterilir.
` },
    ] },
    { id: "context", title: "Bağlam ve hafıza", icon: "gauge", articles: [
      { id: "ring", title: "Bağlam halkası ve token sayımı", summary: "Gerçek token sayımı, canlı sayaç.", md: `
- Mesaj kutusundaki **halka** bağlam doluluğunu gösterir; tıklayınca kalem kalem dağılımı (sistem, araçlar, yetenekler, proje, mesajlar), çıktıları ve arka plan görevlerini görürsünüz.
- Sayım gömülü bir **tokenizer** ve sağlayıcının kendi bildirdiği sayı ile yapılır; araç tanımları da sayılır, gizli düşünme tokenları sayılmaz.
- Sayaç model düşünürken ve yazarken de **canlı** ilerler.
` },
      { id: "compress", title: "Sıkıştırma", summary: "Eşik, görev içi özet, elle sıkıştırma.", md: `
- Bağlam eşiğe (varsayılan **%80**) ulaşınca eski mesajlar otomatik özetlenir; **Şimdi sıkıştır** ile elle de yapılabilir.
- Uzun görevlerde önce eski dosya içerikleri kırpılır, gerekirse adımlar özetlenir.
- Özetin sonuna **yapılmış araç çağrılarının kesin listesi** eklenir; model aynı adımları tekrarlamaz ve yapmadığı bir şeyi yaptım demez.
` },
      { id: "memory", title: "Proje hafızası ve kurallar", summary: "AIIQ.md, genel kurallar, bunu hatırla.", md: `
- **Proje kuralları** (proje menüsü) proje kökünde \`AIIQ.md\` dosyasına yazılır ve o projedeki her sohbete eklenir.
- **Ayarlar > Genel > Genel kurallar** tüm sohbetlere eklenir.
- Sohbette **"bunu hatırla"** dediğinizde model kuralı kendisi kaydeder.
` },
      { id: "language", title: "Dil", summary: "Etkin dil, başka dil sızıntısı.", md: `
- Etkin dil her yerde geçerlidir: düşünme, planlar, notlar, takım raporları ve cevap o dilde yazılır.
- Cevapta başka bir dilde sözcük çıkarsa (ör. Çince bir kelime) model yeniden düşünmez. Kısa bir istekle yalnızca cevap düzeltilir, bağlam büyümez. Adım listesinde bir not olarak görünür.
` },
    ] },
    { id: "safety", title: "Güvenlik", icon: "shield", articles: [
      { id: "permissions", title: "İzin modları", summary: "Onay iste, benim için onayla, tam erişim.", md: `
| Mod | Ne sorar |
|---|---|
| **Onay iste** | Dosya yazma, komut ve internet işlemlerinden önce |
| **Benim için onayla** | Yalnızca proje dışı ve riskli işlemleri |
| **Tam erişim** | Hiçbir şey (yıkıcı komutlar hariç) |

- Onay kartında dosya farkı önce görünür: eklenecek satırlar yeşil, silinecekler kırmızı. Reddederseniz dosyaya dokunulmaz.
- \`rm -rf\`, \`format\`, \`os.remove\` gibi yıkıcı komutlar tam erişimde bile onay ister; disk biçimlendirme hiç çalıştırılmaz.
- Model kendi oluşturmadığı dosyaları silmez.
- Komutlar bilgisayarınızda doğrudan çalışır; filtre bir yalıtım (sandbox) değildir. Asıl kontrol onay modudur.
` },
    ] },
    { id: "web", title: "Web ve entegrasyonlar", icon: "globe", articles: [
      { id: "research", title: "Web araştırması nasıl çalışır", summary: "Arama katmanları, birleştirme, arşiv yedeği.", md: `
Model **web_search** (sonuç listesi), **research** (arar ve en iyi kaynakları paralel okur) ve **fetch_url** (tek sayfa okur) araçlarını kullanır.

## Arama sırası
| Sıra | Kaynak | Ne zaman |
|---|---|---|
| 1 | **Anahtarlı API'ler**: Google, Yandex, Bing, Brave, Tavily, SearXNG | Ayarlar > Web'de anahtar girildiyse; yeterli sonuç verirse başka motora sorulmaz |
| 2 | **ddgs kütüphanesi**: Google, Yahoo, Bing, Yandex, Brave arka uçları paralel | API yoksa veya az sonuç verdiyse; ücretsiz, anahtarsız |
| 3 | **Wikipedia ve Wikidata** | Her aramada başvuru kaynağı olarak |
| 4 | **Yerleşik motorlar** (DuckDuckGo, Bing sayfaları) | 2. adımla birlikte |
| 5 | **Arka plan tarayıcısı** (Playwright) | Hepsi yetersiz kalırsa arama sayfasını gerçek tarayıcıda açar |

## Sonuçlar nasıl sıralanır
- Birden çok motorun bulduğu sayfa öne geçer (sıra birleştirme).
- Sorguyla hiçbir anahtar sözcüğü ortak olmayan sonuçlar elenir.
- Konu dışı sonuç ya da doğrulama sayfası döndüren motor bir süre **dinlendirilir**, aramalar yavaşlamaz.
- Aynı arama 10 dakika önbellekte tutulur.

## Sayfa okuma
- JavaScript ile oluşan sayfalar arka plan tarayıcısında açılır. Tarayıcı bir kez başlar, açık kalır, 5 dk boşta kalınca kapanır. Resim ve yazı tipi yüklenmez, bu yüzden hızlıdır.
- Sayfadaki **yapısal veri** (JSON-LD) öne alınır: ürün adı, fiyat, puan, adres, telefon, çalışma saatleri.
- Okunamayan veya kaldırılmış sayfa için **Wayback Machine arşiv kopyası** kullanılır ve tarihi yazılır.
- Bot doğrulaması (CAPTCHA vb.) çözülmeye çalışılmaz; model başka kaynağa geçer ve uydurmaz.
- Güncel bilgi ya da kaynak isteyen bir soruyu model ezberden cevaplarsa (fiyat, haber, hava durumu), cevap bir kez geri çevrilir ve önce araştırma yapması sağlanır.

**Test:** Ayarlar > Web > Aramayı test et her motorun durumunu (çalıştı, sonuç yok, konu dışı, dinleniyor) gösterir.
` },
      { id: "doc-reading", title: "Belge okuma, OCR ve sayfa numaraları", summary: "PDF, Office, OpenDocument, CSV; taranmış sayfalar.", md: `
Model belgeleri **read_document** (bilgisayardaki dosyalar) ve **fetch_url** (web'deki belgeler) ile okur; web araştırması da kaynak olarak bulduğu belgeleri okur.

| Biçim | Alıntı birimi |
|---|---|
| PDF | sayfa (s. 3) |
| Word (.docx), OpenDocument metin (.odt) | paragraf aralığı |
| Excel (.xlsx), OpenDocument tablo (.ods), CSV | sayfa adı ve satır aralığı |
| PowerPoint (.pptx), OpenDocument sunu (.odp) | slayt |
| Metin, Markdown, HTML, JSON | satır aralığı |
| Resim (png, jpg, tiff…) | OCR ile |

- **Taranmış sayfalar** (metin katmanı olmayan) OCR ile okunur: Windows'ta yerleşik Windows OCR (çevrimdışı, sayfa başına ~0,1 sn, Türkçe karakterler korunur), Linux/macOS'ta Tesseract varsa o, yoksa RapidOCR.
- **Uzun belgeler** tamamen dökülmez: bir soru verilirse en uygun pasajlar sayfa numaralarıyla gelir (nadir sözcükler ve sayılar daha ağır basar), \`pages="3-7"\` ile istenen sayfalar okunur, yoksa sayfa sayfa içindekiler listesi gelir.
- Cevaplar alıntıladığı yerin etiketini yazar ([s. 5], [slayt 2]); kaynağı kontrol etmeniz kolaylaşır.
- Web'de engellenen ya da kaldırılmış bir belgenin **tarihli Wayback kopyası** belge olarak okunur.
- Eski ikili Office biçimleri (.doc, .xls, .ppt) için önce .docx/.xlsx/.pptx ya da PDF olarak kaydetmeniz istenir.
` },
      { id: "search-apis", title: "Arama API'lerini kurma", summary: "Google, Yandex, Bing, Brave, Tavily, SearXNG adım adım.", md: `
Hiçbir anahtar şart değil; ücretsiz katman yeterli değilse aşağıdakilerden birini ekleyin. Anahtarlar **Ayarlar > Web**'e girilir ve yalnızca bilgisayarınızda saklanır.

## Brave Search API
1. **api-dashboard.search.brave.com** adresinde hesap açın ve bir plan seçin (ücretsiz katman mevcut).
2. **API Keys**'ten anahtarı kopyalayın (\`BSA…\`) ve **Brave Search API** alanına yapıştırın.

## Tavily
1. **app.tavily.com**'da kaydolun; ücretsiz aylık kredi verir.
2. \`tvly-…\` anahtarını **Tavily API** alanına girin. Yapay zekâ ajanları için özetli sonuç döndürür.

## SearXNG (kendi arama motorunuz)
1. Docker ile çalıştırın: \`docker run -d -p 8888:8080 searxng/searxng\`
2. \`settings.yml\` içinde \`search.formats\` listesine \`json\` ekleyip yeniden başlatın.
3. **SearXNG** alanına \`http://127.0.0.1:8888\` yazın. Sınırsız ve ücretsizdir; onlarca motoru birleştirir.

## Google Programmable Search
1. **programmablesearchengine.google.com**'da bir arama motoru oluşturun ve **Tüm web'de ara**'yı açın; **arama motoru kimliğini (cx)** kopyalayın.
2. Google Cloud'da **Custom Search API**'yi etkinleştirip bir API anahtarı oluşturun (günde 100 sorgu ücretsiz).
3. Anahtarı **Google Programmable Search**, kimliği **Google arama motoru kimliği (cx)** alanına girin.

## Yandex Search API
1. **console.yandex.cloud**'da bir klasör açın ve **Search API**'yi etkinleştirin.
2. Bir servis hesabı ve **API anahtarı** oluşturun (\`search-api.webSearch.user\` rolü).
3. Anahtarı **Yandex Search API**, klasör kimliğini (\`b1g…\`) **Yandex Cloud klasör kimliği** alanına girin. Türkçe sonuçlarda güçlüdür.

## Bing Web Search API
Microsoft 2025'te yeni satışı durdurdu. Elinizde geçerli bir Azure anahtarı varsa **Bing Web Search API** alanına girin; yoksa ddgs zaten Bing sonuçlarını getirir.
` },
      { id: "places", title: "Harita ve mekân araması", summary: "places aracı, OpenStreetMap, Google/Yandex Places, harita sayfası.", md: `
Model **places** aracıyla bir semt, adres ya da koordinat çevresindeki mekânları bulur: kafe, restoran, otel, eczane, market, spor salonu, rakip işletmeler…

## Ne getirir
- Ad, tür, adres, **mesafe**, telefon, web sitesi, çalışma saatleri.
- Google veya Yandex anahtarı varsa ek olarak **puan, yorum sayısı ve fiyat seviyesi**.
- \`map: true\` ile \`maps/…html\` adında **etkileşimli harita sayfası**: solda liste, sağda işaretli harita. Uygulama içi tarayıcıda açılır.

## Sağlayıcılar
| Sağlayıcı | Anahtar | Notlar |
|---|---|---|
| **OpenStreetMap** (Nominatim + Overpass) | Gerekmez | Her zaman açık; Overpass yoğunsa Nominatim'e geçer |
| **Google Places API (New)** | Ayarlar > Web > Harita servisleri | Google Cloud'da Places API (New) etkin olmalı |
| **Yandex Places API** | Aynı yer | developer.tech.yandex.com'dan alınır; Türkiye'de işletme bilgisi zengindir |

## Anlık konum
- "Yakınımdaki eczaneler", "buralarda iyi bir kafe" gibi isteklerde model **my_location** ile konumunuzu alır: uygulama tarayıcının konum servisini kullanır (Windows'ta Wi-Fi/GPS, metre düzeyinde; tarayıcı ilk seferde izin sorar).
- İzin verilmezse ya da konum alınamazsa internet adresinden **yaklaşık** (şehir düzeyi) konum kullanılır ve bu açıkça yazılır.
- Konum birkaç dakika hatırlanır, sokak adresine çevrilir; mesafeler ve yol tarifi bulunduğunuz yerden hesaplanır.

## Harita sayfası
- Solda filtrelenebilir, mesafe / puan / ada göre sıralanabilir **detay kartları**: numara, tür simgesi, puan yıldızları ve yorum sayısı, mesafe, adres, bugünkü çalışma saati, telefon.
- Her kartta **Yol tarifi** (konumunuzdan), **Ara**, **Web** ve **Haritada** düğmeleri; karta tıklayınca harita o yere uçar.
- "Buradasınız" işareti ve doğruluk çemberi, numaralı iğneler, koyu tema ve telefon görünümü.

## Örnek istemler
- *"Yakınımdaki eczaneleri bul, haritada göster."*
- *"Moda, Kadıköy'de 1 km içindeki kahvecileri bul, haritada göster."*
- *"Taksim meydanına en yakın 5 eczaneyi telefonlarıyla listele."*
- *"41.0369,28.9850 çevresinde açık restoranlar."*
` },
      { id: "place-skills", title: "Mekân, karşılaştırma ve pazarlama yetenekleri", summary: "/place-research, /place-compare, /map-market, /catalog, /compare.", md: `
| Yetenek | Ne yapar |
|---|---|
| **/place-research** | Bir konumdaki mekânları bulur, yorum/fiyat araştırır, tablo + harita + öneri verir |
| **/place-compare** | İki veya daha fazla mekânı puan, fiyat, saat, ulaşım ve yorumlarla yan yana karşılaştırır |
| **/map-market** | Bir işletme için konum bazlı pazar ve rakip analizi: rakip yoğunluğu, boşluklar, hedef kitle, SWOT, pazarlama stratejisi ve KPI'lar |
| **/catalog** | Web'den ya da dosyanızdan ürün kataloğu: Excel, Word/PDF veya aramalı/filtreli HTML sayfası |
| **/compare** | Ürün veya hizmet karşılaştırması: tablo, artı/eksi, net öneri |

Yetenek adını yazmanız şart değil; model isteğe uyanı kendisi seçer. @researcher ve @comparer ajanları da harita aracını kullanır.

**Örnekler**
- */map-market Bostancı'da butik kahve dükkânı açmak istiyorum, rakipleri ve fırsatları analiz et, rapor Word olsun.*
- */place-compare Kızılay'daki iki burger dükkânını karşılaştır: X ve Y.*
- */catalog 2026 Audi modellerinin fiyat kataloğunu Excel olarak hazırla.*
` },
      { id: "screenshot", title: "Web ekran görüntüsü", summary: "Masaüstü, tablet, telefon; PNG/JPEG/PDF.", md: `
- Model gerektiğinde bir sayfanın görüntüsünü kendisi alır; + menüsündeki **Web ekran görüntüsü** ile de isteyebilirsiniz.
- Masaüstü, tablet veya telefon görünümü, tam sayfa, tek öğe, koyu tema ve PNG/JPEG/PDF desteklenir.
- Görüntü adım listesinin altında küçük resim olarak çıkar; tıklayınca görüntüleyicide açılır.
` },
      { id: "mcp", title: "MCP sunucuları", summary: "Harici araçları bağlamak.", md: `
- **Ayarlar > MCP**: komut (stdio) ya da HTTP adresiyle bir MCP sunucusu ekleyin.
- Araçları her sohbette modele sunulur; salt okunur araçlar onaysız, diğerleri onayla çalışır.
- Tokenlar gizli anahtar deposunda saklanır.
` },
    ] },
    { id: "voice", title: "Ses", icon: "mic", articles: [
      { id: "speech", title: "Sesli yanıt ve sesli komut", summary: "Okutma, ses seçimi, komutlar.", md: `
## Sesli yanıt
Cevabın altındaki hoparlöre basın veya **Ayarlar > Genel > Sesli yanıt**'tan otomatik okumayı açın. Doğal Microsoft sesleri kadın/erkek etiketiyle listelenir. Emojiler ve semboller okunmaz.

## Sesli komut
Mesaj kutusundaki **dalga** simgesi:

| Söyleyin | Ne olur |
|---|---|
| gönder | Mesajı gönderir |
| durdur | Görevi durdurur |
| onayla / reddet | Bekleyen onayı yanıtlar |
| yeni sohbet, oku, sus | İlgili işlemi yapar |
` },
    ] },
    { id: "help", title: "Sorun giderme", icon: "help", articles: [
      { id: "errors", title: "Hata mesajları", summary: "API hatalarının anlamı ve çözümü.", md: `
| Hata | Anlamı | Ne yapmalı |
|---|---|---|
| Geçersiz anahtar (401) | Anahtar yanlış ya da iptal edilmiş | Ayarlar > Sağlayıcılar'dan yenileyin |
| Kredi / kota bitti (402) | Hesapta bakiye ya da günlük ücretsiz kota kalmamış | Hesabı doldurun veya çoklu modeli açın |
| Hız sınırı (429) | Dakikalık istek/token sınırı | Uygulama bekleyip yeniden dener |
| Model bulunamadı (404) | Model kaldırılmış veya adı değişmiş | Başka model seçin |
| Aşırı yük (503) | Sağlayıcı yoğun | Uygulama yeniden dener |
| Ücretli plan gerekli | Model ücretsiz planda yok | Başka model seçin |
| Şartlar (403) | Kullanım şartları onaylanmamış | Test > Şartları oku ve kabul et |
` },
      { id: "faq", title: "Sık sorulanlar", summary: "Kısa çözümler.", md: `
**Model listesi boş.** Sağlayıcı etkin mi, anahtar kayıtlı mı? Ayarlar > Sağlayıcılar > Test sonucuna bakın.

**Arayüz eski görünüyor.** Güncellemeden sonra tarayıcıda bir kez Ctrl+F5 yapın.

**Model takım kurmadı, işi kendi yaptı.** Çoklu model açık mı ve havuzda araç destekli başka bir model var mı? İsteminizde "takım" ya da "çoklu ajan" deyin.

**"Başka modele soruldu" yazıyor ama takım panosu yok.** Bu bir danışmadır (ask_model); gerçek takım için *Ajan takımı* sayfasına bakın.

**Yerel model çok yavaş.** Ekran kartınız desteklenmiyorsa model CPU'da çalışır; daha küçük bir model veya bulut modeli seçin.
` },
    ] },
  ],
};

const en = {
  title: "Guide",
  intro: "Every feature of AI IQ 300, topic by topic: pick a page on the left or search.",
  search: "Search the guide…",
  results: "{n} results",
  empty: "Nothing found. Try another word.",
  toc: "On this page",
  prev: "Previous",
  next: "Next",
  topics: "Topics",
  cats: [
    { id: "start", icon: "rocket", title: "Getting started", articles: [
      { id: "install", title: "Install and first run", summary: "install.bat, run.bat and the first start.", md: `
## Install
1. Run **install.bat** in the project folder. It installs the Python and Node dependencies (the tokenizer too).
2. Start the app with **run.bat**. It opens at **http://127.0.0.1:8300**.
3. After an update run install.bat once more and press **Ctrl+F5** in the browser.

## Folders
| Folder | Contents |
|---|---|
| \`data/\` | Settings, chat database, secret keys |
| \`workspace/\` | Working area of chats without a project |
| \`chat/<id>-session/\` | Each chat's session record (deleted with the chat) |
| \`skills/\`, \`agents/\` | Skill and agent files |
| \`languages/\` | UI language files (tr.json, en.json…) |

> Keys are kept only in \`data/secrets.json\` and are never sent to the UI in plain text.
` },
      { id: "providers", title: "Adding providers", summary: "Local and cloud model sources, keys, Test.", md: `
## Local models
- **Ollama** and **LM Studio** need no key; their models are listed automatically while they run.
- Switching to a local model unloads the other local models from memory.

## Cloud APIs
1. Open **Settings > Providers** and enable the provider.
2. Enter the API key and press **Test**. It shows the model list, or the reason when something is wrong.
3. Supported: OpenAI, Anthropic, Gemini, OpenRouter, Groq, DeepSeek, Hugging Face, **NVIDIA NIM**, **Cloudflare Workers AI**, EVREN, Ollama Cloud and 20+ more.

## Cloudflare Workers AI
- Besides the API token it needs the **Account ID**: the 32-character hex code at the top right of the Cloudflare dashboard.
- The free plan gives 10,000 neurons a day; when they run out (error 3036) the app waits until midnight UTC. Some models need the paid plan (error 5035): that model is skipped for 24 hours.

## NVIDIA NIM
- Enter the key that starts with \`nvapi-\`; 80+ models are listed. On rate limits the app waits and retries.

## EVREN
- If the first call returns 403, accept the terms with **Test > Read & accept terms**.
` },
      { id: "models", title: "Choosing models and profiles", summary: "Model picker, context size, effort, model profiles.", md: `
## Model picker
Pick the model under the message box. The size chip next to it (e.g. **33K**) is the model's context window; for local models you can change it there.

## Effort
The **Effort** menu (gauge icon) shows the thinking levels the model supports. OpenRouter, OpenAI, Anthropic, Gemini and Ollama use the API's own setting; other models get the level as an instruction.

## Model profiles
**Settings > Models > Model profiles**: per-model thinking, image input, streaming, tool-call format, temperature and maximum output length. **Auto** uses what the provider reports.
` },
      { id: "tour", title: "A tour of the UI", summary: "Sidebar, chat, step list, panels.", md: `
- **Sidebar:** projects, chats, Files, Skills, Agents, Settings, Guide, About.
- **Chat:** the **step group** (thinking, notes, tools) sits above the answer; the to-do list, file cards and the task board below it.
- **Message box:** + menu, permission mode, model picker, context ring, effort, voice commands, microphone and send.
- **Side panels:** code editor, in-app browser, document preview, process panel.
` },
    ] },
    { id: "chat", title: "Chats and projects", icon: "folder", articles: [
      { id: "projects", title: "Projects and chats", summary: "Project folder, pinning, archive.", md: `
- Create a project with **+** in the sidebar; choose a folder on your computer or create a new one. All agent output is written there.
- Chats without a project work in \`workspace/\`.
- **Right-click** chats and projects to pin, rename, archive or delete them.
- **Project rules** in the project menu sets the rules every chat of the project follows (see *Project memory*).
` },
      { id: "files", title: "Files and time machine", summary: "File manager, git snapshots, preview.", md: `
- **Files**: folder tree, type filters, preview, upload, rename and right-click menus.
- Project folders get an automatic **git snapshot** after each run; go back to any point with the **Time machine**.
- The model edits only the changed part of an existing file; open the step to see added lines in green and removed ones in red.
- HTML pages and localhost links open in the **in-app browser** (desktop/tablet/mobile views).
` },
      { id: "attachments", title: "Attachments, drawing and image editing", summary: "Files/folders, drawing pad, drawing on images.", md: `
- **Drag and drop** files and folders anywhere on the chat, or upload them from the + menu.
- **Drawing pad** (+ menu): sketch and send it as an image.
- Click an attached image: pen, line, arrow, rectangle, ellipse, text and eraser. **Apply and attach** replaces it at the original resolution.
` },
      { id: "documents", title: "Documents and preview", summary: "Word, Excel, PDF, PowerPoint.", md: `
- The model creates Word, Excel, PDF and PowerPoint files with the **make_doc** tool.
- Documents appear as **cards** in the chat; click one to preview it inside the app.
- The **/web-to-doc** skill writes web research into an existing Word/Excel/Markdown document.
` },
    ] },
    { id: "agents", title: "Agents and skills", icon: "bot", articles: [
      { id: "roles", title: "Agents (@)", summary: "Built-in roles and switching roles.", md: `
The default assistant adapts to the conversation: it chats when you chat and does the work with tools when you ask for it.

| Agent | Job |
|---|---|
| @coder | Writes and edits code |
| @tester | Tests |
| @debugger | Fixes errors |
| @planner | Makes a plan |
| @researcher | Web research |
| @comparer | Product comparison |
| @writer | Writes articles |
| @prompt-wizard | Builds prompts |
| @skill-maker / @agent-maker | Creates new skills / agents |

When a command fails, the **debugger** role takes over by itself.
` },
      { id: "skills", title: "Skills (/)", summary: "Built-in skills and automatic choice.", md: `
- **/web-research, /web-summary, /web-report, /web-to-doc, /compare, /article, /prompt, /docs, /webapp, /git**.
- Maps and marketing: **/place-research, /place-compare, /map-market, /catalog** (see *Web and integrations*).
- You don't have to type one: the model picks and loads the skill that matches your request. Skills are loaded only when needed.
` },
      { id: "custom", title: "Your own agents and skills", summary: "Create, import, the tools: line.", md: `
- Create new ones on the **Skills** and **Agents** pages, edit them with Monaco, or import them from a file or a GitHub URL.
- Add a **tools:** line and only those tools are sent while it is in use: tool definitions shrink by 60–85% and small models make fewer wrong calls.
- @skill-maker and @agent-maker validate the new file and add it with your approval; use it at once with / or @.
` },
    ] },
    { id: "auto", title: "Autonomous work", icon: "wrench", articles: [
      { id: "tools", title: "Tools", summary: "What the model can use.", md: `
| Tool | What it does |
|---|---|
| write_file / edit_file / read_file | Writes, partly edits, reads files |
| run / start / stop | Runs commands, starts/stops background processes |
| search_code / symbols / impact | Code search, definition map, impact analysis (Tree-sitter) |
| research / web_search / fetch_url | Web research |
| places | Map and place search, interactive map page |
| web_screenshot / browser_check | Page screenshots and visual tests |
| make_doc | Word/Excel/PDF/PPT files |
| todo | Live to-do list |
| ask_model / team | Asking another model, agent teams (see *Multi-model and teams*) |
| remember | Saves a lasting rule |
| mcp | Tools of connected MCP servers |
` },
      { id: "review", title: "Change review card", summary: "Every difference a turn left in the folder.", md: `
Under every task a **N files changed** card appears: **every** file added, modified or deleted in the working folder since the task started.

- Each row says its source: **tool** (write, edit, document) or **command** (a terminal command, script, formatter, \`npm install\`, code generators).
- Click a row for its colored diff; **Expand all diffs** shows them all; the arrow icon opens the file in the editor.
- Binary or very large files show their size change.
- The folder snapshot is taken in the background when the task starts (while the model writes its first reply) and unchanged files come from a cache, so tasks do not slow down. Folders like \`node_modules\`, \`.git\` and \`dist\` are not counted.
` },
      { id: "timing", title: "Timing and performance", summary: "Where a task's time went.", md: `
Every finished task shows its total time in the step header; open it for the split:

| Item | Meaning |
|---|---|
| First reply | From sending the message to the model's first thought, text or tool call |
| Model | All model turns; *waiting for first token* is the time the provider took before it started answering |
| Tools | Per tool (run, write_file, research…), with the number of calls |
| Team | The agent team's total time |
| Side calls | Summaries, language fixes, compression |
| App | The rest: the app's own work |

Percentiles of recent tasks (p50 / p95 / max) are at \`/api/perf\`, a short summary in \`/api/health\`. So you can see whether a slowdown is in the model, a tool or the team.
` },
      { id: "steps", title: "Steps, notes and to-dos", summary: "How to read the step group.", md: `
- Everything that happens in the background is grouped in the **step group** above the answer; while a task runs only the current step shows, and a click opens them all.
- **Thinking**: the model's reasoning. **Note**: a short remark the model writes between tools; it is not the answer and is shown dimmed.
- Multi-step work opens a live **to-do** list that is ticked off as it goes.
- A model that announces the next step and stops is made to continue; resume an interrupted task with **continue**.
- **Goal mode** (+ menu) works on its own until the goal is reached; **Plan mode** makes a plan first.
` },
      { id: "commands", title: "Commands and system version", summary: "System inventory, shells, argv, scripts, heredocs.", md: `
Commands run directly on your computer, with no isolation, like Codex and Claude Code. To make them fast and correct, the model knows the machine.

## System inventory
At start (once, in the background, in about half a second) the app detects and gives the model:
- The OS, its release and build number (e.g. *Windows 10 Pro 22H2, build 19045*) and CPU architecture
- The shells and their versions: Windows PowerShell 5.1, PowerShell 7, cmd, Git Bash
- Installed tools and versions: git, Node, npm, Python, PHP, Java, .NET, Docker, winget/brew…

A tool that is not listed is not installed; the model checks first or gives the install command.

## Choosing the shell
| Shell | When |
|---|---|
| \`argv=["git","status"]\` | One program with plain arguments: no shell, no quoting problems, fastest |
| \`powershell\` | PowerShell 7 when installed, else 5.1 |
| \`powershell5\` / \`pwsh\` | A specific PowerShell version |
| \`cmd\` | Batch files and cmd commands |
| \`bash\` | Git Bash on Windows (not WSL), bash on Linux/macOS |
| \`python\` / \`node\` | Multi-line scripts: the source is written to a script file and run |

## Windows PowerShell 5.1 compatibility
- \`&&\` and \`||\` do not exist in 5.1; the app translates them with their left-to-right meaning.
- Habits like \`rm -rf\`, \`mkdir -p a b\`, \`ls -la\`, \`del /s /q\` and \`touch\` are handled only when written that way. Native use (\`ls -Filter *.txt\`, \`Remove-Item -Recurse\`, \`dir | Where-Object …\`) goes to the real cmdlet unchanged; its meaning never changes.
- A failing command returns its real exit code.

## Heredocs and multi-line content
- A bash heredoc such as \`cat > file <<'EOF'\` sent to PowerShell runs in Git Bash. Without Git Bash it becomes a file write or piped input.
- An indented closing mark of a PowerShell here-string (\`    '@\`) is fixed automatically.
- File contents are always written with write_file, never with commands.

## Background processes
- \`start\` (e.g. \`npm run dev\`) returns as soon as the server prints its ready line (e.g. *Local: http://localhost:5173*); it used to wait a fixed 6 s.
- Background servers do not take the slots of normal commands; even with 9 servers running, commands start at once.

## Version-aware command skill
\`/host-commands\` (also picked automatically): when the model is not sure a flag or cmdlet exists in this version, it checks the local help first (\`--help\`, \`Get-Help\`, \`man\`), then the official docs of that exact version (Microsoft Learn, git-scm.com, docs.python.org, nodejs.org…). For older releases it opens that release's documentation. It verifies the result and writes a diagnosis when a failure repeats.
` },
    ] },
    { id: "multi", title: "Multi-model and teams", icon: "users", articles: [
      { id: "multi-overview", title: "Overview", summary: "One model, asking another model, agent teams: the differences.", md: `
In AI IQ 300 several models work together in three ways:

| Way | When | Who does it | Uses tools? |
|---|---|---|---|
| **Automatic model switch** | A quota or rate limit runs out | The most available pool model continues where it stopped | Yes |
| **Asking another model** (\`ask_model\`) | A review, analysis or second opinion | One model picked from the pool | No, text only |
| **Agent team** (\`team\`) | You ask for a "team", "group", "several agents", or a big job | Each member is a real agent on its own model | Yes: files, commands, documents, web |

All of them need a **multi-model pool** first (see *Setting up the pool*). Local models never join the pool.
` },
      { id: "pool", title: "Setting up the pool", summary: "Settings > Multi-model, tags, per-agent models.", md: `
1. Open **Settings > Multi-model** and turn it **on**.
2. Add cloud models to the **pool**. Give each a capability tag: \`code\`, \`reasoning\`, \`fast\`, \`writing\`, \`vision\`, \`long_context\`.
3. **Auto switch**: when a quota runs out the task continues on the most available model. **Delegation**: the model may hand parts of the work to others (ask_model and team need it).
4. **Per-agent models**: e.g. one model for @coder and another for @tester.
5. The **Quotas** section shows each provider's last 5 hours and week of usage; with a limit set, a provider is skipped once it is used up.

> Team members use models with **native tool calling**. Models without it (e.g. EVREN \`auto\`) never become members, but can be the main model or answer ask_model.
` },
      { id: "ask-model", title: "Asking another model (ask_model)", summary: "Handing one sub-task to another model.", md: `
Instead of doing everything itself, the model can hand a sub-task to another pool model: a code review, an analysis, a long text, a second opinion.

- The **most available model** for the capability (\`need\`) is chosen (quota, rate limit, context).
- If it is busy the next one is tried (up to 3 attempts).
- The other model returns **text only**: it cannot write files or run commands. So this is a **consultation**, not teamwork.
- It shows in the step list as **Asked another model · model-name**.

**Example:** *"Read index.html and have another model review it for accessibility."*
` },
      { id: "team", title: "Agent team (parallel)", summary: "Running independent parts at once on different models.", md: `
The model splits a big job into parts; each part is done by **its own agent** on **a different pool model**, all at the same time.

## How it works
1. The main model calls the \`team\` tool with each member's **title**, **task** and **capability** (code, reasoning, fast, writing).
2. Each member gets a different model; with a small pool a model is shared.
3. Members read/write files in the same folder, run commands, create documents and use the web.
4. When a model fails (quota, rate limit) the member switches to another one.
5. The main model gets every member's **report, files and model** back and sums them up for you.

## Task board
A live **Agent team** board opens in the chat. Each card shows:
- the member's name and state (queued, running, done, error)
- the **model** it runs on
- its step count and last action
- the files it changed, and its **report** on click

The shared **task list** and the **messages** between members are shown below.

**Example:** *"Form a team: one writes the Flask API (api/app.py), one the HTML UI (web/index.html), one the README."*
` },
      { id: "pipeline", title: "Staged team (a pipeline)", summary: "Chains where team 2 uses team 1's output.", md: `
Some jobs depend on each other: team 2 needs what team 1 made. For that, members get a **stage**.

- Members of the same stage run **at the same time**.
- A stage starts when the earlier ones are **finished**.
- A later member automatically gets the earlier stages' **reports, models and file names**, and reads the files when it needs them.
- On the task board every card starts with a **Stage 1, Stage 2…** label.
- Even when the model forgets the stages, parts whose task builds on an earlier one ("analyze the page team 1 wrote") are run in order automatically.

## Example: HTML → analysis → Word
Prompt: *"Do a team job with several models and agents: team 1 writes a simple HTML page, team 2 analyzes that code, team 3 writes the analysis into a Word document."*

| Stage | Member | Model (example) | Output |
|---|---|---|---|
| 1 | HTML coding | nvidia:nemotron… | output/1_team/index.html |
| 2 | Code analysis | groq:gpt-oss-120b | analysis report |
| 3 | Word report | cloudflare:glm-4.7-flash | output/3_team/HTML_Analysis_Report.docx |

Three members run on three different models, each with its own tools. The main model only forms the team and sums up the result.

> Tip: just say "team", "group" or "several agents" in your prompt; the model sets the stages. For a fixed order write "first…, then…".
` },
      { id: "team-chat", title: "Team messages", summary: "Messages between members and the shared task list.", md: `
- **team_message**: a member sends a message to one teammate (by name) or to all, e.g. an API address, a file name or a finished part.
- Messages reach the receiver together with its next tool result.
- **team_tasks**: the shared task list. Members **add**, **claim** (never someone else's) and **finish** tasks.
- The board shows messages as *sender → receiver* and the tasks with their state, live.
` },
      { id: "verify", title: "Which model did what?", summary: "Checking a team's result.", md: `
- The **task board** shows each member's model; the team step in the step list shows the same on click.
- The main model must name the models as the tool results list them, and cannot present its own work as teamwork.
- In later messages the model still knows which agent ran on which model in an earlier turn; just ask "which team used which model?".
- An **Asked another model** step is a **consultation**, not a team: that model creates no files.
` },
      { id: "quota", title: "Quotas, rate limits and auto switch", summary: "What happens when a limit is hit?", md: `
| Situation | What the app does |
|---|---|
| Rate limit (429) | Waits as long as the provider asks (up to 2 min) and retries |
| Overload (503), network error, timeout | Retries after 5, 15, 30, 60, 90 s |
| Cloud model silent for 3 min | Cuts the request and retries |
| Quota used up / no credit (402) | With multi-model on, continues **where it stopped** on the most available pool model |
| Context exceeded | Trims or summarizes old content and retries |
| Paid plan required | Skips the model for 24 hours |

Every error message is shown in the active language.
` },
    ] },
    { id: "context", title: "Context and memory", icon: "gauge", articles: [
      { id: "ring", title: "Context ring and token counting", summary: "Real token counts, live meter.", md: `
- The **ring** in the message box shows how full the context is; click it to see each category (system, tools, skills, project, messages), outputs and background tasks.
- Counting uses a bundled **tokenizer** and the provider's own count; tool definitions are counted, hidden reasoning tokens are not.
- The meter moves **live** while the model thinks and writes.
` },
      { id: "compress", title: "Compression", summary: "Threshold, in-task summaries, manual compression.", md: `
- At the threshold (default **80%**) old messages are summarized automatically; use **Compress now** to do it by hand.
- In long tasks old file bodies are trimmed first, then steps are summarized if needed.
- The summary ends with an **exact list of the tool calls already made**, so the model does not repeat steps or claim things it did not do.
` },
      { id: "memory", title: "Project memory and rules", summary: "AIIQ.md, global rules, remember this.", md: `
- **Project rules** (project menu) are written to \`AIIQ.md\` at the project root and added to every chat of the project.
- **Settings > General > Global rules** are added to all chats.
- Say **"remember this"** in a chat and the model saves the rule itself.
` },
      { id: "language", title: "Language", summary: "Active language, words in other languages.", md: `
- The active language applies everywhere: thinking, plans, notes, team reports and the answer are written in it.
- When a reply contains words in another language (e.g. a Chinese word), the model does not think again. Only the reply is fixed by a short request, so the context does not grow. It shows as a note in the step list.
` },
    ] },
    { id: "safety", title: "Safety", icon: "shield", articles: [
      { id: "permissions", title: "Permission modes", summary: "Ask, approve for me, full access.", md: `
| Mode | What it asks about |
|---|---|
| **Ask for approval** | File writes, commands and internet actions |
| **Approve for me** | Only actions outside the project and risky ones |
| **Full access** | Nothing (except destructive commands) |

- The approval card shows the diff first: lines to add in green, to remove in red. Deny and the file is untouched.
- Destructive commands such as \`rm -rf\`, \`format\` or \`os.remove\` always ask, even in full access; disk formatting never runs.
- The model never deletes files it did not create.
- Commands run directly on your computer; the filter is not a sandbox. The approval mode is the real control.
` },
    ] },
    { id: "web", title: "Web and integrations", icon: "globe", articles: [
      { id: "research", title: "How web research works", summary: "Search layers, fusion, archive fallback.", md: `
The model uses **web_search** (a result list), **research** (searches and reads the best sources in parallel) and **fetch_url** (reads one page).

## Search order
| Step | Source | When |
|---|---|---|
| 1 | **APIs with a key**: Google, Yandex, Bing, Brave, Tavily, SearXNG | When a key is set in Settings > Web; if they find enough, nothing else is asked |
| 2 | **ddgs library**: Google, Yahoo, Bing, Yandex, Brave backends in parallel | No API, or too few results; free, no key |
| 3 | **Wikipedia and Wikidata** | In every search, as reference sources |
| 4 | **Built-in engines** (DuckDuckGo, Bing pages) | Together with step 2 |
| 5 | **Background browser** (Playwright) | When all of these find too little, it opens the search page in a real browser |

## How results are ranked
- A page that several engines found ranks higher (rank fusion).
- Results that share no keyword with the query are dropped.
- An engine that returns off-topic results or a check page is **rested** for a while, so searches stay fast.
- The same search is cached for 10 minutes.

## Reading pages
- Pages built with JavaScript open in the background browser. It starts once, stays open and closes after 5 idle minutes. Images and fonts are not loaded, so it is fast.
- **Structured data** on the page (JSON-LD) comes first: product names, prices, ratings, addresses, phones, opening hours.
- A page that cannot be read or was removed is taken from its **Wayback Machine archived copy**, with the date.
- Bot checks (CAPTCHAs etc.) are never solved; the model moves to other sources instead of guessing.
- When the model answers a question about current facts or sources (prices, news, weather) from memory, the answer is sent back once and it researches first.

**Test:** Settings > Web > Test search shows each engine's state (ok, no results, off-topic, resting).
` },
      { id: "doc-reading", title: "Reading documents, OCR and page numbers", summary: "PDF, Office, OpenDocument, CSV; scanned pages.", md: `
The model reads documents with **read_document** (files on the computer) and **fetch_url** (documents on the web); web research reads the documents it finds as sources too.

| Format | Quote unit |
|---|---|
| PDF | page (p. 3) |
| Word (.docx), OpenDocument text (.odt) | paragraph range |
| Excel (.xlsx), OpenDocument sheet (.ods), CSV | sheet name and row range |
| PowerPoint (.pptx), OpenDocument presentation (.odp) | slide |
| Text, Markdown, HTML, JSON | line range |
| Images (png, jpg, tiff…) | by OCR |

- **Scanned pages** (no text layer) are OCR'd: Windows' built-in OCR on Windows (offline, ~0.1 s per page, keeps Turkish and other diacritics); on Linux/macOS Tesseract when installed, else RapidOCR.
- **Long documents** are not dumped whole: with a question you get the best passages with their page numbers (rare words and numbers weigh more), \`pages="3-7"\` reads those pages, otherwise a page-by-page outline comes back.
- Answers quote the label of the place they used ([p. 5], [slide 2]), so you can check the source easily.
- A web document that is blocked or removed is read from its **dated Wayback copy**, as a document.
- Old binary Office formats (.doc, .xls, .ppt) must be saved as .docx/.xlsx/.pptx or PDF first.
` },
      { id: "search-apis", title: "Setting up search APIs", summary: "Google, Yandex, Bing, Brave, Tavily, SearXNG step by step.", md: `
No key is required; if the free layer is not enough, add one of these. Keys go in **Settings > Web** and stay on your computer.

## Brave Search API
1. Sign up at **api-dashboard.search.brave.com** and pick a plan (a free tier exists).
2. Copy the key (\`BSA…\`) from **API Keys** into the **Brave Search API** field.

## Tavily
1. Sign up at **app.tavily.com**; it gives free monthly credits.
2. Enter the \`tvly-…\` key in the **Tavily API** field. It returns summarized results built for AI agents.

## SearXNG (your own search engine)
1. Run it with Docker: \`docker run -d -p 8888:8080 searxng/searxng\`
2. Add \`json\` to \`search.formats\` in \`settings.yml\` and restart it.
3. Enter \`http://127.0.0.1:8888\` in the **SearXNG** field. Unlimited and free; it merges dozens of engines.

## Google Programmable Search
1. Create a search engine at **programmablesearchengine.google.com**, turn on **Search the entire web** and copy the **search engine ID (cx)**.
2. Enable the **Custom Search API** in Google Cloud and create an API key (100 queries a day free).
3. Enter the key in **Google Programmable Search** and the ID in **Google search engine ID (cx)**.

## Yandex Search API
1. Open a folder at **console.yandex.cloud** and enable the **Search API**.
2. Create a service account and an **API key** (role \`search-api.webSearch.user\`).
3. Enter the key in **Yandex Search API** and the folder ID (\`b1g…\`) in **Yandex Cloud folder ID**. Strong for Turkish and Russian results.

## Bing Web Search API
Microsoft stopped selling it in 2025. If you still have a valid Azure key, enter it in **Bing Web Search API**; otherwise ddgs already brings Bing results.
` },
      { id: "places", title: "Maps and place search", summary: "The places tool, OpenStreetMap, Google/Yandex Places, map pages.", md: `
With the **places** tool the model finds venues around a district, address or coordinates: cafes, restaurants, hotels, pharmacies, shops, gyms, competing businesses…

## What it returns
- Name, kind, address, **distance**, phone, website, opening hours.
- With a Google or Yandex key also **rating, review count and price level**.
- With \`map: true\` an **interactive map page** \`maps/…html\`: a list on the left, a marked map on the right. It opens in the in-app browser.

## Providers
| Provider | Key | Notes |
|---|---|---|
| **OpenStreetMap** (Nominatim + Overpass) | None | Always on; falls back to Nominatim when Overpass is busy |
| **Google Places API (New)** | Settings > Web > Map services | Enable Places API (New) in Google Cloud |
| **Yandex Places API** | Same place | From developer.tech.yandex.com; rich business data in Türkiye |

## Current location
- For requests like "pharmacies near me" or "a good cafe around here" the model gets your position with **my_location**: the app uses the browser's location service (Wi-Fi/GPS on Windows, metre level; the browser asks for permission once).
- If permission is refused or no position is available, an **approximate** (city-level) location from the internet address is used, and the answer says so.
- The position is remembered for a few minutes and turned into a street address; distances and directions start where you are.

## The map page
- On the left, **detail cards** you can filter and sort by distance, rating or name: number, type icon, rating stars and review count, distance, address, today's opening hours, phone.
- Every card has **Directions** (from your position), **Call**, **Website** and **On map** buttons; clicking a card flies the map to it.
- A "you are here" marker with its accuracy circle, numbered pins, dark mode and a phone layout.

## Example prompts
- *"Find pharmacies near me and show them on a map."*
- *"Find coffee shops within 1 km of Moda, Kadıköy and show them on a map."*
- *"List the 5 pharmacies closest to Taksim Square with their phone numbers."*
- *"Restaurants open around 41.0369,28.9850."*
` },
      { id: "place-skills", title: "Place, comparison and marketing skills", summary: "/place-research, /place-compare, /map-market, /catalog, /compare.", md: `
| Skill | What it does |
|---|---|
| **/place-research** | Finds places at a location, researches reviews and prices, gives a table, a map and a recommendation |
| **/place-compare** | Compares two or more places side by side: rating, prices, hours, access and reviews |
| **/map-market** | Location-based market and competitor analysis for a business: competitor density, gaps, audience, SWOT, marketing strategy and KPIs |
| **/catalog** | A product catalog from the web or your file: Excel, Word/PDF, or an HTML page with search and filters |
| **/compare** | Product or service comparison: table, pros and cons, a clear recommendation |

You don't have to type the skill; the model picks the one that fits. The @researcher and @comparer agents use the map tool too.

**Examples**
- */map-market I want to open a specialty coffee shop in Bostancı; analyze competitors and opportunities, report as Word.*
- */place-compare Compare two burger places in Kızılay: X and Y.*
- */catalog Prepare a price catalog of the 2026 Audi models as Excel.*
` },
      { id: "screenshot", title: "Web screenshots", summary: "Desktop, tablet, phone; PNG/JPEG/PDF.", md: `
- The model takes a page screenshot on its own when it helps; you can also ask with **Web screenshot** in the + menu.
- Desktop, tablet or phone view, full page, one element, dark mode and PNG/JPEG/PDF are supported.
- The image shows as a thumbnail under the step list and opens in the viewer on click.
` },
      { id: "mcp", title: "MCP servers", summary: "Connecting external tools.", md: `
- **Settings > MCP**: add an MCP server by command (stdio) or HTTP address.
- Its tools are offered in every chat; read-only tools run without asking, the others ask.
- Tokens are kept in the secret store.
` },
    ] },
    { id: "voice", title: "Voice", icon: "mic", articles: [
      { id: "speech", title: "Spoken replies and voice commands", summary: "Reading aloud, voices, commands.", md: `
## Spoken replies
Press the speaker under an answer, or turn on automatic reading in **Settings > General > Spoken replies**. Natural Microsoft voices are listed with a female/male label. Emoji and symbols are not read.

## Voice commands
The **wave** icon in the message box:

| Say | What happens |
|---|---|
| send | Sends the message |
| stop | Stops the task |
| approve / deny | Answers a waiting approval |
| new chat, read, quiet | Does that |
` },
    ] },
    { id: "help", title: "Troubleshooting", icon: "help", articles: [
      { id: "errors", title: "Error messages", summary: "What API errors mean and what to do.", md: `
| Error | Meaning | What to do |
|---|---|---|
| Invalid key (401) | The key is wrong or revoked | Renew it in Settings > Providers |
| Credit / quota used up (402) | No balance or daily free quota left | Top up, or turn on multi-model |
| Rate limit (429) | Per-minute request/token limit | The app waits and retries |
| Model not found (404) | The model was removed or renamed | Pick another model |
| Overloaded (503) | The provider is busy | The app retries |
| Paid plan required | The model is not on the free plan | Pick another model |
| Terms (403) | Terms of use not accepted | Test > Read & accept terms |
` },
      { id: "faq", title: "FAQ", summary: "Quick fixes.", md: `
**The model list is empty.** Is the provider enabled and the key saved? Check Settings > Providers > Test.

**The UI looks outdated.** Press Ctrl+F5 once after an update.

**The model did the work itself instead of forming a team.** Is multi-model on, with another tool-capable model in the pool? Say "team" or "several agents" in your prompt.

**It says "Asked another model" but there is no task board.** That is a consultation (ask_model); for real teamwork see *Agent team*.

**A local model is very slow.** If your graphics card is not supported the model runs on the CPU; pick a smaller model or a cloud model.
` },
    ] },
  ],
};

export const GUIDE = { tr, en };
export const guideFor = (lang) => GUIDE[lang] || GUIDE.en;
