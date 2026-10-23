# VideoFactoryAI

> Documentação técnica simplificada segundo a norma internacional ASD-STE100.

O VideoFactoryAI é um produtor autônomo de documentários em vídeo de 1080p.
Ele transforma um tema ou um roteiro em texto em um vídeo pronto para publicação no YouTube.

---

## Recursos Principais

- **Pesquisa e Roteiro Automáticos:** Pesquisa fatos históricos e escreve roteiros em cinco atos com o parâmetro `--topic`.
- **Narração Neural Sem Custo:** Gera narração clara e natural em português com o Microsoft Edge-TTS.
- **Legendas com Whisper:** Transcreve áudio com alta precisão e queima legendas diretamente no vídeo.
- **Hierarquia de Mídias Livres:** Busca vídeos e fotos reais em arquivos públicos antes de usar geração por inteligência artificial.
- **Capas com Seleção por Contraste:** Gera três versões de capa e escolhe a versão com maior destaque visual.
- **Agente de Qualidade:** Verifica duração, áudio, quadros pretos e resolução antes de liberar o vídeo final.
- **Metadados para YouTube:** Gera título, descrição completa, etiquetas e marcadores de capítulos.
- **Memória entre Execuções:** Salva o tom de voz e o histórico de cada produção na pasta de memória.

---

## Como Instalar

Siga estes passos simples:

1. Baixe ou clone este repositório.
2. Dê um clique duplo no arquivo `install.bat` (ou execute `python setup.py`).
3. O instalador configura o ambiente e verifica o FFmpeg e a placa de vídeo.

---

## Como Usar

### 1. Produção Automática a partir de um Tema (Sem Roteiro)
Execute o comando informando o assunto e o tempo em minutos:

```cmd
python VideoFactoryAI/agent.py --topic "A Guerra Fria" --duration 8
```

### 2. Produção a partir de um Roteiro Pronto
Coloque o seu texto no arquivo `roteiro.txt` e execute:

```cmd
python VideoFactoryAI/agent.py roteiro.txt
```

### 3. Seleção de Estilo de Canal
Use o parâmetro `--channel` para escolher o estilo:

```cmd
python VideoFactoryAI/agent.py --topic "Crise de Cuba" --duration 5 --channel geopolitica
```

Opções de canais disponíveis:
- `documentario`: Tom jornalístico e analítico.
- `geopolitica`: Tom estratégico e ritmo rápido.
- `historia`: Tom clássico e imagens de arquivo.
- `tecnologia`: Tom moderno e visual dinâmico.

---

## Arquivos Gerados na Pasta `saida/`

Ao final do processamento, você recebe:

- `documentario_final.mp4`: Vídeo final em resolução 1920x1080 a 30 quadros por segundo.
- `thumbnail.jpg`: Imagem de capa vencedora por teste de contraste.
- `thumbnail_v1.jpg`, `thumbnail_v2.jpg`, `thumbnail_v3.jpg`: Todas as opções geradas.
- `youtube_metadata.json`: Título, descrição, etiquetas e capítulos para copiar e colar no YouTube.
- `quality_report.json`: Relatório de controle de qualidade do vídeo.

---

## Estrutura do Projeto

```
VideoFactoryAI/
├── agent.py                  # Ponto de entrada e orquestrador
├── script_writer_agent.py    # Agente pesquisador e roteirista
├── media_research_agent.py   # Agente de busca hierárquica de mídia
├── quality_agent.py          # Agente auditor de qualidade
├── seo_agent.py              # Agente de metadados para YouTube
├── thumbnail_agent.py        # Agente gerador de capas
├── voice_memory.py           # Agente de persistência de voz
├── asset_cache.py            # Cache inteligente de mídias
├── analytics.py              # Histórico e estatísticas
├── config.yaml               # Arquivo de configurações padrão
├── channels/                 # Perfis de canais
└── memory/                   # Memória de preferências e histórico
```

Para mais detalhes passo a passo para iniciantes, consulte o [Manual do Usuário](MANUAL_DO_USUARIO.md).
