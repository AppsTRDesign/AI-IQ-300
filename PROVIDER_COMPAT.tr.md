# Sağlayıcı uyumluluğu: araştırma ve plan (2026-11-22)

Bu belge, ayarlardaki sağlayıcıların akış (streaming), araç çağrısı ve düşünme davranışlarını, AI IQ 300'ün bunları nasıl karşıladığıyla karşılaştırır. "Kopma" sorunlarının çoğunun kökü burada: sağlayıcı/sunucu davranışı ile bizim varsayımlarımız uyuşmadığında akış susuyor ya da kesiliyor.

## Kopmaların asıl nedenleri (kayıtlardan + belgelerden)

| Belirti (kayıtlarda) | Neden | Durum |
|---|---|---|
| "no data for 62/90/92 s", sağlayıcı yeni isteğe 1 sn'de cevap veriyor | vLLM/NIM araç parser'ı, araç çağrısının argümanlarını **tamamlanana kadar biriktiriyor**; o sürede tek bayt gelmiyor, araya giren vekil/ağ geçidi boşta kalan bağlantıyı kesiyor. NVIDIA forumunda aynı durum: argümanlar akmıyor, 300 sn sessizlikte akış finish_reason olmadan kapanıyor. | Var olan: sessiz yazan sağlayıcı metin protokolüne geçirilir (dosya metin olarak akar). |
| "the provider ends a request after about 194 s" (evren) | Evren tarafında her isteğe sabit üst süre var (ölçülen 194 sn). DeepSeek her turda 120–190 sn **düşündüğü** için yazmaya zaman kalmıyordu. | **Düzeltildi:** evren'de araçlı isteklerde `thinking_token_budget` süre sınırına ve model hızına göre veriliyor. |
| "Düşünme kapalı" iken DeepSeek yine düşünüyor | Kod yalnızca `chat_template_kwargs.enable_thinking=false` gönderiyordu; bu Qwen/Nemotron/GLM anahtarı. vLLM belgesine göre DeepSeek V3.1+ şablonu `thinking` anahtarını okuyor. | **Düzeltildi:** ikisi birden gönderiliyor (şablon tanımadığını yok sayar); NVIDIA NIM'e de uygulanıyor. |
| Dosya 80K → 0, game.js 50K kayıp | Bizim hatamız: canlı yazma, var olan dosyanın düz yeniden yazımında geri yükleme tabanını `""` tutuyordu; kopunca dosya boşalıyordu. İkinci kopmada kesik yeniden yazım dosyanın üstüne yazılıyordu. | **Düzeltildi:** dosya guard (aşağıda). |
| "Hazırlanıyor tool_my_location", döngü | (1) Bazı OpenAI uyumlu sunucular araç adını her parçada yeniden yolluyor; birleşince ad bozuluyordu. (2) Argümansız araçta argüman döngüsü. (3) Eksik çeviri anahtarı ham adı gösteriyordu. | **Düzeltildi:** ad tekrarı birleştirilmiyor; kısa argümanlı araçta 3000+ karakter döngü sayılıp kesiliyor; 32 eksik araç etiketi TR/EN eklendi. |

## Sağlayıcı bazında

- **Evren (vLLM, OpenAI uyumlu)**: SSE, `stream_options.include_usage` destekli. Araç argümanları modele/parser'a göre biriktirilebilir. Düşünme `chat_template_kwargs` ile (`enable_thinking` / `thinking`). İstek başına sabit süre sınırı var (ölçülüyor: `data/request_caps.json`). DeepSeek'te araç çağrısı vLLM belgesine göre düşünmesiz modda destekleniyor.
- **NVIDIA NIM (integrate.api.nvidia.com)**: OpenAI uyumlu. Düşünme `chat_template_kwargs.enable_thinking`, ayrıca `thinking_token_budget`. Araç argümanları akmıyor ve 300 sn sessizlikte akış kapanıyor (forum bildirimi; bizde de görüldü). NIM sürüm notlarında akış + araç çağrısında parser hatası için öneri: araçlı isteklerde `stream:false`.
- **Ollama (yerel / Cloud)**: `/api/chat` NDJSON akışı. Araç çağrıları parça parça değil bütün gelir. CPU'da ilk token dakikalar sürebilir (yerel sessizlik kesilmez).
- **Google Gemini (OpenAI uyumluluk katmanı)**: Akıştaki `tool_calls` parçalarında `index` olmayabilir, `id` boş gelebilir, argümanlar tek parçada gelir, finish_reason `stop` olabilir. Gemini 3'te `thought_signature` geri gönderilmezse 400. Bizde: index yoksa yeni çağrı sayılıyor, boş id üretiliyor, imza `extra_content` ile geri gidiyor.
- **Mistral**: araç çağrısı kimliği **tam 9 harf/rakam** olmalı, yoksa 422. **Düzeltildi:** başka sağlayıcıdan gelen kimlikler çağrıda ve sonucunda aynı şekilde 9 karaktere eşleniyor.
- **OpenRouter**: SSE yorum satırlarıyla canlı tutma (`: OPENROUTER PROCESSING`) gönderir; bizde `_ping` olarak sayılıyor. Düşünme `reasoning` nesnesiyle.
- **Anthropic (yerel API)**: SSE olayları, `ping`, araç argümanları `input_json_delta` ile akar (sessiz kalmaz).
- **Groq, Cerebras, SambaNova, Together, Fireworks, DeepSeek, xAI, Moonshot, Z.ai, MiniMax, HF router, Requesty, Vercel, Poe**: OpenAI uyumlu. Çoğu araç argümanlarını tek parçada gönderir. Kısıtlar (rpm, eşzamanlılık) ayarlarda tutuluyor. Model bazlı düşünme anahtarları farklı (MiniMax `thinking_mode`, Kimi `thinking`).

