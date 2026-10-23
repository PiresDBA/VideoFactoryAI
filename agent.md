# VideoFactoryAI

## Missão

Converter um roteiro em um documentário completo.

## Entrada

roteiro.txt

## Saídas

- video_final.mp4
- thumbnail.jpg
- narracao.mp3
- legendas.srt

## MEDIA ACQUISITION STRATEGY

Priority 1:
- Pixabay
- Pexels
- Unsplash
- Wikimedia Commons
- Internet Archive

Priority 2:
- Public AI-generated assets with reuse permission.

Priority 3:
- Generate with AI.

Never assume YouTube videos are reusable.

Only use YouTube content when the license explicitly allows reuse or when the user provides authorization.

Prefer real footage over generated footage whenever possible.

Prefer existing high-quality public media over generating new assets.

## Pipeline

1. Leitura do roteiro
2. Planejamento de cenas
3. Busca de mídia
4. Geração de narração
5. Geração de legendas
6. Processamento visual
7. Montagem FFmpeg
8. Exportação

## Componentes existentes

- pipeline_ecc.py (orquestrador)
- media_engine.py
- visual_processor.py
- composer.py
- srt_parser.py

## Objetivo

Executar todo o fluxo automaticamente quando receber um novo roteiro.