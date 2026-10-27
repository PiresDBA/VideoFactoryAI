# 📘 Manual do Usuário — VideoFactoryAI

> **Versão:** 3.8<br>
> **Data:** Outubro 2026
> **Local do projeto:** C:\Fabrica-de-videos\VideoFactoryAI  
> **Público-alvo:** Desenvolvedores, operadores de sistema e gestores de projeto  
> **Nível:** Iniciante a intermediário (não é necessário ser especialista em IA)

---

# ⚠️ REGRA DE OURO — LEIA ANTES DE QUALQUER ALTERAÇÃO

## ⚠️⚠️⚠️ ATENÇÃO: LEIA ESTA SEÇÃO ANTES DE QUALQUER ALTERAÇÃO ⚠️⚠️⚠️

### 1. Este documento é a fonte da verdade

Este arquivo `manual.md` é a **fonte oficial de verdade** sobre como o VideoFactoryAI funciona, como está estruturado e como deve ser modificado. 

**Antes de fazer QUALQUER alteração no código, na configuração ou na infraestrutura, leia este documento inteiro.** Ele explica como o sistema funciona, por que as decisões foram tomadas e quais são as regras de ouro que não podem ser quebradas.

### 2. Após qualquer alteração, ATUALIZE ESTE DOCUMENTO

Se você fizer qualquer uma das seguintes ações, **deve** atualizar este manual:

| Tipo de mudança | O que fazer no manual |
|-----------------|----------------------|
| Adicionar ou remover um módulo Python | Atualizar a seção "Módulos Python e Suas Funções" |
| Alterar o pipeline (adicionar, remover ou reordenar passos) | Atualizar a seção "Fluxo de Dados (Pipeline)" |
| Adicionar ou remover uma fonte de mídia | Atualizar a seção "Fontes de Mídia Suportadas" |
| Alterar variáveis de ambiente | Atualizar a seção "Variáveis de Ambiente" |
| Alterar configurações do config.yaml | Atualizar a seção "Configuração Principal" |
| Mudar a estrutura de pastas | Atualizar a seção "Estrutura de Pastas" |
| Adicionar um novo canal de estilo | Atualizar a seção "Canais Disponíveis" |
| Mudar qualquer regra de ouro | Atualizar a seção "Regras de Ouro do Projeto" |
| Adicionar ou remover uma dependência | Atualizar a seção "Stack Tecnológica" e "Dependências Principais" |

**Não altere o código sem primeiro atualizar este documento.** Se você alterar o código e não atualizar o manual, o documento ficará desatualizado e outros desenvolvedores (ou você mesmo no futuro) poderão cometer erros baseados em informações desatualizadas.

---

## 1. Visão Geral

O **VideoFactoryAI** é um sistema automatizado de produção de documentários em vídeo 1080p, pronto para YouTube. Ele transforma um tema (ex: "Segunda Guerra Mundial") ou um roteiro pronto em um vídeo completo com narração, legendas, imagens, vídeos, capa e metadados.

O usuário não precisa saber editar vídeo, escrever roteiros ou gravar áudio. O sistema faz tudo automaticamente.

---

## 2. Arquitetura do Sistema

### 2.1 Visão Geral

O **VideoFactoryAI** é um sistema automatizado de produção de documentários em vídeo 1080p, pronto para YouTube. Ele transforma um tema (ex: "Segunda Guerra Mundial") ou um roteiro pronto em um vídeo completo com narração, legendas, imagens, vídeos, capa e metadados.

O usuário não precisa saber editar vídeo, escrever roteiros ou gravar áudio. O sistema faz tudo automaticamente.

---

## 2. Arquitetura do Sistema

### 2.1 Visão Geral

O **VideoFactoryAI** é um sistema automatizado de produção de documentários em vídeo 1080p, pronto para YouTube. Ele transforma um tema (ex: "Segunda Guerra Mundial") ou um roteiro pronto em um vídeo completo com narração, legendas, imagens, vídeos, capa e metadados.

O usuário não precisa saber editar vídeo, escrever roteiros ou gravar áudio. O sistema faz tudo automaticamente.

### 2.2 Como os Módulos se Comunicam

O sistema **não usa banco de dados relacional**. Toda a comunicação entre módulos acontece por:

1. **Arquivos de disco**: roteiros, SRT, imagens, vídeos, JSONs de metadados.
2. **Arquivos de checkpoint**: `roteiros/<slug>/ckpts/last_run.json` permite retomar de onde parou.
3. **Variáveis de ambiente**: `VF_MODO_ESCRITA`, `VF_WEBCHAT_VALIDAR`, etc.
4. **Arquivo de configuração**: `config.yaml` (YAML).

---

## 3. Stack Tecnológica

### 3.1 Linguagem e Ambiente

| Item | Detalhe |
|------|---------|
| Linguagem principal | Python 3.12.9 |
| Ambiente principal | `C:\Docling\venv\Scripts\python.exe` |
| Ambiente XTTS (conda) | `C:\Users\Pires\miniconda3\envs\xtts\python.exe` (Python 3.10, torch 2.3.1+cu118) |
| FFmpeg | `C:\Fabrica-de-videos\ffmpeg.exe` (já incluído no projeto) |

### 3.2 Bibliotecas Python Principais

| Biblioteca | Função |
|------------|--------|
| `faster-whisper` | Transcrição de áudio para texto (legendas) |
| `ctranslate2` | Motor de inferência do faster-whisper |
| `edge-tts` | Síntese de voz neural (Microsoft Edge) |
| `TTS` (Coqui TTS) | Clonagem de voz XTTS-v2 |
| `requests` | Requisições HTTP |
| `PIL` (Pillow) | Processamento de imagem |
| `opencv-python` | Processamento de vídeo e imagem |
| `playwright` | Automação de navegador (webchat) |
| `requests` | Requisições HTTP para APIs de mídia |
| `numpy` | Manipulação de arrays numéricos (processamento de imagem) |
| `pydub` | Manipulação de áudio |
| `yaml` | Leitura/escrita de config.yaml |

