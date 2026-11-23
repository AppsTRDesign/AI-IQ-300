"""A scripted OpenAI-compatible model that solves the five eval tasks with real tool calls (run_eval.py --models mock).
It checks the runner and the checkers without a real model: every check must pass against it.

    python mock_solver.py <port>
"""
import asyncio
import json
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()


def w(path: str, text: str) -> str:
    return f'<tool name="write_file" path="{path}">{text}</tool>\n'


INDEX = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>Yapılacaklar</title><link rel="stylesheet" href="style.css"></head>
<body><main><h1>Yapılacaklar</h1>
<div class="row"><input id="new-todo" placeholder="Yeni iş"><button id="add">Ekle</button></div>
<ul id="list"></ul></main><script src="app.js"></script></body></html>
"""
CSS = "body{font-family:system-ui;margin:2rem}main{max-width:30rem}.row{display:flex;gap:.5rem}li{padding:.3rem 0}\n"
JS = """const KEY = "todos";
const list = document.getElementById("list");
const box = document.getElementById("new-todo");
let items = [];
try { items = JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { items = []; }
function draw() {
  list.innerHTML = "";
  for (const t of items) { const li = document.createElement("li"); li.textContent = t; list.appendChild(li); }
}
document.getElementById("add").addEventListener("click", () => {
  const t = box.value.trim();
  if (!t) return;
  items.push(t);
  localStorage.setItem(KEY, JSON.stringify(items));
  box.value = "";
  draw();
});
draw();
"""
STATS = '''"""Small statistics helpers.

mean([])       -> ValueError
median(xs)     -> middle value; for an even count the mean of the two middle values
mode(xs)       -> the most common value; on a tie the smallest of them
variance(xs)   -> sample variance (divides by n - 1); fewer than 2 values -> ValueError
clamp(x, lo, hi) -> x limited to [lo, hi]
"""


def mean(xs):
    if not xs:
        raise ValueError("mean of an empty list")
    return sum(xs) / len(xs)


def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        raise ValueError("median of an empty list")
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def mode(xs):
    counts = {}
    for x in xs:
        counts[x] = counts.get(x, 0) + 1
    return min(counts, key=lambda k: (-counts[k], k))


def variance(xs):
    if len(xs) < 2:
        raise ValueError("variance needs at least two values")
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))
'''
SHOP = {
    "shop/models.py": "from dataclasses import dataclass\n\n\n@dataclass\nclass Product:\n    name: str\n    unit_price: float\n"
                      "    qty: int = 0\n\n    def value(self) -> float:\n        return self.unit_price * self.qty\n",
    "shop/inventory.py": "from .models import Product\n\n\nclass Inventory:\n    def __init__(self):\n        self.items: dict[str, Product] = {}\n\n"
                         "    def add(self, name: str, unit_price: float, qty: int = 0) -> Product:\n        p = self.items.get(name)\n"
                         "        if p:\n            p.qty += qty\n            p.unit_price = unit_price\n        else:\n"
                         "            p = self.items[name] = Product(name, unit_price, qty)\n        return p\n\n"
                         "    def total(self) -> float:\n        return round(sum(p.value() for p in self.items.values()), 2)\n\n"
                         "    def cheapest(self) -> Product | None:\n        return min(self.items.values(), key=lambda p: p.unit_price, default=None)\n\n"
                         "    def low_stock(self, limit: int = 5) -> list[Product]:\n        return [p for p in self.items.values() if p.qty < limit]\n",
    "shop/pricing.py": "from .models import Product\n\n\ndef discounted(p: Product, percent: float) -> float:\n"
                       "    return round(p.unit_price * (1 - percent / 100), 2)\n\n\ndef with_tax(p: Product, rate: float = 0.20) -> float:\n"
                       "    return round(p.unit_price * (1 + rate), 2)\n",
    "shop/report.py": "from .inventory import Inventory\n\n\ndef render(inv: Inventory) -> str:\n    lines = [\"INVENTORY\"]\n"
                      "    for p in sorted(inv.items.values(), key=lambda p: p.name):\n"
                      "        lines.append(f\"{p.name:<12} {p.qty:>4} x {p.unit_price:>8.2f}\")\n"
                      "    lines.append(f\"TOTAL {inv.total():.2f}\")\n    lines.append(\"Low stock:\")\n"
                      "    for p in inv.low_stock():\n        lines.append(f\"  {p.name} ({p.qty})\")\n    return \"\\n\".join(lines)\n",
    "shop/cli.py": "from .inventory import Inventory\nfrom .pricing import discounted\nfrom .report import render\n\n\n"
                   "def demo() -> Inventory:\n    inv = Inventory()\n    inv.add(\"apple\", 0.5, 40)\n    inv.add(\"bread\", 2.25, 3)\n"
                   "    inv.add(\"cheese\", 7.8, 12)\n    inv.add(\"milk\", 1.1, 2)\n    return inv\n\n\ndef main() -> None:\n"
                   "    inv = demo()\n    print(render(inv))\n    p = inv.cheapest()\n"
                   "    print(f\"cheapest: {p.name} {p.unit_price:.2f} (-10%: {discounted(p, 10):.2f})\")\n\n\n"
                   "if __name__ == \"__main__\":\n    main()\n",
    "README.md": "# shop\n\nA tiny inventory demo.\n\n- `Product(name, unit_price, qty)`: `value()` is `unit_price * qty`.\n"
                 "- `Inventory.add`, `total()`, `cheapest()`, `low_stock(limit=5)` (qty < limit).\n"
                 "- `python -m shop.cli` prints the report with a Low stock section.\n",
}
PARA = ("Python okunması kolay bir dildir ve yeni başlayanlar onu hızla öğrenir. Geniş standart kütüphanesi dosya, ağ ve "
        "veri işlerini ek paket olmadan çözer. Topluluğu büyüktür; bilimsel hesaplama, web ve otomasyon için olgun "
        "kütüphaneler vardır. ")
DOC_TR = (f"# Python Raporu\n\n## Giriş\n\n{PARA * 2}\n\n## Güçlü Yanlar\n\n- **Okunabilirlik:** {PARA}\n- **Kütüphaneler:** {PARA}\n"
          f"- **Topluluk:** {PARA}\n\n## Sonuç\n\n{PARA}\n")
DOC_EN = DOC_TR.replace("Python Raporu", "Python Report").replace("## Giriş", "## Introduction").replace(
    "## Güçlü Yanlar", "## Strengths").replace("## Sonuç", "## Conclusion")
PLANETS = {
    "a.md": "Merkür Güneş'e en yakın gezegendir. Bir yılı 88 gün sürer. Atmosferi neredeyse yoktur. Gündüz çok sıcak, gece çok soğuktur. Yüzeyi kraterlerle kaplıdır.",
    "b.md": "Venüs en sıcak gezegendir. Kalın bir karbondioksit atmosferi vardır. Kendi ekseninde ters yönde döner. Bir günü bir yılından uzundur. Bulutları sülfürik asit içerir.",
    "c.md": "Mars kızıl gezegendir. Yüzeyindeki demir oksit ona rengini verir. İki küçük uydusu vardır. Olympus Mons Güneş sisteminin en yüksek dağıdır. Kutuplarında buz bulunur.",
    "d.md": "Jüpiter en büyük gezegendir. Bir gaz devidir. Büyük Kırmızı Leke yüzyıllardır süren bir fırtınadır. Onlarca uydusu vardır. Kütlesi diğer gezegenlerin toplamından büyüktür.",
}
PLANETS_EN = {
    "a.md": "Mercury is the planet closest to the Sun. Its year lasts 88 days. It has almost no atmosphere. Days are very hot and nights very cold. Its surface is covered with craters.",
    "b.md": "Venus is the hottest planet. It has a thick carbon dioxide atmosphere. It spins backwards on its axis. Its day is longer than its year. Its clouds contain sulfuric acid.",
    "c.md": "Mars is the red planet. Iron oxide on its surface gives it its colour. It has two small moons. Olympus Mons is the highest mountain in the Solar System. There is ice at its poles.",
    "d.md": "Jupiter is the largest planet. It is a gas giant. The Great Red Spot is a storm that has lasted for centuries. It has dozens of moons. Its mass is greater than all other planets together.",
}


def script(first: str) -> tuple[list[str], float]:
    en = "Build a small" in first or "stats.py is broken" in first or "In this project" in first or "Write a short report" in first or "Write four files" in first
    if "todo/" in first:
        return [w("todo/index.html", INDEX) + w("todo/style.css", CSS) + w("todo/app.js", JS), "Hazır: todo/ çalışıyor."], 0
    if "stats.py" in first:
        return [w("stats.py", STATS), '<tool name="run">python -m pytest -q test_stats.py</tool>', "Düzeltildi, testler geçiyor."], 0
    if "unit_price" in first:
        return ["".join(w(p, t) for p, t in SHOP.items()), '<tool name="run">python -m shop.cli</tool>', "Tamam."], 0
    if "docx" in first:
        doc, name = (DOC_EN, "report") if en else (DOC_TR, "rapor")
        return [f'<tool name="make_doc" type="docx" path="docs/{name}.docx">{doc}</tool>\n'
                f'<tool name="make_doc" type="pdf" path="docs/{name}.pdf">{doc}</tool>',
                f'<tool name="read_document" path="docs/{name}.pdf"></tool>', "Belgeler hazır ve doğrulandı."], 0
    if "notes/" in first:
        texts = PLANETS_EN if en else PLANETS
        return [f"{n} yazılıyor.\n" + w(f"notes/{n}", t) for n, t in texts.items()] + ["Dört dosya yazıldı."], 0.04
    return ["Merhaba."], 0


def chunk(text):
    return "data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\n\n"


@app.get("/v1/models")
def models():
    return {"data": [{"id": "solver", "context_length": 64000}]}


@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    msgs = body["messages"]
    system = next((str(m["content"]) for m in msgs if m["role"] == "system"), "")
    users = [str(m.get("content") or "") for m in msgs if m["role"] == "user"]
    last = users[-1] if users else ""
    delay = 0.0
    if last == "ping" and body.get("max_tokens") == 1:
        text = "p"
    elif "Write a short title" in system or "Summarize the conversation" in system:
        text = "Eval"
    else:
        steps, delay = script(users[0] if users else "")
        asst = [str(m.get("content") or "") for m in msgs if m["role"] == "assistant"]
        k = len(asst)
        if "connection dropped" in last.lower() and asst:
            # continue the reply that was cut: the part after what already came through
            k -= 1
            want = steps[min(k, len(steps) - 1)]
            part = asst[-1]
            if want.startswith(part):
                text = want[len(part):]
            else:
                tail = part[-40:]
                i = want.find(tail) if tail else -1
                text = want[i + len(tail):] if i >= 0 else want
        else:
            text = steps[min(k, len(steps) - 1)]

    async def gen():
        for i in range(0, len(text), 12):
            yield chunk(text[i:i + 12])
            await asyncio.sleep(delay or 0.002)
        yield "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}],
                                     "usage": {"prompt_tokens": sum(len(str(m.get('content') or '')) for m in msgs) // 4,
                                               "completion_tokens": max(1, len(text) // 4)}}) + "\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
