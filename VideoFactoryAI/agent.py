#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
===============================================================================
VideoFactoryAI — Orquestrador do Pipeline Autônomo de Produção de Documentários
===============================================================================

ESTE SCRIPT É O PONTO DE ENTRADA PRINCIPAL DO SISTEMA VIDEOFACTORYAI.
Ele automatiza 100% da criação de vídeos documentários em resolução 1080p,
transformando um roteiro em texto ou um simples tema em um vídeo pronto para o YouTube.

-------------------------------------------------------------------------------
COMO RODAR ESTE SCRIPT (GUIA RÁPIDO PARA QUALQUER USUÁRIO):
-------------------------------------------------------------------------------

1. INSTALAÇÃO INICIAL (feita apenas uma vez):
   Dê dois cliques no arquivo:
       install.bat
   Ou execute no terminal:
       python setup.py

2. MODO 1: Você já possui um roteiro escrito (arquivo roteiro.txt):
   Coloque seu texto em 'roteiro.txt' e execute:
       python VideoFactoryAI/agent.py roteiro.txt

3. MODO 2: Você NÃO possui roteiro (O agente pesquisa, escreve e produz sozinho):
   Apenas informe o tema entre aspas e a duração desejada em minutos:
       python VideoFactoryAI/agent.py --topic "A Guerra Fria" --duration 8

4. SELEÇÃO DE ESTILO E CANAL (opcional):
   Você pode escolher a identidade visual e o ritmo do documentário:
       python VideoFactoryAI/agent.py --topic "Crise de Cuba" --duration 5 --channel geopolitica
       python VideoFactoryAI/agent.py roteiro.txt --channel historia
       python VideoFactoryAI/agent.py roteiro.txt --channel tecnologia
       python VideoFactoryAI/agent.py roteiro.txt --channel documentario

5. TROCA DE VOZ DE NARRAÇÃO (opcional):
   Para usar outra voz neural do Microsoft Edge-TTS:
       python VideoFactoryAI/agent.py roteiro.txt --voice pt-BR-FranciscaNeural

6. RETOMAR EXECUÇÃO CASO A INTERNET CAIA (--resume):
   Se o computador desligar ou a conexão cair no meio da produção:
       python VideoFactoryAI/agent.py roteiro.txt --resume
   O agente continuará exatamente da etapa onde parou, sem re-baixar o que já fez.

-------------------------------------------------------------------------------
OS 10 PASSOS AUTOMÁTICOS DO PIPELINE:
-------------------------------------------------------------------------------
Passo 0:  ScriptWriterAgent     -> Pesquisa na Wikipedia e escreve o roteiro (se usar --topic)
Passo 1:  Planejamento de Cenas -> Segmenta o roteiro em cenas coerentes de ~12 segundos
Passo 2:  Geração de Voz (TTS)  -> Narração neural em português e memorização da voz
Passo 3:  Legendas (Whisper)    -> Transcrição com timecodes precisos e sincronização
Passo 4:  Busca de Mídia (MRA)  -> Hierarquia L1 (vídeo) a L4 (IA) com verificação de licença
Passo 5:  Processador Visual    -> Aplicação de efeito Ken Burns e normalização para 1080p
Passo 6:  Renderização Final    -> FFmpeg concatena clipes, queima legendas e mescla áudio
Passo 7:  ThumbnailAgent        -> Produz 3 variações de capa e elege a de maior contraste
Passo 8:  QualityAgent          -> Audita duração, frames pretos e integridade do vídeo
Passo 9:  SeoAgent              -> Gera título, descrição, tags e capítulos para o YouTube
Passo 10: Analytics             -> Registra estatísticas e histórico em project_history.json

-------------------------------------------------------------------------------
ONDE OS ARQUIVOS FINAIS SÃO SALVOS:
-------------------------------------------------------------------------------
Na pasta 'saida/':
  - documentario_final.mp4      (Vídeo final 1080p completo com áudio e legendas)
  - thumbnail.jpg               (Capa eleita com maior destaque visual)
  - thumbnail_v1, v2, v3.jpg    (Todas as 3 opções de capa geradas)
  - youtube_metadata.json       (Título, descrição, tags e capítulos prontos)
  - quality_report.json         (Laudo técnico de aprovação do QualityAgent)

Na pasta 'VideoFactoryAI/memory/':
  - preferences.json            (Configurações de voz e fontes aprendidas)
  - project_history.json        (Histórico consolidado de todos os vídeos produzidos)
  - media_report.json           (Auditoria de direitos autorais de cada mídia usada)