### 3.3 Fontes de Mídia Suportadas

| Nível | Tipo | Fontes |
|-------|------|--------|
| L0 | Biblioteca local | Imagens fornecidas pelo usuário (direitos de uso confirmados pelo usuário) |
| L1 | Vídeo real livre | Pixabay, Pexels, Internet Archive, Wikimedia |
| L1 (extra) | Vídeo via yt-dlp | YouTube, Vimeo, Internet Archive (CC) |
| L2 | Imagem real | Pixabay, Pexels, Unsplash, Wikimedia Commons |
| L2 (extras aprovados) | Imagem livre | reshot, negativespace, freestocks, newoldstock |
| L3 | Conteúdo IA público | Openverse (CC comercial) |
| L4 | IA gerada | Pollinations, Pollinations AI (fallback final) |

> **Regra de ouro:** Somente 4 de 35 fontes de imagem testadas foram aprovadas. As demais são bloqueadas em runtime.

---

## 4. Dependências Principais

### 4.1 Dependências Python (ambiente principal `C:\Docling\venv`)

| Biblioteca | Função |
|------------|--------|
| `faster-whisper` | Transcrição de áudio (mais rápido que openai-whisper) |
| `ctranslate2` | Motor de inferência do faster-whisper |
| `edge-tts` | Síntese de voz neural (Microsoft Edge) |
| `TTS` (Coqui TTS) | Clonagem de voz XTTS-v2 |
| `torch` | Backend de deep learning (PyTorch) |
| `transformers` | Modelos de linguagem/visão |
| `requests` | Requisições HTTP |
| `PIL` (Pillow) | Processamento de imagem |
| `opencv-python` | Processamento de vídeo/imagem |
| `playwright` | Automação de navegador (webchat) |
| `requests` | Requisições HTTP para APIs de mídia |
| `numpy` | Manipulação de arrays numéricos (processamento de imagem) |
| `pydub` | Manipulação de áudio |
| `yaml` | Leitura/escrita de config.yaml |

### 4.2 Dependências do Ambiente Conda (XTTS)

| Pacote | Versão | Função |
|--------|--------|--------|
| torch | 2.3.1+cu118 | Deep learning (GPU) |
| transformers | 4.41.2 | Modelos de linguagem/visão |
| TTS | XTTS-v2 | Clonagem de voz |
| soundfile | 0.14.0 | Leitura/gravação WAV |
| numpy | 1.22.0 | Arrays numéricos |

---

## 5. Fluxo de Dados (Pipeline)

O sistema funciona em **10 passos sequenciais**:

No modo **somente narração** (`--audio-only`), o pipeline encerra após sintetizar `projetos/<slug>/narracao.mp3`; não planeja cenas, não busca mídias e não gera SRT nem vídeo.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PASSO 1: PESQUISA E REDAÇÃO                       │
│  script_writer_agent.py → Wikipedia → roteiro.txt                   │
└─────────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     PASSO 2: PLANEJAMENTO DE CENAS                  │
│  agent.py → divide roteiro em cenas de ~12 segundos                │
└─────────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     PASSO 3: GERAÇÃO DE VOZ (TTS)                  │
│  xtts_engine.py → xtts_worker.py → XTTS-v2 → narracao.mp3          │
└─────────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     PASSO 4: LEGENDAS (Whisper)                    │
│  agent.py → faster-whisper → narracao.srt                          │
└─────────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     PASSO 5: BUSCA DE MÍDIA (L1→L4)                │
│  media_research_agent.py → imagens/vídeos livres                  │
└─────────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     PASSO 6: PROCESSAMENTO VISUAL                  │
│  modules/visual_processor.py → Ken Burns + 1080p                  │
└─────────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     PASSO 7: RENDERIZAÇÃO FINAL                    │
│  modules/composer.py → concatenação + áudio + legendas            │
└─────────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     PASSO 8: THUMBNAIL AGENT                        │
│  thumbnail_agent.py → 3 versões + eleição por contraste           │
└─────────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     PASSO 9: QUALITY AGENT                          │
│  quality_agent.py → auditoria de qualidade                          │
└─────────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     PASSO 10: SEO AGENT                             │
│  seo_agent.py → título, descrição, tags e capítulos para o YouTube │
└─────────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     PASSO 11: ANALYTICS                             │
│  analytics.py → registro de execução                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 6. Módulos Python e Suas Funções

A seguir, cada arquivo Python do projeto explicado de forma detalhada:

### 6.1 `VideoFactoryAI/agent.py` — Orquestrador Principal

**O que faz:** É o cérebro do sistema. Orquestra todos os 10 passos do pipeline.

**Principais responsabilidades:**
- Lê o roteiro (arquivo `.txt` ou gera via `--topic`)
- Chama os módulos em sequência
- Gerencia checkpoints (retomada após falha)
- Coordena a passagem de dados entre módulos

**Principais funções:**
- `main()`: Orquestra todo o pipeline
- `plan_scenes()`: Divide roteiro em cenas
- `generate_voice()`: Chama o TTS (edge-tts ou xtts)
- `generate_subtitles()`: Chama o Whisper
- `source_media()` / `source_all()`: Busca mídia
- `assemble_master_documentary()`: Renderiza o vídeo final

### 6.2 `VideoFactoryAI/script_writer_agent.py` — Roteirista Automático

