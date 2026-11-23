# Ajan Değerlendirmesi

[English](README.md) · **Türkçe**

Her model için aynı beş görev. Puan yalnızca görevden sonra gerçekten var olana göre verilir; modelin yaptım *dediği*
hiçbir şey sayılmaz.

| Görev | Modelden istenen | Nasıl denetlenir |
|---|---|---|
| `web_app` | `todo/` içinde yapılacaklar web uygulaması (metin kutusu, Ekle düğmesi, liste, localStorage), tarayıcıda test | Dosyalar var; gerçek bir Chromium sayfayı açar, yazar, Ekle'ye basar, yeniler; konsol hatası yok, başarısız istek yok |
| `fix_python` | `stats.py` bozuk (bir sözdizimi hatası, dört mantık hatası); düzelt, testleri çalıştır, testlere dokunma | `test_stats.py` değişmemiş; verilen testler ve aynı tanımın gizli test dosyası geçer |
| `multi_file` | `price` adını beş modülde `unit_price` yap, `low_stock()` ve rapor bölümü ekle, README'yi güncelle | Eski ad kalmamış; beş modülün hepsi değişmiş; README güncel; gizli testler (yeniden adlandırma, yeni metot, rapor, CLI) geçer |
| `documents` | Üç adlı bölümü olan raporu Word ve PDF olarak üret, sonra ikisini de açıp doğrula | `python-docx` ve `pypdfium2` açar; bölümler gerçek başlık; ≥ 120 kelime; Markdown kalıntısı yok (`#`, `**`, ```) |
| `net_drop` | Her biri bir gezegen hakkında dört dosya, teker teker | Runner görevin ortasında modelin bağlantısını 8 sn gerçekten keser; dört dosya da tam; uygulama kopmayı fark edip devam etti; biten dosya yeniden yazılmadı; model aynı kaldı |

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

- `report.md`: model başına özet (puan, tam geçen görev, süre, çıktı token'ı, araç çağrıları ve hataları), görev başına
  bir satır (durum, tur, yeniden deneme, model değişimi), geçmeyen her kontrol, araca göre hata türleri ve tüm kontroller.
- `report.json`: aynı veri, çalıştırmaları karşılaştırmak için.
- `traces/<model>__<görev>.jsonl`: her görevin iz kaydı (aşağıda).

Puan = geçen kontrol / tüm kontroller.

## İz kayıtları (trace)

Uygulamadaki her görev (yalnızca değerlendirmede değil) `chat/<id>/.session/traces/<görev id>.jsonl` yazar:

```
{"type": "run",  "run": "…", "model": "…", "status": "ok", "request": "…", "timing": {…}, "files": [...]}
{"type": "turn", "i": 1, "wait_ms": 900, "total_ms": 2000, "out_tokens": 120, "tps": 30.0}
{"type": "step", "t": 1763870000.1, "ms": 12, "kind": "file", "tool": "write_file", "args": {…}, "status": "done"}
{"type": "step", …, "status": "error", "error": "ModuleNotFoundError: No module named 'flask'"}
```

Bunu model değil, uygulama kendi kayıtlarından yazar; uzun değerler kısaltılır, komutlardaki gizli bilgiler zaten
gizlenmiştir. Bir sohbetin son 30 iz kaydı tutulur. `GET /api/sessions/<sohbet id>/traces/<görev id>` birini sayılarıyla
birlikte döndürür.

## Görev ekleme

`eval/tasks.py` dosyasına bir `Task` ekle: Türkçe ve İngilizce görev metni, `eval/tasks/` altında isteğe bağlı bir
başlangıç klasörü ve klasöre ve iz kaydına bakıp `(ad, geçti, bilgi)` satırları döndüren bir denetim fonksiyonu.
Sonra kendi kendine test geçmeye devam etsin diye `eval/mock_solver.py`'ye onu çözmeyi öğret.
