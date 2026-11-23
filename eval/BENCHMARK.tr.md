# Benchmark

[English](BENCHMARK.md) · **Türkçe**

[Ajan değerlendirmesinin](README.tr.md) gerçek modellerdeki sonuçları. Her satır bir görevin bir çalıştırmasıdır ve yalnızca gerçek çıktıya göre puanlanır. En yenisi üstte.

## 2026-11-23 · v0.20.0 · `evren:auto` · Türkçe görev metinleri · yalnızca CPU'lu PC (model bulutta çalışır)

| Görev | Kontrol | Durum | Süre | Tur | Çıktı token | Araç çağrısı (hata) | Yeniden deneme | Model değişimi |
|---|---|---|---|---|---|---|---|---|
| Web uygulaması (klasör düzeltmesinden sonra 3. çalıştırma) | **8/8** | ok | 1022 sn | 22 | 4.696 | 16 (0) | 1 | 0 |
| Bozuk Python düzeltme | **3/3** | ok | 262 sn | 8 | 2.064 | 8 (0) | 0 | 0 |
| 5 dosyalı değişiklik | **4/4** ¹ | ok | 1008 sn | 21 | 4.585 | 18 (1) | 0 | 0 |
| Word + PDF | **7/7** | ok | 537 sn | 12 | 2.552 | 8 (2) | 0 | 0 |
| Bağlantı kopması | **9/9** | ok | 268 sn | 7 | 2.161 | 5 (0) | 1 | 0 |

**Beş görevin hepsi geçti: 31/31 kontrol.**

### Çalıştırmaların bulduğu ve düzeltilenler

| Çalıştırma | Sonuç | Neden | v0.20.0'daki düzeltme |
|---|---|---|---|
| Web uygulaması, 1. | 0/4, 1200 sn'de durduruldu | Dosyalar `todo/` yerine sohbetin köküne yazıldı; `browser_key {"key": "F5", "keys": ""}` 3 kez reddedildi | `browser_key` tuşu `key` / `ref` alanından da alır |
| Web uygulaması, 2. | 5/8 | Uygulama çalışıyor (Ekle, yenileme, konsol hatası yok), ama dosyalar yine kökte | Uygulama, adı verilen bir klasör için sayılan dosyaların o klasörde olduğunu denetler; görevin sonunda modele söylenir ve model dosyaları taşır |
| Web uygulaması, 3. | 8/8 | Model köke yazdı, uyarıyı aldı, dosyaları tek komutla `todo/` içine taşıdı ve `todo/index.html`'i yeniden test etti | – |
| 5 dosyalı değişiklik | 3/4 → 4/4 | Denetleyici, bir docstring'deki İngilizce "price" sözcüğünü kalıntı saydı | Denetleyici düzeltildi (yalnızca Python adları); modelin değişikliği doğruydu |

¹ Aynı dosyalar üzerinde düzeltilmiş denetleyiciyle puanlandı.

**Bağlantı kopması:** runner, görevin 97. saniyesinde, bir cevabın 71 KB'ında modelin akışını 8 sn kesti. Uygulama bunu fark etti, bekledi ve aynı modelle devam etti. Dört dosya da tamdı, hiçbiri iki kez yazılmadı.

**Modelin kendi kendine toparladığı araç hataları:** uygulamanın tanımadığı biçimde iki `edit_file` çağrısı (bir sonraki çağrı çalıştı) ve modelin kendi yazdığı, hatayla çıkan bir Python betiği.

## Kendin çalıştır

```powershell
.venv\Scripts\python.exe eval\run_eval.py --models "evren:auto,nvidia:nvidia/nemotron-3.5-super-vl-120b-a12b"
```

Rapor `eval/reports/<tarih-saat>/` klasörüne yazılır (`report.md`, `report.json`, iz kayıtları). Sonuçlarını tarih, sürüm, model ve dil ile buraya ekle.