**O que faz:** Pesquisa na Wikipedia e escreve o roteiro completo quando o usuário usa `--topic`.

**Funcionalidades:**
- Pesquisa na Wikipedia aberta (PT-BR)
- Estrutura narrativa em 5 atos (Gancho, Origens, Desenvolvimento, Desfecho, Legado)
- Adapta estilo ao canal (historia, geopolitica, tecnologia, documentario)
- Controla contagem de palavras (mínimo exigido)
- Salva em `roteiros/<slug>.txt`

### 6.3 `VideoFactoryAI/webchat_writer.py` — Geração via WebChat

**O que faz:** Usa LLMs via navegador (Gemini, Copilot, ChatGPT, DeepSeek, Perplexity) via Playwright.

**Funcionalidades:**
- Geração sequencial em partes (para roteiros longos)
- Validação de contagem de palavras por parte
- Anti-alucinação: não inventa datas/nomes que não estão nas fontes
- Validação humana opcional (A/E/R/C no terminal)

### 6.4 `VideoFactoryAI/webchat_bridge.py` — Ponte para Navegador

**O que faz:** Automação de navegador (Playwright) para interagir com LLMs via navegador.

**Funcionalidades:**
- Abre navegador visível
- Envia prompts e captura respostas
- Aprende seletores de cada site (auto-cura)
- Validação humana opcional (A/E/R/C no terminal)

### 6.5 `VideoFactoryAI/xtts_engine.py` — Orquestrador XTTS-v2

**O que faz:** Orquestra a síntese de voz com clonagem (XTTS-v2) rodando em ambiente conda separado (Python 3.10 + torch 2.3.1+cu118).

**Funcionalidades:**
- Carrega modelo XTTS-v2 uma única vez (economia de tempo)
- Divide texto em trechos (chunks) de ~240 caracteres
- Concatena trechos com pausa de 220ms
- Normaliza pico de áudio (0.95)
- Converte WAV → MP3 via ffmpeg
- Fallback para edge-tts se XTTS falhar

### 5.6 `VideoFactoryAI/media_research_agent.py` — Pesquisa de Mídia

**O que faz:** Busca imagens e vídeos usando biblioteca local prioritária para imagens e hierarquia L1→L4 para fontes online.

**Hierarquia:**
- **L0 (Biblioteca local):** imagens fornecidas pelo usuário, pré-selecionadas pelos títulos em português e avaliadas visualmente pelo Ollama local
- **L1 (Vídeo real):** Pixabay, Pexels, Wikimedia, Internet Archive
- **L2 (Imagem real):** Pixabay, Wikimedia, Pexels, Unsplash, reshot, negativespace, freestocks, newoldstock
- **L3 (IA pública):** Openverse (CC comercial)
- **L4 (IA gerada):** Pollinations (fallback final)

**Funcionalidades:**
- Validação de imagem via PIL (rejeita logos, ícones, thumbnails)
- Validação de compatibilidade imagem↔roteiro (ImageEvaluatorAgent)
- Proteção contra duplicatas (hash MD5)
- Normalização WEBP/PNG → JPEG
- Busca de imagens locais antes das fontes online e da geração por IA

### 5.6.1 `VideoFactoryAI/local_media_agent.py` — Biblioteca Local de Imagens

**O que faz:** Indexa os títulos de imagens JPG, JPEG, PNG e WEBP e usa o modelo de visão Ollama configurado para selecionar a imagem visualmente mais compatível com cada cena.

**Funcionamento:**
- Os tokens do texto da cena são comparados aos títulos dos arquivos para formar uma lista curta de candidatas; as imagens e seus títulos são enviados somente ao serviço Ollama local.
- A resposta JSON do modelo contém a imagem escolhida e uma nota de confiança de 0 a 10, normalizada para 0 a 1. Correspondências abaixo do limiar configurado são rejeitadas.
- Na GUI, a opção **Revisar imagens locais abaixo do limiar** vem ativada. Para candidatas abaixo do limiar, a tela mostra a imagem e o trecho do roteiro; aprovar aceita a imagem para a cena. Rejeitar coloca a candidata em quarentena somente para aquela cena e exibe a próxima candidata. Nenhum arquivo da biblioteca é movido ou alterado; imagens rejeitadas continuam disponíveis para outras cenas.
- Em `prefer`, é usado para cenas de imagem; vídeos mantêm a hierarquia existente.
- Em `required`, todas as cenas usam imagens locais (cenas planejadas como vídeo são convertidas para imagem) e nenhuma fonte online é consultada.
- A avaliação visual do Ollama substitui a validação Gemini para imagens locais; o `MediaResearchAgent` ainda aplica deduplicação por hash e normaliza as imagens para JPEG.
- As imagens são reduzidas em memória para no máximo 768 px antes da análise, como no `renomear_imagens.py`; os originais permanecem intactos.
- O índice de títulos é criado em memória no início da execução; não são necessários embeddings, PyTorch ou `open_clip_torch`.

### 5.7 `VideoFactoryAI/image_evaluator_agent.py` — Validador de Imagem

**O que faz:** Verifica se a imagem baixada é compatível com o texto da cena.

**Funcionalidades:**
- Score 0–100 de compatibilidade
- Rejeita logos, ícones, banners, cartões sociais
- Valida resolução mínima (800×450)

### 5.8 `modules/visual_processor.py` — Processador Visual

**O que faz:** Aplica efeito Ken Burns (zoom suave) em imagens estáticas e normaliza para 1080p.

**Efeitos disponíveis:**
- `pan`: Panorama suave (esquerda-direita, cima-baixo, diagonal)
- `ken_burns_smooth`: Zoom suave com easing (suavização)
- `slide`: Deslizamento
- `static`: Imagem estática (sem movimento)

