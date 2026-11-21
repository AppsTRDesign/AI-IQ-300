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
1. Proje klasöründe **install.bat** dosyasını çalıştırın. Python ve Node bağımlılıkları (tokenizer dahil) kurulur; her adım, ilerleme çubuğu, geçen ve kalan süre ekranda görünür, ayrıntılı kayıt \`data/logs\` klasörüne yazılır. Türkçe Windows'ta Türkçe, diğerlerinde İngilizce konuşur.
2. **run.bat** ile uygulamayı başlatın. Tarayıcıda **http://127.0.0.1:8300** açılır. Pencerede okunaklı, renkli bir kayıt akar; sık yoklamalar gizlidir (\`run.bat --verbose\` hepsini gösterir, \`run.bat 8400\` başka port).
3. Güncellemeden sonra install.bat'ı bir kez daha çalıştırın ve tarayıcıda **Ctrl+F5** yapın.

## Klasörler
| Klasör | İçerik |
|---|---|
| \`data/\` | Ayarlar, sohbet veritabanı, gizli anahtarlar |
| \`chat/<id>/\` | Projesiz her sohbetin klasörü: dosyaları, indirilenler, üretilen her şey (sohbet silinince silinir) |
| \`chat/<id>/.session/\` | O sohbetin gizli oturum kaydı: mesajlar, özetler, betikler |
| \`chat/projects/\` | Klasör seçilmeden oluşturulan projeler |
| \`skills/\`, \`agents/\` | Yetenek ve ajan dosyaları |
| \`languages/\` | Arayüz dil dosyaları (tr.json, en.json…) |

> Anahtarlar yalnızca \`data/secrets.json\` içinde tutulur ve arayüze hiçbir zaman açık olarak gönderilmez.
` },
      { id: "providers", title: "Sağlayıcı ekleme", summary: "Yerel ve bulut model kaynakları, anahtarlar, Test.", md: `
## Yerel modeller
- **Ollama** ve **LM Studio** anahtar istemez; uygulama açıkken modeller otomatik listelenir.
- Yerel bir modele geçildiğinde diğer yerel modeller bellekten boşaltılır.

## Bellek koruması (RAM / VRAM)
- Yüklemeden önce: modelin ağırlıkları ve bağlam penceresi boş belleğe sığmıyorsa pencere sığacak boyuta indirilir; ağırlıklar tek başına sığmıyorsa model yüklenmez.
- Çalışırken boş bellek azalırsa sırayla: uygulamanın kendi önbellekleri boşaltılır, kullanılmayan modeller bellekten çıkarılır, sonra çalışan modelin bağlam penceresi küçültülür (ör. 16K → 8K).
- **Çalışan model kapatılmaz** ve sohbet hafızası silinmez: mesajlar, özet ve görev ilerlemesi uygulamada tutulur; görev küçük pencerede kaldığı yerden sürer.
- Ekran kartı olan bilgisayarlarda VRAM de izlenir (NVIDIA, AMD, Intel; Windows ve Linux). Eşikler bilgisayarın toplam belleğine göre kendiliğinden ayarlanır.
- Ayarlar > Güvenlik > "Yerel model belleği" bölümünden korumayı kapatabilir ya da "acil durumda modeli çıkar" seçeneğini açabilirsiniz (varsayılan kapalı).

## İlk istem boyutu
- Yavaş modeller (CPU'da yerel modeller, yoğun ücretsiz bulut modelleri) görevin ilk isteğindeki kuralları ve araç tanımlarını okurken bekletir. **Yalın istem** aynı bilgiyi yaklaşık yarı token ile verir: kısa kurallar, tek paragraflık yetenek dizini, kısa araç tanımları.
- Model yeteneklerini bu dizinden bilir; gereken araç grubunu \`need_tools\`, beceriyi \`use_skill\` ile kendisi açar. Bir sohbette açılan gruplar o sohbetin sonraki görevlerinde açık kalır.
- Ayarlar > Güvenlik > "İlk istem boyutu": Otomatik (yerel, küçük pencereli ve yavaş ölçülen modellerde yalın), Yalın ya da Tam.

## Bulut API'leri
1. **Ayarlar > Sağlayıcılar**'ı açın, sağlayıcıyı etkinleştirin.
2. API anahtarını girin ve **Test**'e basın. Test model listesini ve hata varsa nedenini gösterir.
3. Desteklenenler: OpenAI, Anthropic, Gemini, OpenRouter, Groq, DeepSeek, Hugging Face, **NVIDIA NIM**, **Cloudflare Workers AI**, EVREN, Ollama Cloud ve 20'den fazlası.

## İnternet kesilirse
- Uygulama internet bağlantısını arka planda izler. Bağlantı gidince **"İnternet bağlantısı kesildi"**, gelince **"geri geldi (N sn kesik kaldı)"** bildirimi çıkar.
- Bulut modelle çalışan bir görev yarıda **bitmez**: duraklar, sohbette "İnternet yok — bağlantı bekleniyor" kutusu geçen süreyle görünür. Bağlantı gelince **aynı model**, aynı konuşma ve yapılacaklar listesiyle kaldığı yerden kendiliğinden devam eder; yarım yazılan dosya korunur. Kesinti kotadan deneme harcamaz ve başka modele geçilmez, yani model hiçbir şeyi unutmaz.
- İnternet isteyen araçlar (web araması, sayfa okuma, görsel üretimi…) da bağlantıyı bekler; localhost sayfaları ve yerel modeller kesintiden etkilenmez.
- Bekleme süre sınırı yoktur; isterseniz görevi durdurabilirsiniz. Uygulama kapanırsa görev "yarıda kaldı" olarak işaretlenir ve devam ettirilebilir.

## Akış susarsa (bağlantı denetimi)
- Model cevap yazarken akış 20 sn susarsa uygulama aynı modele küçük, ayrı bir istek gönderir. "Hazırlanıyor" adımında sonucu görünür.
- **Sağlayıcı hemen yanıt veriyor ama akış hâlâ susuyorsa** akış kopmuştur: kesme süresi akışın kendi temposuna göre ayarlanır (en az 90 sn; parça parça gönderen Evren gibi sağlayıcılarda daha uzun), sunucu bağlantıyı canlı tutma sinyalleriyle açık tutuyorsa hiç kesilmez. Yazılan kısım korunur ve model kaldığı yerden sürer.
- Kısa sessizlikler (5-12 sn'lik normal parça araları) artık "veri gelmiyor" uyarısı vermez ve canlı düşünce akışını kapatmaz.
- **Sağlayıcı yavaşsa** model hâlâ çalışıyordur, beklenir. **Hiç ulaşılamıyorsa** internet kontrol edilir; kesikse bağlantı beklenir.

## Belge şablonları ve mod çipleri
- (+) menüsünde Görsel üret, Tanıtım videosu, AI klip, Resimden video, Word, PDF, Excel ve PowerPoint seçilince mesaj kutusuna renkli bir **çip** eklenir; ne istediğinizi çipin yanına yazarsınız. Çip × ile ya da boş kutuda Backspace ile kalkar.
- Belge çiplerinde o formata özel **şablon galerisi** açılır (gerçek önizlemeler). Bir şablon seçilince renkleri, yazı tipi, kapağı ve bölüm düzeni belgeye uygulanır.
- **Şablon oluştur** Şablon Oluşturucu'yu başlatır: model önce şablonları anlatır, sizden bir referans dosyası (PDF, Word, PowerPoint veya görsel) ister; dosyanın renk paletini, yazı tiplerini, başlıklarını ve kapak düzenini tek adımda çıkarıp yeni şablonu kaydeder. Galeride görünür, kendi şablonlarınız silinebilir.
- 35 hazır şablon ve 8 sayfa düzeni vardır: kapaklı rapor, antetli resmî yazı, not, akademik, dergi, fatura/teklif, özgeçmiş, minimal (faaliyet raporu, vaka çalışması, teknik makale, fiyat teklifi, prosedür, iş planı, satış hunisi, stok takibi, ürün lansmanı...). Kapak stilleri: hero, bant, minimal, koyu, fotoğraf, split, editoryal, köşe; numaralı / alt çizgili / büyük harfli başlıklar ve dolu / çizgili / yumuşak tablolar.
- Gönderilen mesajda mod ve şablon, mesaj kutusundaki gibi **çip** olarak görünür.
- Galerideki oklar uçlarda pasifleşir; **Tümünü gör** kartı formatın tüm şablonlarını bir pencerede açar (aşağı kaydırdıkça devamı yüklenir). Şablon yalnızca tasarımdır: başlık, bölümler ve antet satırları belgenin kendi içeriğinden gelir.
- **Resimden video** sohbetin çalışma klasöründeki resimleri ve mesaja eklenenleri gösterir; yeni resim de yüklenebilir.

## Sesler (yerel ve çevrimiçi)
- **Ayarlar > Sesler**: her dil için varsayılan ses, ton (hız, perde, duygu, cümle arası duraklama), stüdyo işlemesi ve motor sırası. Sesli yanıtlar, yazıyı sese çevirme, video seslendirme ve Video Stüdyo aynı ayarları kullanır.
- **Yerel motorlar (internetsiz):** Piper (hızlı, 50+ dil; Türkçe: Fettah kadın, Eren / Dfki / Fahrettin erkek), Kokoro (çok doğal İngilizce + 5 dil), Chatterbox (en doğal ve duygulu, 23 dil, kendi sesiniz; ayrı ortama kurulur, ~4 GB, işlemcide yavaş). Microsoft'un çevrimiçi sesleri yedektir.
- Sesler ilk dinlemede ya da seçildiğinde indirilir (data/tts). Cinsiyet bilgisi olmayan seslerin kadın/erkek etiketi, sesin perdesi ölçülerek otomatik belirlenir.
- **Stüdyo:** Doğal, Podcast, Yayın (-23 LUFS), Video (-14 LUFS), Sıcak anlatım veya Ham. EQ, de-esser, sıkıştırma ve ses düzeyi standardı tek geçişte uygulanır; isteğe bağlı oda yankısı.
- **Yedek sırası:** motorlar aynı anda çalışmaz. Seçilen ses başarısız olursa aynı dil ve cinsiyetteki sonraki ses kullanılır; kapalı motorlar hiç kullanılmaz.
- **Diyalog:** "Ayşe: ..." / "Can: ..." satırları farklı seslerle okunur (kadın/erkek otomatik ya da konuşmacı başına ses).
- **Video:** seslendirme altında müzik otomatik kısılır; "Altyazı ekle" seçilirse cümleler gerçek zamanlamalarıyla videoya yazılır ve yanına .srt kaydedilir.
- **Kendi sesiniz (Chatterbox):** 5–30 saniyelik kayıt; yalnızca kendi sesiniz ya da izinli bir ses için.

## Kapatılan modeller
- Bir sağlayıcı modeli yeni kullanıcılara kapattığında ("no longer available"), uygulama modeli listeden gizler ve sağlayıcının önerdiği yeni modele kendiliğinden geçer; etkin model de güncellenir.
- Gömme (embedding), ses, koruma (guard) ve yalnızca görsel üreten modeller sohbet model listesinde gösterilmez.

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
- Projesiz her sohbet kendi klasöründe çalışır (\`chat/<sohbet kimliği>/\`); sohbetler birbirinin dosyalarını görmez. Yeni sohbetin klasörü ilk mesajla oluşur.
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
      { id: "testing", title: "Projeyi localhost'ta ve mobilde test etme", summary: "localhost-project ve mobile-app-test yetenekleri, mobile_env.", md: `
**Web projeleri (PHP, ASP.NET, Node, Python, Ruby, Java, Go, Rust, statik, Docker Compose):** "şu projeyi localhost'ta kur ve test et" deyin; **localhost-project** yeteneği kendiliğinden yüklenir:
1. Depoyu bulur ya da sizinkini alır (ZIP tek adımda indirilir, git şart değil), yığını tanır.
2. Eksik çalışma ortamını ve paketleri kurar; veritabanında önce SQLite. Veritabanı sunucusu, XAMPP, Docker gibi büyük kurulumlar için önce size sorar.
3. Python paketleri her zaman doğru ortama gider: uygulamanın kendi \`.venv\`'i, ya da proje kendi venv'ini kullanıyorsa o venv (önce içinde ne kurulu olduğu sorgulanır).
4. Sunucuyu başlatır (port doluysa kendi eski sunucusunu kapatır ya da boş port seçer), sayfaları, formları, girişleri gerçek tarayıcıda dener; projenin kendi testlerini çalıştırır, rapor yazar.

**Mobil uygulamalar (Android, iOS, Flutter, React Native, Expo, Capacitor):** **mobile-app-test** yeteneği:
- Hızlı yol: web derlemesi tarayıcıda telefon boyutunda test edilir.
- Tam yol: \`mobile_env\` aracı Android emülatörünü (Windows, macOS, Linux) kurar ve başlatır, APK'yı yükler, ekran görüntüsü alır, **Maestro** UI akışlarını çalıştırır. iOS simülatörü yalnızca macOS + Xcode'da.
- Kurulum: \`install.bat\` / \`install.sh\` başta sorar (\`AIIQ_MOBILE=1\` sormadan kurar) ve bilgisayarda zaten olanı gösterir: Android Studio'nun SDK'sı, JDK'sı veya daha önce kurulmuş araçlar yeniden indirilmez, sadece eksikler eklenir ve eskiler güncellenir (JDK 21, Gradle 8.13, platform-tools, build-tools, Android 36 imajı). Ajan da gerektiğinde \`mobile_env action=setup\` ile kurabilir.
- \`mobile_env action=status\` tüm yolları (ANDROID_HOME, JAVA_HOME, gradle, adb, emülatör, sdkmanager), kurulu platform / build-tools / imajları ve compileSdk 36 / 37 için doğrulanmış sürüm setlerini verir; \`action=gradle\` Gradle'ı, \`action=sdk\` SDK paketlerini kurar.

**Takılmazlar:** aynı hata tekrar gelince model denediği komutları görür ve farklı bir yol seçmek zorundadır; yaygın hatalar için bilinen çözümler (program PATH'te yok, yanlış yol, izin, dolu port, eksik paket) otomatik verilir.
` },
      { id: "settings-buttons", title: "Ayar düğmeleri: ∞, Kapalı, Otomatik", summary: "Kaydırıcıda zor seçilen özel değerler tek dokunuşla.", md: `
- Sayısal ayarlarda kaydırıcının yanında **∞** (sınırsız) ya da **Kapalı** düğmesi vardır: özel değeri tek dokunuşla seçer; seçiliyken vurgulu görünür.
- **Otomatik** (↺) düğmesi ayarı uygulamanın kendi seçtiği değere döndürür.
- Kutuya elle de yazabilirsiniz; Enter ya da kutudan çıkmak kaydeder. Telefonda düğmeler yalnızca simgeyle görünür.
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
- **Hazır sunucular** (16, kategorili, aramalı): DeepWiki, Context7, Microsoft Learn, Cloudflare Docs, Hugging Face, GitHub (jeton), Sentry / Notion / Linear (oturum), Git, Playwright, Fetch, Time, Memory, Sequential Thinking, Everything. Tek tıkla eklenir; açık olanlar hemen çalışır.
- **Kayıt defterinde bul**: resmi MCP kayıt defteri, npm ve GitHub'da arayın; anahtar istemeyen sunucu tek tıkla eklenir, isteyende form açılır.
- **Dene**: bir sunucunun araç etiketine tıklayın, argümanları doldurun, **Çalıştır** ile sonucu görün (modelin yaptığı çağrının aynısı). **Sohbette kullan** aracı sohbet kutusuna çip olarak koyar.
- **Sohbette \`#\` kısayolu**: \`/\` yetenek ve \`@\` ajan gibi, \`#\` yazınca çalışan MCP araçları listelenir; seçtiğiniz aracın değişkenleri çipin altında alan olarak açılır (çipe tıklayıp değiştirin), model o aracı bu değerlerle çağırır. (+) menüsünde **MCP aracı** da aynı listeyi açar. Kopyalanan mesajdaki çipler yapıştırınca yine çip olur.
- Ajan gerektiğinde \`mcp_search\` ile resmi kayıt / npm / GitHub'da sunucu bulup \`mcp_add\` ile kendisi bağlar; oturum isteyenlerde (OAuth) Oturum aç düğmesi çıkar.
` },
      { id: "browser", title: "Tarayıcı ajanı: gerçek bir pencerede gezinme", summary: "Siteye girip tıklama, form doldurma, giriş yapma; proje testi.", md: `
Model artık **gerçek, görünür bir tarayıcı penceresinde** bir kullanıcı gibi gezinebilir: sayfa açar, elemanları okur, tıklar, form doldurur, tuş basar, bekler, ekran görüntüsü alır — kendi sitenizi test ederken ya da bir web uygulamasını kullanırken siz nasıl yapardınız, model de öyle yapar.

## Pencere ve oturum
- Pencere **kalıcı bir profille** açılır (\`data/browser-profile\`): bir sitede bir kez elle giriş yaparsanız, çerezler bu profilde kalır ve **sonraki görevlerde model sizi zaten giriş yapmış bulur**.
- Profil yalnızca bu bilgisayarda saklanır, hiçbir yere gönderilmez. **Ayarlar > Web > Tarayıcı ajanı**'ndan pencereyi kapatabilir, görünür/gizli yapabilir veya tüm girişleri tek tıkla unutturabilirsiniz (profili siler).
- Modelin kendi okuma tarayıcısından (araştırma, fetch_url) tamamen ayrıdır: o hep gizli çalışır ve hiçbir çerez tutmaz.

## Nasıl "görür"
Model ekran görüntüsünden tahmin etmez: sayfayı **erişilebilirlik ağacı** olarak okur — her tıklanabilir/yazılabilir öğenin rolü, adı, değeri ve kısa bir referansı (\`[e12]\`) ile. Bu referansla doğrudan o düğmeye tıklar veya o kutuya yazar; sayfa tasarımı değişse de bozulmaz. Her eylemden sonra sayfayı yeniden okur ve gerçekten olanı doğrular.

| Araç | Ne yapar |
|---|---|
| **browser_navigate** | Bir adres açar (http(s) veya çalışma klasöründeki bir .html dosyası) |
| **browser_snapshot** / **browser_find** | Sayfayı okur; metinle eleman arar |
| **browser_click** / **browser_type** / **browser_key** / **browser_form** | Tıklar, yazar, tuş basar, birkaç alanı birden doldurur |
| **browser_scroll** / **browser_wait** | Kaydırır; bir metnin çıkmasını/kaybolmasını bekler |
| **browser_inspect** | Konsol hataları, başarısız ağ istekleri, çerez adları (giriş yapılmış mı?) |
| **browser_screenshot** | Sekmenin görüntüsünü sohbette gösterir |
| **browser_tabs** / **browser_batch** | Sekmeleri yönetir; birkaç adımı tek seferde çalıştırır |
| **browser_handoff** | Pencereyi size bırakır (aşağıya bakın) |

## Güvenlik kuralları
- **Kart ve banka bilgisini model gerçek sitelerde asla yazmaz.** Ödeme gerektiğinde **browser_handoff** çağırır: pencere öne gelir, siz girersiniz, model "bitti" dediğinizde kaldığı yerden devam eder.
- **Şifre:** **Tam erişim** kipinde, isteğinizde adını verdiğiniz sitede (ör. "siteadi.com'a şu e-posta ve şifreyle üye ol") model şifreyi kendisi yazar, kayıt/giriş düğmelerine onay sormadan basar. Diğer sitelerde ve diğer kiplerde girişi size bırakır.
- Test şifreleri yalnızca **localhost / 127.0.0.1** gibi yerel geliştirme adreslerinde veya isteğinizde açıkça adını verdiğiniz bir *staging/dev/test* adresinde, projenin kendi örnek verisinden yazılabilir — gerçek bir sitede asla.
- **Gönder, sil, satın al, yayınla, abonelikten çık** gibi geri dönüşü olmayan bir düğmeye tıklamadan önce sizden onay ister (yerel test ortamınız ve Tam erişimde adını verdiğiniz site hariç; ödeme her zaman size kalır).
- **CAPTCHA veya bot doğrulaması model tarafından çözülmez**: model browser_handoff ile pencereyi size verir (tarayıcı gizli çalışıyorsa görünür pencere kendiliğinden açılır). Siz çözdüğünüz anda bu algılanır ve model "bitti" demenizi beklemeden kaldığı yerden devam eder.
- confirm()/alert() gibi tarayıcı pencereleri varsayılan olarak reddedilir; onaylaması gerektiğinde açıkça belirtir.
- **Açılır pencereler kendiliğinden kapanır:** her sitede bülten, kampanya, cinsiyet seçimi, uygulama reklamı gibi sayfanın önüne çıkan modallar algılanır ve kapatma düğmesiyle (×, Kapat, Şimdi değil…) ya da Escape ile kapatılır; çerez bandında her zaman **Tümünü Reddet** seçilir. Şifre/kart alanı olan pencerelere dokunulmaz. Ayarlar > Tarayıcı ajanı > Açılır pencereleri kapat.

## Projeyi gerçek kullanıcı gibi test etmek
"Projeyi test et" dediğinizde model artık yalnızca kod okumaz: projeyi başlatır (gerekirse), **gerçek tarayıcı penceresinde açar**, formları doldurur, düğmelere tıklar, sonucu kontrol eder, konsol hatalarına ve başarısız isteklere bakar — tıpkı sizin test ettiğiniz gibi. @tester ajanı bu akışı izler; bir takımda test aşaması da bu araçları kullanabilir.

## Örnek istemler
- *"localhost:5173'teki giriş formunu test et: yanlış şifreyle hata gösteriyor mu?"*
- *"example.com sitesinde ürünü sepete ekle, fiyatı doğru mu kontrol et."*
- *"Bu projeyi çalıştır ve ana sayfadaki tüm bağlantıları gerçek tarayıcıda dene."*
` },
    ] },
    { id: "create", title: "Oluşturma ve medya", icon: "film", articles: [
      { id: "studio", title: "Video Stüdyosu", summary: "Zaman çizelgesi, sürüklenen yazılar, efektler, müzik, AI ile canlı düzenleme.", md: `
**Açmak:** (+) > Oluştur > **Video Stüdyosu**, ya da sohbetteki bir video kartında **Stüdyo**.

- **Önizleme:** her yazı, logo ve görsel katmanı resmin üstünde sürüklenir; köşedeki mavi noktayla boyutlanır.
- **Neye tıklarsanız o açılır:** önizlemedeki bir yazı, görsel ya da resmin kendisi; zaman çizelgesindeki bir blok. Sağdaki (telefonda alttaki) panelde o öğenin ayarları açılır, oynatma başlığı oraya atlar.
- **Yazı stili:** yazı tipi, boyut, renk, kutu rengi ve saydamlığı, kontur, gölge, hizalama, animasyon. **Yazı ▾** menüsünde hazır stiller: başlık, alt yazı, fiyat, alıntı, sosyal, harekete çağrı.
- **Görsel / logo:** medya kutusundan bir resmi katman olarak ekleyin; Logo yapıcıda kaydettiğiniz saydam PNG'ler de burada.
- **Seslendirme:** metni yazın, 400+ doğal sesten birini seçin; ses klibi oynatma başlığına eklenir.
- **Müzik:** 8 stilde çevrimdışı üretilen özgün müzik (her basışta yeni varyasyon) ya da telifsiz kütüphane (Openverse / Jamendo; lisans ve kaynak \`music/CREDITS.txt\` dosyasına yazılır). Ses varken müzik otomatik kısılır.
- **Efektler:** film greni, VHS, glitch, ışık sızıntısı, sinema bantları… sahneye ya da tüm videoya; önizlemede canlı.
- **AI ile canlandır:** fotoğraf sahneleri render sırasında gerçek hareketli klibe dönüşür (ücretsiz Wan 2.2; foto başına ~1 dk).
- **AI paneli:** "logoyu sağ üste koy, alt yazıyı sarı yap" yazın; seçili model düzenlemeyi anında uygular. Yeni görsel/indirme isteyen işler sohbet ajanına gider ve adımları stüdyoda canlı görünür.
- **Render al:** ffmpeg ile MP4; proje \`<ad>.timeline.json\` olarak otomatik kaydedilir, geri al/yinele (Ctrl+Z / Ctrl+Y) çalışır.
` },
      { id: "ai-video", title: "AI klip: yazıdan / resimden gerçek video", summary: "generate_video, animate_image, ücretsiz video motorları.", md: `
- **(+) > Oluştur > AI klip** ya da "şu sahneden video üret" deyin: model \`generate_video\` aracını kullanır.
- **Yazıdan video:** önce açıklamadan ilk kare üretilir (anahtarlı görsel servisleri, yoksa ücretsiz FLUX), sonra Wan 2.2 ile gerçek hareket eklenir. **Resimden video:** \`image=\` ile verilen fotoğraf canlandırılır.
- Klip 1,5-5 sn; daha uzun bir film için birkaç klip Video Stüdyosunda müzik, ses ve yazıyla birleştirilir.
- **Ayarlar > Web araştırması > AI video motorları:** Wan 2.2 ve AnimateLCM-SVD'nin canlı durumu (çalışıyor / uykuda). Kurulum ve ücret yok.
- **Kota:** anahtarsız paylaşılan ücretsiz kota kullanılır; **Görsel üretimi > Hugging Face** kartına ücretsiz bir anahtar girerseniz kendi günlük kotanız kullanılır.
` },
      { id: "voices", title: "Ses kütüphanesi, yazıdan ses, sesten yazı", summary: "400+ doğal ses, arama, dinleme, MP3 ve SRT.", md: `
- **(+) > Yazıdan ses:** metni yazın, sesi adına, diline ya da ülkesine göre arayın, cinsiyet filtreleyin, ▶ ile dinleyin, hızı ayarlayın; **Seslendir** MP3 üretir; indirin ya da sohbet klasörüne kaydedin.
- **(+) > Sesten yazı:** bir ses/video dosyası seçin ya da mikrofonla kaydedin; çevrimdışı faster-whisper döküm ve **SRT altyazı** üretir (tiny en hızlı, medium en doğru).
- Aynı ses kütüphanesi Video Stüdyosunun seslendirmesinde ve modelin \`text_to_speech\` aracında kullanılır.
` },
      { id: "logo", title: "Logo yapıcı", summary: "AI yönleri, AI sembolleri, saydam PNG.", md: `
1. (+) > Oluştur > **Logo yapıcı**. Marka adı, slogan ve sektör / anahtar kelimeler yazın.
2. **AI ile 3 yön öner:** model üç marka yönü (yazı tipi, renkler, yerleşim) önerir; birine tıklayın.
3. **AI ile sembol üret:** görsel servisleri sembol çizer, arka planı otomatik temizlenir. **Kendi sembolünü yükle** de arka planı temizler.
4. Yazı tipi, kalınlık, yerleşim (sembol solda/üstte, yalnız yazı, rozet), şekil, renkler, harf aralığı, sembol boyutu.
5. **PNG indir (saydam)** ya da **Sohbet klasörüne kaydet** (\`logos/\`). Kayıtlı logo Video Stüdyosunda logo katmanı olur.
` },
      { id: "image-services", title: "Görsel üretim ve stok fotoğraf servisleri", summary: "Anahtarlar, kota, otomatik geçiş, ücretsiz yedek.", md: `
**Ayarlar > Web araştırması:**
- **Görsel üretimi:** Google Gemini, Cloudflare (FLUX), Hugging Face, Together, OpenAI, Stability. Kartı açın, anahtarı kaydedin, **Test** edin; anahtarlı servisler sırayla denenir.
- Bir servisin kotası / hız sınırı dolarsa sıfırlanana kadar atlanır, sıradaki kullanılır; hepsi kapalıysa ücretsiz **Pollinations (FLUX)** devreye girer (sistem servisleri yeşil görünür, test gerekmez).
- **Stok fotoğraf:** Pexels, Pixabay, Unsplash (anahtarla), sonra Openverse ve Wikimedia Commons. Adım satırında fotoğrafın hangi sağlayıcıdan geldiği yazar; sayfalara yazar/lisans satırı eklenir.
- Hatalar (hız sınırı, kota, eksik anahtar, engel) Türkçe ve İngilizce gösterilir.
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
1. Run **install.bat** in the project folder. It installs the Python and Node dependencies (the tokenizer too) and shows each step with a progress bar, elapsed and remaining time; the full log goes to \`data/logs\`. It speaks Turkish on a Turkish Windows and English elsewhere.
2. Start the app with **run.bat**. It opens at **http://127.0.0.1:8300**. The window shows a readable, coloured log; frequent polling is hidden (\`run.bat --verbose\` shows everything, \`run.bat 8400\` uses another port).
3. After an update run install.bat once more and press **Ctrl+F5** in the browser.

## Folders
| Folder | Contents |
|---|---|
| \`data/\` | Settings, chat database, secret keys |
| \`chat/<id>/\` | Each chat without a project: its files, downloads and everything made (deleted with the chat) |
| \`chat/<id>/.session/\` | That chat's hidden session record: messages, summaries, scripts |
| \`chat/projects/\` | Projects created without choosing a folder |
| \`skills/\`, \`agents/\` | Skill and agent files |
| \`languages/\` | UI language files (tr.json, en.json…) |

> Keys are kept only in \`data/secrets.json\` and are never sent to the UI in plain text.
` },
      { id: "providers", title: "Adding providers", summary: "Local and cloud model sources, keys, Test.", md: `
## Local models
- **Ollama** and **LM Studio** need no key; their models are listed automatically while they run.
- Switching to a local model unloads the other local models from memory.

## Memory guard (RAM / VRAM)
- Before loading: when a model's weights and context window do not fit in the free memory, the window is reduced to what fits; when the weights alone do not fit, the model is not loaded.
- While running, when free memory gets low, in this order: the app's own caches are released, unused models are unloaded, then the context window of the model in use is made smaller (e.g. 16K → 8K).
- **The model in use is not closed** and no chat memory is lost: messages, the summary and the task's progress live in the app; the task continues in the smaller window where it stopped.
- On computers with a graphics card, VRAM is watched too (NVIDIA, AMD, Intel; Windows and Linux). The limits follow the computer's total memory by themselves.
- Settings > Security > "Local model memory" turns the guard off or turns "unload the model in an emergency" on (off by default).

## First prompt size
- Slow models (local models on a CPU, busy free cloud models) make you wait while they read the rules and tool definitions of a task's first request. The **lean prompt** says the same in about half the tokens: short rules, a one-paragraph capability index, short tool definitions.
- The model knows its abilities from that index; it opens the tool group it needs with \`need_tools\` and a skill with \`use_skill\`. Groups opened in a chat stay open for that chat's next tasks.
- Settings > Security > "First prompt size": Automatic (lean for local models, small windows and models measured as slow), Lean or Full.

## Cloud APIs
1. Open **Settings > Providers** and enable the provider.
2. Enter the API key and press **Test**. It shows the model list, or the reason when something is wrong.
3. Supported: OpenAI, Anthropic, Gemini, OpenRouter, Groq, DeepSeek, Hugging Face, **NVIDIA NIM**, **Cloudflare Workers AI**, EVREN, Ollama Cloud and 20+ more.

## If the internet drops
- The app watches the internet connection in the background. When it drops you see **"Internet connection lost"**; when it returns, **"back (it was down for N s)"**.
- A task running on a cloud model does **not** end half-way: it pauses, and the chat shows a "No internet — waiting for the connection" box with the time passed. Once the connection is back it continues by itself on the **same model**, with the same conversation and to-do list, where it stopped; a half-written file is kept. The drop uses no retries against the quota and does not switch models, so the model forgets nothing.
- Tools that need the internet (web search, reading pages, image generation…) wait for the connection too; localhost pages and local models are not affected.
- There is no time limit on the wait; you can stop the task. If the app is closed, the task is marked as interrupted and can be resumed.

## When a stream goes silent (connection check)
- If the stream is silent for 20 s while the model writes, the app sends a tiny separate request to the same model. The "Preparing" step shows the result.
- **The provider answers at once but the stream stays silent:** the stream was lost. The cut follows the stream's own pace (at least 90 s; longer for providers that send in batches, such as Evren), and a stream the server keeps alive with keep-alives is never cut. What was written is kept and the model continues where it stopped.
- Short pauses (the normal 5-12 s gaps between batches) no longer show "no data" and no longer close the live reasoning.
- **The provider is slow:** the model is still working, so the app waits. **It cannot be reached:** the internet is checked; if it is down, the app waits for the connection.

## Document templates and mode chips
- Choosing Make an image, Promo video, AI clip, Image to video, Word, PDF, Excel or PowerPoint in the (+) menu puts a coloured **chip** into the message box; you write what you want next to it. × or Backspace in an empty box removes it.
- Document chips open that format's **template gallery** (real previews). A chosen template gives the document its colours, type, cover and section layout.
- **Create template** starts the Template Creator: the model explains templates and asks for a reference file (PDF, Word, PowerPoint or an image); it reads the file's colour palette, fonts, headings and cover look in one step and saves the new template. It appears in the gallery and your own templates can be deleted.
- 35 built-in templates in 8 page layouts: report with cover, official letter, memo, academic, magazine, invoice / quote, résumé, minimal (annual report, case study, white paper, price quote, SOP, business plan, sales pipeline, inventory, product launch...). Cover styles: hero, band, minimal, dark, photo, split, editorial, corner; numbered / underlined / caps headings and solid / line / soft tables.
- In the sent message the mode and template show as **chips**, as in the message box.
- The gallery arrows grey out at the ends; the **View all** card opens every template of the format in a dialog (more load while you scroll). A template is only the design: the title, sections and letterhead lines come from the document's own content.
- **Image to video** shows the pictures in the chat's working folder and the ones attached to the message; you can also upload a new one.

## Voices (local and online)
- **Settings > Voices**: the default voice per language, tone (speed, pitch, emotion, pause between sentences), the studio finish and the engine order. Spoken replies, text to speech, video voice-overs and the Video Studio all use them.
- **Local engines (offline):** Piper (fast, 50+ languages; Turkish: Fettah female, Eren / Dfki / Fahrettin male), Kokoro (very natural English + 5 languages), Chatterbox (the most natural and expressive, 23 languages, your own voice; installed into its own environment, ~4 GB, slow on a CPU). Microsoft's online voices are the fallback.
- Voices download the first time they are played or chosen (data/tts). A voice without gender metadata is labelled female/male by measuring its pitch.
- **Studio:** Natural, Podcast, Broadcast (-23 LUFS), Video (-14 LUFS), Warm narration or Raw. EQ, de-esser, compression and a loudness standard in one pass; optional room echo.
- **Fallback order:** engines never run at the same time. If the chosen voice fails, the next voice of the same language and gender is used; engines switched off are never used.
- **Dialogs:** "Anna: ..." / "Ben: ..." lines are read by different voices (female/male automatically, or a voice per speaker).
- **Video:** the music is ducked under the voice-over; with "Add subtitles" the sentences are written on the video with their real timings and a .srt is saved next to it.
- **Your own voice (Chatterbox):** a 5–30 second clip; only your own voice or one you have permission to use.

## Retired models
- When a provider retires a model for new users ("no longer available"), the app hides it and moves to the successor the provider names; the active model is updated too.
- Embedding, speech, guard and image-only models are not shown in the chat model list.

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
- Each chat without a project works in its own folder (\`chat/<chat id>/\`); chats never see each other's files. A new chat's folder is made with its first message.
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
      { id: "testing", title: "Testing a project on localhost and on mobile", summary: "The localhost-project and mobile-app-test skills, mobile_env.", md: `
**Web projects (PHP, ASP.NET, Node, Python, Ruby, Java, Go, Rust, static, Docker Compose):** say "set up this project on localhost and test it"; the **localhost-project** skill loads by itself:
1. It finds the repository or takes yours (the ZIP comes in one step, git is not required) and detects the stack.
2. It installs the missing runtimes and packages; SQLite first for the database. Big installs (database servers, XAMPP, Docker) are asked first.
3. Python packages always go to the right environment: the app's own \`.venv\`, or the project's own venv when it has one (what it already holds is checked first).
4. It starts the server (a busy port: its own earlier server is stopped, or a free port is used), tries pages, forms and logins in a real browser, runs the project's own tests and writes a report.

**Mobile apps (Android, iOS, Flutter, React Native, Expo, Capacitor):** the **mobile-app-test** skill:
- Fast path: the web build is tested in the browser at phone size.
- Full path: the \`mobile_env\` tool sets up and starts the Android emulator (Windows, macOS, Linux), installs the APK, takes screenshots and runs **Maestro** UI flows. The iOS simulator needs macOS + Xcode.
- Setup: \`install.bat\` / \`install.sh\` ask at the start (\`AIIQ_MOBILE=1\` installs without asking) and show what the computer already has: Android Studio's SDK and JDK or tools installed earlier are not downloaded again; only missing parts are added and old ones updated (JDK 21, Gradle 8.13, platform-tools, build-tools, the Android 36 image). The agent can also run \`mobile_env action=setup\` when needed.
- \`mobile_env action=status\` returns every path (ANDROID_HOME, JAVA_HOME, gradle, adb, emulator, sdkmanager), the installed platforms / build-tools / images and the verified version sets for compileSdk 36 / 37; \`action=gradle\` installs Gradle, \`action=sdk\` installs SDK packages.

**No loops:** when the same error comes back the model sees the commands it already tried and must take a different route; known fixes for common errors (program not on PATH, wrong path, permission, busy port, missing package) are given automatically.
` },
      { id: "settings-buttons", title: "Setting buttons: ∞, Off, Auto", summary: "Special values that were hard to hit on a slider, in one tap.", md: `
- Numeric settings have an **∞** (unlimited) or **Off** button next to the slider: it picks that special value in one tap and is highlighted while selected.
- The **Auto** (↺) button returns the setting to the value the app chooses itself.
- You can also type in the box; Enter or leaving the box saves it. On a phone the buttons show as icons.
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
- **Ready servers** (16, by category, searchable): DeepWiki, Context7, Microsoft Learn, Cloudflare Docs, Hugging Face, GitHub (token), Sentry / Notion / Linear (sign-in), Git, Playwright, Fetch, Time, Memory, Sequential Thinking, Everything. One click adds one; public ones work at once.
- **Find in registry**: search the official MCP registry, npm and GitHub; a server that needs no key is added with a click, the others open the form.
- **Try**: click a tool's label on a server, fill in its arguments, **Run** shows the result (the same call the model makes). **Use in chat** puts the tool into the message box as a chip.
- **\`#\` in the message box**: like \`/\` skills and \`@\` agents, typing \`#\` lists the running MCP tools; the arguments of the tool you pick open as fields under its chip (click the chip to change them) and the model calls that tool with them. **MCP tool** in the (+) menu opens the same list. Chips in a copied message come back as chips when pasted.
- When needed the agent finds a server with \`mcp_search\` (official registry / npm / GitHub) and connects it with \`mcp_add\` itself; servers that need a sign-in (OAuth) get a Sign in button.
` },
      { id: "browser", title: "Browser agent: acting in a real window", summary: "Opening a site, clicking, filling forms, signing in; testing a project.", md: `
The model can now navigate a **real, visible browser window** like a person: open a page, read what is on it, click, fill forms, press keys, wait, take a screenshot - the same way you would when testing your own site or using a web app.

## Window and sign-ins
- The window opens with a **lasting profile** (\`data/browser-profile\`): sign in once by hand on a site, and the cookies stay in that profile, so **later tasks find you already signed in**.
- The profile is kept only on this computer and never sent anywhere. **Settings > Web > Browser agent** can close the window, make it visible or hidden, and forget every sign-in with one click (deletes the profile).
- It is entirely separate from the model's own reading browser (research, fetch_url): that one always runs hidden and never keeps cookies.

## How it "sees" the page
The model does not guess from a screenshot: it reads the page as an **accessibility tree** - every clickable/typable element's role, name, value and state, each with a short reference (\`[e12]\`). It clicks or types using that reference directly, so a redesigned page does not break it. After every action it reads the page again and checks what really happened.

| Tool | What it does |
|---|---|
| **browser_navigate** | Opens an address (http(s), or a .html file in the working folder) |
| **browser_snapshot** / **browser_find** | Reads the page; finds an element by its text |
| **browser_click** / **browser_type** / **browser_key** / **browser_form** | Clicks, types, presses keys, fills several fields at once |
| **browser_scroll** / **browser_wait** | Scrolls; waits for a text to appear/disappear |
| **browser_inspect** | Console errors, failed requests, cookie names (are you signed in?) |
| **browser_screenshot** | Shows the tab in the chat |
| **browser_tabs** / **browser_batch** | Manages tabs; runs several steps at once |
| **browser_handoff** | Hands the window to you (see below) |

## Safety rules
- **The model never types card or bank details on a real site.** When a payment is needed it calls **browser_handoff**: the window comes to the front, you enter them, and the model continues once you say it is done.
- **Passwords:** in **Full access** mode, on the site your request names (e.g. "sign me up on mysite.com with this e-mail and password"), the model types the password itself and presses the sign-up/sign-in buttons without asking. On other sites and in the other modes it hands the sign-in to you.
- Test credentials are typed only on **localhost / 127.0.0.1** (or a *staging/dev/test* address you explicitly name in your request), from the project's own test data - never on a real site.
- It asks for your OK before clicking an irreversible button - **send, delete, buy, publish, unsubscribe** - except on your own local test environment and, in Full access, on the site you named (payments always stay with you).
- **CAPTCHAs and bot checks are never solved by the model**: it hands the window to you with browser_handoff (a hidden browser opens a visible window by itself). As soon as you solve it this is detected and the model continues without waiting for you to say "done".
- Browser dialogs (confirm()/alert()) are dismissed by default; it says plainly when one needs your confirmation.
- **Pop-ups close by themselves:** on every site, modals in front of the page (newsletter, campaign, gender picker, app ads...) are detected and closed with their close button (×, Close, Not now...) or Escape; cookie banners always get **Reject all**. Windows with a password/card field are left alone. Settings > Browser agent > Close pop-ups.

## Testing a project like a real user
When you say "test this", the model no longer just reads code: it starts the project (if needed), **opens it in the real browser window**, fills forms, clicks through, checks the result, and looks at console errors and failed requests - the way you would test it yourself. The @tester agent follows this flow; a team's testing stage can use these tools too.

## Example prompts
- *"Test the sign-in form at localhost:5173: does a wrong password show an error?"*
- *"Add the product to the cart on example.com and check the price is right."*
- *"Run this project and try every link on the home page in the real browser."*
` },
    ] },
    { id: "create", title: "Create and media", icon: "film", articles: [
      { id: "studio", title: "Video Studio", summary: "Timeline, draggable texts, effects, music, live AI edits.", md: `
**Open it:** (+) > Create > **Video Studio**, or **Studio** on a video card in the chat.

- **Preview:** every text, logo and picture layer is dragged on the picture and resized with the blue dot in its corner.
- **Click anything to open it:** a text, a picture or the picture itself on the preview, or a block on the timeline. Its settings open in the panel on the right (below on a phone) and the playhead jumps into it.
- **Text style:** font, size, colour, box colour and opacity, outline, shadow, alignment, animation. Presets in the **Text ▾** menu: heading, caption, price, quote, social, call to action.
- **Picture / logo:** add a picture from the media bin as a layer; transparent PNGs saved in the Logo maker are there too.
- **Voice-over:** type the text and pick one of 400+ natural voices; the clip is added at the playhead.
- **Music:** original music generated offline in 8 styles (a new variation on every press) or a royalty-free library (Openverse / Jamendo; licence and source go to \`music/CREDITS.txt\`). Music ducks under the voice automatically.
- **Effects:** film grain, VHS, glitch, light leak, letterbox… per scene or for the whole video, previewed live.
- **Animate with AI:** photo scenes become real moving clips when rendering (free Wan 2.2; ~1 min per photo).
- **AI panel:** type "put the logo top right, make the caption yellow"; the selected model applies the edit at once. Work that needs new pictures or downloads goes to the chat agent, whose steps show live in the studio.
- **Render:** MP4 with ffmpeg; the project saves itself as \`<name>.timeline.json\`, undo/redo (Ctrl+Z / Ctrl+Y) works.
` },
      { id: "ai-video", title: "AI clip: text / image to real video", summary: "generate_video, animate_image, the free video engines.", md: `
- **(+) > Create > AI clip**, or say "make a video clip of …": the model uses the \`generate_video\` tool.
- **Text to video:** the first frame is generated from the description (keyed image services, else free FLUX), then Wan 2.2 adds real motion. **Image to video:** the photo given with \`image=\` is animated.
- A clip is 1.5-5 s; for a longer film several clips are joined with music, voice and titles in the Video Studio.
- **Settings > Web research > AI video engines:** the live state of Wan 2.2 and AnimateLCM-SVD (running / sleeping). Nothing to install or pay.
- **Quota:** without a key the shared free quota is used; a free key in the **Image generation > Hugging Face** card uses your own daily quota.
` },
      { id: "voices", title: "Voice library, text to speech, speech to text", summary: "400+ natural voices, search, listen, MP3 and SRT.", md: `
- **(+) > Text to speech:** type the text, search voices by name, language or country, filter by gender, listen with ▶, set the speed; **Speak** makes an MP3 to download or save to the chat folder.
- **(+) > Speech to text:** pick an audio/video file or record with the microphone; offline faster-whisper writes the transcript and **SRT subtitles** (tiny is fastest, medium most accurate).
- The same voice library is used by the Video Studio's voice-over and the model's \`text_to_speech\` tool.
` },
      { id: "logo", title: "Logo maker", summary: "AI directions, AI symbols, transparent PNG.", md: `
1. (+) > Create > **Logo maker**. Type the brand name, a tagline and the industry / keywords.
2. **3 AI directions:** the model suggests three brand directions (font, colours, layout); click one.
3. **AI symbols:** the image services draw symbols and their background is removed. **Upload your own symbol** removes the background too.
4. Font, weight, layout (symbol left/top, text only, badge), shape, colours, letter spacing, symbol size.
5. **Download PNG (transparent)** or **Save to the chat folder** (\`logos/\`). A saved logo becomes a logo layer in the Video Studio.
` },
      { id: "image-services", title: "Image generation and stock photo services", summary: "Keys, quotas, automatic switching, free backup.", md: `
**Settings > Web research:**
- **Image generation:** Google Gemini, Cloudflare (FLUX), Hugging Face, Together, OpenAI, Stability. Open a card, save the key, press **Test**; keyed services are tried in order.
- A service out of quota or rate limited is skipped until it resets and the next one is used; when all are off the free **Pollinations (FLUX)** steps in (system services show green without a test).
- **Stock photos:** Pexels, Pixabay, Unsplash (with keys), then Openverse and Wikimedia Commons. The step line names the provider a photo came from; pages get an author/licence line.
- Errors (rate limit, quota, missing key, blocked) are shown in English and Turkish.
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
