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
    V -->|"Evet"| SAVE["Kontrol noktası ve sohbet defteri<br/>durdurmadan sonra devam · unutma yok"]
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
  döngüye geri döner. Biten görev kontrol noktası olarak kaydedilir ve adımlarıyla gösterilir. Uygulama sohbet defterini de yazar
  (dosyalar, komutlar, ortam, hatalar); sonraki görev neyin yapıldığını bilerek başlar.

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

## 4. Uç durumlar

İşler plana göre gitmediğinde uygulamanın ne yaptığı. Her şema kodun bugünkü davranışını izler; modül adları aşağıdaki
tablodadır.

### 4.1 Görev ortasında durdurma

```mermaid
flowchart TD
  S(["⏹ Kullanıcı Durdur'a basar"]) --> C["Model akışı iptal edilir"]
  C --> K["Hemen temizlenir:<br/>bekleyen onaylar · görünür tarayıcı ·<br/>çalışan komutlar · bu görevin sunucuları"]
  K --> R["Çalışan adımlar durduruldu olarak işaretlenir<br/>yapılan adımlar Devam için saklanır"]
  R --> L["Sohbet defteri görevi iptal edildi olarak kaydeder"]
  L --> M(["Mesaj: Durduruldu<br/>düğmeler: Devam · Bu görevin dosya değişikliklerini geri al"])
  M -->|"Devam"| RES["Devam: yapılan adımların kaydı<br/>modele gider, hiçbiri tekrarlanmaz"]
  M -->|"Geri al"| U{"Dosya hâlâ görevin<br/>bıraktığı gibi mi?"}
  U -->|"Evet"| B["Geri konur: eski içerik döner,<br/>yeni dosyalar silinir, silinenler geri gelir"]
  U -->|"Hayır, sonra değişmiş"| KEEP["Olduğu gibi bırakılır ve listelenir"]
  classDef warn fill:#fef3c7,stroke:#d97706,color:#78350f
  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  class KEEP warn
  class B,RES ok
```

- **Geri alınanlar:** `write_file`, `edit_file` ve `delete_file` ile değişen dosyalar. Her dosyanın görevin ilk
  değişikliğinden önceki hâli, sohbetin son 5 görevi için saklanır.
- **Geri alınmayanlar:** kabuk komutlarının yaptığı değişiklikler (derleme, `npm install`, bir betik). Projelerde
  bunları Dosyalar altındaki git zaman makinesi karşılar.
- Görevden sonra kullanıcının (ya da sonraki bir görevin) değiştirdiği dosyanın üzerine geri alma asla yazmaz.

### 4.2 İki ajan aynı dosyayı değiştirir

```mermaid
flowchart TD
  A["Ajan A app.js'i yazar"] --> V["Uygulama not eder: app.js sürüm 2, yazan A"]
  B["Ajan B (sürüm 1'i okumuştu) app.js'in tamamını yeniden yazar"] --> CHK{"B sürüm 2'yi gördü mü?"}
  V --> CHK
  CHK -->|"Hayır"| REF["Reddedilir: sen okuduktan sonra A değiştirdi<br/>yeniden oku, yalnızca kendi bölümünü değiştir"]
  REF --> RD["B: read_file, ardından edit_file"]
  RD --> LOCK
  CHK -->|"Evet"| LOCK["Dosya başına kilit: aynı anda tek yazar"]
  LOCK --> AT["Atomik değiştirme: geçici dosya, sonra takas<br/>diskteki baytlar denetlenir; uyuşmazsa eski içerik döner"]
  AT --> OK(["İki değişiklik de korunur"])
  classDef warn fill:#fef3c7,stroke:#d97706,color:#78350f
  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  class REF warn
  class OK ok
```

- `edit_file` ve `write_file append` her zaman dosyanın kilit altındaki o anki hâline uygulanır; başka ajanın
  değişikliğini kaybettirmez.
- Tam yeniden yazım yalnızca **aynı görevin** başka bir ajanı dosyayı, bu ajan son okuduktan sonra değiştirdiyse
  reddedilir. Sohbetin sonraki bir görevi paralel yazar sayılmaz.
- Yeniden yazım üçüncü denemede geçer; böylece tamamı okunamayacak kadar büyük bir dosya çıkmaza girmez. Eski sürümü
  `.aiiq/backups` klasöründe durur.

### 4.3 Görev ortasında model değişir