## Plan (yapılanlar ✓ / sıradakiler)

1. ✓ Dosya guard: bu görevde yazılmış bir dosya, unutulmuş bir yeniden yazımla küçültülemez. İlk deneme reddedilir ve dosyanın gerçek sonu gösterilir; bilinçli tekrar yedekle geçer. İkinci kopma kayıtlı dosyayı asla ezmez (`.cut-rewrite.txt` yanına konur); düz devam yazımı sona eklenir. Canlı yazma var olan dosyayı yeniden yazarken hiç dokunmaz.
2. ✓ Kopmadan sonra modele kayıtlı dosyanın **gerçek diskteki sonu** (1200 karakter) gösteriliyor, hafızasındaki değil.
3. ✓ Düşünme kapatma anahtarları (vLLM/NIM) ve evren için düşünme bütçesi.
4. ✓ Kapatılmamış araç çağrısı bir sonrakini yutmuyor (arama sızıntısı); arama sorgusu protokol parçalarından temizleniyor.
5. ✓ `run`: 120 sn hiç çıktı vermeyen ya da port dinleyen komut arka plana alınıyor; görev kilitlenmiyor.
6. ✓ NIM: akış sırasında araç ayrıştırıcısı hata veren araçlı istek `stream:false` ile tekrarlanıyor.
7. ✓ Kimi / Z.ai `thinking:{type}`, Cerebras `reasoning_effort:"none"`, Groq `reasoning_format`, xAI düşünen modelleri / SambaNova / OpenAI o-serisi için `frequency_penalty` gönderilmiyor.

## Sağlayıcı başına derin plan (2. tur, 2026-11-22)

Her sağlayıcı kendi güncel belgesiyle karşılaştırıldı. ✓ = artık kodda.

### Anthropic (yerel Messages API)
- ✓ Düşünme, model kuşağına göre ayarlanıyor (`claude_gen`). 4.6 öncesinde istek `budget_tokens` kullanıyor. 4.6'dan itibaren `thinking:{type:"adaptive", display:"summarized"}` ve `output_config.effort` kullanılıyor; 4.7'den itibaren `budget_tokens` ve `temperature` 400 hatası veriyor.
- ✓ Düşünme kapalıyken:
  - Opus 5.5, Fable ve Mythos'ta düşünme kapatılamıyor; bunlara en düşük effort veriliyor.
  - Sonnet 5.5'te `{type:"between_tools"}` gönderiliyor.
  - Diğer modellerde `{type:"disabled"}` gönderiliyor (effort en çok `high`).
- ✓ Her araçta `eager_input_streaming:true` var: yazılan dosya, dakikalarca sessizlikten sonra tek blok hâlinde gelmek yerine canlı akıyor.
- ✓ Durma nedenleri: `max_tokens` / `model_context_window_exceeded` → kesik sayılıyor (yazılan korunuyor ve sürdürülüyor, yarım araç çağrısı kurtarılıyor). `refusal` → kategorisiyle açık bir hata.
- ✓ Zaten vardı: `ping` canlı tutma, `input_json_delta`, araç turlarında imzalı düşünme bloklarının geri gönderilmesi, sistem isteminin önbelleğe alınması.

### Hugging Face (router.huggingface.co/v1)
- Araç ve akış destekli, OpenAI uyumlu chat completions. Model kimliğine politika ya da sağlayıcı eki eklenebiliyor (`:fastest` varsayılan, `:cheapest`, `:preferred`, `:groq`, `:together`…). Ek olduğu gibi iletiliyor.
- Her arka uç sağlayıcının kendi araç/düşünme davranışı var. Genel OpenAI uyumlu yol bunları karşılıyor: `index` olmayan çağrılar, `reasoning` / `reasoning_content`, tekrarlanan adlar.

