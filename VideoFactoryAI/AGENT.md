# VideoFactoryAI — Documentação Oficial de Uso

Agente autônomo completo que transforma um **roteiro `.txt`** em um **documentário 1080p pronto para publicação**.  
Executa os 10 passos do pipeline sem necessidade de intervenção manual.

---

## Instalação em 1 Clique (Zero Dúvidas Daqui a 6 Meses)

Basta dar duplo clique no Windows em `install.bat` ou executar no terminal:

```bash
python setup.py
```

O instalador verifica e configura automaticamente:
- Python 3.10+ e ambiente 64 bits
- Detecção de GPU NVIDIA e PyTorch com suporte CUDA
- Dependências: `openai-whisper`, `edge-tts`, `Pillow`, `requests`, `pyyaml`
- Binário local do `ffmpeg.exe` (com download automático se ausente)
- Estrutura completa de diretórios e canais
- Validação por import de todos os 10 agentes

---

## Modos de Execução

### Modo 1: A partir de um Roteiro Pronto
```bash
python VideoFactoryAI/agent.py roteiro.txt
```

### Modo 2: Produtor Executivo Completo (Sem Roteiro Prévia)
Basta informar o tema e a duração desejada em minutos:

```bash
# Gera o roteiro do zero, pesquisa os fatos e monta o documentário de 8 minutos
python VideoFactoryAI/agent.py --topic "A Guerra Fria" --duration 8

# Documentário de 5 minutos direcionado ao canal de geopolítica
python VideoFactoryAI/agent.py --topic "A Crise dos Misseis de Cuba" --duration 5 --channel geopolitica

# Documentário de 10 minutos para o canal de história
python VideoFactoryAI/agent.py --topic "A Queda de Constantinopla" --duration 10 --channel historia
```

O `ScriptWriterAgent` integrado executa:
1. **Pesquisa Enciclopédica:** Consulta a API da Wikipedia em português para fatos, nomes, tratados e datas verificadas.
2. **Cálculo de Ritmo:** Aplica a cadência de 135 palavras por minuto para atingir com precisão a duração especificada.
3. **Estrutura em 5 Atos Documentais:**
   - *Ato 1:* O Gancho e a Ruptura (Hook & Inciting Incident)
   - *Ato 2:* As Origens e o Cenário (Context & Genesis)
   - *Ato 3:* A Escalada e os Pontos Críticos (Rising Tension & Turning Points)
   - *Ato 4:* As Consequências e o Desfecho (Aftermath & Resolution)
   - *Ato 5:* O Legado e a Reflexão Contemporânea (Legacy & Contemporary Reflection)
4. **Voz e Vocabulário:** Alinha o tom ao canal selecionado (ex: estratégico em Geopolítica, épico em História).
5. **Persistência:** Salva o roteiro gerado em `roteiros/<slug>.txt` e dá início automático aos 10 passos de produção.

---

## Saídas Geradas Automaticamente

O usuário fornece **apenas** o roteiro (ou o `--topic`). O sistema executa todos os agentes e entrega:
1. `saida/documentario_final.mp4` — Vídeo final 1080p montado e legendado
2. `saida/thumbnail.jpg` — Thumbnail eleita com maior contraste visual
3. `saida/thumbnail_v1.jpg`, `thumbnail_v2.jpg`, `thumbnail_v3.jpg` — Variações geradas
4. `saida/thumbnail_report.json` — Pontuação de contraste de cada versão
5. `saida/quality_report.json` — Relatório de controle de qualidade
6. `saida/youtube_metadata.json` — Metadados YouTube completos (título, descrição, tags, hashtags, capítulos)
7. `VideoFactoryAI/memory/media_report.json` — Auditoria de licenças e proveniência de mídias
8. `VideoFactoryAI/memory/project_history.json` — Analytics e histórico do projeto
9. `VideoFactoryAI/memory/preferences.json` — Memória de preferências e voz aprendidas
10. `roteiros/<slug>.txt` — Roteiro gerado (quando usado o modo `--topic`)

---

## Pipeline dos 10 Passos Automáticos