### 5.9 `modules/composer.py` — Compositor Master

**O que faz:** Concatena todos os clipes, adiciona áudio e queima legendas no vídeo final via FFmpeg.

### 5.10 `VideoFactoryAI/thumbnail_agent.py` — Gerador de Capa

**O que faz:** Gera 3 versões de thumbnail e escolhe a de maior contraste visual.

### 5.11 `VideoFactoryAI/seo_agent.py` — SEO Agent

**O que faz:** Gera título, descrição, tags e capítulos para o YouTube.

### 5.12 `VideoFactoryAI/quality_agent.py` — Agente de Qualidade

**O que faz:** Audita o vídeo final:
- Verifica se não há imagens duplicadas
- Verifica se não há cenas pretas
- Verifica se legendas estão sincronizadas
- Aprova ou reprova o vídeo final

---

## 6. Como o Sistema Funciona Passo a Passo

A seguir, o fluxo detalhado de cada passo:

### Passo 1: Pesquisa e Roteiro (ScriptWriterAgent)

O sistema consulta a Wikipedia aberta (PT-BR) sobre o tema. Se o tema não existir na Wikipedia, busca palavras-chave relacionadas. Depois escreve o roteiro em 5 atos:
1. **Ato 1 - Gancho:** Apresenta o tema de forma envolvente
2. **Ato 2 - Origens:** Contexto histórico/científico
3. **Ato 3 - Desenvolvimento:** Conflitos, tensões, pontos de virada
4. **Ato 4 - Desfecho:** Consequências, lições
5. **Ato 5 - Legado:** Reflexão final

### Passo 2: Planejamento de Cenas

O roteiro é dividido em cenas de aproximadamente 12 segundos cada. Cada cena recebe:
- Texto narrado
- Tipo (vídeo ou imagem)
- Query de busca (para mídia)
- Duração

### Passo 3: Geração de Voz (TTS)

Se o engine for `edge-tts`: usa Microsoft Edge-TTS (voz neural gratuita).
Se o engine for `xtts`: usa XTTS-v2 com voz clonada via ambiente conda separado (Python 3.10 + torch 2.3.1+cu118).

### Passo 4: Transcrição (Whisper)

O áudio da narração é transcrito via faster-whisper (mais rápido que openai-whisper). Usa:
- Modelo: tiny, base, small, medium ou large
- GPU: `int8_float32` para GTX 1060 (Pascal), `float16` para Turing+
- Hotwords: nomes próprios extraídos do roteiro (ex: "Constantinopla", "Mehmed")
- Pós-processamento: acentuação PT-BR e correção fuzzy de nomes próprios

### Passo 5: Busca de Mídia (L0→L4)

Para cenas de imagem, o pipeline busca mídia nesta ordem:
0. **L0:** biblioteca local configurada (shortlist por título e avaliação visual pelo Ollama local; direitos de uso confirmados pelo usuário)
1. **L1:** Pixabay, Pexels, Wikimedia, Internet Archive (vídeo/imagem real)
2. **L2:** reshot, negativespace, freestocks, newoldstock (imagem)
3. **L3:** Openverse (CC comercial)
4. **L4:** Pollinations (IA gerada) ou PIL card (fallback)

Na GUI, escolha a estratégia em **Origem das imagens** e indique a pasta da biblioteca local:

Os nomes amigáveis mostrados na lista são convertidos para identificadores CLI (`local_only`, `local_then_online`, `webchat_only` ou `internet_images`); esses valores técnicos não devem ser substituídos pelo texto exibido.

- **Somente biblioteca local (`local_only`):** usa apenas imagens locais; cenas planejadas como vídeo viram imagens. Cenas sem correspondência ficam pendentes, sem cache ou fallback online.
- **Biblioteca local → internet / WebChat (`local_then_online`):** tenta a biblioteca local primeiro e, sem correspondência, percorre mídia online e geradores WebChat. Cenas planejadas como vídeo ainda podem usar fontes de vídeo.
- **Somente WebChat (`webchat_only`):** usa apenas geradores de imagem via navegador, como Gemini, Dreamina, Copilot e demais provedores WebChat configurados. Não consulta a biblioteca local, bancos de imagens ou Openverse.
- **Somente imagens da internet (`internet_images`):** consulta bancos de imagens e Openverse; não usa a biblioteca local nem geração WebChat/IA. Cenas planejadas como vídeo viram imagens.

Os modos explícitos não reutilizam imagens de execuções anteriores, o cache persistente ou clipes retomados, pois esses arquivos poderiam ter vindo de uma fonte não permitida pela estratégia selecionada. Se o agente de mídia falhar, o pipeline também não usa o fallback legado. `local_media_mode` permanece disponível para compatibilidade com configurações antigas; `media_source_mode` define a política completa quando informado. Cada imagem local selecionada passa por validação de imagem↔roteiro e dedup por hash MD5.

Na retomada da produção, a narração existente só é reutilizada se o texto e as configurações TTS coincidirem, incluindo motor, voz, velocidade e tom. Trocar a voz invalida a narração antiga e gera um novo áudio. Uma voz explicitamente selecionada na GUI/CLI tem prioridade sobre a voz padrão do perfil do canal.

#### Configuração da biblioteca local

Em `VideoFactoryAI/config.yaml`, configure:

```yaml
media:
  media_source_mode: local_only
  local_media_enabled: true
  local_media_mode: required
  local_media_folder: 'C:\Fabrica-de-videos\projetos\makete_ho\imagens'
  local_similarity_threshold: 0.80
  min_local_images: 150
```

