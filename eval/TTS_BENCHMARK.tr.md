# Türkçe TTS benchmark

[English](TTS_BENCHMARK.md) · **Türkçe**

AI IQ 300'ün her yerel Türkçe sesi aynı beş cümleyi tek bir bilgisayarda, uygulamanın üzerinden (seslendirmeyle aynı yoldan) okudu. Her sesi uygulama ölçtü; buradaki hiçbir sayı model kartından alınmadı.

**Doğruluk:** her cümle faster-whisper `small` ile yazıya çevrildi ve metinle karşılaştırıldı (CER, karakter hata oranı; düşük daha iyi; sayılar ve noktalama dışarıda bırakıldı). **Hız:** RTF = üretim süresi / ses süresi, 2-5. cümleler (1'in altı = gerçek zamandan hızlı). **İlk:** ilk cümle, model yüklemesi dahil. **Perde:** ortanca, cinsiyet denetimi.

**Bilgisayar:** Intel64 Family 6 Model 151 Stepping 5, GenuineIntel · Windows-10-10.0.19045-SP0 · CPU · 2026-11-26 22:12

> Bu bilgisayarda NVIDIA GPU yok: GPU paketleri `--force` ile kurulup CPU'da çalıştırıldı, bu yüzden buradaki hızları GPU hakkında bir şey söylemez. NVIDIA GPU'da kat kat hızlıdırlar.

| Ses | Paket | CER | RTF | İlk | Perde | Lisans | Cihaz |
|---|---|---|---|---|---|---|---|
| `supertonic:F1` | Supertonic 3 | **0.0%** | 0.20 | 2.3 s | kadın 191 | OpenRAIL-M | cpu |
| `supertonic:M1` | Supertonic 3 | **0.0%** | 0.18 | 1.0 s | erkek 140 | OpenRAIL-M | cpu |
| `ahenkcep:f022` | Ahenk Cep | **0.0%** | 0.13 | 2.4 s | kadın 221 | CC BY 4.0 | cpu |
| `anka:male` | Anka TTS | **0.0%** | 32.76 | 149.9 s | erkek 123 | CC BY-NC 4.0 (ticari değil) | cpu |
| `trendyol:default` | Trendyol TTS | **0.0%** | 12.40 | 72.9 s | erkek 110 | MIT | cpu |
| `seda:v03` | Seda TTS | **0.3%** | 0.12 | 4.6 s | kadın 245 | Apache-2.0 | cpu |
| `clarvia:male_1` | Clarvia Tiny | **0.3%** | 0.02 | 2.5 s | erkek 106 | Apache-2.0 | cpu |
| `ema:default` | EMA Lightning | **0.4%** | 0.10 | 8.1 s | kadın 253 | Apache-2.0 | cpu |
| `pocket:female_1` | Pocket TTS Türkçe | **0.4%** | 0.21 | 17.9 s | kadın 231 | CC BY 4.0 | cpu |
| `openbible:SPEAKER_00_Turkish` | VITS OpenBible | **0.6%** | 0.24 | 7.2 s | erkek 91 | CC BY-SA 4.0 | cpu |
| `clarvia:female_1` | Clarvia Tiny | **0.9%** | 0.02 | 0.1 s | kadın 175 | Apache-2.0 | cpu |
| `xtts:Aaron Dreschner` | XTTS v2 (Coqui) | **0.9%** | 1.08 | 45.1 s | erkek 108 | Coqui CPML (ticari değil) | cpu |
| `kizagan:default` | Kızagan | **0.9%** | 12.96 | 87.4 s | erkek 109 | Apache-2.0 | cpu |
| `pocket:male_1` | Pocket TTS Türkçe | **1.6%** | 0.22 | 1.4 s | erkek 110 | CC BY 4.0 | cpu |
| `turkvits:default` | Türkçe VITS | **1.9%** | 0.14 | 13.1 s | kadın 203 | Apache-2.0 | cpu |
| `xtts:Alexandra Hisakawa` | XTTS v2 (Coqui) | **2.4%** | 0.98 | 5.2 s | kadın 205 | Coqui CPML (ticari değil) | cpu |
| `drifting:studio` | Drifting TTS | **2.4%** | 0.60 | 13.5 s | erkek 110 | CC BY 4.0 | cpu |
| `freya:default` | Freya TTS | **4.7%** | 0.92 | 41.7 s | kadın 294 | Apache-2.0 | cpu |
| `drifting:male` | Drifting TTS | **4.7%** | 0.67 | 2.3 s | erkek 99 | CC BY 4.0 | cpu |
| `mms:default` | MMS-TTS (Meta) | **5.8%** | 0.17 | 26.7 s | erkek 113 | CC BY-NC 4.0 (ticari değil) | cpu |
| `drifting:female` | Drifting TTS | **7.1%** | 0.55 | 2.7 s | kadın 173 | CC BY 4.0 | cpu |

**Bu çalıştırmada ölçülmedi (kurulu; çalıştırma onlardan önce durduruldu):** Ahenk TTS, Nefes 0.5, Fish S2 Pro

## Kendin çalıştır

```powershell
.venv\Scripts\python.exe backend\voice_packs.py light
.venv\Scripts\python.exe eval\tts_bench.py
.venv\Scripts\python.exe eval\tts_report.py
```