| Passo | Agente / Módulo | O que faz |
|-------|-----------------|-----------|
| **1/10** | `agent.py` | Planejamento e segmentação semântica de cenas |
| **2/10** | `VoiceMemory` + `edge-tts` | Geração de narração neural e persistência da voz |
| **3/10** | `Whisper` (GPU/CPU) | Transcrição e timecodes precisos (`narracao.srt`) |
| **4/10** | `MediaResearchAgent` + `AssetCache` | Busca hierárquica L1→L4 com compliance e cache |
| **5/10** | `visual_processor.py` | Efeito Ken Burns em imagens e normalização 1080p |
| **6/10** | `composer.py` | Concatenação de clipes, áudio e queima de legendas |
| **7/10** | `ThumbnailAgent` | Gera 3 versões e elege a de maior contraste |
| **8/10** | `QualityAgent` | Auditoria de duração, frames pretos, cenas e legendas |
| **9/10** | `SeoAgent` | Gera título, descrição, tags e capítulos do YouTube |
| **10/10**| `Analytics` | Registra histórico de produção em `project_history.json` |

---

## Diretor de Arte — validação cruzada de mídia e sincronização

O passo 4.5 verifica se os assets existem e são legíveis, compara o conteúdo visual com o texto da cena quando o avaliador visual Gemini está configurado, avalia a duração de vídeos e registra a linha do tempo das cenas. O relatório por projeto é salvo como `art_director_report.json`.

Modos por execução:

```bash
# Padrão: valida e registra problemas, sem interromper o fluxo atual
python agent.py roteiro.txt --art-director standard

# Rigoroso: interrompe antes do render se houver problemas não resolvidos
python agent.py roteiro.txt --art-director strict

# Desliga a validação explicitamente
python agent.py roteiro.txt --art-director off
```

`standard` é o padrão para preservar a compatibilidade com o pipeline existente. `strict` é recomendado para uma execução final de produção, mas pode interromper o processo se o avaliador visual não estiver instalado/configurado ou se houver assets rejeitados. A comparação lexical entre roteiro e transcrição Whisper é apenas indicativa e não prova equivalência semântica. Sem o Gemini configurado, a validação de conteúdo usa heurísticas e não deve ser tratada como avaliação visual semântica confiável. O relatório registra os problemas que precisam de revisão; não promete correção automática quando nenhum provider consegue obter uma mídia adequada.

A regeneração não apaga mais o asset atual antes de confirmar que existe um arquivo substituto, evitando perda da única mídia disponível quando uma busca falha.

---

## Sistema de Canais (`--channel` / `--canal`)

O VideoFactoryAI suporta múltiplos canais com identidades visuais, vozes e ritmos próprios:

```bash
# Canal Geopolítica (estilo urgente, contraste alto, cortes dinâmicos)
python VideoFactoryAI/agent.py roteiro.txt --channel geopolitica

# Canal Documentários (estilo sóbrio, analítico, narração solene)
python VideoFactoryAI/agent.py roteiro.txt --channel documentario

# Canal História (estética vintage/sépiada, tom épico, fontes de arquivo)
python VideoFactoryAI/agent.py roteiro.txt --channel historia

# Canal Tecnologia (moderno, ágil, voz feminina clara, paleta ciano)
python VideoFactoryAI/agent.py roteiro.txt --channel tecnologia
```

Os perfis residem em `VideoFactoryAI/channels/<canal>.yaml` e são mesclados automaticamente com `config.yaml`.

---

## Estratégia de Mídia Hierárquica (L1 → L4)

Em conformidade rigorosa com direitos autorais e minimização de custos com IA:

1. **Nível 1 — Vídeos com direitos verificáveis:** Pixabay, Pexels, Wikimedia Commons, Internet Archive e YouTube com licença reutilizável explícita (`--youtube-mode cc`). Um arquivo local só é usado com confirmação de autorização (`authorized`/`both`).
2. **Nível 2 — Imagens Reais Livres:** Wikimedia Commons, Pixabay, Pexels, Unsplash.
3. **Nível 3 — Conteúdo IA Público:** Openverse (Creative Commons verificável).
4. **Nível 4 — Geração própria:** Gemini; se não entregar imagem aprovada, CapCut Dreamina e depois Copilot. Todas as imagens geradas são baixadas como arquivo real e avaliadas contra o tema e o texto da cena.

*Direitos de uso:* O modo YouTube CC aceita somente licença reutilizável declarada nos metadados completos; vídeos indisponíveis, sem licença explícita ou sem correspondência com o tema são descartados. A licença e a origem são registradas em `memory/media_report.json`. CC não garante monetização: confira atribuições exigidas e as políticas atuais da plataforma.