`media_source_mode` aceita `local_only`, `local_then_online`, `webchat_only` e `internet_images`, com a mesma seleção disponível na tela inicial da GUI. O caminho da biblioteca pode ser absoluto ou relativo ao workspace da produção; a GUI carrega o padrão do `config.yaml` e permite escolher outra pasta. `local_media_mode` aceita `off`, `prefer` e `required` para compatibilidade com configurações anteriores. Configure `local_ollama_model`, `local_ollama_url`, `local_ollama_candidate_count` e `local_ollama_timeout_s` em `media`; por segurança, a URL só aceita o serviço local (`localhost` ou loopback HTTP). Os títulos dos arquivos em português formam uma shortlist de até quatro imagens, e apenas essas candidatas são enviadas ao modelo local, junto ao texto, à descrição e à consulta planejada para a cena. A escolha precisa atingir `local_similarity_threshold`; a nota Ollama de 0 a 10 é normalizada para 0 a 1. Na GUI, **Revisar imagens locais abaixo do limiar** permite aprovar manualmente uma candidata que não atingiu a nota; ao rejeitar, ela é excluída apenas da cena atual e a próxima candidata é apresentada. Desative a opção para não revisar candidatos abaixo do limiar; no modo somente local, cenas sem correspondência interrompem a produção. Nenhuma decisão move ou altera as imagens originais. As imagens aceitas são convertidas para JPEG no destino da cena. O relatório identifica a origem local, mas cabe ao usuário confirmar que possui os direitos de uso.

`min_local_images` (ou `--min-local-images`) define uma quantidade mínima de imagens locais únicas para o vídeo. O valor `0` mantém o comportamento de uma imagem por cena; por exemplo, `150` reparte no mínimo 150 imagens em cortes dentro das cenas existentes, sem criar novas cenas de narração. Em `local_only`, a produção é interrompida se não houver imagens suficientes aprovadas ou se alguma cena ficar sem imagem — nunca completa o vídeo com internet ou cartões de fallback. A GUI oferece o campo **Mínimo de imagens locais únicas**.

Configuração Ollama:

```yaml
media:
  local_ollama_model: llava-phi3
  local_ollama_url: http://127.0.0.1:11434
  local_ollama_candidate_count: 4
  local_ollama_timeout_s: 180
```

### Passo 6: Processamento Visual

Cada imagem passa por Ken Burns (zoom suave com easing). Vídeos são normalizados para 1080p@30fps.

### Passo 7: Renderização Final

FFmpeg concatena todos os clipes, adiciona a narração em MP3 e queima as legendas (se habilitadas).

### Passo 8: Thumbnail Agent

Gera 3 versões de thumbnail e escolhe a de maior contraste visual.

### Passo 9: Quality Agent

Audita:
- Duplicatas de assets
- Cenas pretas
- Duração sincronizada
- Qualidade geral

### Passo 10: SEO Agent

Gera:
- Título do vídeo
- Descrição
- Tags
- Capítulos

---

## 7. Como Usar (Linha de Comando)

Todos os comandos devem ser executados na pasta `C:\Fabrica-de-videos\VideoFactoryAI`.

### 7.1 Modo Tema (geração automática completa)

```powershell
cd C:\Fabrica-de-videos\VideoFactoryAI
python agent.py --topic "Segunda Guerra Mundial" --duration 15 --channel historia --min-words 1800
```

### 7.2 Modo Roteiro (arquivo já existe)

```powershell
cd C:\Fabrica-de-videos\VideoFactoryAI
python agent.py roteiros/meu_roteiro.txt
```

### 7.3 Usar voz clonada (XTTS)
```powershell
python VideoFactoryAI/agent.py --topic "Tema" --duration 10 --tts-engine xtts
```

### 7.4 Com legendas
```powershell
python VideoFactoryAI/agent.py --topic "Tema" --duration 10 --subtitles
```

### 7.5 Sem legendas (padrão)
```powershell
python VideoFactoryAI/agent.py --topic "Tema" --duration 10
```

(O padrão é sem legendas)

### 7.6 Retomar produção interrompida
```powershell
python VideoFactoryAI/agent.py roteiro.txt --resume
```

Na GUI, **Gerar somente SRT da narração existente** não produz áudio e não usa a voz selecionada; exige um `narracao.mp3` já existente no projeto. Para gerar/regerar a narração com a voz escolhida, use **Gerar SRT e incluir no vídeo** ou **Não gerar legendas** e inicie a produção completa.

Para criar apenas o áudio, selecione **Gerar somente narração MP3 (sem legenda nem vídeo)** em **Saída da produção**. A voz e o motor TTS selecionados serão usados; o MP3 será salvo em `projetos/<slug>/narracao.mp3`. Esse modo não executa Whisper, pesquisa de imagens ou renderização. Pela linha de comando, use `--audio-only`; esse modo é incompatível com `--subtitles-only`.

### 7.7 Parâmetros disponíveis

| Parâmetro | O que faz | Exemplo |
|-----------|-----------|---------|
| `--topic "TEMA"` | O assunto do documentário | `--topic "Segunda Guerra Mundial"` |
| `--duration MIN` | Duração estimada em minutos | `--duration 15` |
| `--min-words N` | Mínimo de palavras exigido | `--min-words 1800` |
| `--channel NOME` | Estilo do documentário | `--channel historia` |
| `--tts-engine xtts` | Usar voz clonada (XTTS) | `--tts-engine xtts` |
| `--subtitles` | Gerar legendas no vídeo | `--subtitles` |
| `--no-subtitles` | Sem legendas (padrão) | (padrão) |
| `--audio-only` | Gerar apenas `narracao.mp3`, sem cenas, legendas ou vídeo | `python agent.py roteiro.txt --audio-only --voice pt-BR-ThalitaNeural --tts-engine edge-tts` |
| `--voice VOZ` | Escolher voz da narração | `--voice pt-BR-AntonioNeural` |
| `--resume` | Retomar produção interrompida | `--resume` |
| `--media-source-mode MODO` | Escolher uma das quatro estratégias de origem de imagem | `--media-source-mode local_only` |
| `--local-media-folder PASTA` | Definir a biblioteca local de imagens | `--local-media-folder "C:\Fabrica-de-videos\projetos\makete_ho\imagens"` |
| `--min-local-images N` | Exigir no mínimo N imagens locais únicas e distribuí-las em cortes dentro das cenas | `--min-local-images 150` |

