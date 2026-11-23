# Ajan Değerlendirmesi

[English](README.md) · **Türkçe**

Her model için aynı dokuz görev. Puan yalnızca görevden sonra gerçekten var olana göre verilir; modelin yaptım *dediği*
hiçbir şey sayılmaz.

| Görev | Modelden istenen | Nasıl denetlenir |
|---|---|---|
| `web_app` | `todo/` içinde yapılacaklar web uygulaması (metin kutusu, Ekle düğmesi, liste, localStorage), tarayıcıda test | Dosyalar var; gerçek bir Chromium sayfayı açar, yazar, Ekle'ye basar, yeniler; konsol hatası yok, başarısız istek yok |
| `fix_python` | `stats.py` bozuk (bir sözdizimi hatası, dört mantık hatası); düzelt, testleri çalıştır, testlere dokunma | `test_stats.py` değişmemiş; verilen testler ve aynı tanımın gizli test dosyası geçer |
| `multi_file` | `price` adını beş modülde `unit_price` yap, `low_stock()` ve rapor bölümü ekle, README'yi güncelle | Eski ad kalmamış; beş modülün hepsi değişmiş; README güncel; gizli testler (yeniden adlandırma, yeni metot, rapor, CLI) geçer |
| `documents` | Üç adlı bölümü olan raporu Word ve PDF olarak üret, sonra ikisini de açıp doğrula | `python-docx` ve `pypdfium2` açar; bölümler gerçek başlık; ≥ 120 kelime; Markdown kalıntısı yok (`#`, `**`, ```) |
| `net_drop` | Her biri bir gezegen hakkında dört dosya, teker teker | Runner görevin ortasında modelin bağlantısını 8 sn gerçekten keser; dört dosya da tam; uygulama kopmayı fark edip devam etti; biten dosya yeniden yazılmadı; model aynı kaldı |
| `research` | Karmaşık web araştırması: dört bilgi (iki yayın tarihi, bir PEP numarası, bir lisans) ve bunlardan hesaplanan gün sayısı; her bilginin aynı satırında kaynak URL'si; ≥ 3 siteden ≥ 4 kaynak | Her bilgi doğru; gün sayısı doğru; her bilginin yanında kaynağı var; denetleyici gösterilen her URL'yi kendisi açar (404 ya da ölü site = uydurma kaynak); iz kaydında ≥ 2 web aracı çağrısı |
| `skill_review` | Küçük bir uygulamayı hata ve güvenlik açısından incele, `review.md`'ye ciddiyet sırasıyla yaz, koda dokunma | Yerleştirilen dört sorun dosyasıyla anılmış (SQL enjeksiyonu, dizin geçişi, kodda gizli anahtar, sayfalamada bir kayma); SQL enjeksiyonu kritik / yüksek; kod değişmemiş |
| `skill_flowchart` | İki kararı ve stok döngüsü olan bir sipariş sürecinin Mermaid akış şeması, `diagrams/order.mmd`'ye kayıtlı | Uygulamanın kendi Mermaid'i gerçek tarayıcıda ayrıştırıp çizer; ≥ 7 adım; iki eşkenar dörtgen karar; Evet / Hayır çıkışları; döngü gerçekten geri dönüyor (çizgede çevrim) |
| `skill_git` | `main` üzerinde depo başlat, `.env` ve `__pycache__` için `.gitignore`, ilk commit, `login.py` ile `feature/login` dalı, `main`'e dönüş | git'in kendisiyle denetlenir: dallar, commit mesajı, `.env` ve `__pycache__` hiç commit edilmemiş, `login.py` yalnızca dalda, HEAD `main`'de, commit edilmemiş bir şey yok |

Üç yetenek görevinde istek yeteneğin adını vermez. Modelin uygun yeteneği yükleyip yüklemediği raporda puanlanmayan bir not olarak gösterilir: uygulama bu seçimi modele bırakır; işi yeteneksiz de doğru yapan model geçer.

## Çalıştırma

```powershell
.venv\Scripts\python.exe eval\run_eval.py --models mock
```

```powershell
.venv\Scripts\python.exe eval\run_eval.py --models "evren:auto,nvidia:nvidia/nemotron-3.5-super-vl-120b-a12b"
```

```powershell
.venv\Scripts\python.exe eval\run_eval.py --models evren:auto --tasks fix_python,documents --lang en
```

- `--models mock` kendi kendine testtir: senaryolu bir model her görevi gerçek araç çağrılarıyla çözer, yani her
  kontrol geçmelidir. CI bunu her push'ta çalıştırır.
- Model kimlikleri model seçicideki gibi `sağlayıcı:model` biçimindedir. Birden çok model sırayla çalışır.
- `--lang tr|en` görev metinlerinin ve raporun dilidir.
- `--timeout` görev başına saniyedir (varsayılan 1800). Süreyi aşan görevi runner durdurur. Bu yalnızca bir
  değerlendirme sınırıdır: uygulamanın kendisi hata ya da bütçe yüzünden bir görevi asla durdurmaz.
- `--keep` geçici veri klasörünü (sohbetler, uygulama günlüğü) bir hatayı incelemek için saklar.

## Verilerin sende kalır

Her çalıştırma, çalışan uygulamanın yanında, 8390 numaralı portta (`--port`) geçici veri klasörlü kendi uygulama
örneğini başlatır. `data/` klasörün yalnızca okunur: sağlayıcıların çalışsın diye `settings.json` ve `secrets.json`
geçici klasöre kopyalanır ve kopya sonda silinir (`--keep` ile anahtarlar sen silene kadar yalnızca o geçici klasörde
kalır). Değerlendirme örneğinde izin modu "tam"dır; kendi ayarların değişmez.

## Rapor

`eval/reports/<tarih-saat>/`:

- `report.html`: etkileşimli rapor. İçinde şunlar var:
  - puan kutucukları
  - model başına değerlendirme: önce başarı oranı, sonra sürenin ne kadarının sağlayıcıda (ilk token beklemesi, hız
    sınırı), modelin yazmasında, araçlarda ve uygulamada geçtiği, ve uygulamanın kendisinde bir sorun olup olmadığı.
    Ölçüt başarı oranı ve uygulama hatası olmamasıdır; yavaş bir sağlayıcı kuyruğu öyle adlandırılır ve puanı
    değiştirmez.
  - üzerine gelince ayrıntı gösteren üç grafik (açık ve koyu tema)
  - tam tablo
  - tüm kontroller
- `report.md`: aynısı, grafikler SVG resmi olarak. İçeriği:
  - model başına özet
  - görev başına sürenin nereye gittiği
  - görev başına bir satır: durum, tur, yeniden deneme, model değişimi
  - geçmeyen her kontrol
  - araca göre hata türleri
  - tüm kontroller
- `charts/*.svg`: grafikler:
  - `scores`: modele göre üç puan
  - `heatmap`: görev × model, geçen kontroller
  - `time`: her görevin süresinin nereye gittiği
- `report.json`: aynı veri, çalıştırmaları karşılaştırmak için; model başına `scores` ile.
- `traces/<model>__<görev>.jsonl`: her görevin iz kaydı (aşağıda).

Ayrı ayrı çalıştırılan modeller (paralel ya da farklı günlerde) tek raporda birleştirilebilir:

```powershell
.venv\Scripts\python.exe eval\run_eval.py --merge "eval\reports\<a>,eval\reports\<b>"
```

`--keep` ile saklanan bir çalıştırma, denetleyicide bir düzeltmeden sonra, modeller yeniden çalıştırılmadan, gerçekten
bıraktığı dosyalar üzerinde yeniden puanlanabilir (rapor "yeniden puanlandı" diye işaretlenir):

```powershell
.venv\Scripts\python.exe eval\run_eval.py --rescore "eval\reports\<a>" --kept "<saklanan geçici klasör>"
```

### Birbirinden ayrı üç puan

Farklı sorulara cevap verdikleri için üçü de gösterilir:

| Puan | Nedir | Cevapladığı soru |
|---|---|---|
| Görev başına (eşit ağırlık) | her görevin geçen / kendi kontrolleri oranının ortalaması | model ortalama bir görevde ne kadar iyi |
| Kontrol başına (tek havuz) | geçen tüm kontroller / tüm kontroller | tek tek gereksinimlerin kaçını karşıladı; çok kontrollü görev daha ağır basar |
| Tam geçen | her kontrolü geçen görevler / görevler | işin tamamı ne sıklıkla gerçekten bitirildi |

Örnek: 5/8, 3/3, 2/4, 7/7, 5/5 şunu verir:
- görev başına: %82,5
- kontrol başına: 22/27 = %81,5
- tam geçen: 3/5 = %60

### Süre nereye gitti

Her görevin süresi aşağıdaki parçalara ayrılır. Hepsi uygulamanın kendi saatinden gelir:

| Parça | Neyi kapsar |
|---|---|
| bekleme | her isteğin ilk token'ına kadar: sağlayıcı kuyruğu artı istemin okunması |
| üretim | ilk token'dan sonraki akış |
| araçlar | araçların çalışması (geçen gerçek süre: paralel çalışan çağrılar bir kez sayılır) |
| hata sonrası bekleme | hız sınırı gibi sağlayıcı hatalarından sonra beklenen süre |
| uygulama | geri kalan |

Her görevle iki sayı daha gelir:
- **en uzun tek bekleme**
- **1K istem token'ı başına bekleme:** görevin isteklerinin medyanı. Küçük istemlerde 1K başına bekleme yüksekse gecikme modelin işinden değil, sağlayıcıdan gelir.

## İz kayıtları (trace)

Uygulamadaki her görev (yalnızca değerlendirmede değil) `chat/<id>/.session/traces/<görev id>.jsonl` yazar:

```
{"type": "run",  "run": "…", "model": "…", "status": "ok", "request": "…", "timing": {…}, "files": [...]}
{"type": "turn", "i": 1, "wait_ms": 900, "total_ms": 2000, "in_tokens": 6200, "out_tokens": 120, "tps": 30.0}
{"type": "step", "t": 1763870000.1, "ms": 12, "kind": "file", "tool": "write_file", "args": {…}, "status": "done"}
{"type": "step", …, "status": "error", "error": "ModuleNotFoundError: No module named 'flask'"}
```

Bunu model değil, uygulama kendi kayıtlarından yazar; uzun değerler kısaltılır, komutlardaki gizli bilgiler zaten
gizlenmiştir. Bir sohbetin son 30 iz kaydı tutulur. `GET /api/sessions/<sohbet id>/traces/<görev id>` birini sayılarıyla
birlikte döndürür.

## Görev ekleme

`eval/tasks.py` dosyasına şunlarla bir `Task` ekle:
- Türkçe ve İngilizce görev metni
- `eval/tasks/` altında isteğe bağlı bir başlangıç klasörü
- git'teki bir başlangıç klasörünün taşıyamadığı dosyalar (`.env` gibi) için isteğe bağlı bir `setup`
- klasöre ve iz kaydına bakıp `(ad, geçti, bilgi)` satırları döndüren bir denetim fonksiyonu.
Sonra kendi kendine test geçmeye devam etsin diye `eval/mock_solver.py`'ye onu çözmeyi öğret.