---

## Sistema de Cache Inteligente (`cache/`)

Evita downloads repetidos quando temas similares são produzidos:
- Indexação por hash de consulta e tipo (`video` ou `image`)
- TTL configurável de 30 dias com controle de capacidade (LRU)
- Reutilização instantânea de assets idênticos

---

## Memória de Voz (`VoiceMemory`)

O agente memoriza e reaproveita automaticamente:
- Voz escolhida (ex: `pt-BR-AntonioNeural` ou `pt-BR-FranciscaNeural`)
- Velocidade (`rate`)
- Tom (`pitch`)
- Engine utilizada (`edge-tts`, `f5-tts`, `openai`)

Você não precisa reconfigurar a voz em cada execução. Ela é salva em `VideoFactoryAI/memory/preferences.json`.

---

## Agente de Qualidade (`QualityAgent`)

Executado logo após a renderização final:
- Compara a duração do vídeo contra a duração exata do áudio
- Detecta frames pretos acima do limiar aceitável via FFmpeg `blackdetect`
- Analisa keyframes para detectar repetição indevida de cenas
- Audita integridade do arquivo `.srt` de legendas
- Valida resolução e presença de trilha de áudio
- **Gera `saida/quality_report.json`**
- **Bloqueia a exportação (`sys.exit(1)`) caso existam erros críticos.**

---

## Agente de SEO YouTube (`SeoAgent`)

Gera `saida/youtube_metadata.json` contendo:
- Título otimizado com sufixo do canal
- Descrição completa com resumo do roteiro
- Capítulos automáticos com timestamps (`00:00 - Introdução`, etc.) baseados nas cenas
- Tags YouTube com controle de tamanho
- Top hashtags temáticas e palavras-chave extraídas

---

## Agente de Thumbnail (`ThumbnailAgent`)

Gera 3 abordagens distintas:
- `thumbnail_v1.jpg`: Frame do início da narrativa com overlay e título
- `thumbnail_v2.jpg`: Frame central com ambientação visual
- `thumbnail_v3.jpg`: Card tipográfico de alto contraste com cores do canal

Mede o contraste de luminância (desvio padrão) de cada versão e salva a melhor como `saida/thumbnail.jpg`.

---

## Histórico e Métricas (`Analytics`)

Cada execução é adicionada a `VideoFactoryAI/memory/project_history.json`:
- Data e hora de execução
- Tema / roteiro
- Duração final (segundos e minutos)
- Número de cenas
- Proporção de mídia real vs. IA gerada
- Fontes utilizadas
- Tempo total de processamento do pipeline

---

## Estrutura de Diretórios

```
c:\Projeto_Ira_EUA\
│
├── VideoFactoryAI/
│   ├── agent.py                  # Orquestrador do pipeline (10 passos)
│   ├── config.yaml               # Configuração padrão do sistema
│   ├── AGENT.md                  # Documentação de uso
│   ├── ARCHITECTURE_REPORT.md    # Relatório técnico completo
│   ├── quality_agent.py          # QualityAgent
│   ├── seo_agent.py              # SeoAgent
│   ├── thumbnail_agent.py        # ThumbnailAgent
│   ├── media_research_agent.py   # MediaResearchAgent
│   ├── voice_memory.py           # VoiceMemory
│   ├── asset_cache.py            # AssetCache
│   ├── analytics.py              # Analytics
│   │
│   ├── channels/                 # Perfis de canais
│   │   ├── documentario.yaml
│   │   ├── geopolitica.yaml
│   │   ├── historia.yaml
│   │   └── tecnologia.yaml
│   │
│   └── memory/                   # Memória persistente
│       ├── preferences.json
│       ├── last_run.json
│       ├── project_history.json
│       └── media_report.json
│
├── cache/                        # Cache persistente de mídia
├── saida/                        # Diretório de artefatos finais
│   ├── documentario_final.mp4
│   ├── thumbnail.jpg
│   ├── thumbnail_v1.jpg, v2, v3
│   ├── thumbnail_report.json
│   ├── quality_report.json
│   └── youtube_metadata.json
│
├── modules/                      # Módulos reutilizados de vídeo e áudio
├── roteiro.txt                   # Roteiro de entrada
└── ffmpeg.exe                    # Binário do FFmpeg com NVEnc
```