```mermaid
flowchart TD
  E{"Kota bitti, sağlayıcı meşgul<br/>ya da bağlantı koptu"} -->|"Çoklu model açık, otomatik geçiş"| P["En müsait havuz modeli seçilir<br/>(görev başına en çok 3 geçiş)"]
  E -->|"Kapalı"| W["Bekle ve aynı modeli yeniden dene<br/>ya da devam ettirilebilir hatayla dur"]
  P --> H["Aynı konuşma + devir notu:<br/>yapılacaklar listesi aynen, [x] olanlar bitti"]
  H --> D["Yapılmış çağrıların kaydı<br/>+ yazılan dosyalar (diskte var)"]
  D --> G["Tekrar korumaları: aynı sonucu veren aynı çağrı<br/>yeniden çalıştırılmaz"]
  G --> CUT{"Dosya yazılırken mi koptu?"}
  CUT -->|"Evet"| SV["Yazılan kısım kaydedilir<br/>yeni model append ile devam eder"]
  CUT -->|"Hayır"| GO(["Yeni model kaldığı maddeden devam eder"])
  SV --> GO
  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  class GO ok
```

### 4.4 İşe yaramayan düzeltme

Kullanıcının kuralı: **devre kesici yok**. Hata kodlamanın parçasıdır; hata sayısı görevi asla durdurmaz, dosya ve
komut araçlarını kapatmaz. Uygulamanın engellediği şey *aynı* şeyin tekrar tekrar olmasıdır.

```mermaid
flowchart TD
  F["Bir araç çağrısı başarısız olur"] --> S1{"Aynı çağrı aynı hatayla<br/>iki kez başarısız oldu mu?"}
  S1 -->|"Evet"| NR["Üçüncü kez çalıştırılmaz:<br/>bayrakları değil yolu değiştir"]
  S1 -->|"Hayır"| S2{"Aynı hata türü 3., 6., 9.…<br/>kez mi geri geldi?"}
  S2 -->|"Evet"| EX["Modele söylenir: düzeltmelerin nedene ulaşmıyor.<br/>Denediklerin şunlar. Hatayı ve satırını oku,<br/>kök nedeni söyle, tam mesajı ara"]
  S2 -->|"Hayır"| S3{"Bu sohbetin önceki bir<br/>görevinde görüldü mü?"}
  S3 -->|"Evet"| PR["Belirtilir: bu hata N. görevi de durdurmuştu"]
  S3 -->|"Hayır"| ON(["Model hatayı görür ve çalışmaya devam eder"])
  NR --> ON
  EX --> ON
  PR --> ON
  classDef warn fill:#fef3c7,stroke:#d97706,color:#78350f
  classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
  class NR,EX,PR warn
  class ON ok
```

- **Art arda her 4 başarısız turda:** "takıldın, başka bir yol izle".
- **Aynı çağrı aynı sonucu 3 kez verirse:** açıklamalı bir hataya çevrilir.
- **İşin kendisi için gerekmeyen araçlar** (örneğin sürekli reddeden bir arama API'si) aynı hatayı 3 kez verince o görev için kapanır. Dosya, komut ve okuma araçları asla kapanmaz.
- **Adım sınırı** (Ayarlar > Ajan, varsayılan 60, sınırsız da olabilir) görevi bitirir; "Devam" yapılanların kaydıyla sürdürür.

## 5. Kodda nerede

| Adım | Modül |
|---|---|
| Dil, niyet, araç grupları, cevap denetimleri | `backend/app/agents/checks.py` |
| Sistem istemi (kimlik, kurallar, yetenek haritası) | `agents/prompts.py`, `agents/prompting.py` |
| Çalışma döngüsü, son denetimler | `agents/orchestrator.py` |
| Akan bir tur, takılmalar, döngüler | `agents/streaming.py`, `agents/stream_parser.py` |
| Araçları çalıştırma, yapılacaklar, tekrar koruması | `agents/tooling.py` |
| Çıktı korumaları (tekrar, saçmalama, kelime salatası) | `agents/guards.py` |
| Kontrol noktaları, devam, kesilen dosyalar | `agents/continuity.py` |
| Sohbet defteri (önceki görevler ne yaptı; `recall`) | `agents/ledger.py` |
| Dosya kilitleri, atomik yazım, paralel değişiklik denetimi | `tools/safe_io.py` |
| Bir görevin dosya değişikliklerini geri alma | `tools/undo.py` |
| Tekrarlayan hata notları, tekrar korumaları | `agents/tooling.py` |
| Model değişiminden sonra devir | `agents/continuity.py` (`_handover`), `agents/orchestrator.py` |
| Ajan ekipleri | `agents/team.py` |
| Sağlayıcılar, yönlendirme, kotalar, model aileleri | `llm/providers.py`, `llm/router.py`, `llm/usage.py`, `llm/families.py` |
| Yerel modeller için RAM / VRAM koruması | `llm/memguard.py` |
| Araçlar (dosya, kabuk, web, tarayıcı, belge, medya, şema, sistem) | `backend/app/tools/` |
| Sohbet, şemalar, önizlemeler | `frontend/src/components/` |
