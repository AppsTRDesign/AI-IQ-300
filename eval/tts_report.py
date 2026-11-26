"""eval/tts/results.json -> eval/TTS_BENCHMARK.md and eval/TTS_BENCHMARK.tr.md (tables, sorted by accuracy).

    python eval/tts_report.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "eval" / "tts" / "results.json"

T = {
    "en": {
        "title": "Turkish TTS benchmark", "other": "[Türkçe](TTS_BENCHMARK.tr.md)", "me": "**English**",
        "intro": "Every local Turkish voice of AI IQ 300 read the same five sentences on one computer, through the app "
                 "(the same path as a voice-over). The app measured each voice; nothing here is from a model card.",
        "how": "**Accuracy:** each sentence was transcribed by faster-whisper `{w}` and compared with the text (CER, "
               "character error rate; lower is better; numbers and punctuation are left out). **Speed:** RTF = "
               "synthesis time / audio length over sentences 2-5 (below 1 = faster than real time). **First:** the "
               "first sentence, model loading included. **Pitch:** median, the gender check.",
        "machine": "Computer", "cols": ["Voice", "Pack", "CER", "RTF", "First", "Pitch", "Hz", "Licence", "Device"],
        "failed": "Did not run on this computer", "nc": "non-commercial", "cpu_note":
        "This computer has no NVIDIA GPU: the GPU packs were installed with `--force` and run on the CPU, so their "
        "speed here says nothing about a GPU. On an NVIDIA GPU they are many times faster.",
        "run": "Run it yourself", "f": "female", "m": "male", "u": "?",
        "not_run": "Not measured in this run (installed; the run was stopped before them)",
    },
    "tr": {
        "title": "Türkçe TTS benchmark", "other": "**Türkçe**", "me": "[English](TTS_BENCHMARK.md)",
        "intro": "AI IQ 300'ün her yerel Türkçe sesi aynı beş cümleyi tek bir bilgisayarda, uygulamanın üzerinden "
                 "(seslendirmeyle aynı yoldan) okudu. Her sesi uygulama ölçtü; buradaki hiçbir sayı model kartından "
                 "alınmadı.",
        "how": "**Doğruluk:** her cümle faster-whisper `{w}` ile yazıya çevrildi ve metinle karşılaştırıldı (CER, "
               "karakter hata oranı; düşük daha iyi; sayılar ve noktalama dışarıda bırakıldı). **Hız:** RTF = üretim "
               "süresi / ses süresi, 2-5. cümleler (1'in altı = gerçek zamandan hızlı). **İlk:** ilk cümle, model "
               "yüklemesi dahil. **Perde:** ortanca, cinsiyet denetimi.",
        "machine": "Bilgisayar", "cols": ["Ses", "Paket", "CER", "RTF", "İlk", "Perde", "Hz", "Lisans", "Cihaz"],
        "failed": "Bu bilgisayarda çalışmadı", "nc": "ticari değil", "cpu_note":
        "Bu bilgisayarda NVIDIA GPU yok: GPU paketleri `--force` ile kurulup CPU'da çalıştırıldı, bu yüzden buradaki "
        "hızları GPU hakkında bir şey söylemez. NVIDIA GPU'da kat kat hızlıdırlar.",
        "run": "Kendin çalıştır", "f": "kadın", "m": "erkek", "u": "?",
        "not_run": "Bu çalıştırmada ölçülmedi (kurulu; çalıştırma onlardan önce durduruldu)",
    },
}


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    rows = data["results"]
    for lang, t in T.items():
        name = "TTS_BENCHMARK.md" if lang == "en" else "TTS_BENCHMARK.tr.md"
        hw = data["machine"]["hardware"]
        out = [f"# {t['title']}", "", f"{t['me']} · {t['other']}" if lang == "en" else f"{t['me']} · {t['other']}",
               "", t["intro"], "", t["how"].format(w=data["whisper"]), "",
               f"**{t['machine']}:** {data['machine']['cpu']} · {data['machine']['os']} · "
               f"{'NVIDIA ' + str(hw['vram_gb']) + ' GB' if hw.get('cuda') else 'CPU'} · {data['at']}", ""]
        if not hw.get("cuda"):
            out += [f"> {t['cpu_note']}", ""]
        c = t["cols"]
        out += [f"| {c[0]} | {c[1]} | {c[2]} | {c[3]} | {c[4]} | {c[5]} | {c[7]} | {c[8]} |",
                "|---|---|---|---|---|---|---|---|"]
        for r in [r for r in rows if r.get("ok")]:
            g = {"female": t["f"], "male": t["m"]}.get(r.get("gender"), t["u"])
            lic = r["license"] + ("" if r.get("commercial", True) else f" ({t['nc']})")
            out.append(f"| `{r['voice']}` | {r['name']} | **{r['cer'] * 100:.1f}%** | {r['rtf']:.2f} | "
                       f"{r['first_s']:.1f} s | {g} {r['pitch_hz']} | {lic} | {r.get('device', 'cpu')} |")
        bad = [r for r in rows if not r.get("ok")]
        if bad:
            out += ["", f"**{t['failed']}:**", ""]
            out += [f"- `{r['voice']}` ({r['name']}): {r.get('error', '')[:200]}" for r in bad]
        done = {r["voice"].split(":", 1)[0] for r in rows}
        sys.path.insert(0, str(ROOT / "backend"))
        from app.voice import packs
        left = [p["name"] for e, p in packs.PACKS.items() if e not in done]
        if left:  # packs this run did not reach (a run can be stopped: the big GPU packs take minutes a sentence on a CPU)
            out += ["", f"**{t['not_run']}:** {', '.join(left)}"]
        out += ["", f"## {t['run']}", "", "```powershell", ".venv\\Scripts\\python.exe backend\\voice_packs.py light",
                ".venv\\Scripts\\python.exe eval\\tts_bench.py", ".venv\\Scripts\\python.exe eval\\tts_report.py",
                "```", ""]
        (ROOT / "eval" / name).write_text("\n".join(out), encoding="utf-8")
        print("written", name)


if __name__ == "__main__":
    main()