### 7.8 Exemplo completo

```powershell
python VideoFactoryAI/agent.py --topic "Segunda Guerra Mundial" --duration 15 --channel historia --min-words 1800 --tts-engine xtts --subtitles
```

---

## 8. Canais Disponíveis (Estilos de Documentário)

O programa adapta o estilo do texto de acordo com o canal escolhido:

| Canal | Estilo | Quando usar |
|-------|--------|-------------|
| **historia** | Tom solene, cronológico, épico. Foca em datas, nomes, causas e consequências. | História, guerras, revoluções |
| **geopolitica** | Tom analítico, estratégico. Foco em interesses nacionais e poder. | Política internacional, conflitos atuais |
| **tecnologia** | Tom moderno, preciso. Explica como funciona a tecnologia. | Ciência, inovação, computação |
| **documentario** | Tom envolvente, reflexivo, cinematográfico. (PADRÃO) | Qualquer tema geral |

Se não escolher nenhum, usa `documentario` por padrão.

---

## 9. Onde os Arquivos Ficam Salvos

| Pasta | O que contém |
|-------|--------------|
| `saida/` | **O vídeo final MP4** pronto para o YouTube |
| `saida/thumbnail.jpg` | A capa (imagem de capa do YouTube) |
| `saida/youtube_metadata.json` | Título, descrição, tags e capítulos prontos para publicar |
| `roteiros/` | O texto do roteiro escrito pelo programa |
| `projetos/<slug>/` | Todos os arquivos individuais de cada produção |
| `VideoFactoryAI/memory/` | Memória do programa (preferências de voz, histórico) |

---

## 10. O que Aparece no Final

Após terminar, você terá na pasta `saida/`:
- `segunda_guerra_mundial.mp4` — O vídeo completo, pronto para publicar
- `thumbnail.jpg` — A capa do vídeo
- `youtube_metadata.json` — Título, descrição, tags e capítulos prontos para publicar
- `quality_report.json` — Relatório de qualidade (se passou ou não nas verificações)

---

## 11. Sobre as Imagens e Vídeos (Importante)

O programa **não usa imagens aleatórias da internet**. Ele busca apenas mídia **livre de direitos autorais**.

### Fontes aprovadas (que funcionam de verdade):
| Fonte | Tipo |
|-------|------|
| reshot | Imagem |
| negativespace | Imagem |
| freestocks | Imagem |
| newoldstock | Imagem |

Uma biblioteca local pode ser priorizada antes da busca online, mas isso não altera a lista de fontes online aprovadas. Use nela apenas imagens próprias ou com autorização/licença adequada; o sistema não verifica os direitos desses arquivos.

**O programa NÃO usa:**
- Shutterstock, Getty Images, iStock, Adobe Stock (são pagos)
- Qualquer imagem com direitos autorais
- Qualquer imagem que não entregue arquivo válido (o programa testa cada fonte antes de usar)

Se uma fonte falhar, o programa tenta a próxima aprovada automaticamente. Se nenhuma funcionar, ele usa geração por IA (Pollinations ou PIL card) como fallback.

---

## 11. Sobre a Voz (XTTS-v2 — Clonagem de Voz)

O programa pode narrar com **SUA PRÓPRIA VOZ** clonada, usando o modelo XTTS-v2. Isso dá um toque pessoal ao documentário.

### Como ativar a voz clonada:

No arquivo `VideoFactoryAI/config.yaml`, mude:
```yaml
tts:
  engine: xtts           # edge-tts | xtts | f5-tts | openai
  xtts_python: C:\Users\Pires\miniconda3\envs\xtts\python.exe
  xtts_speaker_wav: voice/xtts/ale.wav
  xtts_use_cuda: true
```

E certifique-se de que o arquivo `voice/xtts/ale.wav` exista (é sua amostra de voz, 10-30 segundos de fala limpa).

Depois, na linha de comando:
```bash
python VideoFactoryAI/agent.py --topic "Segunda Guerra Mundial" --duration 15 --tts-engine xtts
```

Se não quiser usar a voz clonada, o padrão é Edge-TTS (voz neural da Microsoft, já funciona sem configuração extra).

---

## 11. Regras de Ouro (Importante)

| Regra | O que significa |
|-------|-----------------|
| **Não invente dados** | O programa NÃO inventa datas, nomes ou números que não estejam nas fontes |
| **Não repita imagens** | Cada cena usa uma imagem/vídeo diferente (não repete) |
| **Imagens são livres de direitos** | Só usa fontes que permitem reutilização gratuita |
| **Roteiro fiel ao tema** | Não inventa fatos que não estejam nas fontes pesquisadas |
| **WebChat é exclusivo** | Se usar modo webchat, não cai automaticamente para outro modo |
| **Legendas opcionais** | Padrão é sem legendas. Use `--subtitles` se quiser |

---

## 12. Problemas Comuns e Como Resolver