### NVIDIA NIM (integrate.api.nvidia.com)
- ✓ Düşünme `chat_template_kwargs.enable_thinking` / `thinking` ile kapatılıyor; `thinking_token_budget` dikkate alınıyor.
- ✓ Araç argümanları akmıyor ve NIM 300 sn sessiz kalan akışı kapatıyor. "Bütün gelen araç çağrısı" bekçisi böyle bir modeli canlı akan metin biçimine geçiriyor. Araç ayrıştırıcısı hata verirse istek `stream:false` ile tekrarlanıyor.
- ✓ Hız sınırı 40 RPM (sağlayıcının `rpm` ayarı).

### EVREN (vLLM)
- ✓ vLLM düşünme alanının adını artık `reasoning` yapıyor (eskiden `reasoning_content`). İkisi de okunuyor.
- ✓ Düşünmeyi kapatan anahtar şablona göre değişiyor: Qwen / Nemotron / GLM için `enable_thinking`, DeepSeek için `thinking`. İkisi de gönderiliyor.
- ✓ Ölçülen istek sınırı (~194 sn) `thinking_token_budget`'ı sınırlıyor; böylece yazmaya zaman kalıyor.
- ✓ Araç çağrıları yalnızca içerikten ayrıştırılıyor (vLLM belgesi) ve bütün olarak gönderiliyor. Sessizlik bekçileri bu durumu karşılıyor.

### Ollama (yerel) ve Ollama Cloud (ollama.com)
- ✓ `/api/chat` üzerinde `think` (true/false, gpt-oss için low/medium/high), yerel `tools` ve `done_reason:"length"` → kesik.
- ✓ Araç turu `thinking` ile birlikte geri gönderiliyor (Ollama belgesi: thinking, content ve tool_calls birlikte döndürülmeli).
- ✓ Ollama Cloud Bearer kimlik doğrulaması (API anahtarı) kullanıyor. Yerel CPU seçenekleri (`num_thread`, yerel `num_ctx`) oraya gönderilmiyor.
- ✓ Yerel: `keep_alive`, bellek koruması, `prompt_eval_count` alt sınır olarak sayılıyor (önbellekteki önek).

### LM Studio (yerel, /v1 OpenAI uyumlu)
- ✓ Araçlar `/v1/chat/completions` üzerinde çalışıyor. Düşünme `reasoning` (gpt-oss, yeni sürümler) ya da `reasoning_content` alanında geliyor; ikisi de okunuyor.
- Yerel `/api/v1/chat` durumlu sohbet ve MCP sunuyor, ama orada özel araçlar belgelenmemiş. Uygulama `/v1` üzerinde kalıyor.

### Tüm modeller için MCP
- ✓ Bağlı her sunucu görünüyor. En çok 40 araç argümanlarıyla, sunuculara adil dağıtılarak listeleniyor; diğer tüm araçlar adlarıyla listeleniyor. Eskiden düz "ilk 80" kesimi bazı sunucuları tümden gizliyordu.
- ✓ `mcp` aracı `tool="list"` ile çağrılınca sunucunun araçlarını tüm argümanlarıyla döndürüyor.
- ✓ Düz sorularda da `mcp` aracı açık kalıyor.
- ✓ Playwright MCP bağlıysa modele bunun ikinci bir tarayıcı olduğu söyleniyor; yerleşik `browser_*` aracı bir sayfada sürekli hata verirse kullanılabilir.