===============================================================================
"""

# =============================================================================
# IMPORTAÇÃO DE BIBLIOTECAS DO SISTEMA
# =============================================================================
import os             # Operações de sistema de arquivos e caminhos
import sys            # Acesso a argumentos de linha de comando e encerramento
import json           # Leitura e gravação de arquivos de dados JSON
import time           # Contagem de tempo de execução do pipeline
import shutil         # Operações de cópia e limpeza de diretórios
import argparse       # Parser profissional de opções de linha de comando
import asyncio        # Suporte a rotinas assíncronas (usado pelo Edge-TTS)
import re             # Expressões regulares para limpeza de texto e timecodes
import subprocess     # Execução do FFmpeg em segundo plano
import urllib.parse   # Codificação de URLs para requisições web
import requests       # Requisições HTTP para APIs de mídia e pesquisa
from pathlib import Path  # Manipulação moderna e segura de caminhos de arquivos
from typing import List, Dict, Any, Optional, Tuple  # Tipagem estática defensiva

# =============================================================================
# CARREGAMENTO SEGURO DOS AGENTES ESPECIALIZADOS (LAZY IMPORT)
# =============================================================================
# Usamos blocos try/except para importar cada agente. Se alguma biblioteca opcional
# não estiver instalada, o sistema não falha na inicialização do script ou no --help.

# Agente de Pesquisa Hierárquica de Mídia (L1 a L4 com compliance)
_MRA_AVAILABLE = False
try:
    from media_research_agent import MediaResearchAgent as _MRA
    _MRA_AVAILABLE = True
except ImportError:
    _MRA = None  # type: ignore

# Agente de Auditoria de Qualidade pós-renderização
_QUALITY_AVAILABLE = False
try:
    from quality_agent import QualityAgent as _QA
    _QUALITY_AVAILABLE = True
except ImportError:
    _QA = None  # type: ignore

# Agente de Otimização e Metadados para YouTube (SEO)
_SEO_AVAILABLE = False
try:
    from seo_agent import SeoAgent as _SEO
    _SEO_AVAILABLE = True
except ImportError:
    _SEO = None  # type: ignore

# Agente de Geração e Classificação de Thumbnails por Contraste
_THUMB_AGENT_AVAILABLE = False
try:
    from thumbnail_agent import ThumbnailAgent as _THUMBA
    _THUMB_AGENT_AVAILABLE = True
except ImportError:
    _THUMBA = None  # type: ignore

# Agente de Registro de Histórico e Métricas de Produção
_ANALYTICS_AVAILABLE = False
try:
    from analytics import Analytics as _ANALYTICS
    _ANALYTICS_AVAILABLE = True
except ImportError:
    _ANALYTICS = None  # type: ignore

# Agente de Memória e Reuso de Preferências de Voz
_VOICE_MEM_AVAILABLE = False
try:
    from voice_memory import VoiceMemory as _VMEM
    _VOICE_MEM_AVAILABLE = True
except ImportError:
    _VMEM = None  # type: ignore

# Cache Persistente de Assets de Mídia (evita re-downloads de consultas iguais)
_CACHE_AVAILABLE = False
try:
    from asset_cache import AssetCache as _CACHE
    _CACHE_AVAILABLE = True
except ImportError:
    _CACHE = None  # type: ignore

# Roteirista e Pesquisador Autônomo (permite o modo --topic sem roteiro pronto)
_WRITER_AVAILABLE = False
try:
    from script_writer_agent import ScriptWriterAgent as _SWA
    _WRITER_AVAILABLE = True
except ImportError:
    _SWA = None  # type: ignore

# =============================================================================
# LOCALIZAÇÃO DE DIRETÓRIOS E COMPATIBILIDADE DE IMPORTAÇÃO
# =============================================================================
# Garante que o Python encontre os módulos existentes dentro da pasta modules/
AGENT_DIR = Path(__file__).resolve().parent  # Pasta C:\Projeto_Ira_EUA\VideoFactoryAI
ROOT_DIR  = AGENT_DIR.parent                # Pasta raiz C:\Projeto_Ira_EUA
sys.path.insert(0, str(ROOT_DIR))            # Adiciona a raiz ao caminho de busca do Python

# Importa módulos de áudio e vídeo existentes na codebase (sem qualquer modificação neles)
from modules.media_engine     import ensure_media_for_scenes
from modules.visual_processor import process_all_scenes
from modules.composer         import assemble_master_documentary

# Carregamento seguro da biblioteca PyYAML (com fallback para dict se ausente)
try:
    import yaml
    def load_config(path: Path) -> dict:
        """Carrega e interpreta um arquivo YAML retornando um dicionário Python."""
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
except ImportError:
    def load_config(path: Path) -> dict:  # type: ignore
        """Fallback defensivo caso PyYAML não esteja instalado."""
        return {}


# =============================================================================
# GERENCIAMENTO DE CONFIGURAÇÃO (HIERARQUIA DE PRIORIDADES)
# =============================================================================
def get_config(config_path: Path, overrides: dict) -> dict:
    """
    Carrega as configurações aplicando a ordem de prioridade oficial:
    1. Defaults internos embutidos no código (base de segurança)
    2. Valores definidos em VideoFactoryAI/config.yaml (configuração do usuário)
    3. Parâmetros passados via linha de comando (máxima prioridade)
    """
    cfg = load_config(config_path)

    # Valores padrão embutidos: garantem que o sistema nunca quebre por falta de chave
    defaults = {
        "tts": {
            "engine": "edge-tts",
            "voice": "pt-BR-AntonioNeural",
            "rate": "+0%",
            "pitch": "+0Hz",
            "f5_ref_audio": "voice/minhavoz_curta.wav",
            "f5_ref_text": ""
        },
        "whisper": {
            "model": "base",
            "language": "pt",
            "device": "auto"
        },
        "scenes": {
            "target_duration_s": 12.0,
            "min_duration_s": 5.0,
            "max_duration_s": 25.0
        },
        "media": {
            "pixabay_api_key": "58184749-b92df4cd039274d2c7a6aac7a",
            "ai_image_provider": "pollinations"
        },
        "video": {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "crf": 20,
            "preset": "fast",
            "ken_burns_zoom_speed": 0.0008
        },
        "subtitles": {
            "font_size": 24,
            "margin_v": 35
        },
        "output": {
            "video_filename": "documentario_final.mp4",
            "thumbnail_filename": "thumbnail.jpg",
            "thumbnail_width": 1280,
            "thumbnail_height": 720
        },
        "agent": {
            "checkpoint_enabled": True,
            "verbose": True,
            "clean_temp_on_success": False
        },
    }

    # Mescla: defaults <- arquivo config.yaml
    for section, vals in defaults.items():
        if section not in cfg:
            cfg[section] = {}
        for k, v in vals.items():
            cfg[section].setdefault(k, v)

    # Aplica substituições manuais de linha de comando (se fornecidas pelo usuário)
    if overrides.get("voice"):
        cfg["tts"]["voice"] = overrides["voice"]
    if overrides.get("whisper_model"):
        cfg["whisper"]["model"] = overrides["whisper_model"]
    if overrides.get("tts_engine"):
        cfg["tts"]["engine"] = overrides["tts_engine"]

    return cfg


# =============================================================================
# PASSO 1 — PLANEJAMENTO E CLASSIFICAÇÃO SEMÂNTICA DE CENAS
# =============================================================================
# Dicionários de palavras-chave para identificar termos históricos e associar
# automaticamente à melhor fonte de imagem pública e verificada.

HISTORICAL_KEYWORDS = [
    "1953", "1979", "golpe", "mossadegh", "shah", "pahlavi", "khomeini",
    "reféns", "embaixada", "revolução islâmica", "guerra fria",
]

# Mapa de entidades históricas com fotos documentais no Wikimedia Commons
WIKIMEDIA_MAP = {
    "mossadegh":          "Court officials in military trial of Mohammad Mosaddegh",
    "shah":               "Mohammad Reza Pahlavi Shah portrait",
    "pahlavi":            "Mohammad Reza Pahlavi Shah portrait",
    "khomeini":           "Portrait of Ruhollah Khomeini By Ali Kaveh",
    "reféns":             "Iran hostage crisis Tehran 1979 US embassy",
    "golpe":              "1953 Iran coup d'etat Mossadegh protest Tehran",
    "guerra fria":        "Cold War 1950s historical archive",
    "revolução islâmica": "Islamic Revolution Iran 1979 Khomeini historical",
    "embaixada":          "Iran hostage crisis Tehran 1979 US embassy siege",
}

# Consultas alternativas para o Pixabay caso o Wikimedia não retorne mídia
WIKIMEDIA_PIXABAY_FALLBACK = {
    "mossadegh":          "iran history archive vintage",
    "shah":               "iran history archive vintage middle east",
    "pahlavi":            "iran history archive vintage",
    "khomeini":           "iran revolution crowd vintage protest",
    "reféns":             "protest crowd embassy crisis vintage",
    "golpe":              "protest crowd 1950s historical vintage",
    "guerra fria":        "cold war nuclear bomb vintage archive",
    "revolução islâmica": "crowd protest revolution vintage",
    "embaixada":          "protest crowd embassy crisis vintage",
}

# Mapa de termos conceituais e suas buscas equivalentes em inglês (para vídeos stock)
SEMANTIC_QUERIES = {
    # Geopolítica e Poder
    "bandeiras":       "american flag waving",
    "aliados":         "american flag waving politics",
    "aliança":         "handshake diplomacy meeting politicians",
    "aliadas":         "american flag waving politics",
    "sanções":         "economic sanctions protest inflation market",
    "manchetes":       "news broadcast studio television journalism",
    "geopolítica":     "world map rotating globe geopolitics",
    "tabuleiro":       "chess board strategy game global",
    "xadrez":          "chess board strategy game",
    # Recursos e Petróleo
    "petróleo":        "oil pump jack desert oilfield",
    "estreito":        "oil tanker cargo ship sea ocean",
    "ormuz":           "oil tanker cargo ship hormuz sea",
    "refinaria":       "oil refinery industrial plant sunset",
    "posto":           "gas station fuel pump car",
    "combustível":     "gas station fuel pump car",
    "energia":         "nuclear power plant cooling towers",
    # Governo e Conflitos Militares
    "casa branca":     "white house washington dc government",
    "washington":      "white house washington dc politics",
    "militares":       "aircraft carrier ocean military navy",
    "presença militar":"aircraft carrier ocean military",
    "militar":         "soldiers patrol military desert",
    "guerra":          "military smoke explosion war destruction",
    "confronto":       "military smoke explosion war conflict",
    "custo":           "military smoke explosion war destruction",
    # Tecnologia e Energia Nuclear
    "nuclear":         "nuclear power plant cooling towers reactor",
    "urânio":          "nuclear power plant cooling towers",
    "tecnologia":      "laboratory scientist microscope research",
    "científico":      "laboratory scientist microscope research",
    "científica":      "laboratory scientist microscope research",
    # Economia e Moeda
    "inflação":        "money counting cash inflation economy",
    "econômica":       "economic market stock trading finance",
    "resistência":     "money counting cash inflation economy",
    "sobrevivência":   "money counting cash inflation economy",
    # Conflitos Cibernéticos e Sociais
    "ciberataque":     "binary code matrix digital data hacker",
    "cibernétic":      "binary code matrix digital data hacker",
    "procuração":      "binary code matrix digital data hacker",
    "refugiados":      "refugee camp humanitarian crisis displaced",
    "humanitária":     "refugee camp humanitarian crisis",
    "tensão":          "military tension standoff armed forces",
    # Diplomacia e Tratados
    "diplomacia":      "diplomats meeting table negotiation treaty",
    "diplomátic":      "diplomats meeting table negotiation",
    "acordo":          "diplomats meeting table negotiation signing",
    "negociação":      "diplomats meeting table negotiation",
    # Relações Internacionais
    "onu":             "united nations flags international assembly",
    "século xxi":      "united nations flags international diplomacy",
    # Oriente Médio
    "oriente médio":   "soldiers patrol middle east desert",
    "teerã":           "modern tehran iran city skyline aerial",
    "irã":             "modern tehran iran city skyline aerial",
    "soberania":       "modern tehran iran city skyline aerial",
    # Chamadas para Ação no YouTube
    "inscreva":        "youtube subscribe bell button notification",
    "inscrição":       "youtube subscribe bell button notification",
    "like":            "youtube subscribe bell button notification",
    "comentário":      "youtube subscribe bell button notification",
    "comentários":     "youtube subscribe bell button notification",
    "gostou":          "youtube subscribe bell button notification",
}


def _classify_scene(text: str) -> tuple:
    """
    Analisa o texto de uma cena e decide a estratégia de mídia:
    Retorna: (tipo, query_pixabay, query_wikimedia, ai_prompt, precisa_de_ia)
    - tipo: 'video' ou 'image'
    - query_pixabay: termo em inglês para buscar no Pixabay/Pexels
    - query_wikimedia: busca específica para imagem histórica no Wikimedia
    - ai_prompt: prompt detalhado caso seja necessário gerar com IA
    - precisa_de_ia: se True, aciona IA gerativa caso a busca real não encontre
    """
    low = text.lower()

    # 1. Prioridade Máxima: figuras históricas com fotos documentadas no Wikimedia
    for kw, wm_q in WIKIMEDIA_MAP.items():
        if kw in low:
            px_fallback = WIKIMEDIA_PIXABAY_FALLBACK.get(kw, "vintage historical archive documentary")
            ai_prompt   = f"Cinematic historical documentary photograph, film grain: {text[:100]}"
            return "image", px_fallback, wm_q, ai_prompt, False

    # 2. Palavras-chave históricas gerais -> imagens de época
    for kw in HISTORICAL_KEYWORDS:
        if kw in low:
            ai_prompt = (
                f"Cinematic historical documentary photograph, realistic 1970s film grain, "
                f"dramatic lighting, subject: {text[:100]}"
            )
            return "image", "vintage historical archive documentary", "", ai_prompt, True

    # 3. Termos modernos ou conceituais -> vídeos de arquivo (Pixabay)
    for kw, en_q in SEMANTIC_QUERIES.items():
        if kw in low:
            return "video", en_q, "", "", False

    # 4. Fallback padrão: imagens ou vídeos genéricos de documentário
    return "video", "geopolitics world news documentary footage", "", "", False


def plan_scenes(script_text: str, cfg: dict) -> List[Dict[str, Any]]:
    """
    Passo 1 do Pipeline:
    Divide o texto do roteiro em cenas de aproximadamente 12 segundos cada.
    A duração inicial é estimada pela contagem de palavras (taxa de 2.3 palavras/segundo).
    Mais tarde (no Passo 3), o Whisper ressincroniza com precisão milimétrica.
    """
    target_dur   = cfg["scenes"]["target_duration_s"]  # Duração alvo de cada cena (12s)
    min_dur      = cfg["scenes"]["min_duration_s"]     # Duração mínima aceitável (5s)
    words_per_s  = 2.3                                 # Velocidade média de narração em PT-BR

    # Divide o roteiro em sentenças respeitando pontos finais e exclamações
    sentences = re.split(r'(?<=[.!?])\s+', script_text.strip())
    target_words = int(target_dur * words_per_s)

    scenes, group, wcount, scene_id = [], [], 0, 1
    for sent in sentences:
        group.append(sent)
        wcount += len(sent.split())

        # Quando o bloco atinge a meta de palavras da cena, fecha e classifica
        if wcount >= target_words:
            combined = " ".join(group)
            tipo, q_en, wm_q, ai_prompt, needs_ai = _classify_scene(combined)
            ext = ".mp4" if tipo == "video" else ".jpg"

            scenes.append({
                "id":           scene_id,
                "tipo":         tipo,
                "arquivo":      f"cena_{scene_id:02d}{ext}",
                "query":        q_en,
                "wikimedia_q":  wm_q,
                "ai_prompt":    ai_prompt,
                "needs_ai":     needs_ai,
                "descricao":    combined[:80],
                "texto":        combined,
                "start":        0.0,  # Será atualizado após o Whisper gerar o SRT
                "end":          0.0,
                "duration":     max(round(wcount / words_per_s, 2), min_dur),
            })
            scene_id += 1
            group, wcount = [], 0

    # Adiciona as frases restantes como última cena
    if group:
        combined = " ".join(group)
        tipo, q_en, wm_q, ai_prompt, needs_ai = _classify_scene(combined)
        ext = ".mp4" if tipo == "video" else ".jpg"
        scenes.append({
            "id":           scene_id,
            "tipo":         tipo,
            "arquivo":      f"cena_{scene_id:02d}{ext}",
            "query":        q_en,
            "wikimedia_q":  wm_q,
            "ai_prompt":    ai_prompt,
            "needs_ai":     needs_ai,
            "descricao":    combined[:80],
            "texto":        combined,
            "start":        0.0,
            "end":          0.0,
            "duration":     max(round(wcount / words_per_s, 2), min_dur),
        })

    return scenes


# =============================================================================
# PASSO 2 — GERAÇÃO DE VOZ NEURAL (TTS)
# =============================================================================

async def _edge_tts_async(text: str, out: str, voice: str, rate: str, pitch: str):
    """Executa a síntese de voz assíncrona usando a biblioteca Microsoft Edge-TTS."""
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await comm.save(out)


def generate_voice(text: str, out_path: str, cfg: dict) -> str:
    """
    Passo 2 do Pipeline:
    Sintetiza a narração completa do documentário em um arquivo MP3 de alta qualidade.
    Por padrão, utiliza o Microsoft Edge-TTS (100% gratuito, sem limite e neural).
    Possui suporte integrado e fallbacks para clonagem via F5-TTS e OpenAI TTS.
    """
    engine = cfg["tts"]["engine"]
    voice  = cfg["tts"]["voice"]
    rate   = cfg["tts"]["rate"]
    pitch  = cfg["tts"]["pitch"]

    # Se o áudio já existe e tem tamanho válido, reaproveita
    if os.path.exists(out_path) and os.path.getsize(out_path) > 50_000:
        log("  [TTS] Narração já existe — pulando geração.")
        return out_path

    log(f"  [TTS] Gerando narração via {engine} (voz: {voice})...")

    # 1. Motor padrão: Microsoft Edge-TTS
    if engine == "edge-tts":
        asyncio.run(_edge_tts_async(text, out_path, voice, rate, pitch))

    # 2. Motor opcional: F5-TTS para clonagem de voz do usuário
    elif engine == "f5-tts":
        try:
            from f5_tts.api import F5TTS
            ref = cfg["tts"]["f5_ref_audio"]
            ref_text = cfg["tts"]["f5_ref_text"]
            F5TTS().infer(ref_file=ref, ref_text=ref_text, gen_text=text, file_wave=out_path)
        except Exception as e:
            log(f"  [TTS] F5-TTS falhou ({e}) — usando fallback edge-tts.", warn=True)
            asyncio.run(_edge_tts_async(text, out_path, voice, rate, pitch))

    # 3. Motor opcional: OpenAI TTS HD
    elif engine == "openai":
        try:
            from openai import OpenAI
            client = OpenAI(api_key=cfg["media"].get("openai_api_key") or os.getenv("OPENAI_API_KEY"))
            resp = client.audio.speech.create(
                model="tts-1-hd",
                voice=cfg["tts"]["openai_voice"],
                input=text
            )
            resp.stream_to_file(out_path)
        except Exception as e:
            log(f"  [TTS] OpenAI TTS falhou ({e}) — usando fallback edge-tts.", warn=True)
            asyncio.run(_edge_tts_async(text, out_path, voice, rate, pitch))

    # Validação de integridade do arquivo de áudio gerado
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        raise RuntimeError(f"Erro no TTS: arquivo de áudio inválido em {out_path}")

    size_kb = os.path.getsize(out_path) / 1024
    log(f"  [TTS] Narração concluída: {Path(out_path).name} ({size_kb:.0f} KB)")
    return out_path


# =============================================================================
# PASSO 3 — TRANSCRIÇÃO E GERAÇÃO DE LEGENDAS (WHISPER)
# =============================================================================

def _format_ts(s: float) -> str:
    """Converte segundos em ponto flutuante para o formato SRT: HH:MM:SS,mmm"""
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    sc, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sc:02d},{ms:03d}"


def generate_subtitles(audio_path: str, srt_out: str, cfg: dict) -> List[Dict]:
    """
    Passo 3 do Pipeline:
    Executa o modelo OpenAI Whisper diretamente na máquina (usando GPU via CUDA).
    Transcreve a narração gerada e produz o arquivo de legendas 'narracao.srt'.
    Retorna uma lista de blocos de legenda com tempo inicial, final e texto.
    """
    if os.path.exists(srt_out) and os.path.getsize(srt_out) > 500:
        log("  [Whisper] Legenda SRT já existe — lendo arquivo existente.")
        return _parse_srt(srt_out)

    import whisper
    import torch

    model_name = cfg["whisper"]["model"]
    device_cfg = cfg["whisper"]["device"]
    # Seleção automática de GPU ou CPU
    device = ("cuda" if torch.cuda.is_available() else "cpu") if device_cfg == "auto" else device_cfg

    log(f"  [Whisper] Carregando modelo '{model_name}' na aceleração '{device}'...")
    model = whisper.load_model(model_name, device=device)

    log(f"  [Whisper] Transcrevendo áudio '{Path(audio_path).name}'...")
    result = model.transcribe(audio_path, language=cfg["whisper"]["language"], verbose=False)
    segments = result.get("segments", [])
    blocks   = []

    # Gravação do arquivo SRT em disco
    os.makedirs(os.path.dirname(os.path.abspath(srt_out)), exist_ok=True)
    with open(srt_out, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            st  = round(float(seg["start"]), 3)
            et  = round(float(seg["end"]),   3)
            txt = seg["text"].strip()
            f.write(f"{i}\n{_format_ts(st)} --> {_format_ts(et)}\n{txt}\n\n")
            blocks.append({
                "id": i, "start": st, "end": et,
                "duration": round(et - st, 3), "text": txt
            })

    log(f"  [Whisper] {len(blocks)} blocos de legenda sincronizados com sucesso.")
    return blocks


def _parse_srt(srt_path: str) -> List[Dict]:
    """Lê um arquivo .srt existente e extrai seus blocos com timecodes em segundos."""
    with open(srt_path, encoding="utf-8-sig") as f:
        content = f.read()
    pattern = re.compile(
        r'(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n([\s\S]*?)(?=\n\s*\d+\s*\n|\Z)'
    )
    def pt(ts):
        h, m, s = ts.replace(",", ".").split(":")
        return int(h)*3600 + int(m)*60 + float(s)

    return [{
        "id": int(m[0]),
        "start": round(pt(m[1]), 3),
        "end": round(pt(m[2]), 3),
        "duration": round(pt(m[2]) - pt(m[1]), 3),
        "text": re.sub(r'\s+', ' ', m[3]).strip()
    } for m in pattern.findall(content)]


def resync_scenes(scenes: List[Dict], blocks: List[Dict], total_dur: float) -> List[Dict]:
    """
    Ressincroniza os tempos de corte de cada cena com os timecodes exatos do Whisper.
    Garante que os cortes de vídeo coincidam com pausas de frases, evitando cortes bruscos.
    """
    if not scenes or not blocks:
        return scenes

    bps     = max(1, len(blocks) // len(scenes))
    cursor  = 0
    updated = []

    for i, scene in enumerate(scenes):
        is_last = (i == len(scenes) - 1)
        end_idx = min(cursor + bps, len(blocks) - 1)

        # Procura pontuação final de frase para fazer o corte no momento mais natural
        if not is_last:
            for j in range(end_idx, min(end_idx + 4, len(blocks))):
                if re.search(r'[.!?]$', blocks[j]["text"].strip()):
                    end_idx = j
                    break

        if is_last:
            end_idx = len(blocks) - 1

        st = blocks[cursor]["start"]
        et = (total_dur if is_last else blocks[end_idx]["end"])

        updated.append({
            **scene,
            "start":    round(st, 3),
            "end":      round(et, 3),
            "duration": round(max(et - st, 1.0), 3)
        })
        cursor = end_idx + 1
        if cursor >= len(blocks):
            cursor = len(blocks) - 1

    return updated


# =============================================================================
# PASSO 4 — BUSCA DE MÍDIA (FALLBACK PROCEDURAL LEGADO)
# =============================================================================
# Caso o MediaResearchAgent encontre alguma cena sem imagem, estas funções
# garantem que o vídeo nunca fique com buracos pretos ou sem mídia.

def _pollinations(prompt: str, dest: str) -> bool:
    """Gera uma imagem de 1920x1080 via Pollinations AI gratuito."""
    enc = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{enc}?width=1920&height=1080&nologo=true"
    try:
        r = requests.get(url, timeout=35)
        if r.status_code == 200 and len(r.content) > 15_000:
            os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(r.content)
            return True
    except Exception as e:
        log(f"  [Pollinations] Erro na requisição: {e}", warn=True)
    return False


def source_media(scenes: List[Dict], cfg: dict, root: Path) -> Dict[int, str]:
    """
    Função legada de busca de mídia (usada como fallback de segurança).
    O orquestrador principal utiliza preferencialmente o MediaResearchAgent.
    """
    videos_dir  = str(root / "videos")
    imagens_dir = str(root / "imagens")
    api_key     = cfg["media"]["pixabay_api_key"]

    scenes_for_module = []
    for s in scenes:
        s_copy = dict(s)
        if s.get("wikimedia_q"):
            s_copy["query"] = s["wikimedia_q"]
        elif s.get("needs_ai") and not s.get("query"):
            s_copy["query"] = "vintage historical archive documentary"
        scenes_for_module.append(s_copy)

    asset_map = ensure_media_for_scenes(scenes_for_module, videos_dir, imagens_dir, api_key)

    for scene in scenes:
        sid = scene["id"]
        if sid in asset_map:
            continue

        dest = str(Path(imagens_dir) / scene["arquivo"].replace(".mp4", ".jpg"))
        prompt = scene.get("ai_prompt") or scene.get("descricao") or scene["texto"][:120]

        log(f"  [Passo 4] Cena {sid:02d} — gerando imagem com IA...")
        ok = _pollinations(prompt, dest)

        if ok:
            asset_map[sid] = dest
            for s in scenes:
                if s["id"] == sid:
                    s["tipo"]    = "image"
                    s["arquivo"] = Path(dest).name
        else:
            log(f"  [Fallback PIL] Cena {sid:02d} — gerando card procedural de segurança.", warn=True)
            _pil_fallback(scene.get("descricao", f"Cena {sid}"), dest)
            asset_map[sid] = dest
            for s in scenes:
                if s["id"] == sid:
                    s["tipo"]    = "image"
                    s["arquivo"] = Path(dest).name

    return asset_map


def _pil_fallback(title: str, dest: str):
    """Gera um card escuro e elegante com PIL quando todas as fontes de rede falham."""
    from PIL import Image, ImageDraw
    img  = Image.new("RGB", (1920, 1080), (15, 23, 42))
    draw = ImageDraw.Draw(img)
    draw.text((80, 500), title[:80], fill=(240, 240, 240))
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    img.save(dest, "JPEG", quality=85)


# =============================================================================
# PASSO 7 — THUMBNAIL (FALLBACK SIMPLES)
# =============================================================================

def generate_thumbnail(first_asset: str, out_path: str, title: str,
                       w: int = 1280, h: int = 720):
    """
    Gera uma thumbnail básica em 1280x720 com gradiente e título sobreposto.
    O pipeline principal utiliza o ThumbnailAgent (com 3 variações e teste de contraste).
    """
    from PIL import Image, ImageDraw
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    try:
        if first_asset.lower().endswith((".jpg", ".jpeg", ".png")):
            img = Image.open(first_asset).convert("RGB").resize((w, h), Image.LANCZOS)
        else:
            img = Image.new("RGB", (w, h), (15, 23, 42))
        draw = ImageDraw.Draw(img)

        # Desenha gradiente escuro na base da imagem para garantir legibilidade do texto
        for y in range(h // 2, h):
            alpha = int(180 * (y - h // 2) / (h // 2))
            r, g, b = img.getpixel((w // 2, y))
            draw.line([(0, y), (w, y)],
                      fill=(int(r*(1-alpha/255)), int(g*(1-alpha/255)), int(b*(1-alpha/255))))
        draw.text((30, h - 60), title[:60], fill=(255, 255, 255))
        img.save(out_path, "JPEG", quality=92)
        log(f"  [Thumbnail] Capa salva em: {Path(out_path).name}")
    except Exception as e:
        log(f"  [Thumbnail] Falha ao gerar capa simples: {e}", warn=True)


# =============================================================================
# PERSISTÊNCIA DE CHECKPOINT (RETOMADA APÓS QUEDA)
# =============================================================================

def save_checkpoint(state: dict, path: Path):
    """Salva o progresso da execução em formato JSON para permitir o uso de --resume."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_checkpoint(path: Path) -> dict:
    """Carrega o estado salvo da última execução para retomar do ponto de interrupção."""
    if path.exists() and path.stat().st_size > 2:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


