# AI IQ 300 nasıl çalışır

> [English](WORKFLOW.md) · [README](README.tr.md) · [Proje durumu](PROJECT_STATE.tr.md)

Bu sayfa bir mesajın mesaj kutusundan bitmiş cevaba kadar izlediği yolu gösterir. Şemalar Mermaid kodudur; GitHub
bunları çizer, aynı kod uygulamanın sohbetinde de çizilir.

## 1. Genel bakış

```mermaid
flowchart TD
  U(["💬 Kullanıcı mesajı<br/>metin · dosya · @ajan · /yetenek · #MCP"]) --> R

  subgraph P1["1 · İsteği oku"]
    direction TB
    R["Dil ve niyet<br/>sohbet · iş · web · tarayıcı"] --> G["Görevin gerektirdiği araç grupları<br/>(need_tools: çekirdek + yalnızca uyanlar)"]
    G --> SP["Sistem istemi<br/>kimlik · kurallar · yetenekler · ajanlar"]
  end

  SP --> M{"Hangi model?"}
  M -->|"Yerel"| L["Ollama / LM Studio<br/>RAM-VRAM koruması"]
  M -->|"Bulut"| C["Bulut sağlayıcı<br/>kota kontrolü · otomatik geçiş"]
  M -->|"Ekip"| T[["Ajan ekibi<br/>havuz modellerinde aşamalar"]]
  L --> LOOP
  C --> LOOP
  T --> LOOP

  subgraph P2["2 · Araç döngüsü"]
    direction TB
    LOOP["Model turu akar<br/>düşünme · metin · araç çağrıları"] --> SPL["Akış ayrıştırıcı<br/>sohbette çağrı sözdizimi yok"]
    SPL --> Q{"Araç çağrısı var mı?"}
    Q -->|"Evet"| AP{"Onay gerekli mi?"}
    AP -->|"Evet"| ASK[/"Kullanıcıya sor"/]
    ASK --> RUN
    AP -->|"Hayır"| RUN["Araçları çalıştır<br/>paralel işler · yapılacaklar listesi güncel"]
    RUN --> GD["Korumalar<br/>tekrar · döngü · saçmalama · dosya küçülmesi · benzer arama"]
    GD --> LOOP
  end

  Q -->|"Hayır: cevap"| V

  subgraph P3["3 · Denetle ve bitir"]
    direction TB
    V{"İş gerçekten bitti mi?<br/>dosyalar · sayfalar · testler · sözler"} -->|"Hayır"| FIX["İşe geri dön<br/>hata ayıklayıcı ipucu, gerçek hata metni"]
    V -->|"Evet"| SAVE["Kontrol noktası ve geçmiş<br/>durdurmadan sonra devam"]
  end

  FIX --> LOOP
  SAVE --> A(["✅ Cevap + adımlar<br/>şemalar · dosyalar · önizlemeler"])

  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  classDef warn fill:#fef3c7,stroke:#d97706,color:#78350f
  classDef ext fill:#ede9fe,stroke:#7c3aed,color:#3b0764
  class A ok
  class FIX,ASK warn
  class T,C ext
```

- **İsteği oku.** Önce cevap dili ve niyet belirlenir. İstem yalnızca bu sohbetin ihtiyaç duyduğu araç gruplarını
  taşır; küçük ve yerel modeller kısa bir istem alır.
- **Modeli seç.** Yerel model ancak bilgisayarda yeterli bellek varsa yüklenir. Bulut modelin kotası kontrol edilir,
  kota bitince görev başka bir modele geçer. Ekip, işi aşamalara böler.
- **Araç döngüsü.** Model düşüncesini, metnini ve araç çağrılarını akıtır. Ayrıştırıcı her çağrı biçimini sohbetten
  gizler. Araçlar (mümkünse paralel) çalışır, yapılacaklar listesi işi izler; korumalar tekrarları, döngüleri,
  saçmalamayı ve içerik kaybettirecek dosya yeniden yazımlarını durdurur.
- **Denetle ve bitir.** Yalnızca söz veren ya da olmayan dosya ve testleri iddia eden cevap, gerçek hata metniyle
  döngüye geri döner. Biten görev kontrol noktası olarak kaydedilir ve adımlarıyla gösterilir.

## 2. Bir model turu

```mermaid
sequenceDiagram
  autonumber
  actor U as Kullanıcı
  participant O as Orkestratör
  participant S as Akış + ayrıştırıcı
  participant P as Sağlayıcı bağdaştırıcı
  participant T as Araçlar
  U->>O: Mesaj
  O->>O: İstem, araç grupları, geçmiş (eski adımlar kısaltılır)
  O->>S: Turu başlat
  S->>P: İstek (yerel araçlar ya da etiket protokolü)
  P-->>S: Düşünme · metin · araç çağrıları (akış)
  S-->>U: Canlı metin ve adımlar (çağrı sözdizimi yok)
  alt turda araç çağrısı var
    S->>O: Ayrıştırılmış çağrılar
    O->>T: Çalıştır (onay, tekrar ve dosya korumaları)
    T-->>O: Sonuçlar
    O->>S: Sonuçlarla sonraki tur
  else son cevap
    O->>O: Denetimler: sözler, eksik dosyalar, bitmemiş maddeler
    O-->>U: Cevap + adımlar
  end
```

## 3. Ajan ekibi (bulut çoklu model)

```mermaid
flowchart LR
  MAIN["Ana ajan<br/>aşamaları planlar"] --> S1
  subgraph S1["Aşama 1 · paralel"]
    direction TB
    A1["Üye A<br/>havuz modeli 1"]
    A2["Üye B<br/>havuz modeli 2"]
  end
  S1 --> S2
  subgraph S2["Aşama 2 · aşama 1 dosyalarını kullanır"]
    direction TB
    B1["Üye C<br/>havuz modeli 3"]
  end
  S2 --> CHK{"Rapor ve dosyalar tamam mı?"}
  CHK -->|"Evet"| DONE(["Ana ajan cevabı yazar"])
  CHK -->|"Hayır"| MAIN
  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  class DONE ok
```

Her üye havuzdaki bir modelde kendi araç döngüsünü çalıştırır. Aynı aşamanın üyeleri paralel çalışır; sonraki aşama
öncekilerin dosyalarını okur. Kotası dolan model havuzdaki başka bir modelle değiştirilir.

## 4. Kodda nerede

| Adım | Modül |
|---|---|
| Dil, niyet, araç grupları, cevap denetimleri | `backend/app/agents/checks.py` |
| Sistem istemi (kimlik, kurallar, yetenek haritası) | `agents/prompts.py`, `agents/prompting.py` |
| Çalışma döngüsü, son denetimler | `agents/orchestrator.py` |
| Akan bir tur, takılmalar, döngüler | `agents/streaming.py`, `agents/stream_parser.py` |
| Araçları çalıştırma, yapılacaklar, tekrar koruması | `agents/tooling.py` |
| Çıktı korumaları (tekrar, saçmalama, kelime salatası) | `agents/guards.py` |
| Kontrol noktaları, devam, kesilen dosyalar | `agents/continuity.py` |
| Ajan ekipleri | `agents/team.py` |
| Sağlayıcılar, yönlendirme, kotalar, model aileleri | `llm/providers.py`, `llm/router.py`, `llm/usage.py`, `llm/families.py` |
| Yerel modeller için RAM / VRAM koruması | `llm/memguard.py` |
| Araçlar (dosya, kabuk, web, tarayıcı, belge, medya, şema, sistem) | `backend/app/tools/` |
| Sohbet, şemalar, önizlemeler | `frontend/src/components/` |