### Model aileleri: sağlayıcı + model (`backend/app/llm/families.py`)
Taşıma işini sağlayıcı belirliyor. Modelin nasıl düşündüğünü ve araç çağırdığını ise, hangi sağlayıcıdan sunulursa sunulsun, **model ailesi** belirliyor. Böylece yarın DeepSeek ya da Qwen ekleyen bir sağlayıcı yeni kod gerekmeden doğru davranışı alıyor.
- **Araç çağrısı.** Güvenilir yerel araç çağrısı olmayan aileler her sağlayıcıda AI IQ 300 metin protokolünü kullanıyor: DeepSeek-R1, Gemma, küçük Llama 3.x, Phi. Model profilindeki "native" ayarı bunu yine de geçersiz kılabiliyor.
- **Şablon sunucularında düşünme anahtarı (vLLM, NIM).** Her aile kendi anahtarını alıyor: Qwen3, GLM, Nemotron ve Seed-OSS `enable_thinking`, DeepSeek V3.1+ `thinking` kullanıyor. Her zaman düşünen ailelere anahtar gönderilmiyor: R1, QwQ, `*-thinking`, gpt-oss, MiniMax, Magistral.
- **Örnekleme.** Başka bir değer ayarlanmamışsa model kartındaki değerler kullanılıyor: Qwen3 0.6/0.95, Kimi K2 0.6, R1 0.6, Gemma 1.0/0.95, MiniMax 1.0/0.95. Sunucunun reddettiği alanları sağlayıcı kuralları yine düşürüyor (Claude 4.7+, OpenAI GPT-5/o, Moonshot'taki Kimi K2.5+).
- **Ayrıştırıcının okuduğu metin araç biçimleri.**

  | Biçim | Aile |
  |---|---|
  | `<tool>` | AI IQ 300 |
  | `<function=…>` | Qwen3-Coder |
  | `<tool_call>{json}` | Hermes / Qwen |
  | `<tool_call>NAME<arg_key>` | GLM |
  | DSML | DeepSeek |
  | harmony | gpt-oss |
  | `[TOOL_CALLS]` | Mistral |
  | `<|tool_call_begin|>functions.AD:0` | Kimi K2 (yeni) |
  | `<minimax:tool_call><invoke name=…>` | MiniMax (yeni) |
  | `<|python_tag|>{"name","parameters"}` | Llama 3 (yeni) |

  Bunların hiçbiri kullanıcıya ham metin olarak ulaşmıyor.
- **Tek tek modellerin istek alanları.**
  - OpenAI GPT-5/o-serisi `max_completion_tokens` kullanıyor ve onlara `temperature` gönderilmiyor.
  - Moonshot'taki Kimi K2.5+ modellerine `temperature` / `top_p` gönderilmiyor.
  - Mistral'in `content` içindeki düşünme parçaları ayrıştırılıyor.
  - Alibaba Model Studio'daki Qwen `enable_thinking` kullanıyor (yeni "qwen" sağlayıcısı).

### Sessizlik bekçileri: nerede?
**Ayarlar > Ajan > "Model bağlantısı ve zaman aşımı"**:
- `stream_timeout` (300 sn)
- `first_token_timeout` (300 sn: "300 saniyelik bekçi" budur)
- `local_stream_timeout` (∞)
- `provider_retries`

**Ayarlar > Ajan > "Sessizlik bekçileri"** (yeni):

| Bekçi | Varsayılan |
|---|---|
| Bağlantı denetimi (yanıt başladıktan sonra) | 30 sn |
| Bağlantı denetimi (ilk karakterden önce) | 45 sn |
| Kopan akışı sürdür | 90 sn |
| Duran dosya akışı tabanı | 90 sn |
| Yarım kalan araç çağrısı | 150 sn |
| Bütün gelen araç çağrısı | 75 sn |

NVIDIA'nın kendi 300 sn kesmesi sağlayıcı tarafında oluyor; bu süre sağlayıcı başına öğreniliyor (`data/request_caps.json`).

## Kaynaklar
- vLLM reasoning outputs: https://docs.vllm.ai/en/stable/features/reasoning_outputs/
- vLLM DeepSeek V3.1 tool parser: https://docs.vllm.ai/en/v0.14.0/api/vllm/tool_parsers/deepseekv31_tool_parser/
- NVIDIA NIM reasoning models: https://docs.nvidia.com/nim/large-language-models/latest/reasoning-model.html
- NVIDIA forum, araç argümanları akmıyor / 300 sn: https://forums.developer.nvidia.com/t/tool-call-arguments-are-not-streamed-300-s-of-silence-closes-the-stream-with-no-finish-reason-integrate-api-nvidia-com/378789
- NIM 1.12 sürüm notları: https://docs.nvidia.com/nim/large-language-models/1.12.0/release-notes.html
- Gemini OpenAI uyumluluk + akışta tool_call: https://discuss.ai.google.dev/t/gemini-openai-compatibility-issue-with-tool-call-streaming/59886
- Gemini 3 thought_signature: https://discuss.ai.google.dev/t/openai-api-compatibility-broken-due-to-thought-signature-on-gemini-3-pro-preview/109823
- Mistral 9 karakter kimlik: https://github.com/vercel/ai/issues/11802
- vLLM `reasoning` alanı: https://docs.vllm.ai/en/latest/features/reasoning_outputs/
- Ollama düşünme / araç çağrısı / akış: https://docs.ollama.com/capabilities/thinking.md, https://docs.ollama.com/capabilities/tool-calling, https://docs.ollama.com/capabilities/streaming
- LM Studio REST + OpenAI uyumu: https://lmstudio.ai/docs/developer/rest, https://lmstudio.ai/docs/developer/openai-compat/tools, https://www.lmstudio.ai/docs/developer/api-changelog
- Hugging Face Inference Providers: https://huggingface.co/docs/inference-providers/index, https://huggingface.co/docs/inference-providers/guides/function-calling
- Anthropic Messages API (düşünme, effort, durma nedenleri): Anthropic'in güncel API başvurusu
- Playwright Python (evaluate, locator, mouse.wheel): https://playwright.dev/python/docs/evaluating, https://playwright.dev/python/docs/api/class-locator, https://playwright.dev/python/docs/api/class-mouse