| Problema | Provável causa | Solução |
|----------|---------------|---------|
| "WebChat falhou: todos os web chats falharam" | O navegador não abriu ou não conseguiu fazer login no Gemini/Copilot | Abra o navegador manualmente e faça login no site antes |
| "WebChat falhou: resposta rejeitada pelo usuário" | Você clicou em "Cancelar" na janela de aprovação | Rode novamente e aperte "A" (Aprovar) quando aparecer |
| "WebChat é exclusivo - não há fallback local automático" | Isso é por design: o modo webchat é exclusivo | Use um arquivo de roteiro pronto se não quiser usar webchat |
| "Não consigo baixar imagem" | Algumas fontes bloqueiam downloads. O programa já filtra e usa apenas as 4 fontes aprovadas | Se nenhuma funcionar, o programa usa IA para gerar a imagem |
| "Áudio sai sem voz" | Verifique se o ambiente conda `xtts` está instalado corretamente (se usar XTTS) |
| "Legendas não aparecem" | Adicione `--subtitles` no comando |

---

## 11. Como Adicionar um Novo Canal de Estilo

Se quiser criar um novo estilo de documentário (ex: "infantil", "tecnologia", "culinária"):

1. Crie um arquivo em `VideoFactoryAI/channels/nomedocanal.yaml`
2. Ou edite o `config.yaml` e adicione a seção do canal
3. Use `--channel nomedocanal` ao rodar o programa

Exemplo de estrutura de canal:
```yaml
nome: "Meu Canal"
descricao: "Descrição do estilo"
persona: "Tom e estilo de narração"
```

---

## 13. Fluxo de Trabalho Resumido (Visual)

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Você escolhe o tema (ou já tem um roteiro)                       │
    ↓
2. O programa pesquisa o tema na Wikipedia e web                    │
    ↓
3. Escreve o roteiro narrado automaticamente                         │
    ↓
4. Gera a narração (sua voz clonada ou voz padrão)                  │
    ↓
5. Busca imagens e vídeos gratuitos na internet                     │
    ↓
6. Edita as imagens (efeito de zoom suave, Ken Burns)               │
    ↓
7. Monta tudo: vídeo + narração + legendas                          │
    ↓
8. Gera a capa (thumbnail) automaticamente                          │
    ↓
9. Verifica a qualidade (não repete imagens, etc.)                  │
    ↓
10. Gera título, descrição e tags para o YouTube                    │
    ↓
✅ VÍDEO PRONTO PARA PUBLICAR NO YOUTUBE                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 11. PRECISA DE AJUDA?

Se algo não funcionar:

1. **Leia a mensagem de erro no terminal** — geralmente diz exatamente o que falhou
2. **Verifique se está usando o Python correto** — use `C:\Docling\venv\Scripts\python.exe`
3. **Verifique se tem conexão com a internet** — o programa precisa baixar imagens e pesquisar na Wikipedia
4. **Se usar XTTS (voz clonada), verifique se o ambiente conda `xtts` está instalado** — senão, use o Edge-TTS (padrão)

---

## 12. CHECKLIST RÁPIDO PARA INICIAR

- [ ] Tenho o Python 3.12+ instalado (`C:\Docling\venv`)
- [ ] Tenho o ffmpeg instalado (já vem com o projeto)
- [ ] Tenho um tema para o documentário
- [ ] Sei se quero usar voz clonada (XTTS) ou voz padrão (Edge-TTS)
- **Comando simples para testar:**
  ```powershell
  cd C:\Fabrica-de-videos\VideoFactoryAI
  python agent.py --topic "Segunda Guerra Mundial" --duration 5 --channel historia
  ```

---

**Boa produção!** Seu documentário está a poucos comandos de distância. 🎬

---

## 13. Resumo Rápido de Comandos

| Objetivo | Comando |
|----------|---------|
| Usar roteiro existente | `python VideoFactoryAI/agent.py roteiros/meu_roteiro.txt` |
| Usar voz clonada (XTTS) | Adicionar `--tts-engine xtts` |
| Sem legendas (padrão) | Não passar `--subtitles` |
| Com legendas | Adicionar `--subtitles` |
| Duração específica | `--duration 15` (15 minutos) |
| Mínimo de palavras | `--min-words 1800` |
| Retomar produção interrompida | `--resume` |

---

# 📋 REGRA DE MANUTENÇÃO DO MANUAL

## ⚠️ OBRIGATÓRIO: Antes de qualquer alteração no sistema

1. **LEIA este manual inteiro** antes de escrever/editar qualquer código, configuração ou infraestrutura.
2. **NUNCA** altere o sistema sem entender primeiro o contexto completo.

## ⚠️ OBRIGATÓRIO: Após qualquer alteração no sistema

Após **QUALQUER** mudança (código, config, dependência, pipeline, fontes, variáveis de ambiente, pastas), você **DEVE** atualizar este manual:

