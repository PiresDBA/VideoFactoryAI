# Fontes de mídia gratuita — o que é usado de verdade

Este documento registra o **teste real** feito nas fontes de mídia livre e o
motivo de cada decisão. Regra do projeto: **se não baixa imagem/vídeo real, não entra.**

## Como testar

```powershell
# todas as fontes de imagem (baixa de verdade e valida com PIL)
python tools/testar_fontes_midia.py --sem-video --query "war" --query "nature"

# fontes específicas
python tools/testar_fontes_midia.py --apenas reshot,freestocks

# inclui as fontes de vídeo
python tools/testar_fontes_midia.py --query "war"
```

Saída: `tools/relatorio_fontes.json` (e `relatorio_fontes_final.json` na última execução).

## Critérios de aprovação

| Item | Exigência |
|------|-----------|
| HTTP | 200 e HTML com candidatos |
| Imagem válida | PIL abre e verifica o arquivo |
| Resolução | ≥ 800×450 e área ≥ 360.000 px |
| Ruído | rejeita logo, ícone, avatar, banner, OG/social card |
| Normalização | WEBP/PNG são convertidos para JPEG antes de usar |
| Colisão | hash MD5 único (nenhuma cena repete asset) |

## Resultado — imagens (24/10/2026)

**Aprovadas (4 de 35):**

| Fonte | Resolução obtida | Licença |
|-------|------------------|---------|
| `reshot` | 2560×1440 | Reshot (uso livre, inclusive comercial) |
| `negativespace` | 2048×1367 | CC0 |
| `freestocks` | 1024×683 | CC0 |
| `newoldstock` | 820×1200 | domínio público (vintage P&B) |

**Reprovadas (31)** — bloqueadas em runtime por
`FREE_IMAGE_SOURCES_APROVADOS`, mesmo estando cadastradas:

`adobestock, burst, canva, depositphotos, focastock, foodiesfeed, freeimages,
freepik, freerange, gettyimages, gratispics, isorepublic, istock, jaymantri,
kaboompics, libreshot, lifeofpix, littlevisuals, morguefile, pexels, picjumbo,
picography, picspree, pikwizard, rgbstock, shutterstock, skitterphoto,
startupstockphotos, stocksnap, stockvault, unsplash`

Motivos mais comuns:
- páginas renderizadas por JavaScript (o HTML não traz a imagem);
- só entregam thumbnail (~200–450 px) na listagem;
- o único link grande era cartão Open Graph (1200×630), não conteúdo;
- site pago/llicença restrita (Shutterstock, Getty, iStock, Adobe, DepositPhotos).

> Pexels e Unsplash continuam disponíveis, mas **pela API oficial** (com chave em
> `media.pexels_api_key` / `media.unsplash_api_key`), não por scraping.

## Hierarquia real do pipeline

```
L1  vídeo real  → Pixabay API, Pexels API, Wikimedia, Internet Archive
L2  imagem real → Pixabay API, Wikimedia, Pexels API, Unsplash API
    + extras    → reshot, negativespace, freestocks, newoldstock  (aprovadas)
L3  IA pública  → Openverse (CC comercial)
L4  IA gerada   → Pollinations (seed única) → PIL card (fallback final)
```

Toda mídia passa pelo **ImageEvaluatorAgent** (compatibilidade imagem↔roteiro,
score 0–100) antes de ser aceita.

## Adicionar uma fonte nova

1. Cadastre em `FREE_IMAGE_SOURCES` (`VideoFactoryAI/media_research_agent.py`).
2. Rode `python tools/testar_fontes_midia.py --apenas nome_da_fonte`.
3. Só então adicione o nome em `FREE_IMAGE_SOURCE_ORDER` (e em
   `FREE_IMAGE_SOURCES_APROVADOS`, que é derivado automaticamente).