# =============================================================================
# UTILITÁRIOS INTERNOS
# =============================================================================

_VERBOSE = True

def log(msg: str, warn: bool = False):
    """Exibe mensagens no console formatadas com prefixo [INFO] ou [WARN]."""
    if _VERBOSE or warn:
        prefix = "[WARN]" if warn else "[INFO]"
        print(f"{prefix} {msg}")


def get_audio_duration_simple(ffmpeg: str, audio: str) -> float:
    """Obtém a duração precisa do áudio em segundos executando o binário do FFmpeg."""
    res = subprocess.run([ffmpeg, "-i", audio],
                         stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    m = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", res.stderr)
    if m:
        h, mn, s = m.groups()
        return int(h)*3600 + int(mn)*60 + float(s)
    return 0.0


# =============================================================================
# PARSER DE LINHA DE COMANDO (ARGPARSE)
# =============================================================================

def parse_args():
    """Define todos os parâmetros e opções que o usuário pode informar no terminal."""
    p = argparse.ArgumentParser(
        prog="VideoFactoryAI",
        description="Transforma um roteiro ou tema em documentário 1080p completo."
    )
    # Entrada principal: arquivo de roteiro (opcional se fornecido --topic)
    p.add_argument("roteiro", nargs="?", default=None,
                   help="Caminho do arquivo de roteiro .txt (opcional se usar --topic)")

    # Modo Produtor Automático (pesquisa, escreve roteiro e produz vídeo)
    p.add_argument("--topic",
                   default=None,
                   metavar="TEMA",
                   help="Assunto para geração automática completa sem precisar de roteiro prévio")
    p.add_argument("--duration",
                   type=float,
                   default=5.0,
                   metavar="MIN",
                   help="Duração estimada em minutos para o documentário no modo --topic (padrão: 5)")

    # Ajustes de Narração e Voz
    p.add_argument("--voice",
                   default=None,
                   help="Voz Edge-TTS (ex: pt-BR-AntonioNeural, pt-BR-FranciscaNeural)")
    p.add_argument("--tts-engine",
                   choices=["edge-tts", "f5-tts", "openai"],
                   default=None,
                   help="Motor de narração (padrão: edge-tts)")

    # Ajustes do Modelo Whisper
    p.add_argument("--whisper-model",
                   choices=["tiny", "base", "small", "medium", "large"],
                   default=None,
                   help="Tamanho do modelo Whisper (padrão: base)")

    # Controle de Retomada e Checkpoint
    p.add_argument("--resume",
                   action="store_true",
                   help="Retoma a execução a partir do último checkpoint salvo")
    p.add_argument("--no-checkpoint",
                   action="store_true",
                   help="Desativa o salvamento de checkpoint intermediário")

    # Identidade do Canal (--channel ou --canal)
    p.add_argument("--canal", "--channel",
                   default=None,
                   dest="canal",
                   metavar="NOME",
                   help="Canal de produção (documentario, geopolitica, historia, tecnologia)")

    # Chaves de API externas opcionais para ampliar fotos e vídeos livres
    p.add_argument("--pexels-key",
                   default=None,
                   dest="pexels_key",
                   help="Chave de API do Pexels (L1/L2 mídias reais)")
    p.add_argument("--unsplash-key",
                   default=None,
                   dest="unsplash_key",
                   help="Chave de API do Unsplash (L2 fotos reais)")

    return p.parse_args()


# =============================================================================
# PIPELINE PRINCIPAL DE EXECUÇÃO (MAIN)
# =============================================================================

def main():
    """
    Função orquestradora:
    Coordena os 10 passos do pipeline em ordem sequencial e monitora falhas críticas.
    """
    global _VERBOSE
    args = parse_args()

    # -------------------------------------------------------------------------
    # DEFINIÇÃO DO ROTEIRO: Lê arquivo existente OU aciona o ScriptWriterAgent
    # -------------------------------------------------------------------------
    if getattr(args, "topic", None):
        # Modo Produtor Automático: o agente pesquisa e escreve o roteiro
        if not _WRITER_AVAILABLE:
            print("Erro crítico: ScriptWriterAgent não está disponível.", file=sys.stderr)
            sys.exit(1)
        writer = _SWA(ROOT_DIR)
        canal_chosen = getattr(args, "canal", None)
        script_text, roteiro_path = writer.generate(
            topic=args.topic,
            duration_min=args.duration,
            canal=canal_chosen
        )
    elif args.roteiro:
        # Modo Roteiro Fornecido: usuário informou o caminho de um arquivo .txt
        roteiro_path = Path(args.roteiro)
        if not roteiro_path.exists():
            print(f"Erro: arquivo de roteiro não encontrado em: {roteiro_path}", file=sys.stderr)
            sys.exit(1)
        script_text = roteiro_path.read_text(encoding="utf-8").strip()
    else:
        # Fallback padrão: procura 'roteiro.txt' na raiz
        roteiro_path = ROOT_DIR / "roteiro.txt"
        if not roteiro_path.exists():
            print(f"Erro: roteiro.txt não encontrado na raiz: {roteiro_path}", file=sys.stderr)
            print("Dica: forneça um arquivo ou use: python VideoFactoryAI/agent.py --topic \"Seu Tema\"")
            sys.exit(1)
        script_text = roteiro_path.read_text(encoding="utf-8").strip()

    if not script_text:
        print("Erro: o texto do roteiro está vazio.", file=sys.stderr)
        sys.exit(1)

    # -------------------------------------------------------------------------
    # CARREGAMENTO DE CONFIGURAÇÕES E PERFIS
    # -------------------------------------------------------------------------
    cfg = get_config(
        AGENT_DIR / "config.yaml",
        {"voice": args.voice, "whisper_model": args.whisper_model, "tts_engine": args.tts_engine}
    )
    _VERBOSE = cfg["agent"]["verbose"]

    # Recupera preferências salvas de voz da memória persistente
    if _VOICE_MEM_AVAILABLE:
        try:
            vmem = _VMEM(AGENT_DIR / "memory")
            cfg = vmem.apply_to_cfg(cfg, cli_voice=args.voice, cli_engine=args.tts_engine)
            log(f"  [VoiceMemory] Preferências recuperadas: {vmem.log_summary()}")
        except Exception as e:
            log(f"  [VoiceMemory] Falha ao recuperar preferências: {e}", warn=True)

    # Carrega estilo do canal selecionado (--channel)
    if getattr(args, "canal", None):
        canal_name = args.canal.lower().strip()
        candidates = [
            AGENT_DIR / "channels" / f"{canal_name}.yaml",
            AGENT_DIR / "channels" / f"{canal_name}s.yaml",
            AGENT_DIR / "channels" / f"{canal_name.rstrip('s')}.yaml",
        ]
        canal_yaml = next((p for p in candidates if p.exists()), None)
        if canal_yaml:
            try:
                canal_cfg = load_config(canal_yaml)
                for section, vals in canal_cfg.items():
                    if isinstance(vals, dict):
                        cfg.setdefault(section, {}).update(vals)
                    else:
                        cfg[section] = vals
                log(f"  Canal carregado com sucesso: {canal_yaml.stem}")
            except Exception as e:
                log(f"  [WARN] Falha ao mesclar canal '{canal_name}': {e}", warn=True)
        else:
            log(f"  [WARN] Canal '{canal_name}' não encontrado. Usando configuração padrão.", warn=True)

    # Aplica chaves de API externas se informadas na linha de comando
    if getattr(args, "pexels_key", None):
        cfg.setdefault("media", {})["pexels_api_key"] = args.pexels_key
    if getattr(args, "unsplash_key", None):
        cfg.setdefault("media", {})["unsplash_api_key"] = args.unsplash_key

    # -------------------------------------------------------------------------
    # DEFINIÇÃO DE CAMINHOS DE TRABALHO
    # -------------------------------------------------------------------------
    ffmpeg_path   = str(ROOT_DIR / "ffmpeg.exe") if (ROOT_DIR / "ffmpeg.exe").exists() else (shutil.which("ffmpeg") or "ffmpeg")
    audio_path    = str(ROOT_DIR / "narracao.mp3")
    srt_path      = str(ROOT_DIR / "narracao.srt")
    manifest_path = str(ROOT_DIR / "concat_list.txt")
    saida_dir     = ROOT_DIR / "saida"
    temp_clips    = str(ROOT_DIR / "temp_clips")
    checkpoint    = AGENT_DIR / "memory" / "last_run.json"
    plan_path     = ROOT_DIR / "ckpts" / "scenes_planned.json"

    # Cria pastas essenciais no disco caso não existam
    for d in [saida_dir, ROOT_DIR / "ckpts", ROOT_DIR / "temp_clips", ROOT_DIR / "videos", ROOT_DIR / "imagens"]:
        d.mkdir(parents=True, exist_ok=True)

    out_video = str(saida_dir / cfg["output"]["video_filename"])
    out_thumb = str(saida_dir / cfg["output"]["thumbnail_filename"])

    # -------------------------------------------------------------------------
    # TRATAMENTO DE RETOMADA OU LIMPEZA DE PRODUÇÃO NOVA
    # -------------------------------------------------------------------------
    state = {}
    if args.resume and not args.no_checkpoint:
        state = load_checkpoint(checkpoint)
        if state:
            log("Retomando execução a partir do checkpoint salvo...")
    else:
        # Se for uma nova execução (sem --resume), limpa os temporários da produção
        # anterior para garantir que áudio, legendas e clipes sejam exclusivos deste tema
        for f in [Path(audio_path), Path(srt_path), Path(manifest_path)]:
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
        if Path(temp_clips).exists():
            shutil.rmtree(temp_clips, ignore_errors=True)
        Path(temp_clips).mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print("\n" + "=" * 62)
    print("  VideoFactoryAI — Pipeline Automático de Produção de Vídeos")
    print("=" * 62)
    print(f"  Roteiro : {roteiro_path.name} ({len(script_text.split())} palavras)")
    print(f"  Saída   : {out_video}")
    print("=" * 62 + "\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 1/10 — Planejamento de Cenas (Storyboard Semântico)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[1/10] Planejamento de cenas...")
    if state.get("scenes"):
        scenes = state["scenes"]
        log(f"  Cenas carregadas do checkpoint: {len(scenes)} cenas")
    else:
        scenes = plan_scenes(script_text, cfg)
        log(f"  {len(scenes)} cenas planejadas "
            f"({sum(1 for s in scenes if s['tipo']=='video')} vídeo | "
            f"{sum(1 for s in scenes if s['tipo']=='image')} imagem)")
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
        if not args.no_checkpoint:
            state["scenes"] = scenes
            save_checkpoint(state, checkpoint)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 2/10 — Geração de Voz Neural (TTS)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[2/10] Geração de voz (TTS)...")
    audio_path = generate_voice(script_text, audio_path, cfg)
    audio_dur  = get_audio_duration_simple(ffmpeg_path, audio_path)
    log(f"  Duração da narração: {audio_dur:.1f}s ({audio_dur/60:.2f} min)")

    # Memoriza a voz utilizada para as próximas execuções
    if _VOICE_MEM_AVAILABLE:
        try:
            vmem = _VMEM(AGENT_DIR / "memory")
            vmem.save(
                voice=cfg["tts"]["voice"],
                rate=cfg["tts"].get("rate", "+0%"),
                pitch=cfg["tts"].get("pitch", "+0Hz"),
                engine=cfg["tts"].get("engine", "edge-tts")
            )
            log("  [VoiceMemory] Configurações de voz salvas na memória.")
        except Exception as e:
            log(f"  [VoiceMemory] Falha ao persistir preferências: {e}", warn=True)

    if not args.no_checkpoint:
        state["audio_path"] = audio_path
        state["audio_dur"]  = audio_dur
        save_checkpoint(state, checkpoint)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 3/10 — Transcrição e Geração de Legendas (Whisper)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[3/10] Geração de legendas (Whisper)...")
    srt_blocks = generate_subtitles(audio_path, srt_path, cfg)
    scenes     = resync_scenes(scenes, srt_blocks, audio_dur)
    log(f"  Timecodes ressincronizados com precisão para {len(scenes)} cenas.")
    if not args.no_checkpoint:
        state["scenes"]     = scenes
        state["srt_path"]   = srt_path
        state["srt_blocks"] = srt_blocks
        save_checkpoint(state, checkpoint)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 4/10 — Busca de Mídia com Compliance (L1 a L4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[4/10] Busca de mídia (Hierarquia L1 vídeo -> L2 imagem -> L3 IA pública -> L4 IA gerada)...")
    compliance = None
    if _MRA_AVAILABLE:
        try:
            mra = _MRA(cfg, ROOT_DIR, AGENT_DIR / "memory")
            asset_map = mra.source_all(scenes)
            compliance = mra.compliance_summary()
            log(f"  {compliance['compliant']}/{compliance['total_assets']} mídias verificadas contra direitos autorais.")
            log(f"  Distribuição por nível: {compliance.get('by_level', {})}")
        except Exception as e:
            log(f"  [WARN] MediaResearchAgent encontrou exceção ({e}). Usando fallback legado.", warn=True)
            asset_map = source_media(scenes, cfg, ROOT_DIR)
    else:
        log("  [INFO] MediaResearchAgent não carregado. Usando fallback de mídia.")
        asset_map = source_media(scenes, cfg, ROOT_DIR)

    log(f"  {len(asset_map)}/{len(scenes)} mídias preparadas para edição.")
    if not args.no_checkpoint:
        state["asset_map"] = {str(k): v for k, v in asset_map.items()}
        save_checkpoint(state, checkpoint)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 5/10 — Processamento Visual (Ken Burns + Normalização 1080p)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[5/10] Processamento visual (Ken Burns em fotos + padronização 1080p)...")
    clips = process_all_scenes(scenes, asset_map, temp_clips, ffmpeg_path)
    log(f"  {len(clips)} clipes processados na pasta temp_clips/")
    if not args.no_checkpoint:
        state["clips"] = clips
        save_checkpoint(state, checkpoint)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 6/10 — Renderização Final (FFmpeg Assembly)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[6/10] Renderização final do master (Concatenação + áudio + legendas queimadas)...")
    ok = assemble_master_documentary(clips, audio_path, srt_path, out_video, ffmpeg_path, manifest_path)
    if not ok:
        print("Erro crítico: a renderização pelo FFmpeg falhou.", file=sys.stderr)
        sys.exit(1)

    size_mb = os.path.getsize(out_video) / (1024 * 1024)
    log(f"  Vídeo master gerado: {Path(out_video).name} ({size_mb:.1f} MB)")
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 7/10 — Geração de Capas com Seleção por Contraste (ThumbnailAgent)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[7/10] Geração de capas (ThumbnailAgent: 3 versões + eleição por contraste visual)...")
    title_text   = roteiro_path.stem.replace("_", " ").title()
    canal_active = getattr(args, "canal", None)
    if _THUMB_AGENT_AVAILABLE:
        try:
            thumb_agent = _THUMBA(
                ffmpeg_path, saida_dir,
                cfg["output"]["thumbnail_width"], cfg["output"]["thumbnail_height"]
            )
            out_thumb = thumb_agent.run(
                video_path=out_video, asset_map=asset_map,
                scenes=scenes, title=title_text, canal=canal_active
            )
        except Exception as e:
            log(f"  [WARN] ThumbnailAgent falhou ({e}). Usando gerador de capa simples.", warn=True)
            first_asset = asset_map.get(scenes[0]["id"], "") if scenes else ""
            generate_thumbnail(first_asset, out_thumb, title_text,
                               cfg["output"]["thumbnail_width"], cfg["output"]["thumbnail_height"])
    else:
        first_asset = asset_map.get(scenes[0]["id"], "") if scenes else ""
        generate_thumbnail(first_asset, out_thumb, title_text,
                           cfg["output"]["thumbnail_width"], cfg["output"]["thumbnail_height"])
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 8/10 — Controle de Qualidade Automatizado (QualityAgent)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[8/10] Controle de qualidade final (QualityAgent)...")
    if _QUALITY_AVAILABLE:
        try:
            qa = _QA(ffmpeg_path, saida_dir)
            passed = qa.run(
                video_path=out_video,
                audio_path=audio_path,
                srt_path=srt_path,
                asset_map=asset_map,
                scenes=scenes,
                expected_duration_s=audio_dur,
            )
            # Se forem detectados erros críticos (ex: áudio mudo ou arquivo corrompido), bloqueia
            if not passed:
                print("\n" + "!" * 62, file=sys.stderr)
                print("  ERRO CRÍTICO: QualityAgent reprovou o vídeo final!", file=sys.stderr)
                print(f"  Consulte o relatório em: {saida_dir / 'quality_report.json'}", file=sys.stderr)
                print("!" * 62 + "\n", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            log(f"  [WARN] QualityAgent encontrou exceção na verificação: {e}", warn=True)
    else:
        log("  [INFO] QualityAgent não disponível. Pulando verificação.")
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 9/10 — Otimização para YouTube e Metadados (SeoAgent)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[9/10] Geração de metadados YouTube (SeoAgent: título, descrição, tags e capítulos)...")
    if _SEO_AVAILABLE:
        try:
            seo = _SEO(saida_dir)
            seo.run(
                script_text=script_text,
                scenes=scenes,
                audio_duration_s=audio_dur,
                roteiro_name=roteiro_path.stem,
                canal=canal_active
            )
        except Exception as e:
            log(f"  [WARN] SeoAgent encontrou exceção: {e}", warn=True)
    else:
        log("  [INFO] SeoAgent não disponível.")
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 10/10 — Registro de Analytics e Histórico de Produção
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[10/10] Registro de analytics (Analytics: salvando em project_history.json)...")
    elapsed = time.time() - t0
    if _ANALYTICS_AVAILABLE:
        try:
            analytics = _ANALYTICS(AGENT_DIR / "memory")
            analytics.record(
                roteiro_name=roteiro_path.stem,
                scenes=scenes,
                asset_map=asset_map,
                audio_duration_s=audio_dur,
                elapsed_s=elapsed,
                canal=canal_active,
                compliance=compliance,
                output_video=out_video
            )
        except Exception as e:
            log(f"  [WARN] Analytics encontrou exceção: {e}", warn=True)
    else:
        log("  [INFO] Analytics não disponível.")
    print("  [OK]\n")

    # -------------------------------------------------------------------------
    # RESUMO FINAL E EXIBIÇÃO DE ARTEFATOS
    # -------------------------------------------------------------------------
    m, s = divmod(int(elapsed), 60)
    if not args.no_checkpoint:
        state["output_video"] = out_video
        state["thumbnail"]    = out_thumb
        save_checkpoint(state, checkpoint)

    print("=" * 62)
    print("  PIPELINE CONCLUÍDO COM SUCESSO!")
    print("=" * 62)
    print(f"  Tempo total    : {m}m {s}s")
    print(f"  Vídeo final    : {out_video}")
    print(f"  Thumbnail      : {out_thumb}")
    print(f"  Qualidade      : {saida_dir / 'quality_report.json'}")
    print(f"  SEO / YouTube  : {saida_dir / 'youtube_metadata.json'}")
    print(f"  Histórico      : {AGENT_DIR / 'memory' / 'project_history.json'}")
    print(f"  Total de Cenas : {len(scenes)}")
    print(f"  Duração Real   : {audio_dur:.1f}s ({audio_dur/60:.2f} min)")
    print("=" * 62 + "\n")


# Ponto de entrada padrão da linguagem Python
if __name__ == "__main__":
    main()