- **Adicionou/removiu um módulo Python?** → Atualizar a seção [Módulos Python e Suas Funções](#6-módulos-python-e-suas-funções)
- **Mudou o pipeline (passos, ordem, adição/remoção)?** → Atualizar a seção [Fluxo de Dados (Pipeline)](#5-fluxo-de-dados-pipeline)
- **Adicionou/removeu fonte de mídia?** → Atualizar [Fontes de Mídia Suportadas](#33-fontes-de-mídia-suportadas) e [docs/FONTES_DE_MIDIA.md](docs/FONTES_DE_MIDIA.md)
- **Adicionou/removeu variável de ambiente?** → Atualizar [Variáveis de Ambiente](#10-variáveis-de-ambiente)
- **Mudou config.yaml?** → Atualizar [Configuração Principal](#9-configuração-principal-configyaml)
- **Mudou estrutura de pastas?** → Atualizar [Estrutura de Pastas](#11-armazenamento-e-estrutura-de-pastas)
- **Adicionou/removeu canal?** → Atualizar [Canais Disponíveis](#8-canais-disponíveis-estilos-de-documentário)
- **Mudou regra de ouro?** → Atualizar [Regras de Ouro](#13-regras-de-ouro-importante)
- **Mudou dependência (instalou/removeu pacote)?** → Atualizar [Stack Tecnológica](#3-stack-tecnológica) e [Dependências Principais](#4-dependências-principais)
- **Corrigiu bug / mudou comportamento?** → Atualizar a seção afetada e adicionar entrada na tabela [Histórico de Versões](#-histórico-de-versões-atualize-sempre) abaixo

## 📌 Tabela de Histórico de Versões (atualize sempre!)

| Versão | Data | O que mudou | Arquivos afetados | Autor |
|--------|------|-------------|-------------------|-------|
| 3.9 | 26/10/2026 | Corrigida a resolução de `imagens` relativa para o workspace do projeto; adicionado mínimo configurável de imagens locais distribuídas em cortes, com falha segura sem fallback no modo local | `VideoFactoryAI/agent.py`, `VideoFactoryAI/videofactory_gui.py`, `VideoFactoryAI/media_research_agent.py`, `VideoFactoryAI/config.yaml`, `modules/visual_processor.py`, `VideoFactoryAI/tests/test_local_media_review.py`, `VideoFactoryAI/tests/test_gui_media_controls.py`, `VideoFactoryAI/tests/test_visual_processor_regressions.py`, `manual.md` | Copilot |
| 3.8 | 26/10/2026 | Adicionado modo GUI/CLI para sintetizar somente a narração MP3, sem planejar cenas, gerar legendas ou renderizar vídeo; voz explicitamente selecionada agora prevalece sobre o perfil do canal | `VideoFactoryAI/agent.py`, `VideoFactoryAI/videofactory_gui.py`, `VideoFactoryAI/tests/test_local_media_review.py`, `VideoFactoryAI/tests/test_gui_media_controls.py`, `manual.md` | Copilot |
| 3.7 | 26/10/2026 | Corrigido o envio do identificador CLI da origem de mídia pela GUI e a derivação do slug dos metadados Gem ao produzir a partir de roteiro existente | `VideoFactoryAI/agent.py`, `VideoFactoryAI/videofactory_gui.py`, `VideoFactoryAI/tests/test_local_media_review.py`, `manual.md` | Copilot |
| 3.6 | 26/10/2026 | Cache de narração passa a considerar configurações TTS para não reutilizar áudio de outra voz; log indica configuração efetiva e GUI esclarece que SRT isolado não gera narração | `VideoFactoryAI/agent.py`, `VideoFactoryAI/pipeline_resume.py`, `VideoFactoryAI/voice_memory.py`, `VideoFactoryAI/videofactory_gui.py`, `VideoFactoryAI/tests/test_local_media_review.py`, `VideoFactoryAI/tests/test_agent_resume_cli.py`, `manual.md` | Copilot |
| 3.5 | 26/10/2026 | Adicionado seletor GUI com quatro políticas de origem, pasta configurável e roteamento que bloqueia fontes/cache/fallback fora do modo escolhido | `VideoFactoryAI/agent.py`, `VideoFactoryAI/videofactory_gui.py`, `VideoFactoryAI/media_research_agent.py`, `VideoFactoryAI/config.yaml`, `VideoFactoryAI/tests/test_local_media_review.py`, `VideoFactoryAI/tests/test_gui_media_controls.py`, `manual.md` | Copilot |
| 3.0 | 26/10/2026 | Versão inicial do manual | — | VideoFactoryAI |
| 3.0 | 26/10/2026 | Regra de ouro de manutenção do manual adicionada | `manual.md` | — |
| 3.1 | 26/10/2026 | Adicionada busca CLIP prioritária para imagens da biblioteca local com cache de embeddings | `.gitignore`, `VideoFactoryAI/local_media_agent.py`, `VideoFactoryAI/media_research_agent.py`, `VideoFactoryAI/config.yaml`, `requirements.txt`, `VideoFactoryAI/tests/test_local_media_agent.py`, `manual.md` | Copilot |
| 3.2 | 26/10/2026 | Configurada a pasta `imagens` e o modo somente local, com bloqueio de fallback online e busca da próxima imagem exclusiva | `VideoFactoryAI/agent.py`, `VideoFactoryAI/media_research_agent.py`, `VideoFactoryAI/local_media_agent.py`, `VideoFactoryAI/config.yaml`, `VideoFactoryAI/tests/test_local_media_agent.py`, `manual.md` | Copilot |
| 3.3 | 26/10/2026 | Substituída busca CLIP por shortlist de títulos em português e seleção visual Ollama local; imagens locais não acionam validação Gemini | `VideoFactoryAI/local_media_agent.py`, `VideoFactoryAI/media_research_agent.py`, `VideoFactoryAI/config.yaml`, `VideoFactoryAI/tests/test_local_media_agent.py`, `requirements.txt`, `manual.md` | Copilot |
| 3.4 | 26/10/2026 | Adicionada revisão visual interativa para candidatos locais abaixo do limiar, rejeição válida apenas por cena e redução de imagens em memória | `.gitignore`, `VideoFactoryAI/agent.py`, `VideoFactoryAI/videofactory_gui.py`, `VideoFactoryAI/local_media_agent.py`, `VideoFactoryAI/media_research_agent.py`, `VideoFactoryAI/tests/test_local_media_agent.py`, `VideoFactoryAI/tests/test_local_media_review.py`, `manual.md` | Copilot |

> **Lembrete:** se a linha acima estiver vazia, o manual NÃO foi atualizado e você deve corrigir antes de commitar qualquer alteração.

---

**Boa produção!** Seu documentário está a poucos comandos de distância. 🎬