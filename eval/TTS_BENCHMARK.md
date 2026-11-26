# Turkish TTS benchmark

**English** · [Türkçe](TTS_BENCHMARK.tr.md)

Every local Turkish voice of AI IQ 300 read the same five sentences on one computer, through the app (the same path as a voice-over). The app measured each voice; nothing here is from a model card.

**Accuracy:** each sentence was transcribed by faster-whisper `small` and compared with the text (CER, character error rate; lower is better; numbers and punctuation are left out). **Speed:** RTF = synthesis time / audio length over sentences 2-5 (below 1 = faster than real time). **First:** the first sentence, model loading included. **Pitch:** median, the gender check.

**Computer:** Intel64 Family 6 Model 151 Stepping 5, GenuineIntel · Windows-10-10.0.19045-SP0 · CPU · 2026-11-26 22:12

> This computer has no NVIDIA GPU: the GPU packs were installed with `--force` and run on the CPU, so their speed here says nothing about a GPU. On an NVIDIA GPU they are many times faster.

| Voice | Pack | CER | RTF | First | Pitch | Licence | Device |
|---|---|---|---|---|---|---|---|
| `supertonic:F1` | Supertonic 3 | **0.0%** | 0.20 | 2.3 s | female 191 | OpenRAIL-M | cpu |
| `supertonic:M1` | Supertonic 3 | **0.0%** | 0.18 | 1.0 s | male 140 | OpenRAIL-M | cpu |
| `ahenkcep:f022` | Ahenk Cep | **0.0%** | 0.13 | 2.4 s | female 221 | CC BY 4.0 | cpu |
| `anka:male` | Anka TTS | **0.0%** | 32.76 | 149.9 s | male 123 | CC BY-NC 4.0 (non-commercial) | cpu |
| `trendyol:default` | Trendyol TTS | **0.0%** | 12.40 | 72.9 s | male 110 | MIT | cpu |
| `seda:v03` | Seda TTS | **0.3%** | 0.12 | 4.6 s | female 245 | Apache-2.0 | cpu |
| `clarvia:male_1` | Clarvia Tiny | **0.3%** | 0.02 | 2.5 s | male 106 | Apache-2.0 | cpu |
| `ema:default` | EMA Lightning | **0.4%** | 0.10 | 8.1 s | female 253 | Apache-2.0 | cpu |
| `pocket:female_1` | Pocket TTS Türkçe | **0.4%** | 0.21 | 17.9 s | female 231 | CC BY 4.0 | cpu |
| `openbible:SPEAKER_00_Turkish` | VITS OpenBible | **0.6%** | 0.24 | 7.2 s | male 91 | CC BY-SA 4.0 | cpu |
| `clarvia:female_1` | Clarvia Tiny | **0.9%** | 0.02 | 0.1 s | female 175 | Apache-2.0 | cpu |
| `xtts:Aaron Dreschner` | XTTS v2 (Coqui) | **0.9%** | 1.08 | 45.1 s | male 108 | Coqui CPML (non-commercial) | cpu |
| `kizagan:default` | Kızagan | **0.9%** | 12.96 | 87.4 s | male 109 | Apache-2.0 | cpu |
| `pocket:male_1` | Pocket TTS Türkçe | **1.6%** | 0.22 | 1.4 s | male 110 | CC BY 4.0 | cpu |
| `turkvits:default` | Türkçe VITS | **1.9%** | 0.14 | 13.1 s | female 203 | Apache-2.0 | cpu |
| `xtts:Alexandra Hisakawa` | XTTS v2 (Coqui) | **2.4%** | 0.98 | 5.2 s | female 205 | Coqui CPML (non-commercial) | cpu |
| `drifting:studio` | Drifting TTS | **2.4%** | 0.60 | 13.5 s | male 110 | CC BY 4.0 | cpu |
| `freya:default` | Freya TTS | **4.7%** | 0.92 | 41.7 s | female 294 | Apache-2.0 | cpu |
| `drifting:male` | Drifting TTS | **4.7%** | 0.67 | 2.3 s | male 99 | CC BY 4.0 | cpu |
| `mms:default` | MMS-TTS (Meta) | **5.8%** | 0.17 | 26.7 s | male 113 | CC BY-NC 4.0 (non-commercial) | cpu |
| `drifting:female` | Drifting TTS | **7.1%** | 0.55 | 2.7 s | female 173 | CC BY 4.0 | cpu |

**Not measured in this run (installed; the run was stopped before them):** Ahenk TTS, Nefes 0.5, Fish S2 Pro

## Run it yourself

```powershell
.venv\Scripts\python.exe backend\voice_packs.py light
.venv\Scripts\python.exe eval\tts_bench.py
.venv\Scripts\python.exe eval\tts_report.py
```
