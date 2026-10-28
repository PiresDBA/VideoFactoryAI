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
import hashlib
import shutil         # Operações de cópia e limpeza de diretórios
import argparse       # Parser profissional de opções de linha de comando
import asyncio        # Suporte a rotinas assíncronas (usado pelo Edge-TTS)
import re             # Expressões regulares para limpeza de texto e timecodes
import subprocess     # Execução do FFmpeg em segundo plano
import urllib.parse   # Codificação de URLs para requisições web
import requests       # Requisições HTTP para APIs de mídia e pesquisa
from pathlib import Path  # Manipulação moderna e segura de caminhos de arquivos
from typing import List, Dict, Any, Optional, Tuple  # Tipagem estática defensiva
from pipeline_resume import (
    DEFAULT_IMAGE_MIN_BYTES,
    DEFAULT_VIDEO_MIN_BYTES,
    build_resume_report,
    narration_cache_matches,
    save_narration_hash,
)

# =============================================================================
# CARREGAMENTO SEGURO DOS AGENTES ESPECIALIZADOS (LAZY IMPORT)
# =============================================================================
# Usamos blocos try/except para importar cada agente. Se alguma biblioteca opcional
# não estiver instalada, o sistema não falha na inicialização do script ou no --help.

#agente usando ollama para criar busca de iamgem com texto sugestivo / adequado
QWEN_CACHE_FILE = Path("qwen_visual_queries.json")


def _load_qwen_cache():
    if QWEN_CACHE_FILE.exists():
        try:
            return json.loads(QWEN_CACHE_FILE.read_text(encoding="utf-8"))
        except:
            return {}
    return {}


def _save_qwen_cache(cache):
    try:
        QWEN_CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass


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

# Image Validator Agent — valida script ↔ imagem + timing, regenera se não bater
_IMAGE_VALIDATOR_AVAILABLE = False
try:
    from image_validator_agent import ImageValidatorAgent, validate_scene_assets as _validate_assets
    _IMAGE_VALIDATOR_AVAILABLE = True
except ImportError:
    _IMAGE_VALIDATOR_AVAILABLE = False
    _validate_assets = None  # type: ignore

# Thumbnail Generator — usa Gemini Nano Banana 2 para thumbnails YouTube
_THUMB_GEN_AVAILABLE = False
try:
    from thumbnail_generator import generate_thumbnail as _gen_thumb
    _THUMB_GEN_AVAILABLE = True
except ImportError:
    _THUMB_GEN_AVAILABLE = False
    _gen_thumb = None  # type: ignore

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
AGENT_DIR = Path(__file__).resolve().parent
ROOT_DIR  = AGENT_DIR.parent
sys.path.insert(0, str(ROOT_DIR))

# Evita que caracteres como ✓/✗ derrubem a busca de mídia em consoles Windows
# com páginas de código antigas. Mantém a codificação atual, substituindo
# apenas caracteres que o console não consegue representar.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

# O FFmpeg pode estar na raiz do workspace (irmão da pasta VideoFactoryAI) ou
# dentro da própria pasta do projeto. Procura ambos antes de consultar o PATH.
_ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
_ffmpeg_candidates = [
    ROOT_DIR / "ffmpeg" / "bin" / _ffmpeg_name,
    AGENT_DIR / "ffmpeg" / "bin" / _ffmpeg_name,
]
_ffmpeg_found = next((candidate for candidate in _ffmpeg_candidates if candidate.is_file()), None)
if _ffmpeg_found is None:
    _ffmpeg_from_path = shutil.which("ffmpeg")
    if _ffmpeg_from_path:
        _ffmpeg_found = Path(_ffmpeg_from_path).resolve()
if _ffmpeg_found is None:
    searched = "\n".join(f"  - {candidate}" for candidate in _ffmpeg_candidates)
    raise FileNotFoundError(
        "FFmpeg não encontrado. Caminhos verificados:\n" + searched +
        "\nInstale ffmpeg/bin/ffmpeg.exe na raiz do workspace ou adicione FFmpeg ao PATH."
    )
ffmpeg_path = str(_ffmpeg_found)

def generate_visual_query_with_qwen(scene_text: str) -> str:
    """
    Converte uma cena em uma query visual curta.
    Usa Qwen 2.5 3B local via Ollama.
    """

    if not scene_text:
        return ""

    cache = _load_qwen_cache()

    cache_key = hashlib.md5(
        scene_text.strip().encode("utf-8")
    ).hexdigest()

    if cache_key in cache:
        return cache[cache_key]

    prompt = f"""
You are an expert documentary visual researcher.

Convert the narration into a SHORT image search query.

RULES:
- English
- Maximum 8 words
- Focus on visual subject
- Historical figures should be prioritized
- Historical inventions should be prioritized
- No explanation
- No quotes
- Return only the query

Narration:

{scene_text}
"""

    try:

        result = subprocess.run(
            [
                "ollama",
                "run",
                "qwen2.5-coder:3b"
            ],
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=60
        )
        output = result.stdout.decode(
            "utf-8",
            errors="replace"
        ).strip()
        query = result.stdout.strip()
        query = query.split("\n")[0]

        query = query.replace(",", " ")

        query = " ".join(query.split())

        words = query.split()

        query = " ".join(words[:6])
        query = query.replace('"', "")
        query = query.replace("'", "")
        query = query.replace("\n", " ")

        if query:

            cache[cache_key] = query

            _save_qwen_cache(cache)

            print(
                f"[QWEN QUERY] {query}",
                flush=True
            )

            return query

    except Exception as e:

        print(
            f"[QWEN ERRO] {e}",
            flush=True
        )

    return ""
def extract_historical_person(scene_text: str):

    import re

    names = re.findall(
        r'\b([A-ZÁÀÂÃÉÈÊÍÓÔÕÚÇ][a-záàâãéèêíóôõúç]+(?:\s+[A-ZÁÀÂÃÉÈÊÍÓÔÕÚÇ][a-záàâãéèêíóôõúç]+)+)\b',
        scene_text
    )

    if names:
        return names[0]

    return None
# Importa módulos de áudio e vídeo existentes na codebase (sem qualquer modificação neles)
def _carregar_vf_env() -> None:
    """Lê VideoFactoryAI/vf.env (uma linha CHAVE=valor). Não sobrescreve variáveis já definidas.
    Assim a configuração vale também quando o pipeline é aberto pela interface gráfica."""
    arq = Path(__file__).resolve().parent / "vf.env"
    if not arq.is_file():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        if chave and chave not in os.environ:
            os.environ[chave] = valor


_carregar_vf_env()

from modules.media_engine     import ensure_media_for_scenes
from modules.visual_processor import process_all_scenes
from modules.composer         import assemble_master_documentary

# =============================================================================
# CONSTANTES YOUTUBE — Slogan de abertura e frase de encerramento padrão
# =============================================================================
YOUTUBE_OPENING_SLOGAN = "Você sabia que o Sabiá sabia assobiar?"
YOUTUBE_CLOSING_PHRASE = (
    "Se você gostou do vídeo, se inscreva no canal e deixe seu like. "
    "Fazendo isso, você vai contribuir para o nosso canal e a gente vai saber "
    "que pessoas como você gostam do nosso conteúdo e isso vai incentivar a "
    "gente continuar gerando esse tipo de conteúdo. Muito obrigado e até o próximo vídeo."
)

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
            "pixabay_api_key": "",
            "ai_image_provider": "pollinations",
            "media_source_mode": "local_only",
            "min_local_images": 0,
            "gemini_only": False,
            "prefer_real_media": True,
            "web_research_before_generation": True,
            "revalidate_images": False,
            "force_regeneration": False,
            "reuse_approved_images": True,
            "gemini_fallback": True,
            "ignore_cache": False,
            "skip_ollama": False,  # Default: Ollama habilitado
        },
        "pipeline": {
            "resume_mode": True,
            "reuse_existing_audio": True,
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
# PASSO 1 — PLANEJAMENTO E CLASSIFICAÇÃO SEMÂNTICA MULTITEMÁTICA DE CENAS
# =============================================================================
# Dicionário de termos visuais ricos que cobrem cultura, expressões populares,
# vida cotidiana, natureza, psicologia, tecnologia, ciência e história.
# NUNCA recorre a termos militares ou de geopolítica para temas culturais ou cotidianos.

def slugify(text: str) -> str:
    """Converte um título ou tema em um identificador seguro para pastas e arquivos."""
    import unicodedata
    clean = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^\w\s-]", "", clean).strip().lower()
    clean = re.sub(r"[-\s]+", "_", clean)
    return clean[:45] or "documentario"


THEMATIC_VISUAL_MAP = {
    # Expressões Populares, Cotidiano, Pensamento e Psicologia
    "morte da bezerra": [
        "person looking through window thoughtful contemplation daydreaming",
        "cow calf grazing in green pasture meadow rural farm",
        "vintage pocket watch ticking antique clock time passing",
        "peaceful countryside farm landscape sunset golden hour"
    ],
    "bezerra": [
        "cow calf grazing in green pasture meadow rural farm",
        "rustic rural farmhouse barn countryside meadow",
        "cattle cows resting peacefully in countryside green grass",
        "shepherd walking in pasture rural farmland sunset"
    ],
    "bezerro": [
        "cow calf grazing in green pasture meadow rural farm",
        "rustic rural farmhouse barn countryside meadow",
        "cattle cows resting peacefully in countryside green grass",
        "peaceful green pasture meadow landscape sunrise"
    ],
    "pensando": [
        "person thoughtful contemplation daydreaming looking away",
        "thoughtful person staring into distance reflection portrait",
        "person sitting quietly by lake sunset reflection thought",
        "close up thoughtful human eyes looking away reflection"
    ],
    "pensativo": [
        "thoughtful person staring into distance reflection portrait",
        "person looking through window thoughtful contemplation daydreaming",
        "person sitting alone peaceful nature landscape sunset",
        "silhouetted person in thought looking at morning sky"
    ],
    "olhar": [
        "close up thoughtful human eyes looking away reflection",
        "person staring into distance quiet contemplation",
        "eyes looking thoughtfully through window morning light"
    ],
    "olhando": [
        "person looking out window daydreaming quiet peaceful",
        "contemplative person sitting alone looking at horizon",
        "person sitting on porch looking out at green field"
    ],
    "devaneio": [
        "daydreaming person sitting alone peaceful sunlight",
        "person looking at sky dreaming thoughtful calm",
        "person leaning against tree daydreaming nature"
    ],
    "reflexão": [
        "person sitting quietly by lake sunset reflection thought",
        "solitary figure walking along path peaceful landscape",
        "person sitting near window warm evening sunlight"
    ],
    "silêncio": [
        "peaceful empty nature landscape calm atmosphere",
        "quiet misty morning forest sunlight peaceful",
        "calm water lake reflection mountains serene"
    ],
    "tempo": [
        "vintage pocket watch ticking antique clock time passing",
        "antique clock gears ticking vintage time passing",
        "hourglass sand falling slow motion vintage",
        "vintage clock hands moving time lapse"
    ],
    "relógio": [
        "antique clock gears ticking vintage time passing",
        "vintage pocket watch ticking time passing nostalgia",
        "grandfather clock pendulum swinging vintage"
    ],
    "espera": [
        "person waiting quietly vintage railway station platform",
        "empty wooden bench in autumn park peaceful waiting",
        "person sitting on porch waiting peaceful afternoon"
    ],
    "solidão": [
        "solitary figure walking along path peaceful landscape",
        "single tree in vast green meadow peaceful calm",
        "contemplative person sitting alone mountain overlook"
    ],
    "ócio": [
        "relaxing in hammock countryside peaceful sunny afternoon",
        "person resting under shade of oak tree peaceful",
        "quiet afternoon tea by sunny window peaceful"
    ],
    "alma": [
        "cinematic sunrise golden light peaceful horizon",
        "dramatic sunbeams breaking through morning mist",
        "calm serene ocean horizon sunset peaceful"
    ],
    "mente": [
        "human silhouette with light creative thought concept",
        "glowing light bulb creative idea inspiration",
        "intricate mechanical clockwork creative thinking"
    ],
    # Campo, Vida Rural e Natureza
    "campo": [
        "rural countryside green farmland rolling hills sunrise",
        "golden wheat field waving in gentle summer breeze",
        "peaceful dirt road winding through green countryside"
    ],
    "pastor": [
        "shepherd with herd in green mountain pasture vintage",
        "rustic shepherd walking in peaceful rural pasture",
        "traditional rural livestock farming countryside"
    ],
    "pasto": [
        "green grass pasture cows grazing countryside sunny day",
        "peaceful morning mist rising from green meadow",
        "fenced green countryside pasture rolling hills"
    ],
    "rebanho": [
        "herd of cattle grazing peacefully in open pasture",
        "rustic herd grazing countryside meadow sunset",
        "traditional countryside farm animal livestock"
    ],
    "gado": [
        "cattle cows grazing in green field meadow countryside",
        "rural herd grazing peacefully under blue sky",
        "countryside cows resting in green meadow"
    ],
    "vaca": [
        "cow close up in rural green field farm peaceful",
        "gentle cow grazing in green meadow sunshine",
        "dairy cow in rustic farm pasture calm"
    ],
    "fazenda": [
        "old rural farmhouse countryside golden hour peaceful",
        "rustic red barn green farmland countryside sunny",
        "traditional farm gate opening to green rolling hills"
    ],
    "rural": [
        "rustic countryside farm landscape sunny morning",
        "rural agricultural landscape green hills morning",
        "countryside dirt road fences trees landscape"
    ],
    "natureza": [
        "pristine forest trees sunlight streaming through green",
        "scenic nature river flowing through lush forest",
        "peaceful green forest canopy sunlight gentle"
    ],
    # Tradição, Livros, Linguagem e Folclore
    "origem": [
        "antique historical map compass vintage exploration archive",
        "old vintage manuscript turning pages library",
        "historical documents parchment quill ink vintage"
    ],
    "expressão": [
        "old vintage book open pages handwriting calligraphy",
        "vintage typewriter typing letters paper close up",
        "ancient parchment scroll vintage library archive"
    ],
    "palavra": [
        "vintage typewriter typing letters paper close up",
        "calligraphy pen writing on antique parchment paper",
        "letters printed in old book pages close up"
    ],
    "livro": [
        "stack of vintage leather books old library shelf",
        "hands gently turning pages of antique leather book",
        "open book on rustic wooden table reading sunlight"
    ],
    "história": [
        "historical archive museum old documents vintage photos",
        "sepia tone vintage historical photographs collection",
        "ancient library bookshelves archive research"
    ],
    "tradição": [
        "traditional cultural village historic cobblestone street",
        "rural community tradition heritage celebration",
        "antique craft artisan hands working tradition"
    ],
    "folclore": [
        "traditional cultural celebration festive vintage history",
        "mythical storytelling by warm campfire evening",
        "storybook open magical fantasy illustration"
    ],
    # Dimensões Religiosas, Míticas e Bíblicas
    "bezerro de ouro": [
        "golden statue ancient desert sunlight biblical history",
        "ancient golden idol sculpture gleaming desert sun",
        "ancient desert mountain dramatic clouds biblical"
    ],
    "ouro": [
        "golden relic ancient artifacts gleaming warm light",
        "warm golden hour light shining on ancient relics",
        "intricate gold craftsmanship gleaming vintage"
    ],
    "bíblia": [
        "antique open bible vintage parchment warm candle light",
        "close up pages of ancient scripture warm illumination",
        "historic sacred book leather binding ancient"
    ],
    # Cidade, Sociedade e Modernidade
    "cidade": [
        "busy city street people walking daily life urban",
        "city skyline modern architecture sunny afternoon",
        "urban pedestrian street bustling daily life"
    ],
    "pressa": [
        "time lapse city commuters walking fast motion urban",
        "busy train station crowd moving fast motion",
        "modern city traffic fast lights evening"
    ],
    "cotidiano": [
        "morning coffee cup window sunlight daily routine",
        "person preparing coffee morning routine sunlight",
        "quiet morning breakfast sunny kitchen table"
    ],
    # Ciência, Tecnologia e Inovação
    "inteligência artificial": [
        "futuristic neural network data flow digital technology",
        "abstract artificial intelligence glowing data nodes",
        "digital technology brain interface glowing network"
    ],
    "computador": [
        "vintage computer mainframe 1960s laboratory vintage",
        "retro computer green monitor typing 1980s",
        "modern high tech computer workstation multiple screens"
    ],
    "dados": [
        "binary digital data stream blue glowing screen",
        "data center server racks flashing blue led lights",
        "digital technology network connection lines"
    ],
    # Chamadas do YouTube
    "inscreva": "youtube subscribe bell button notification animation",
    "inscrição": "youtube subscribe bell button notification animation",
    "like": "thumbs up like button social media icon",
    # ========== SEGUNDA GUERRA MUNDIAL / HISTÓRIA MILITAR ==========
    "segunda guerra mundial": [
        "world war 2 archival footage soldiers battlefield black white",
        "ww2 historical documentary footage vintage war archive",
        "1939 1945 world war two historical footage black and white",
        "second world war historical footage soldiers combat",
    ],
    "guerra mundial": [
        "world war archival footage soldiers trenches historical",
        "great war historical footage vintage military archive",
        "world war one two historical documentary footage",
    ],
    "guerra": [
        "war archival footage soldiers battlefield historical documentary",
        "vintage military footage soldiers marching historical",
        "war documentary historical archive footage black white",
    ],
    "batalha": [
        "battle historical footage soldiers combat vintage archive",
        "world war 2 battle footage soldiers tanks artillery",
        "historical battle scene soldiers fighting archival",
    ],
    "soldados": [
        "soldiers world war 2 marching historical footage",
        "troops marching vintage military archive documentary",
        "soldiers combat historical footage black white",
    ],
    "soldado": [
        "soldier world war 2 portrait historical uniform",
        "soldier trench warfare vintage black white photo",
        "young soldier historical portrait world war",
    ],
    "tanques": [
        "world war 2 tanks battlefield historical footage",
        "german panzer tiger tank ww2 historical archive",
        "sherman tank allied forces world war 2",
    ],
    "tanque": [
        "tank world war 2 battlefield historical footage",
        "armored tank vintage military documentary",
    ],
    "aviões": [
        "world war 2 aircraft planes flying historical footage",
        "spitfire messerschmitt dogfight vintage archive",
        "bomber planes formation world war 2 sky",
    ],
    "avião": [
        "aircraft world war 2 vintage plane historical",
        "fighter plane spitfire messerschmitt ww2",
    ],
    "hitler": [
        "adolf hitler historical footage speeches vintage archive",
        "hitler nazi germany historical documentary black white",
    ],
    "churchill": [
        "winston churchill historical speeches vintage footage",
        "churchill world war 2 leader historical archive",
    ],
    "stalingrado": [
        "battle of stalingrad historical footage ruins winter",
        "stalingrad 1942 1943 world war 2 eastern front",
    ],
    "normandia": [
        "d-day normandy landings june 1944 historical footage",
        "normandy beaches allied invasion world war 2",
    ],
    "dia d": [
        "d-day june 6 1944 normandy landings historical",
        "normandy invasion allied forces world war 2",
    ],
    "pearl harbor": [
        "pearl harbor attack december 1941 historical footage",
        "japanese attack pearl harbor vintage archive",
    ],
    "hiroshima": [
        "hiroshima atomic bomb august 1945 historical footage",
        "atomic bomb mushroom cloud historical archive",
    ],
    "nagasaki": [
        "nagasaki atomic bomb historical footage aftermath",
        "atomic bomb destruction japan 1945 historical",
    ],
    "holocausto": [
        "holocaust concentration camps historical footage archive",
        "world war 2 holocaust memorial historical documentary",
    ],
    "berlim": [
        "fall of berlin 1945 historical footage ruins",
        "berlin 1945 soviet flag reichstag historical",
    ],
    "frança": [
        "france 1940 german invasion historical footage",
        "paris occupation world war 2 historical archive",
    ],
    "polônia": [
        "poland 1939 invasion german tanks historical footage",
        "warsaw uprising 1944 historical archive",
    ],
    "união soviética": [
        "soviet soldiers world war 2 eastern front historical",
        "red army berlin 1945 victory historical footage",
    ],
    "eixo": [
        "axis powers germany italy japan world war 2",
        "nazi germany historical footage propaganda archive",
    ],
    "aliados": [
        "allied forces world war 2 historical footage",
        "american british soviet allied forces ww2",
    ],
    "1939": [
        "1939 world war 2 begins historical footage",
        "german invasion poland 1939 vintage archive",
    ],
    "1945": [
        "1945 end of world war 2 victory historical",
        "v-e day v-j day celebration historical footage",
    ],
    "tratado de versalhes": [
        "treaty of versailles 1919 historical document signing",
        "versailles palace hall of mirrors 1919 historical",
    ],
    "versalhes": [
        "treaty of versailles 1919 historical document",
        "palace of versailles hall of mirrors vintage",
    ],
    "nazismo": [
        "nazi germany propaganda historical footage archive",
        "hitler rallies nuremberg 1930s historical archive",
    ],
    "fascismo": [
        "mussolini italy fascist historical footage vintage",
        "fascist italy historical archive black white",
    ],
    "imperialismo": [
        "japanese imperial expansion 1930s historical footage",
        "japan manchuria invasion 1931 historical archive",
    ],
    "blitzkrieg": [
        "blitzkrieg german tanks lightning war historical",
        "german panzer division 1940 france historical",
    ],
    "barbarossa": [
        "operation barbarossa 1941 german invasion soviet",
        "eastern front world war 2 german advance",
    ],
    "midway": [
        "battle of midway 1942 pacific historical footage",
        "aircraft carrier battle pacific world war 2",
    ],
    "el alamein": [
        "battle of el alamein 1942 north africa historical",
        "montgomery rommel desert war historical footage",
    ],
    "kursk": [
        "battle of kursk 1943 largest tank battle historical",
        "kursk salient soviet german tanks historical",
    ],
    "dunkerque": [
        "dunkirk evacuation 1940 historical footage beaches",
        "operation dynamo dunkirk 1940 historical archive",
    ],
    "resistência": [
        "french resistance world war 2 historical footage",
        "partisans underground resistance europe ww2",
    ],
"partisans": [
        "partisans resistance fighters world war 2 europe",
        "yugoslav partisans tito historical footage",
    ],
    # ========== MODELISMO FERROVIÁRIO / FERREOMODELISMO ==========
    "modelismo": [
        "model railroad HO scale layout benchwork open grid l-girder",
        "model railroad N scale layout design planning",
        "model railroad O scale gauge track layout",
        "model railroad layout design operations prototype",
    ],
    "maquete": [
        "model railroad layout benchwork construction open grid",
        "model railroad layout scenery XPS foam carving",
        "model railroad layout design track plan operations",
        "model railroad modular layout sections benchwork",
    ],
    "ferreomodelismo": [
        "model railroad HO scale brazilian prototype layout",
        "model railroad brazilian locomotive weathering",
        "model railroad brazilian rolling stock weathering",
        "model railroad brazilian prototype scenery",
    ],
    "ferromodelismo": [
        "model railroad HO scale brazilian prototype layout",
        "model railroad brazilian locomotive weathering",
        "model railroad brazilian rolling stock weathering",
        "model railroad brazilian prototype scenery",
    ],
    "escala ho": [
        "HO scale model railroad layout track planning",
        "HO scale model railroad benchwork construction",
        "HO scale model railroad scenery detailing",
        "HO scale model railroad operations prototype",
    ],
    "escala n": [
        "N scale model railroad layout micro layout",
        "N scale model railroad track planning design",
        "N scale model railroad scenery details",
    ],
    "trilho": [
        "model railroad flex track laying code 83 soldering",
        "model railroad track laying code 83 rail joiners",
        "model railroad hand laid track spike details",
        "model railroad curved track easement superelevation",
    ],
    "dormente": [
        "model railroad tie spacing detail close up macro",
        "model railroad concrete ties wood ties detail",
        "model railroad tie plates rail fasteners detail",
    ],
    "lastro": [
        "model railroad ballasting track cork roadbed wet water",
        "model railroad ballast application wet water glue method",
        "model railroad ballast texture color detail close up",
        "model railroad ballast shoulder profile drainage",
    ],
    "xps": [
        "model railroad XPS foam scenery carving hot wire cutter",
        "model railroad XPS foam terrain sculpting hot wire",
        "model railroad extruded polystyrene foam terrain",
        "model railroad foam scenery carving shaping tools",
    ],
    "gesso": [
        "model railroad hydrocal plaster rock molds casting",
        "model railroad plaster cloth terrain shell forming",
        "model railroad hydrocal rock molds casting painting",
        "model railroad plaster scenery base coat wash",
    ],
    "weathering": [
        "model railroad weathering freight car airbrush rust",
        "model railroad locomotive weathering airbrush diesel",
        "model railroad weathering pigments drybrush chalks",
        "model railroad weathering chalks pastels drybrush",
    ],
    "static grass": [
        "model railroad static grass applicator electrostatic",
        "model railroad static grass fibers standing upright",
        "model railroad static grass meadow field application",
        "model railroad static grass wild flowers weeds",
    ],
    "aplicador eletrostático": [
        "static grass applicator electrostatic HO scale fibers",
        "static grass applicator WOODLAND SCENICS proche",
        "static grass applicator homemade DIY high voltage",
        "model railroad static grass electrostatic charging",
    ],
    "aerógrafo": [
        "model railroad airbrush weathering locomotive diesel",
        "model railroad airbrush weathering freight car rust",
        "model railroad airbrush compressor setup technique",
        "airbrush weathering model railroad freight car",
    ],
    "dcc": [
        "model railroad DCC wiring bus wire feeders soldering",
        "model railroad DCC decoder installation locomotive",
        "model railroad DCC bus wire feeder soldering track",
        "model railroad DCC decoder programming CV",
    ],
    "decoder": [
        "model railroad DCC decoder installation steam locomotive",
        "model railroad DCC decoder programming CV values",
        "model railroad sound decoder speaker installation",
        "model railroad DCC function mapping lighting",
    ],
    "trilho flexível": [
        "model railroad flex track code 83 laying curving",
        "model railroad flex track easement transition curve",
        "model railroad flex track rail joiner soldering",
        "model railroad flex track code 83 installation",
    ],
    "code 83": [
        "HO scale code 83 rail profile detail close up",
        "model railroad code 83 rail joining soldering",
        "code 83 rail profile height 0.083 inches detail",
        "model railroad code 83 flex track laying",
    ],
    "cortiça": [
        "model railroad cork roadbed track ballasting HO scale",
        "model railroad cork roadbed beveled edges track",
        "cork roadbed model railroad track sound dampening",
        "model railroad beveled cork roadbed installation",
    ],
    "isopor": [
        "model railroad XPS foam terrain carving hot wire",
        "model railroad extruded polystyrene foam scenery",
        "model railroad pink foam board terrain carving",
        "model railroad foam board terrain shaping tools",
    ],
    "terreno": [
        "model railroad terrain scenery contour elevation changes",
        "model railroad hill mountain terrain construction foam",
        "model railroad elevation changes grade ramping",
        "model railroad scenery base terrain preparation",
    ],
    "relevo": [
        "model railroad relief terrain elevation modeling foam",
        "model railroad topographic relief modeling plaster",
        "model railroad terrain elevation changes grading",
        "model railroad scenic relief details texture",
    ],
    "rocha": [
        "model railroad rock molds hydrocal casting painting",
        "model railroad rock casting hydrocal plaster molds",
        "model railroad rock formations plaster carving detail",
        "model railroad rock outcropping plaster casting",
    ],
    "drybrush": [
        "model railroad drybrush technique rock highlighting",
        "model railroad drybrush rock highlighting technique",
        "model railroad dry brush weathering rock detail",
        "dry brush technique model railroad rock highlighting",
    ],
    "wash": [
        "model railroad wash technique rock staining coloring",
        "model railroad acrylic wash rock weathering technique",
        "model railroad india ink wash rock crevices detail",
        "model railroad wash weathering technique rocks",
    ],
    "pigmento": [
        "model railroad weathering pigments pastel chalks rust",
        "model railroad weathering pigments rust dust soot",
        "model railroad weathering pigments application techniques",
        "weathering pigments model railroad freight car",
    ],
    "static grass applicator": [
        "static grass applicator electrostatic HO scale fibers",
        "static grass applicator WOODLAND SCENICS proche",
        "static grass applicator homemade DIY high voltage",
        "model railroad static grass electrostatic charging",
    ],
    "lastro": [
        "model railroad ballasting track cork roadbed wet water",
        "model railroad ballast application wet water glue method",
        "model railroad ballast texture color detail close up",
        "model railroad ballast shoulder profile drainage",
    ],
    "ballasting": [
        "model railroad ballasting track wet water glue method",
        "model railroad ballast wet water glue application",
        "model railroad ballast shoulder slope drainage detail",
        "model railroad ballast texture color prototype",
    ],
    "feeder": [
        "model railroad DCC feeder wire soldering track bus",
        "model railroad feeder wire soldering track connection",
        "model railroad track feeder wire gauge soldering",
        "model railroad track feeder installation soldering",
    ],
    "barramento": [
        "model railroad DCC bus wire wiring diagram layout",
        "model railroad DCC bus wire gauge twisted pair",
        "model railroad power bus wiring layout design",
        "model railroad DCC power district wiring",
    ],
    "drybrush": [
        "model railroad drybrush technique rock highlighting",
        "model railroad dry brush weathering rock detail",
        "dry brush technique model railroad rock highlighting",
        "model railroad drybrush rock highlight technique",
    ],
    "wash": [
        "model railroad wash technique rock staining coloring",
        "model railroad acrylic wash rock weathering technique",
        "model railroad india ink wash rock crevices detail",
        "model railroad wash weathering technique rocks",
    ],
    "pigmento": [
        "model railroad weathering pigments pastel chalks rust",
        "model railroad weathering pigments rust dust soot",
        "model railroad weathering pigments application techniques",
        "weathering pigments model railroad freight car",
    ],
    "static grass applicator": [
        "static grass applicator electrostatic HO scale fibers",
        "static grass applicator WOODLAND SCENICS proche",
        "static grass applicator homemade DIY high voltage",
        "model railroad static grass electrostatic charging",
    ],
    "weathering": [
        "model railroad weathering freight car airbrush rust",
        "model railroad locomotive weathering airbrush diesel",
        "model railroad weathering pigments drybrush chalks",
        "model railroad weathering chalks pastels drybrush",
    ],
    "aerógrafo": [
        "model railroad airbrush weathering locomotive diesel",
        "model railroad airbrush weathering freight car rust",
        "model railroad airbrush compressor setup technique",
        "airbrush weathering model railroad freight car",
    ],
    "weathering": [
        "model railroad weathering freight car airbrush rust",
        "model railroad locomotive weathering airbrush diesel",
        "model railroad weathering pigments drybrush chalks",
        "model railroad weathering chalks pastels drybrush",
    ],
    "led": [
        "model railroad LED lighting building interior warm white",
        "model railroad LED lighting layout night scene",
        "model railroad building interior LED lighting SMD",
        "model railroad structure LED lighting installation",
    ],
    "iluminação": [
        "model railroad layout lighting night photography",
        "model railroad building interior lighting LED SMD",
        "model railroad street lighting scale lamps posts",
        "model railroad layout night scene lighting design",
    ],
    "rock molds": [
        "model railroad rock molds hydrocal casting painting",
        "model railroad rock molds silicone rubber casting",
        "model railroad rock molds hydrocal plaster casting",
        "rock molds model railroad hydrocal plaster casting",
    ],
    "hydrocal": [
        "model railroad hydrocal plaster rock molds casting",
        "hydrocal plaster model railroad rock casting painting",
        "model railroad hydrocal white strength rock molds",
        "plaster hydrocal model railroad rock casting",
    ],
    "plaster": [
        "model railroad plaster cloth terrain shell forming",
        "model railroad plaster rock molds hydrocal casting",
        "model railroad plaster scenery base coat wash",
        "plaster cloth model railroad terrain scenery",
    ],
    "ballast": [
        "model railroad ballast HO scale texture color prototype",
        "model railroad ballast shoulder profile drainage detail",
        "model railroad ballast application techniques tools",
        "model railroad ballast color texture prototype match",
    ],
    "cork roadbed": [
        "model railroad cork roadbed beveled edges track",
        "cork roadbed model railroad track sound dampening",
        "model railroad cork roadbed installation adhesive",
        "beveled cork roadbed model railroad track",
    ],
    "open grid": [
        "model railroad open grid benchwork L-girder construction",
        "model railroad open grid benchwork framing joists",
        "model railroad L-girder benchwork open grid design",
        "model railroad benchwork open grid framing",
    ],
    "l-girder": [
        "model railroad L-girder benchwork construction design",
        "model railroad L-girder benchwork joists spacing",
        "model railroad benchwork L-girder construction",
        "L-girder benchwork model railroad framing",
    ],
    "benchwork": [
        "model railroad benchwork construction framing open grid",
        "model railroad benchwork L-girder joists plywood",
        "model railroad benchwork design construction plans",
        "model railroad benchwork framing techniques",
    ],
    "rock casting": [
        "model railroad rock casting hydrocal plaster molds",
        "model railroad rock casting rubber molds hydrocal",
        "model railroad rock casting detail painting techniques",
        "rock casting model railroad scenery hydrocal",
    ],
    "scenery": [
        "model railroad scenery ground cover turf grass",
        "model railroad scenery ground cover static grass",
        "model railroad scenery ground cover turf clump foliage",
        "model railroad scenery details details details",
    ],
    "ground cover": [
        "model railroad ground cover turf static grass clump",
        "model railroad ground cover turf grass weeds flowers",
        "model railroad ground cover static grass applicator",
        "model railroad scenic ground cover materials",
    ],
    "turf": [
        "model railroad turf ground cover green grass HO scale",
        "model railroad turf grass static grass blend",
        "model railroad WOODLAND SCENICS turf green grass",
        "model railroad turf application techniques glue",
    ],
    "clump foliage": [
        "model railroad clump foliage bushes trees scenic",
        "model railroad clump foliage application techniques",
        "model railroad WOODLAND SCENICS clump foliage",
        "model railroad scenic clump foliage application",
    ],
    "structure": [
        "model railroad structure kit building assembly painting",
        "model railroad structure kit assembly weathering painting",
        "model railroad structure kit craftsman kit assembly",
        "model railroad building structure kit assembly",
    ],
    "kit": [
        "model railroad structure kit craftsman assembly painting",
        "model railroad building kit assembly weathering",
        "model railroad freight car kit assembly painting",
        "model railroad locomotive kit assembly detail",
    ],
    "building": [
        "model railroad building kit assembly painting weathering",
        "model railroad building interior lighting LED SMD",
        "model railroad building scratchbuilt structure details",
        "model railroad building weathering techniques",
    ],
    "interior": [
        "model railroad building interior lighting LED SMD warm",
        "model railroad building interior detail lighting LED",
        "model railroad structure interior detail painted",
        "model railroad building interior furniture detail",
    ],
    "light leak": [
        "model railroad light leak prevention building interior",
        "model railroad building interior black paint light leak",
        "model railroad structure light bleed prevention LED",
        "model railroad building interior light blocking",
    ],
    "light bleed": [
        "model railroad light bleed prevention building interior",
        "model railroad LED building interior light leak",
        "model railroad structure interior light sealing",
    ],
    "lighting": [
        "model railroad layout lighting night scene photography",
        "model railroad building interior lighting LED warm",
        "model railroad LED lighting layout night operations",
        "model railroad structure lighting installation",
    ],
    "cab view": [
        "model railroad cab view locomotive camera perspective",
        "model railroad locomotive cab view video footage",
        "model railroad cab ride POV footage locomotive",
        "model railroad engineer cab view perspective",
    ],
    "probe camera": [
        "model railroad probe camera miniature lens footage",
        "model railroad probe camera layout tour footage",
        "model railroad miniature camera probe lens footage",
        "model railroad endoscopic camera layout tour",
    ],
    "miniature camera": [
        "model railroad miniature camera layout tour footage",
        "model railroad small camera layout perspective",
        "model railroad tiny camera track level footage",
        "model railroad micro camera layout details",
    ],
}

def _extract_visual_keywords(
    text: str,
    max_keywords: int = 8
):
    return []


def _get_topic_visual_fallback(topic: str, canal: str, scene_idx: int, used_queries: Optional[set] = None, scene_text: str = "") -> Tuple[str, str, str, str, bool]:
    """
    Gera uma query visual estritamente única e cinematográfica para cada cena do documentário.
    Garante diversidade absoluta de enquadramentos, evitando repetições de imagens ou vídeos.
    AGORA USA O TEXTO DA CENA para gerar prompts relevantes baseados no conteúdo real.
    """
    low_t = (topic or "").lower()
    canal_key = (canal or "").lower()
    used = used_queries if used_queries is not None else set()
    
    # Extrai palavras-chave visuais do texto da cena
    visual_keywords = _extract_visual_keywords(scene_text) if scene_text else []
    print(
        f"[FALLBACK DEBUG] cena={scene_idx} "
        f"keywords={visual_keywords} "
        f"texto={scene_text[:120]}",
        flush=True
    )
    # Helper: check if any visual keyword matches
    def has_visual_keyword(*keywords):
        return any(kw in visual_keywords for kw in keywords)
    
    # Helper: check topic + visual keywords
    def matches_topic_or_visual(*keywords):
        import re
        # Use word boundary matching to avoid substring issues (e.g., "ia" in "guerra")
        for kw in keywords:
            # Check topic with word boundaries
            if re.search(rf'\b{re.escape(kw)}\b', low_t):
                return True
            # Check visual keywords (exact match since they're already normalized)
            if kw in visual_keywords:
                return True
        return False
    
    # 1. Expressão "A morte da bezerra" / Temas culturais e contemplativos (24 planos distintos)
    if matches_topic_or_visual("bezerra", "bezerro", "morte da bezerra"):
        palette = [
            ("video", "portrait person looking through window thoughtful contemplation soft light"),
            ("image", "close up antique pocket watch ticking moving gears vintage time"),
            ("video", "wide panoramic drone shot green rolling hills morning mist rural"),
            ("image", "rustic wooden farm gate and stone pathway rural countryside"),
            ("video", "young calf standing peacefully green pasture morning sunlight"),
            ("image", "solitary shepherd walking stick countryside hilltop sunset"),
            ("video", "antique leather book open wooden table candle light vintage"),
            ("image", "old vintage quill pen writing calligraphy aged parchment"),
            ("video", "vast desert sand dunes dramatic golden sunlight heat haze"),
            ("image", "ancient golden artifact relic gleaming warm museum lighting"),
            ("video", "fast paced time lapse crowd commuters walking busy city street"),
            ("image", "person relaxing peacefully in hammock under shady green trees"),
            ("video", "glowing abstract neural network data connections human silhouette"),
            ("image", "steaming cup coffee rustic wooden table window morning light"),
            ("video", "solitary ancient oak tree standing wide open field twilight sky"),
            ("image", "grandfather clock pendulum swinging vintage wooden room shadows"),
            ("video", "artisan craftsman hands carving wooden sculpture workshop"),
            ("image", "majestic sunbeams breaking through misty clouds lush valley"),
            ("video", "contemplative person sitting quietly wooden dock calm lake"),
            ("image", "peaceful dirt path winding tall golden wheat field sunset"),
            ("video", "vintage typewriter mechanism striking letters textured paper"),
            ("image", "old cobblestone street historic colonial village lanterns"),
            ("video", "single autumn leaf floating gently calm river water reflection"),
            ("image", "breathtaking golden sunset peaceful mountain horizon cinematic"),
        ]
        # Procura o primeiro plano da paleta que ainda não foi utilizado neste vídeo
        for tipo_p, q_p in palette:
            if q_p not in used:
                #return tipo_p, q_p, "", f"Cinematic documentary shot: {q_p}", False
                query_real = scene_text[:300]

                return (
                    tipo_p,
                    query_real,
                    "",
                    query_real,
                    False
            )
        
        # Caso ultrapasse 24 cenas, sintetiza novos ângulos únicos
        modifiers = ["wide panoramic view", "detailed close up macro", "cinematic golden hour sunset", "aerial drone landscape perspective", "peaceful quiet morning mist"]
        mod = modifiers[(scene_idx - 1) % len(modifiers)]
        tipo_gen = "video" if (scene_idx % 2 == 1) else "image"
        q_gen = f"peaceful rural countryside {mod} cinematic scene {scene_idx}"
        #return tipo_gen, q_gen, "", f"Cinematic shot: {q_gen}", False
        query_real = scene_text [:300]

        return (
            tipo_gen,
            query_real,
            "",
            query_real,
            False
        )

    # 2. Contos, Folclore e Literatura (ex: João e o pé de feijão)
    if matches_topic_or_visual("feijão", "feijao", "conto", "lenda", "fadas", "história de"):
        palette = [
            ("video", "fairy tale magical beanstalk green nature fantasy landscape"),
            ("image", "rustic medieval village wooden cottages countryside"),
            ("video", "planting seeds in fertile dark soil hands agriculture"),
            ("image", "ancient mystical castle above clouds mountains scenery"),
            ("video", "storybook open on vintage wooden table magical illustration"),
            ("image", "hands holding magic golden beans sunlight close up"),
            ("video", "dramatic mountain clouds storm fantasy adventure"),
            ("image", "quaint cottage fireplace warm hearth medieval interior"),
            ("video", "green bean sprout growing time lapse fertile earth"),
            ("image", "giant mythical footprint in muddy ground fantasy forest"),
            ("video", "aerial flight through magical clouds fantasy kingdom"),
            ("image", "old treasure chest filled with gold coins glowing light"),
        ]
        for tipo_p, q_p in palette:
            if q_p not in used:
                return tipo_p, q_p, "", f"Cinematic fantasy documentary: {q_p}", False

    # 3. Tecnologia e Inovação
    if False:
        pass
    # 4. Segunda Guerra Mundial / História Militar (ESPECÍFICO - antes do genérico)
    if matches_topic_or_visual("segunda guerra", "guerra mundial", "ww2", "1939", "1945", "hitler", "churchill", "stalingrado", "normandia", "pearl harbor", "hiroshima", "nagasaki", "holocausto", "berlim", "blitzkrieg", "barbarossa", "midway", "el alamein", "kursk", "dunkerque", "versalhes", "nazismo", "fascismo", "eixo", "aliados", "resistência", "partisans"):
        palette = [
            ("video", "world war 2 archival footage soldiers battlefield black white"),
            ("image", "world war 2 historical documentary vintage war archive"),
            ("video", "1939 german invasion poland tanks historical footage"),
            ("image", "winston churchill historical speeches vintage footage"),
            ("video", "adolf hitler historical footage speeches vintage archive"),
            ("image", "battle of stalingrad historical footage ruins winter"),
            ("video", "d-day normandy landings june 1944 historical footage"),
            ("image", "pearl harbor attack december 1941 historical footage"),
            ("video", "hiroshima atomic bomb august 1945 historical footage"),
            ("image", "nagasaki atomic bomb historical footage aftermath"),
            ("video", "holocaust concentration camps historical footage archive"),
            ("image", "fall of berlin 1945 historical footage ruins"),
            ("video", "blitzkrieg german tanks lightning war historical"),
            ("image", "operation barbarossa 1941 german invasion soviet"),
            ("video", "battle of midway 1942 pacific historical footage"),
            ("image", "battle of el alamein 1942 north africa historical"),
            ("video", "battle of kursk 1943 largest tank battle historical"),
            ("image", "dunkirk evacuation 1940 historical footage beaches"),
            ("video", "french resistance world war 2 historical footage"),
            ("image", "treaty of versailles 1919 historical document signing"),
            ("video", "nazi germany propaganda historical footage archive"),
            ("image", "mussolini italy fascist historical footage vintage"),
            ("video", "allied forces world war 2 historical footage"),
            ("image", "soviet soldiers world war 2 eastern front historical"),
            ("video", "german panzer tiger tank ww2 historical archive"),
            ("image", "spitfire messerschmitt dogfight vintage archive"),
            ("video", "world war 2 soldiers marching historical footage"),
            ("image", "world war 2 bomber planes formation sky"),
        ]
        for tipo_p, q_p in palette:
            if q_p not in used:
                return tipo_p, q_p, "", f"Cinematic WW2 documentary: {q_p}", False

    # 5. Geopolítica e Conflitos Militares (GENÉRICO - DEPOIS do WW2 específico)
    if canal_key == "geopolitica" or matches_topic_or_visual("guerra", "militar", "diplomacia", "crise"):
        palette = [
            ("video", "diplomats meeting table international negotiations politics"),
            ("image", "vintage historical archival treaty document signing"),
            ("video", "world map rotating globe international relations"),
            ("image", "united nations flags international assembly summit"),
            ("video", "broadcast television news control room journalism"),
            ("image", "historical embassy building architecture diplomacy"),
            ("video", "press conference microphones journalists asking questions"),
            ("image", "old military compass and tactical map table vintage"),
        ]
        for tipo_p, q_p in palette:
            if q_p not in used:
                return tipo_p, q_p, "", f"Cinematic geopolitics footage: {q_p}", False

    # 9. Gera queries dinâmicas baseadas nas visual_keywords extraídas do texto da cena
    dynamic_queries = []
    context_text = f"{topic or ''} {scene_text or ''}".lower()
    model_rail_context = any(term in context_text for term in (
        "ferromodelismo", "ferreomodelismo", "modelismo ferroviário",
        "modelismo ferroviario", "model railroad", "maquete", "ho scale",
    )) or bool(re.search(r"\bho\b", context_text))
    rail_term_aliases = {
        "locomotivas": "locomotives", "locomotiva": "locomotive",
        "compensado naval": "marine plywood", "compensado": "plywood",
        "madeira": "wood", "bancada": "benchwork", "longarinas": "stringers",
        "travessas": "cross braces", "gabarito cênico vertical": "vertical clearance",
        "gabarito vertical": "vertical clearance", "rampas": "grades", "rampa": "grade",
        "curvas": "curves", "curva": "curve", "trilhos": "track", "trilho": "track",
        "viadutos": "bridges", "viaduto": "bridge", "vagões": "freight cars",
    }
    if visual_keywords:
        # Cria queries baseadas nas palavras-chave visuais extraídas
        for kw in visual_keywords[:5]:
            anchor = "HO scale model railroad " if model_rail_context else ""
            visual_term = kw
            for source_term, translated_term in rail_term_aliases.items():
                if source_term in kw.lower():
                    visual_term = kw.lower().replace(source_term, translated_term)
                    break
            dynamic_queries.append(f"{anchor}{visual_term} cinematic documentary footage")
            dynamic_queries.append(f"{anchor}{visual_term} close up macro detail")
            dynamic_queries.append(f"{anchor}{visual_term} wide shot cinematic lighting")
    
    # Adiciona variações baseadas no topic
    clean_topic = re.sub(r"[^\w\s]", "", topic).strip() or "documentary"
    search_topic = "HO scale model railroad" if model_rail_context else clean_topic
    scene_text = (scene_text or "").strip()

    if scene_text:
        dynamic_queries.insert(
            0,
            scene_text[:250]
        )
    
    scene_text = (scene_text or "").strip()


    person = extract_historical_person(scene_text)

    if person:

        query = f"{person} portrait historical"

        return (
            "image",
            query,
            "",
            query,
            False
        )

    qwen_query = generate_visual_query_with_qwen(scene_text)

    if qwen_query:

        return (
            "image",
            qwen_query,
            "",
            qwen_query,
            False
        )

    return (
        "image",
        scene_text[:120],
        "",
        scene_text[:120],
        False
    )

    for tipo_p, q_p in [("video", q) if i % 2 == 0 else ("image", q) for i, q in enumerate(dynamic_queries)]:
        if q_p not in used:
            return tipo_p, q_p, "", q_p, False

    # Fallback final genérico
    clean_topic = search_topic
    angles = ["historical museum archive artifact", "antique document library parchment", "cinematic panoramic landscape golden hour", "old vintage photograph album memory", "historical monument architecture heritage"]
    mod = angles[(scene_idx - 1) % len(angles)]
    tipo_gen = "video" if (scene_idx % 2 == 1) else "image"
    q_gen = scene_text[:250]
    return tipo_gen, q_gen, "", q_gen, False


def _classify_scene(text: str, topic: str = "", canal: str = "", scene_idx: int = 1, used_queries: Optional[set] = None) -> tuple:
    """
    Analisa o texto de uma cena e garante uma estratégia de mídia 100% ÚNICA por cena.
    Evita repetição de imagens ou vídeos idênticos em cenas consecutivas.
    """
    low = text.lower()
    used = used_queries if used_queries is not None else set()
  
    # 1. Procura no mapa semântico multitemático por uma query que ainda NÃO foi utilizada
    #matches = [kw for kw in THEMATIC_VISUAL_MAP if kw in low]
    matches = []
   
    project_context = f"{topic or ''} {text}".lower()
    model_rail_project = any(term in project_context for term in (
        "ferromodelismo", "ferreomodelismo", "modelismo ferroviário",
        "modelismo ferroviario", "model railroad", "maquete", "ho scale",
    )) or bool(re.search(r"\bho\b", project_context))

    if model_rail_project:
        # Uma menção incidental (ex.: "pensando", "floresta", "sabiá") não
        # deve trocar o assunto principal do documentário.
        matches = [kw for kw in matches if any(
            marker in str(option).lower()
            for option in (THEMATIC_VISUAL_MAP[kw] if isinstance(THEMATIC_VISUAL_MAP[kw], list)
                           else [THEMATIC_VISUAL_MAP[kw]])
            for marker in ("model railroad", "ho scale", "ferromodelismo", "railway")
        )]

    def _specificity(kw: str) -> tuple[int, int]:
        options = THEMATIC_VISUAL_MAP[kw]
        options = options if isinstance(options, list) else [options]
        is_subject_specific = any(
            marker in str(option).lower()
            for option in options
            for marker in ("model railroad", "ho scale", "ferromodelismo", "railway")
        )
        return (0 if is_subject_specific else 1, -len(kw))

    # Assuntos visuais do tema têm prioridade sobre palavras incidentais da
    # narração (ex.: "pensando" não deve vencer "ferromodelismo").
    #for kw in sorted(matches, key=_specificity):
    for kw in []:    
        candidates = THEMATIC_VISUAL_MAP[kw]
        candidates = candidates if isinstance(candidates, list) else [candidates]
        for cand in candidates:
            if cand not in used:
                is_video = (scene_idx % 2 == 1)
                tipo = "video" if is_video else "image"
                ai_prompt = f"Cinematic documentary photograph, realistic, subject: {cand}"
                used.add(cand)
                return tipo, cand, "", ai_prompt, False

    # 2. Se nenhuma variação estiver livre ou nenhuma palavra coincidir, usa o storyboard único
    tipo, q_en, wm_q, ai_prompt, needs_ai = _get_topic_visual_fallback(topic, canal, scene_idx, used, text)
    used.add(q_en)
    return tipo, q_en, wm_q, ai_prompt, needs_ai


def plan_scenes(script_text: str, cfg: dict, topic: str = "", canal: str = "") -> List[Dict[str, Any]]:
    """
    Passo 1 do Pipeline:
    Divide o texto do roteiro em cenas de aproximadamente 12 segundos cada.
    Garante que CADA CENA tenha uma imagem ou vídeo diferente, com variedade absoluta.
    """
    target_dur   = cfg["scenes"]["target_duration_s"]  # Duração alvo de cada cena (12s)
    min_dur      = cfg["scenes"]["min_duration_s"]     # Duração mínima aceitável (5s)
    words_per_s  = 2.3                                 # Velocidade média de narração em PT-BR

    # Conjunto para garantir que nenhuma query seja duplicada em todo o documentário
    used_queries: set = set()

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
            tipo, q_en, wm_q, ai_prompt, needs_ai = _classify_scene(
                combined, topic=topic, canal=canal, scene_idx=scene_id, used_queries=used_queries
            )
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
            scene_id += 1
            group, wcount = [], 0

    # Adiciona as frases restantes como última cena
    if group:
        combined = " ".join(group)
        tipo, q_en, wm_q, ai_prompt, needs_ai = _classify_scene(
            combined, topic=topic, canal=canal, scene_idx=scene_id, used_queries=used_queries
        )
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

    pipeline_cfg = cfg.get("pipeline", {})
    if (
        pipeline_cfg.get("resume_mode", False)
        and pipeline_cfg.get("reuse_existing_audio", True)
        and narration_cache_matches(
            out_path,
            text,
            tts_settings=cfg["tts"],
        )
    ):
        log("  [TTS] Roteiro inalterado; reutilizando narração existente.")
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

    # 4. Motor local: XTTS-v2 — clonagem da voz do usuário (GPU / ambiente conda)
    elif engine in ("xtts", "xtts-v2", "xtts_v2", "clone"):
        try:
            import xtts_engine
            from tts_chunks import sintetizar_em_partes
            # XTTS trunca textos acima de ~203 caracteres: divide, sintetiza cada trecho e concatena.
            out_path = sintetizar_em_partes(
                text, out_path,
                lambda trecho, alvo: xtts_engine.sintetizar(trecho, alvo, cfg, log=log),
                log=log,
            )
        except Exception as e:
            if os.getenv("VF_XTTS_SEM_FALLBACK", "0").strip() == "1":
                raise RuntimeError(f"XTTS falhou e VF_XTTS_SEM_FALLBACK=1: {e}") from e
            log(f"  [TTS] XTTS falhou ({e}) — usando fallback edge-tts.", warn=True)
            asyncio.run(_edge_tts_async(text, out_path, voice, rate, pitch))

    else:
        raise RuntimeError(
            f"Motor TTS desconhecido: '{engine}'. "
            "Use edge-tts | xtts | f5-tts | openai (config.yaml → tts.engine)."
        )

    # Validação de integridade do arquivo de áudio gerado
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        raise RuntimeError(f"Erro no TTS: arquivo de áudio inválido em {out_path}")
    save_narration_hash(out_path, text, cfg["tts"])

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


def _glossario_do_roteiro(script_text: str) -> List[str]:
    """
    Extrai nomes próprios e termos de domínio do roteiro que será narrado.

    Como o áudio é gerado a partir deste texto, esses termos com certeza estão
    na narração — usá-los como viés reduz (e muito) erros do Whisper em nomes
    como "Constantinopla", "Mehmed", "Paleólogo".
    """
    if not script_text:
        return []

    VAZIAS = {
        "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da",
        "dos", "das", "em", "no", "na", "nos", "nas", "por", "para", "com",
        "sem", "que", "se", "e", "ou", "mas", "como", "quando", "onde",
        "ele", "ela", "eles", "elas", "isso", "isto", "aquele", "esta",
        "este", "essa", "esse", "seu", "sua", "seus", "suas", "foi", "era",
        "sao", "são", "tem", "tinha", "havia", "depois", "antes", "entao",
        "então", "assim", "porem", "porém", "tambem", "também", "apenas",
        "mais", "menos", "muito", "pouco", "todo", "toda", "todos", "todas",
    }

    # Sequências de palavras capitalizadas (ex.: "Segunda Guerra Mundial")
    sequencias = re.findall(
        r"\b(?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ'-]+)(?:\s+(?:d[aeo]s?\s+)?"
        r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ÿ'-]+){0,3}", script_text
    )

    pesos: Dict[str, int] = {}
    for seq in sequencias:
        seq = re.sub(r"\s+", " ", seq).strip(" .,;:!?\"'()")
        palavras = seq.split()
        # Descarta sequências que começam com palavra vazia/coloquial
        if not palavras or palavras[0].lower() in VAZIAS:
            continue
        if len(seq) < 4:
            continue
        pesos[seq] = pesos.get(seq, 0) + 1

    # Mais frequentes primeiro, com teto para não explodir o viés
    return [t for t, _ in sorted(pesos.items(), key=lambda kv: (-kv[1], -len(kv[0])))][:40]


def _corrigir_termos(texto: str, glossario: List[str]) -> str:
    """
    Corrige termos do glossário que o Whisper transcreveu errado.

    Conservador de propósito: prefere deixar passar um erro a estragar uma
    frase. Regras:
      - nunca casa uma janela que contenha palavra funcional ("de", "do",
        "no", "o", ...) se o termo do glossário não tiver essa palavra;
      - exige semelhança alta (0.90 para 1 palavra, 0.86 para 2+);
      - exige tamanho próximo entre janela e termo.
    """
    if not texto or not glossario:
        return texto

    import difflib

    FUNCIONAIS = {
        "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
        "em", "no", "na", "nos", "nas", "por", "para", "com", "sem", "e",
        "ou", "que", "ao", "aos", "pelo", "pela", "se", "como", "mais",
    }

    def norm(s: str) -> str:
        """Minúsculas, sem acento e sem pontuação — para comparar de verdade."""
        import unicodedata
        s = unicodedata.normalize("NFKD", s.lower())
        s = "".join(c for c in s if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]", "", s)

    limpar = norm

    tokens = texto.split()
    saida: List[str] = []
    i = 0
    while i < len(tokens):
        substituido = False
        for tam in (4, 3, 2, 1):
            if i + tam > len(tokens):
                continue
            janela = tokens[i:i + tam]
            alvo_norm = norm(" ".join(janela))
            if len(alvo_norm) < 5:
                continue
            if tam == 1 and len(alvo_norm) < 6:
                continue

            baixas = {limpar(t) for t in janela}
            tem_funcional = bool(baixas & FUNCIONAIS)

            melhor, melhor_score = None, 0.0
            for termo in glossario:
                termo_norm = norm(termo)
                if not termo_norm or len(termo_norm) < 5:
                    continue
                # Semelhança de tamanho: evita casar frases inteiras
                if abs(len(termo_norm) - len(alvo_norm)) > 3:
                    continue
                # Palavra funcional na janela só é permitida se o termo também tiver
                if tem_funcional:
                    termo_tokens = {limpar(t) for t in termo.split()}
                    if not (baixas & FUNCIONAIS) <= termo_tokens:
                        continue
                score = difflib.SequenceMatcher(None, alvo_norm, termo_norm).ratio()
                if score > melhor_score:
                    melhor, melhor_score = termo, score

            limiar = 0.88 if tam == 1 else 0.86
            if melhor and melhor_score >= limiar and norm(melhor) != alvo_norm:
                sufixo = ""
                m = re.search(r"([.,;:!?]+)$", janela[-1])
                if m:
                    sufixo = m.group(1)
                saida.append(melhor + sufixo)
                i += tam
                substituido = True
                break

        if not substituido:
            saida.append(tokens[i])
            i += 1

    return " ".join(saida)


def _restaurar_acentos(texto: str) -> str:
    """
    Restaura acentos que o Whisper costuma omitir, por regra (não por lista).

    Aplicado apenas a palavras sem acento — palavras já acentuadas não casam
    com as expressões (que só aceitam [a-z]).
    """
    if not texto:
        return texto

    # Palavras de alta frequência que não seguem regra simples
    DIRETO = {
        "memoria": "memória", "historia": "história", "gloria": "glória",
        "vitoria": "vitória", "tambem": "também", "porem": "porém",
        "atraves": "através", "apos": "após", "ate": "até", "ja": "já",
        "la": "lá", "ca": "cá", "so": "só", "voce": "você", "tres": "três",
        "seculo": "século", "seculos": "séculos", "exercito": "exército",
        "imperio": "império", "pais": "país", "paises": "países",
        "possivel": "possível", "dificil": "difícil", "facil": "fácil",
        "familia": "família", "serie": "série", "especie": "espécie",
        "analise": "análise", "crise": "crise", "origem": "origem",
        "politica": "política", "economia": "economia", "cultura": "cultura",
        "ultimo": "último", "ultima": "última", "proprio": "próprio",
        "epoca": "época", "epocas": "épocas", "area": "área", "areas": "áreas",
        "ideia": "ideia", "ideias": "ideias", "heroi": "herói", "herois": "heróis",
        "poderio": "poderio", "minoria": "minoria", "maioria": "maioria",
        "ninguem": "ninguém", "alguem": "alguém", "tambem,": "também,",
        "guerra": "guerra", "exercitos": "exércitos", "interesses": "interesses",
        "nao": "não", "entao": "então", "sao": "são", "cristao": "cristão",
        "cristaos": "cristãos", "orgao": "órgão", "orgaos": "órgãos",
        "amanha": "amanhã", "irmao": "irmão", "irma": "irmã",
    }

    REGRAS = [
        (re.compile(r"^([a-z]{3,})cao$"), r"\1ção"),
        (re.compile(r"^([a-z]{3,})coes$"), r"\1ções"),
        (re.compile(r"^([a-z]{3,})soes$"), r"\1sões"),
        (re.compile(r"^([a-z]{3,})sao$"), r"\1são"),
        (re.compile(r"^([a-z]{3,})iao$"), r"\1ião"),
        (re.compile(r"^([a-z]{3,})encia$"), r"\1ência"),
        (re.compile(r"^([a-z]{3,})encias$"), r"\1ências"),
    ]

    saida = []
    for token in texto.split():
        m = re.match(r"^([\wÀ-ÿ]+)([.,;:!?]*)$", token)
        if not m:
            saida.append(token)
            continue
        corpo, pont = m.group(1), m.group(2)
        baixo = corpo.lower()

        novo = None
        if baixo in DIRETO:
            novo = DIRETO[baixo]
        else:
            for regex, repl in REGRAS:
                if regex.match(baixo):
                    novo = regex.sub(repl, baixo)
                    break
        if not novo:
            saida.append(token)
            continue
        if corpo[:1].isupper():
            novo = novo.capitalize()
        saida.append(novo + pont)
    return " ".join(saida)


def generate_subtitles(audio_path: str, srt_out: str, cfg: dict,
                       script_text: str = "", force: bool = False) -> List[Dict]:
    """
    Passo 3 do Pipeline:
    Executa o modelo faster-whisper (mais rápido, melhor PT-BR) via CTranslate2.
    Transcreve a narração gerada e produz o arquivo de legendas 'narracao.srt'.
    Retorna uma lista de blocos de legenda com tempo inicial, final e texto.
    
    Melhorias para PT-BR:
    - initial_prompt com um trecho real da narração
    - hotwords com os nomes próprios extraídos do próprio roteiro
    - temperature=0 para saída determinística
    - condition_on_previous_text=True
    - Pós-processamento PT-BR + correção fuzzy dos termos do roteiro

    Use force=True ou VF_WHISPER_REGERAR=1 para ignorar um SRT existente e transcrever de novo.
    """
    regerar = force or os.getenv("VF_WHISPER_REGERAR", "0").strip() in ("1", "true", "yes", "sim")
    if not regerar and os.path.exists(srt_out) and os.path.getsize(srt_out) > 500:
        log("  [Whisper] Legenda SRT já existe — lendo arquivo existente.")
        log("            (use VF_WHISPER_REGERAR=1 para transcrever novamente)")
        return _parse_srt(srt_out)

    from faster_whisper import WhisperModel

    model_name = cfg["whisper"]["model"]
    device_cfg = cfg["whisper"]["device"]

    # faster-whisper usa device "cpu" ou "cuda" (não "auto")
    if device_cfg == "auto":
        device = "cuda"
        try:
            import torch
            if not torch.cuda.is_available():
                device = "cpu"
        except Exception:
            device = "cpu"
    else:
        device = device_cfg

    # Compute type depende da GPU:
    #   - Pascal (GTX 10xx) e anteriores NÃO têm fp16 eficiente no CTranslate2
    #     → usar int8_float32
    #   - Turing/Ampere/Ada (capability >= 7) → float16
    #   - CPU → int8
    compute_type = "int8"
    if device == "cuda":
        cap_major = 0
        try:
            import torch
            cap_major = torch.cuda.get_device_capability(0)[0]
        except Exception:
            cap_major = 0
        compute_type = "float16" if cap_major >= 7 else "int8_float32"

    log(f"  [Whisper] Carregando modelo '{model_name}' na aceleração '{device}' (compute_type={compute_type})...")

    def _carregar_modelo(dev: str, ctype: str):
        return WhisperModel(model_name, device=dev, compute_type=ctype)

    try:
        model = _carregar_modelo(device, compute_type)
    except (ValueError, RuntimeError) as e:
        log(f"  [Whisper] Falha com {device}/{compute_type} ({e}). Tentando fallback...", warn=True)
        tentativas = []
        if device == "cuda":
            tentativas = [("cuda", "float32"), ("cuda", "int8_float32"), ("cpu", "int8")]
        else:
            tentativas = [("cpu", "int8"), ("cpu", "float32")]
        model = None
        for dev, ctype in tentativas:
            if dev == device and ctype == compute_type:
                continue
            try:
                log(f"  [Whisper] Tentando {dev}/{ctype}...")
                model = _carregar_modelo(dev, ctype)
                device, compute_type = dev, ctype
                break
            except Exception as e2:
                log(f"  [Whisper] {dev}/{ctype} indisponível: {e2}", warn=True)
        if model is None:
            raise RuntimeError(
                "Não foi possível carregar o faster-whisper em nenhuma configuração. "
                "Use --whisper-model tiny/base ou defina whisper.device: cpu no config.yaml."
            ) from e

    # ── Viés de transcrição a partir do próprio roteiro ───────────────────────
    # Como o áudio é a leitura deste texto, os termos do roteiro são a verdade.
    glossario = _glossario_do_roteiro(script_text)

    base_prompt = (
        "Esta é a narração de um documentário em português do Brasil. "
        "Use pontuação correta e acentuação padrão (ã, õ, á, é, í, ó, ú, ç). "
        "Não use inglês. Não misture idiomas."
    )
    if script_text:
        trecho = re.sub(r"\s+", " ", script_text).strip()[:700]
        initial_prompt = f"{base_prompt} Trecho da narração: {trecho}"
    else:
        initial_prompt = base_prompt

    hotwords = ", ".join(glossario[:30]) if glossario else None

    log(f"  [Whisper] Transcrevendo áudio '{Path(audio_path).name}' (PT-BR otimizado)...")
    if glossario:
        log(f"  [Whisper] Termos do roteiro usados como viés: {', '.join(glossario[:8])}...")

    opcoes = dict(
        language=cfg["whisper"]["language"],
        temperature=0.0,                    # Determinístico
        condition_on_previous_text=True,    # Consistência entre segmentos
        initial_prompt=initial_prompt,      # Contexto PT-BR + trecho real
        compression_ratio_threshold=2.4,    # Evita alucinações repetitivas
        log_prob_threshold=-1.0,            # Rejeita segmentos de baixa confiança
        no_speech_threshold=0.6,            # Detecta silêncio melhor
        beam_size=5,                        # Melhor qualidade
        best_of=5,                          # Melhor qualidade
        patience=1.0,
    )
    if hotwords:
        opcoes["hotwords"] = hotwords

    try:
        segments, info = model.transcribe(audio_path, **opcoes)
    except TypeError:
        # Versões antigas do faster-whisper não conhecem 'hotwords'
        opcoes.pop("hotwords", None)
        segments, info = model.transcribe(audio_path, **opcoes)
    
    blocks = []

    # Pós-processamento de erros comuns PT-BR
    def corrigir_portugues(texto: str) -> str:
        """
        Corrige a transcrição em três etapas:
          1. acentuação por regra + palavras frequentes;
          2. nomes próprios do próprio roteiro (fuzzy, conservador);
          3. ajustes pontuais de grafia.
        """
        texto = _restaurar_acentos(texto)

        trocas = {
            "impero": "império", "imperos": "impérios",
            "documentario": "documentário", "portugues": "português",
            "ingles": "inglês", "frances": "francês", "alemao": "alemão",
            "japones": "japonês", "chines": "chinês",
        }
        palavras = texto.split()
        corrigidas = []
        for p in palavras:
            m = re.match(r"^([\wÀ-ÿ]+)([.,;:!?]*)$", p)
            if not m:
                corrigidas.append(p)
                continue
            corpo, pont = m.group(1), m.group(2)
            baixo = corpo.lower()
            if baixo in trocas:
                novo = trocas[baixo]
                if corpo[:1].isupper():
                    novo = novo.capitalize()
                corrigidas.append(novo + pont)
            else:
                corrigidas.append(p)

        return _corrigir_termos(" ".join(corrigidas), glossario)

    # Gravação do arquivo SRT em disco
    os.makedirs(os.path.dirname(os.path.abspath(srt_out)), exist_ok=True)
    with open(srt_out, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            st  = round(float(seg.start), 3)
            et  = round(float(seg.end),   3)
            txt = seg.text.strip()
            # Correção PT-BR
            txt = corrigir_portugues(txt)
            f.write(f"{i}\n{_format_ts(st)} --> {_format_ts(et)}\n{txt}\n\n")
            blocks.append({
                "id": i, "start": st, "end": et,
                "duration": round(et - st, 3), "text": txt
            })

    log(f"  [Whisper] {len(blocks)} blocos de legenda sincronizados com sucesso (PT-BR corrigido).")
    return blocks


def generate_subtitles_only(
    audio_path: str, srt_out: str, cfg: dict, script_text: str
) -> List[Dict]:
    """Generate a subtitle file from an existing narration without running TTS."""
    audio_file = Path(audio_path)
    if not audio_file.is_file() or audio_file.stat().st_size == 0:
        raise FileNotFoundError(
            f"Arquivo de narração existente não encontrado ou vazio: {audio_file}"
        )
    log(f"  [Legendas] Usando narração existente: {audio_file}")
    blocks = generate_subtitles(
        str(audio_file), srt_out, cfg, script_text=script_text, force=True
    )
    log(f"  [Legendas] Arquivo SRT pronto: {srt_out}")
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
    api_key     = (
        cfg.get("media", {}).get("pixabay_api_key", "")
        or os.environ.get("VF_PIXABAY_API_KEY", "")
    )

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
    path.parent.mkdir(parents=True, exist_ok=True)
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

def _sanitize_for_console(msg: str) -> str:
    """Remove caracteres que o console Windows (charmap) não suporta."""
    try:
        # Tenta codificar/decodificar para verificar
        msg.encode('ascii', 'strict').decode('ascii')
        return msg
    except UnicodeEncodeError:
        # Substitui caracteres problemáticos
        return msg.encode('ascii', 'replace').decode('ascii')

def _safe_print(msg: str):
    """Print seguro para Windows console (charmap)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        safe = _sanitize_for_console(msg)
        print(safe)

def log(msg: str, warn: bool = False):
    """Exibe mensagens no console formatadas com prefixo [INFO] ou [WARN]."""
    if _VERBOSE or warn:
        prefix = "[WARN]" if warn else "[INFO]"
        safe_msg = _sanitize_for_console(f"{prefix} {msg}")
        _safe_print(safe_msg)


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

LOCAL_MEDIA_REVIEW_MARKER = "__LOCAL_MEDIA_REVIEW__"


def _request_local_media_review(scene: dict, candidate: dict):
    """Request a manual decision over stdin; the desktop GUI renders the image.
    
    Returns:
        bool: True if approved, False if rejected (simple mode)
        list: List of selected image paths (multiple selection mode)
    """
    review = {
        "scene_id": scene.get("id"),
        "scene_text": str(
            scene.get("texto") or scene.get("descricao") or ""
        ),
        "image_path": str(candidate["path"]),
        "image_title": str(candidate.get("title") or Path(candidate["path"]).name),
        "score": float(candidate["score"]),
    }
    if os.environ.get("VF_LOCAL_MEDIA_REVIEW_GUI") == "1":
        print(
            LOCAL_MEDIA_REVIEW_MARKER + json.dumps(review),
            flush=True,
        )
    else:
        print(
            f"\n[REVISÃO LOCAL] Cena {review['scene_id']}: "
            f"{review['image_title']} (score={review['score']:.3f})\n"
            f"Imagem: {review['image_path']}\n"
            f"Trecho: {review['scene_text']}\n"
            "Digite 'aprovar' ou 'rejeitar' (ou cole caminhos separados por ';'): ",
            end="",
            flush=True,
        )
    answer = sys.stdin.readline().strip()
    
    # Check if answer is a JSON array (multiple selection from GUI)
    if answer.startswith('[') and answer.endswith(']'):
        try:
            paths = json.loads(answer)
            if isinstance(paths, list) and paths:
                print(f"    [REVIEW] Recebidas {len(paths)} fotos selecionadas para Cena {review['scene_id']}", flush=True)
                return paths
        except json.JSONDecodeError:
            pass  # Fall through to simple approve/reject
    
    # Check for multiple paths separated by semicolons (terminal mode)
    if ';' in answer:
        paths = [p.strip() for p in answer.split(';') if p.strip()]
        if paths:
            print(f"    [REVIEW] Recebidas {len(paths)} fotos selecionadas para Cena {review['scene_id']}", flush=True)
            return paths
    
    # Simple approve/reject
    answer = answer.casefold()
    if answer in {"approve", "aprovar", "a", "yes", "y"}:
        return True
    if answer in {"reject", "rejeitar", "r", "no", "n"}:
        return False
    if not answer:
        raise RuntimeError("A revisão manual de mídia local foi encerrada sem resposta.")
    raise RuntimeError(
        "Resposta inválida na revisão local; use 'aprovar', 'rejeitar' ou JSON array."
    )


def parse_args():
    """Define todos os parâmetros e opções que o usuário pode informar no terminal."""
    def non_negative_int(value):
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("informe um número inteiro") from exc
        if parsed < 0:
            raise argparse.ArgumentTypeError("o valor não pode ser negativo")
        return parsed

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
    p.add_argument("--min-words",
                   type=int,
                   default=None,
                   dest="min_words",
                   metavar="N",
                   help="Mínimo de palavras exigido no roteiro (padrão: 90%% da meta de duração)")

    # Ajustes de Narração e Voz
    p.add_argument("--voice",
                   default=None,
                   help="Voz Edge-TTS (ex: pt-BR-AntonioNeural, pt-BR-FranciscaNeural)")
    p.add_argument("--tts-engine",
                   choices=["edge-tts", "xtts", "f5-tts", "openai"],
                   default="xtts",
                   help="Motor de narração (padrão: XTTS - voz clonada). Use 'edge-tts' para voz neural da Microsoft.")

    # Ajustes do Modelo Whisper
    p.add_argument("--whisper-model",
                   choices=["tiny", "base", "small", "medium", "large"],
                   default=None,
                   help="Tamanho do modelo Whisper (padrão: base)")
    p.add_argument(
        "--skip-ollama",
        action="store_true",
        default=False,
        help="Pula a triagem do Ollama e abre direto a seleção manual de fotos",
    )

    # As legendas podem ser desativadas, incluídas no render ou geradas
    # separadamente usando uma narração já existente.
    subtitles_group = p.add_mutually_exclusive_group()
    subtitles_group.add_argument("--subtitles",
                                 action="store_true",
                                 default=False,
                                 help="Gera legendas PT-BR e as queima no vídeo")
    subtitles_group.add_argument("--no-subtitles",
                                 action="store_true",
                                 default=False,
                                 help="Não gera nem inclui legendas")
    subtitles_group.add_argument("--subtitles-only",
                                 action="store_true",
                                 default=False,
                                 help="Gera somente o SRT PT-BR da narração existente; não executa o pipeline de vídeo")
    p.add_argument(
        "--audio-only",
        action="store_true",
        help="Gera somente a narração MP3; não planeja cenas, busca mídia nem renderiza vídeo/legendas",
    )

    # Diretor de Arte: validação cruzada de mídia, cena e timing.
    # standard preserva o fluxo atual; strict bloqueia o render se houver falhas críticas.
    p.add_argument(
        "--art-director",
        choices=["off", "standard", "strict"],
        default="standard",
        help=(
            "Diretor de Arte: off=desligado; standard=valida e registra problemas sem bloquear; "
            "strict=interrompe antes do render se houver cenas sem asset ou assets reprovados."
        ),
    )

    # Controle de Retomada e Checkpoint
    resume_group = p.add_mutually_exclusive_group()
    resume_group.add_argument("--resume",
                              dest="resume",
                              action="store_true",
                              default=None,
                              help="Retoma a execução a partir do último checkpoint salvo")
    resume_group.add_argument("--no-resume",
                              dest="resume",
                              action="store_false",
                              help="Desativa a retomada mesmo quando habilitada no config.yaml")
    p.add_argument("--revalidate-images", action="store_true", default=None,
                   help="Ignora aprovações visuais em cache e revalida as imagens")
    p.add_argument("--force-regeneration", action="store_true", default=None,
                   help="Ignora assets locais e solicita nova mídia")
    p.add_argument("--reuse-existing-audio", dest="reuse_existing_audio",
                   action="store_true", default=None,
                   help="Reutiliza narração se o hash do roteiro não mudou")
    p.add_argument("--no-reuse-existing-audio", dest="reuse_existing_audio",
                   action="store_false",
                   help="Gera novamente a narração mesmo se roteiro e áudio coincidirem")
    p.add_argument("--reuse-approved-images", dest="reuse_approved_images",
                   action="store_true", default=None,
                   help="Reutiliza aprovações visuais cujo hash de imagem não mudou")
    p.add_argument("--no-reuse-approved-images", dest="reuse_approved_images",
                   action="store_false",
                   help="Revalida imagens aprovadas anteriormente")
    p.add_argument("--gemini-only", dest="gemini_only", action="store_true", default=None,
                   help="Tenta Gemini primeiro para geração de imagens")
    p.add_argument("--no-gemini-only", dest="gemini_only", action="store_false",
                   help="Desativa o modo exclusivo/prioritário do Gemini")
    p.add_argument("--web-research-before-generation", dest="web_research_before_generation",
                   action="store_true", default=None,
                   help="Pesquisa contexto web no WebChat antes de gerar uma imagem")
    p.add_argument("--no-web-research-before-generation", dest="web_research_before_generation",
                   action="store_false",
                   help="Desativa a pesquisa web prévia em WebChats")
    p.add_argument("--prefer-real-media", dest="prefer_real_media", action="store_true", default=None,
                   help="Tenta mídia real antes da geração por IA")
    p.add_argument("--no-prefer-real-media", dest="prefer_real_media", action="store_false",
                   help="Permite geração por IA antes da busca de mídia real")
    p.add_argument("--debug", dest="debug", action="store_true", default=None,
                   help="Ativa logs detalhados")
    p.add_argument("--no-debug", dest="debug", action="store_false",
                   help="Desativa logs detalhados")
    p.add_argument("--ignore-cache", dest="ignore_cache", action="store_true", default=None,
                   help="Ignora cache de mídia")
    p.add_argument("--gemini-fallback", dest="gemini_fallback", action="store_true", default=None,
                   help="Permite Gemini como fallback após falha dos demais provedores")
    p.add_argument("--no-gemini-fallback", dest="gemini_fallback", action="store_false",
                   help="Desativa Gemini como fallback")
    p.add_argument("--no-checkpoint",
                   action="store_true",
                   help="Desativa o salvamento de checkpoint intermediário")
    p.add_argument(
        "--review-local-media",
        action="store_true",
        default=False,
        help="Abre revisão manual para candidatos locais abaixo do limiar Ollama",
    )
    p.add_argument(
        "--media-source-mode",
        choices=["local_only", "local_then_online", "webchat_only", "internet_images"],
        default=None,
        help=(
            "Origem da mídia: somente local, local antes de internet/WebChat, "
            "somente WebChat ou somente imagens de bancos da internet"
        ),
    )
    p.add_argument(
        "--local-media-folder",
        default=None,
        help="Pasta da biblioteca local de imagens",
    )
    p.add_argument(
        "--min-local-images",
        type=non_negative_int,
        default=None,
        help="Quantidade mínima de imagens locais únicas a distribuir pelo vídeo",
    )

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

    # YouTube: escolha explícita por execução. O padrão "off" preserva o
    # comportamento anterior e evita buscar/baixar conteúdo do YouTube sem pedido.
    p.add_argument(
        "--youtube-mode",
        choices=["off", "cc", "authorized", "both"],
        default="cc",
        help=(
            "Fonte YouTube nesta execução: off=desligada; cc=busca automática de vídeos "
            "identificados como Creative Commons (padrão para preservar o comportamento anterior); "
            "authorized=usa trechos de um arquivo de vídeo local que você declara "
            "ter direito de reutilizar; both=arquivo autorizado primeiro e depois "
            "busca CC. Não transforma um vídeo público em conteúdo livre."
        ),
    )
    p.add_argument(
        "--youtube-authorized-file",
        default=None,
        metavar="ARQUIVO",
        help=(
            "Caminho de um arquivo de vídeo LOCAL que você tem autorização/licença "
            "para reutilizar. Usado somente com --youtube-mode authorized ou both. "
            "O programa extrai segmentos distintos para cenas consecutivas; ele não "
            "baixa o arquivo do YouTube a partir de uma URL."
        ),
    )
    p.add_argument(
        "--youtube-source-url",
        default=None,
        metavar="URL",
        help=(
            "URL original opcional do vídeo autorizado, usada apenas para proveniência "
            "no relatório. Não é usada para baixar o vídeo."
        ),
    )
    p.add_argument(
        "--youtube-rights-confirmed",
        action="store_true",
        help=(
            "Confirma que você verificou e possui autorização/licença para reutilizar "
            "o arquivo indicado em --youtube-authorized-file. Obrigatório nos modos "
            "authorized e both quando um arquivo local é informado."
        ),
    )

    # Pipeline control - permite executar apenas partes do pipeline
    p.add_argument("--script-only", action="store_true", default=False,
                   help="Apenas gerar/planejar o roteiro (passo 1), sem TTS/mídia/render")
    p.add_argument("--images-only", action="store_true", default=False,
                   help="Apenas buscar/gerar mídias (passo 4), precisa de roteiro e áudio existentes")
    p.add_argument("--render-only", action="store_true", default=False,
                   help="Apenas renderizar vídeo final (passos 5-6), precisa de mídia/clips existentes")

    # Text injection - permite injetar texto no início/fim do roteiro
    p.add_argument("--prepend-text", default=None, metavar="TEXTO",
                   help="Texto a inserir no INÍCIO do roteiro (ex: slogan de abertura)")
    p.add_argument("--append-text", default=None, metavar="TEXTO",
                   help="Texto a inserir no FIM do roteiro (ex: call-to-action)")

    args = p.parse_args()
    if args.subtitles_only and (not args.roteiro or args.topic):
        p.error("--subtitles-only exige o caminho do roteiro original e não aceita --topic.")
    if args.audio_only and args.subtitles_only:
        p.error("--audio-only e --subtitles-only são modos incompatíveis.")
    # skip_ollama será processado em main() após cfg ser criado
    if args.youtube_mode in ("authorized", "both"):
        if not args.youtube_authorized_file:
            p.error("--youtube-mode authorized/both exige --youtube-authorized-file com um arquivo LOCAL.")
        if not args.youtube_rights_confirmed:
            p.error("Para usar arquivo próprio/autorizado, informe também --youtube-rights-confirmed.")
        if not Path(args.youtube_authorized_file).expanduser().is_file():
            p.error(f"Arquivo de vídeo local não encontrado: {args.youtube_authorized_file}")
    elif args.youtube_authorized_file and not args.youtube_rights_confirmed:
        p.error("--youtube-authorized-file exige --youtube-rights-confirmed.")

    # Validação de controle de pipeline
    pipeline_modes = [args.script_only, args.images_only, args.render_only]
    if sum(pipeline_modes) > 1:
        p.error("--script-only, --images-only e --render-only são mutuamente exclusivos.")

    # --images-only e --render-only exigem roteiro existente
    if (args.images_only or args.render_only) and not args.roteiro:
        p.error("--images-only e --render-only exigem um arquivo de roteiro (--roteiro / caminho do .txt).")
    # --render-only precisa de mídia pré-existente
    if args.render_only and not args.subtitles_only:
        # Sem --subtitles-only, precisa de áudio/mídia
        pass  # A validação ocorre em main()

    return args


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
    canal_chosen = getattr(args, "canal", None)

    if getattr(args, "topic", None):
        # Modo Produtor Automático: o agente pesquisa e escreve o roteiro
        slug_topic = slugify(args.topic)
        expected_script_path = ROOT_DIR / "roteiros" / f"{slug_topic}.txt"
        expected_script_path.parent.mkdir(parents=True, exist_ok=True)
        roteiro_path = expected_script_path
        reuse_topic_script = (
            bool(args.resume)
            and expected_script_path.is_file()
            and expected_script_path.stat().st_size > 0
        )
        script_text = (
            expected_script_path.read_text(encoding="utf-8").strip()
            if reuse_topic_script
            else ""
        )
        if reuse_topic_script:
            log(f"  [RESUME] Reutilizando roteiro existente: {expected_script_path.name}")

        # Verifica se deve usar WebChat (múltiplos LLMs via navegador)
        modo_escrita = os.getenv("VF_MODO_ESCRITA", "").strip().lower()
        print(f"  [Escrita] modo={modo_escrita or 'procedural'} | webchat_writer={'ok' if _WRITER_AVAILABLE else 'NÃO CARREGOU'}")
        if modo_escrita in ("webchat", "cadeia", "gem") and not _WRITER_AVAILABLE:
            print("  [ERRO] Modo webchat/cadeia/gem pedido, mas o webchat_writer não carregou. Verifique as dependências.")
        usar_webchat = (
            modo_escrita in ("webchat", "cadeia", "gem")
            and _WRITER_AVAILABLE
            and not reuse_topic_script
        )

        if usar_webchat and modo_escrita == "gem":
            # === MODO GEM @roteiroparavideos ===
            # Usa o Gem personalizado do Gemini para gerar roteiro + cenas + narração
            try:
                from webchat_writer import escrever_via_webchat_gem
                target_words = int(args.duration * 135)  # ~135 palavras por minuto
                min_words_target = args.min_words or int(target_words * 0.85)
                
                log(f"  [Gem Mode] Ativo — usando @roteiroparavideos no Gemini")
                log(f"  [Gem Mode] Meta: ~{target_words} palavras | Duração: {args.duration:.0f} min")
                
                gem_dados = escrever_via_webchat_gem(
                    topic=args.topic,
                    duration_min=args.duration,
                    target_words=target_words,
                    roteiros_dir=ROOT_DIR / "roteiros",
                    slug=slug_topic,
                    log=log,
                    min_words=min_words_target
                )
                
                # Salva narração como roteiro principal
                script_text = gem_dados["narracao_completa"]
                roteiro_path.write_text(script_text, encoding="utf-8")
                log(f"  [Gem] Narração salva em: {roteiro_path.relative_to(ROOT_DIR)}")
                
                # Salva dados extras do Gem (cenas, título, etc.)
                gem_extras_path = ROOT_DIR / "roteiros" / f"{slug_topic}_gem_extras.json"
                import json as _json
                gem_extras = {
                    "titulo": gem_dados["titulo"],
                    "cenas": gem_dados["cenas"],
                    "duracao_total_min": gem_dados["duracao_total_min"],
                    "total_cenas": gem_dados["total_cenas"],
                    "site": gem_dados["site"],
                }
                gem_extras_path.write_text(_json.dumps(gem_extras, ensure_ascii=False, indent=2), encoding="utf-8")
                log(f"  [Gem] Extras (cenas/título) salvos em: {gem_extras_path.name}")
                log(f"  [Gem] ✓ {gem_dados['total_cenas']} cenas | {gem_dados['duracao_total_min']:.1f} min | Título: {gem_dados['titulo'][:60]}")
                
            except Exception as e:
                if os.getenv("VF_WEBCHAT_PERMITIR_FALLBACK", "0").strip() == "1":
                    log(f"  [WARN] Gem falhou ({e}) — fallback local habilitado por VF_WEBCHAT_PERMITIR_FALLBACK=1.", warn=True)
                    usar_webchat = False
                else:
                    raise RuntimeError(
                        f"Gem falhou: {e}\n"
                        f"VF_MODO_ESCRITA=gem é EXCLUSIVO — não há fallback local automático.\n"
                        "Verifique se o Gemini está acessível ou defina "
                        "VF_WEBCHAT_PERMITIR_FALLBACK=1 para permitir o fallback procedural."
                    ) from e

        elif usar_webchat:
            # Usa webchat_writer com Gemini, Copilot, ChatGPT, DeepSeek, etc.
            try:
                from webchat_writer import escrever_via_webchat, pesquisar_fontes_web
                from roteiro_em_cadeia import gerar_roteiro_em_cadeia
                writer = _SWA(ROOT_DIR)
                
                # Pesquisa fontes (Wikipedia + web)
                research_data = writer._research_wikipedia(args.topic)
                web_sources = pesquisar_fontes_web(args.topic, max_fontes=6)
                
                # Combina fontes
                all_sources = []
                if research_data.get("full_text"):
                    all_sources.append({
                        "title": research_data.get("title", args.topic),
                        "url": f"https://pt.wikipedia.org/wiki/{urllib.parse.quote(args.topic)}",
                        "text": research_data["full_text"]
                    })
                all_sources.extend(web_sources)
                
                # Persona do canal
                canal_key = (canal_chosen or "documentario").lower().rstrip("s")
                persona = writer.CANAL_PERSONAS.get(canal_key, writer.CANAL_PERSONAS["documentario"])
                
                target_words = int(args.duration * writer.WORDS_PER_MINUTE)
                min_words_target = args.min_words or int(target_words * 0.90)

                log(f"  [WebChat Mode] Ativo — usando LLMs via navegador: {os.getenv('VF_WEBCHAT_SITES', 'gemini,chatgpt,copilot,deepseek')}")
                log(f"  [WebChat Mode] Meta: {target_words} palavras (mínimo exigido: {min_words_target})")
                _gerador = gerar_roteiro_em_cadeia if modo_escrita == "cadeia" else escrever_via_webchat
                script_text = _gerador(
                    topic=args.topic,
                    duration_min=args.duration,
                    target_words=target_words,
                    persona=persona,
                    sources=all_sources,
                    roteiros_dir=ROOT_DIR / "roteiros",
                    slug=slug_topic,
                    canal=canal_key,
                    log=log,
                    min_words=min_words_target
                )
                roteiro_path.write_text(script_text, encoding="utf-8")
                log(f"  [WebChat] Roteiro salvo em: {roteiro_path.relative_to(ROOT_DIR)}")
                
            except Exception as e:
                if os.getenv("VF_WEBCHAT_PERMITIR_FALLBACK", "0").strip() == "1":
                    log(f"  [WARN] WebChat falhou ({e}) — fallback local habilitado por VF_WEBCHAT_PERMITIR_FALLBACK=1.", warn=True)
                    usar_webchat = False
                else:
                    raise RuntimeError(
                        f"WebChat falhou: {e}\n"
                        f"VF_MODO_ESCRITA={modo_escrita} é EXCLUSIVO — não há fallback local automático.\n"
                        "Corrija o acesso aos sites (VF_WEBCHAT_SITES) ou defina "
                        "VF_WEBCHAT_PERMITIR_FALLBACK=1 para permitir o fallback procedural."
                    ) from e

        if not usar_webchat and _WRITER_AVAILABLE and not reuse_topic_script:
            try:
                writer = _SWA(ROOT_DIR)
                script_text, roteiro_path = writer.generate(
                    topic=args.topic,
                    duration_min=args.duration,
                    canal=canal_chosen
                )
            except Exception as e:
                log(f"  [WARN] ScriptWriterAgent encontrou falha temporária: {e}", warn=True)

        # Validação de profundidade do roteiro: se o texto for nulo ou insuficiente
        min_words = args.min_words or max(80, int(args.duration * 135 * 0.40))
        if not script_text or len(script_text.split()) < min_words:
            print("\n" + "=" * 62)
            print("  [AVISO] O roteiro automático não atingiu a profundidade desejada.")
            print(f"  Tema solicitado: '{args.topic}'")
            print("=" * 62)
            print(f"  Você pode escrever ou colar seu roteiro personalizado no arquivo:")
            print(f"  >>> {expected_script_path} <<<")
            print("=" * 62 + "\n")

            # Se estiver em terminal interativo, aguarda o usuário salvar o arquivo
            if sys.stdin.isatty():
                try:
                    ans = input(f"Escreva o roteiro em '{expected_script_path.name}', salve o arquivo e pressione [ENTER] para continuar (ou 'q' para sair): ")
                    if ans.strip().lower() == "q":
                        sys.exit(0)
                    if expected_script_path.exists():
                        script_text = expected_script_path.read_text(encoding="utf-8").strip()
                        roteiro_path = expected_script_path
                except (EOFError, KeyboardInterrupt):
                    sys.exit(0)

            # Se ainda assim o arquivo estiver vazio
            if not script_text or len(script_text.split()) < 20:
                print(f"\n[INFO] Pipeline pausado aguardando roteiro.", file=sys.stderr)
                print(f"Quando terminar de redigir '{expected_script_path}', execute:", file=sys.stderr)
                print(f"    python VideoFactoryAI/agent.py {expected_script_path} --channel {canal_chosen or 'historia'}\n", file=sys.stderr)
                sys.exit(1)

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
    # INJEÇÃO DE TEXTO: prepend/append (CLI flags --prepend-text / --append-text)
    # -------------------------------------------------------------------------
    if getattr(args, "prepend_text", None):
        script_text = f"{args.prepend_text} {script_text}"
        log(f"  [Script] Texto injetado no INÍCIO: \"{args.prepend_text[:80]}...\"")
    if getattr(args, "append_text", None):
        script_text = f"{script_text} {args.append_text}"
        log(f"  [Script] Texto injetado no FIM: \"{args.append_text[:80]}...\"")

    # -------------------------------------------------------------------------
    # CONTROLE DE PIPELINE: --script-only / --images-only / --render-only
    # -------------------------------------------------------------------------
    script_only = getattr(args, "script_only", False)
    images_only = getattr(args, "images_only", False)
    render_only = getattr(args, "render_only", False)

    if script_only:
        print("\n" + "=" * 62)
        print("  MODO --script-only: Apenas geração/planejamento do roteiro (Passo 1)")
        print("=" * 62)
        # Roteiro já foi gerado/carregado acima
        print(f"\n[OK] Roteiro salvo em: {roteiro_path}")
        print(f"[OK] {len(script_text.split())} palavras | {len(script_text)} caracteres")
        return

    # -------------------------------------------------------------------------
    # CARREGAMENTO DE CONFIGURAÇÕES E PERFIS
    # -------------------------------------------------------------------------
    cfg = get_config(
        AGENT_DIR / "config.yaml",
        {"voice": args.voice, "whisper_model": args.whisper_model, "tts_engine": args.tts_engine}
    )
    pipeline_cfg = cfg.setdefault("pipeline", {})
    media_cfg = cfg.setdefault("media", {})
    cfg.setdefault("agent", {})
    if args.resume is not None:
        pipeline_cfg["resume_mode"] = args.resume
    if args.reuse_existing_audio is not None:
        pipeline_cfg["reuse_existing_audio"] = args.reuse_existing_audio
    if args.reuse_approved_images is not None:
        media_cfg["reuse_approved_images"] = args.reuse_approved_images
        media_cfg["revalidate_images"] = not args.reuse_approved_images
    if args.revalidate_images is not None:
        media_cfg["revalidate_images"] = args.revalidate_images
    if args.force_regeneration is not None:
        media_cfg["force_regeneration"] = args.force_regeneration
    if args.gemini_only is not None:
        media_cfg["gemini_only"] = args.gemini_only
    if args.web_research_before_generation is not None:
        media_cfg["web_research_before_generation"] = args.web_research_before_generation
    if args.prefer_real_media is not None:
        media_cfg["prefer_real_media"] = args.prefer_real_media
    if hasattr(args, 'skip_ollama') and args.skip_ollama:
        media_cfg["skip_ollama"] = True
        print("  [CONFIG] Ollama desabilitado (--skip-ollama ativo)")
    if args.debug is not None:
        cfg["agent"]["verbose"] = args.debug
    if args.ignore_cache is not None:
        media_cfg["ignore_cache"] = args.ignore_cache
    if args.gemini_fallback is not None:
        media_cfg["gemini_fallback"] = args.gemini_fallback
    resume_mode = bool(pipeline_cfg.get("resume_mode", False))
    # O Diretor de Arte usa o mesmo executável descoberto pelo pipeline para
    # extrair frames dos vídeos; não depende de ffmpeg estar no PATH global.
    cfg["ffmpeg_path"] = ffmpeg_path
    cfg["ffprobe_path"] = str(Path(ffmpeg_path).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe"))
    _VERBOSE = cfg["agent"].get("verbose", True)

    # Recupera preferências salvas de voz da memória persistente
    vmem = None
    if _VOICE_MEM_AVAILABLE and not args.subtitles_only:
        try:
            vmem = _VMEM(AGENT_DIR / "memory")
            cfg = vmem.apply_to_cfg(cfg, cli_voice=args.voice, cli_engine=args.tts_engine)
        except Exception as e:
            log(f"  [VoiceMemory] Falha ao recuperar preferências: {e}", warn=True)

    # Carrega estilo do canal selecionado (--channel)
    canal_name = getattr(args, "canal", None)
    if canal_name:
        canal_name = canal_name.lower().strip()
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
    else:
        canal_name = "documentario"

    # O perfil do canal fornece preferências padrão, mas não pode substituir
    # uma voz explicitamente escolhida na GUI/CLI.
    if args.voice:
        cfg.setdefault("tts", {})["voice"] = args.voice
    if vmem is not None:
        log(f"  [VoiceMemory] Configurações ativas: {vmem.log_summary(cfg)}")

    # Aplica chaves de API externas se informadas na linha de comando
    if getattr(args, "pexels_key", None):
        cfg.setdefault("media", {})["pexels_api_key"] = args.pexels_key
    if getattr(args, "unsplash_key", None):
        cfg.setdefault("media", {})["unsplash_api_key"] = args.unsplash_key

    # Opções do YouTube são por execução e não sobrescrevem arquivos de configuração.
    media_cfg = cfg.setdefault("media", {})
    if args.media_source_mode is not None:
        media_cfg["media_source_mode"] = args.media_source_mode
    if args.local_media_folder is not None:
        media_cfg["local_media_folder"] = args.local_media_folder
    if args.min_local_images is not None:
        media_cfg["min_local_images"] = args.min_local_images
    media_cfg["youtube_mode"] = args.youtube_mode
    media_cfg["youtube_authorized_file"] = (
        str(Path(args.youtube_authorized_file).expanduser().resolve())
        if args.youtube_authorized_file else ""
    )
    media_cfg["youtube_source_url"] = args.youtube_source_url or ""
    media_cfg["youtube_rights_confirmed"] = bool(args.youtube_rights_confirmed)
    log(f"  YouTube: modo={args.youtube_mode}" + (" (arquivo local autorizado informado)" if args.youtube_authorized_file else ""))

    # -------------------------------------------------------------------------
    # IDENTIFICAÇÃO DO PROJETO E WORKSPACE EXCLUSIVO
    # -------------------------------------------------------------------------
    # Cada tema ou roteiro possui seu próprio diretório em 'projetos/<slug>/'.
    # Isso evita reutilização acidental de mídias, temporários ou clipes de outros temas.
    topic_active = getattr(args, "topic", "") or ""
    if topic_active:
        project_slug = slugify(topic_active)
    else:
        project_slug = slugify(roteiro_path.stem)
        if project_slug in ("roteiro", "roteiros") and script_text:
            first_line = script_text.strip().split("\n")[0][:40]
            if len(first_line) > 5:
                project_slug = slugify(first_line)
    # Para o planejamento de cenas, usa o topic se fornecido, senão deriva do slug do projeto
    topic_for_planning = topic_active or project_slug
    # Scripts existentes também precisam de um slug para localizar metadados
    # de cenas do Gem; nesse fluxo slug_topic não é definido pelo escritor.
    slug_topic = project_slug

    project_dir   = ROOT_DIR / "projetos" / project_slug
    videos_dir    = project_dir / "videos"
    imagens_dir   = project_dir / "imagens"
    temp_clips    = str(project_dir / "temp_clips")
    ckpts_dir     = project_dir / "ckpts"
    thumbs_dir    = project_dir / "thumbnails"
    metadados_dir = project_dir / "metadados"
    saida_dir     = ROOT_DIR / "saida"

    # Nomes e caminhos oficiais: o master final leva o nome real do tema solicitado!
    video_filename = f"{project_slug}.mp4"
    audio_path     = str(project_dir / "narracao.mp3")
    srt_path_file  = str(project_dir / "narracao.srt")
    if args.subtitles_only:
        print("[Legendas] Modo isolado: não haverá geração de voz, busca de mídia nem renderização.")
        try:
            generate_subtitles_only(audio_path, srt_path_file, cfg, script_text)
        except FileNotFoundError as exc:
            print(f"[ERRO] {exc}", file=sys.stderr)
            sys.exit(1)
        return
    if args.audio_only:
        project_dir.mkdir(parents=True, exist_ok=True)
        opening = YOUTUBE_OPENING_SLOGAN.strip()
        closing = YOUTUBE_CLOSING_PHRASE.strip()
        if opening.lower() not in script_text.lower():
            script_text = f"{opening} {script_text}"
        if closing.lower() not in script_text.lower():
            script_text = f"{script_text} {closing}"
        print("[Narração] Modo isolado: gerando somente o arquivo MP3, sem legendas ou vídeo.")
        audio_path = generate_voice(script_text, audio_path, cfg)
        if _VOICE_MEM_AVAILABLE:
            try:
                vmem = _VMEM(AGENT_DIR / "memory")
                vmem.save(
                    voice=cfg["tts"]["voice"],
                    rate=cfg["tts"].get("rate", "+0%"),
                    pitch=cfg["tts"].get("pitch", "+0Hz"),
                    engine=cfg["tts"].get("engine", "edge-tts"),
                )
                log("  [VoiceMemory] Configurações de voz salvas na memória.")
            except Exception as e:
                log(f"  [VoiceMemory] Falha ao persistir preferências: {e}", warn=True)
        print(f"[Narração] Arquivo pronto: {audio_path}")
        return

    # -------------------------------------------------------------------------
    # CONTROLE DE PIPELINE: --script-only / --images-only / --render-only
    # -------------------------------------------------------------------------
    if script_only:
        print("\n" + "=" * 62)
        print("  MODO --script-only: Apenas geração/planejamento do roteiro (Passo 1)")
        print("=" * 62)
        # Roteiro já foi gerado/carregado acima
        print(f"\n[OK] Roteiro salvo em: {roteiro_path}")
        print(f"[OK] {len(script_text.split())} palavras | {len(script_text)} caracteres")
        # Pula o restante do pipeline
        return

    # Força criação das pastas necessárias (ainda que em modo reduzido)
    # Em modo --images-only, ainda precisamos de pastas para os assets
    # Em modo --render-only, precisamos de pastas de saída
    for d in [project_dir, imagens_dir, videos_dir, ckpts_dir, thumbs_dir, metadados_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # O Resto do Pipeline: adicione skip checks em cada passo abaixo.
    # Cada passo verificará getattr(args, "images_only", False) ou
    # getattr(args, "render_only", False) para pular.
    # -------------------------------------------------------------------------
    # O passo 1 (planejamento) já foi concluído acima para script_only.
    # Para os demais modos, continuamos normalmente.
    # srt_path real para o composer (None se legendas desativadas)
    want_subs      = getattr(args, "subtitles", False) and not getattr(args, "no_subtitles", False)
    srt_path       = srt_path_file if want_subs else None
    manifest_path  = str(project_dir / "concat_list.txt")
    out_video      = str(project_dir / video_filename)
    export_video   = str(saida_dir / video_filename)
    checkpoint     = ckpts_dir / "last_run.json"
    plan_path      = ckpts_dir / "scenes_planned.json"
    out_thumb      = str(thumbs_dir / "thumbnail.jpg")

    # -------------------------------------------------------------------------
    # TRATAMENTO DE RETOMADA OU LIMPEZA DE PRODUÇÃO NOVA
    # -------------------------------------------------------------------------
    state = {}
    if resume_mode and not args.no_checkpoint:
        state = load_checkpoint(checkpoint)
        if state:
            log("Retomando execução a partir do checkpoint salvo...")
    else:
        # Se for uma nova execução (sem --resume), limpa os temporários da produção
        # anterior deste projeto específico
        for f in [
            Path(audio_path),
            Path(f"{audio_path}.script.sha256"),
            Path(srt_path_file),
            Path(manifest_path),
        ]:
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
    print(f"  Projeto : {project_slug}")
    print(f"  Roteiro : {roteiro_path.name} ({len(script_text.split())} palavras)")
    print(f"  Destino : {export_video}")
    print(f"  Pasta   : {project_dir}")
    print("=" * 62 + "\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 1/10 — Planejamento de Cenas (Storyboard Semântico)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[1/10] Planejamento de cenas...")
    if state.get("scenes"):
        scenes = state["scenes"]
        log(f"  Cenas carregadas do checkpoint: {len(scenes)} cenas")
    else:
        # Verifica se o Gem já definiu as cenas (modo VF_MODO_ESCRITA=gem)
        gem_extras_path = ROOT_DIR / "roteiros" / f"{slug_topic}_gem_extras.json"
        gem_dados_path = ROOT_DIR / "roteiros" / f"{slug_topic}_gem_dados.json"
        
        if gem_extras_path.exists() and gem_dados_path.exists():
            # Usa as cenas definidas pelo Gem @roteiroparavideos
            try:
                import json as _json
                gem_extras = _json.loads(gem_extras_path.read_text(encoding="utf-8"))
                gem_dados = _json.loads(gem_dados_path.read_text(encoding="utf-8"))
                
                cenas_gem = gem_dados.get("cenas", [])
                if cenas_gem:
                    log(f"  [Gem] Usando {len(cenas_gem)} cenas definidas pelo @roteiroparavideos")
                    
                    # Converte cenas do Gem para formato do pipeline
                    scenes = []
                    words_per_s = 2.3
                    used_queries = set()
                    
                    for i, cena in enumerate(cenas_gem):
                        scene_id = i + 1
                        texto = cena.get("texto", "")
                        duracao = cena.get("duracao", 12.0)
                        query = cena.get("query", f"{topic_for_planning} {cena.get('titulo_cena', '')}")
                        ai_prompt = cena.get("ai_prompt", cena.get("visual", topic_for_planning))
                        
                        # Garante query única
                        if query in used_queries:
                            query = f"{query} {scene_id}"
                        used_queries.add(query)
                        
                        scenes.append({
                            "id": scene_id,
                            "tipo": "imagem",  # Default, o media_research_agent decide
                            "arquivo": f"cena_{scene_id:02d}.jpg",
                            "query": query[:200],
                            "wikimedia_q": "",
                            "ai_prompt": ai_prompt[:500],
                            "needs_ai": False,
                            "descricao": texto[:80],
                            "texto": texto,
                            "start": 0.0,
                            "end": 0.0,
                            "duration": max(round(duracao, 2), 5.0),
                            "titulo_cena": cena.get("titulo_cena", ""),
                            "timestamp": cena.get("timestamp", ""),
                        })
                    
                    log(f"  [Gem] {len(scenes)} cenas carregadas do Gem")
                    log(f"  [Gem] Título: {gem_extras.get('titulo', 'N/A')}")
                    log(f"  [Gem] Duração total: {gem_extras.get('duracao_total_min', 0):.1f} min")
                    
            except Exception as e:
                log(f"  [WARN] Falha ao carregar cenas do Gem: {e}. Usando plan_scenes normal.", warn=True)
                scenes = plan_scenes(script_text, cfg, topic=topic_for_planning, canal=canal_name)
        else:
            scenes = plan_scenes(script_text, cfg, topic=topic_for_planning, canal=canal_name)
        
        log(f"  {len(scenes)} cenas planejadas "
            f"({sum(1 for s in scenes if s['tipo']=='video')} vídeo | "
            f"{sum(1 for s in scenes if s['tipo']=='image')} imagem)")
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
        if not args.no_checkpoint:
            state["scenes"] = scenes
            save_checkpoint(state, checkpoint)
    if resume_mode:
        saved_assets = state.get("asset_map", {})
        resume_asset_map = {}
        if isinstance(saved_assets, dict):
            for key, value in saved_assets.items():
                try:
                    resume_asset_map[int(key)] = str(value)
                except (TypeError, ValueError):
                    continue
        resume_report = build_resume_report(
            scenes,
            resume_asset_map,
            image_min_bytes=DEFAULT_IMAGE_MIN_BYTES,
            video_min_bytes=DEFAULT_VIDEO_MIN_BYTES,
            asset_root=project_dir,
        )
        print(
            "\n" + "=" * 22 + " RESUME REPORT " + "=" * 22 + "\n"
            f"Total cenas: {resume_report['total']}\n"
            f"Já concluídas: {resume_report['completed']}\n"
            f"Faltando: {resume_report['pending']}\n"
            f"Serão processadas: {resume_report['to_process']}\n"
            + "=" * 59
        )
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 2/10 — Geração de Voz Neural (TTS)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # Apenas o slogan de abertura é injetado (botoeira --opening-slogan).
    # A frase de encerramento do YouTube NÃO é mais injetada automaticamente
    # para preservar o conteúdo original do roteiro e evitar duplicatas.
    opening = YOUTUBE_OPENING_SLOGAN.strip()
    if opening and opening.lower() not in script_text.lower():
        script_text = f"{opening} {script_text}"
        log(f"  [Script] Injetado slogan de abertura: \"{opening}\"")

    print("[2/10] Geração de voz (TTS)...")
    # Em modo --images-only, pula a geração de voz pois o áudio já existe
    if not images_only:
        audio_path = generate_voice(script_text, audio_path, cfg)
    else:
        log("[PULA] Passo 2 (TTS pulado em modo --images-only)")
        print("  [PULA] Passo 2: Geração de voz pulada (áudio já existente)")
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
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 3/10 — Transcrição e Geração de Legendas (Whisper) — OPCIONAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    want_subs = getattr(args, "subtitles", False) and not getattr(args, "no_subtitles", False)
    srt_blocks = []
    if want_subs:
        print("[3/10] Geração de legendas (Whisper)...")
        srt_blocks = generate_subtitles(audio_path, srt_path_file, cfg, script_text=script_text)
        scenes     = resync_scenes(scenes, srt_blocks, audio_dur)
        log(f"  Timecodes ressincronizados com precisão para {len(scenes)} cenas.")
        if not args.no_checkpoint:
            state["scenes"]     = scenes
            state["srt_path"]   = srt_path
            state["srt_blocks"] = srt_blocks
            save_checkpoint(state, checkpoint)
        print("  [OK]\n")
    else:
        print("[3/10] Legendas desativadas (padrão) — pulando Whisper.")
        # Sem legendas: usa duração do áudio para distribuir cenas uniformemente
        total_dur = audio_dur
        n = len(scenes)
        if n > 0:
            per = total_dur / n
            for i, sc in enumerate(scenes):
                st = round(i * per, 3)
                et = round((i + 1) * per, 3) if i < n - 1 else round(total_dur, 3)
                sc["start"] = st
                sc["end"] = et
                sc["duration"] = round(max(et - st, 1.0), 3)
        if not args.no_checkpoint:
            state["scenes"] = scenes
            save_checkpoint(state, checkpoint)
        print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 4/10 — Busca de Mídia com Compliance (L0 a L4)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[4/10] Busca de mídia (L0 biblioteca local -> L1 vídeo -> L2 imagem -> L3 IA pública -> L4 IA gerada)...")
    compliance = None
    local_asset_sequences = {}
    if _MRA_AVAILABLE:
        try:
            mra = _MRA(cfg, project_dir, AGENT_DIR / "memory", cache_dir=ROOT_DIR / "cache")
            if getattr(args, "review_local_media", False):
                mra.local_media_review_callback = _request_local_media_review
            # Passa o tópico para o avaliador de imagens
            topic_for_eval = args.topic if getattr(args, "topic", None) else (
                Path(roteiro_path).stem.replace("_", " ") if 'roteiro_path' in locals() else "documentario"
            )
            asset_map = mra.source_all(scenes, topic=topic_for_eval)
            local_asset_sequences = getattr(mra, "local_assets_by_scene", {})
            compliance = mra.compliance_summary()
            log(f"  {compliance['compliant']}/{compliance['total_assets']} mídias verificadas contra direitos autorais.")
            log(f"  Distribuição por nível: {compliance.get('by_level', {})}")
        except Exception as e:
            media_cfg = cfg.get("media") or {}
            source_mode = str(media_cfg.get("media_source_mode", "")).strip().lower()
            local_only = str(media_cfg.get("local_media_mode", "prefer")).lower() == "required"
            if source_mode or local_only:
                raise RuntimeError(
                    f"Modo de origem de mídia '{source_mode or 'local_only'}' ativo; "
                    f"fallback legado bloqueado após falha no MediaResearchAgent: {e}"
                ) from e
            log(f"  [WARN] MediaResearchAgent encontrou exceção ({e}). Usando fallback legado.", warn=True)
            asset_map = source_media(scenes, cfg, project_dir)
    else:
        media_cfg = cfg.get("media") or {}
        source_mode = str(media_cfg.get("media_source_mode", "")).strip().lower()
        local_only = str(media_cfg.get("local_media_mode", "prefer")).lower() == "required"
        if source_mode or local_only:
            raise RuntimeError(
                f"Modo de origem de mídia '{source_mode or 'local_only'}' ativo, "
                "mas MediaResearchAgent não está disponível; fallback legado bloqueado."
            )
        log("  [INFO] MediaResearchAgent não carregado. Usando fallback de mídia.")
        asset_map = source_media(scenes, cfg, project_dir)

    log(f"  {len(asset_map)}/{len(scenes)} mídias preparadas para edição.")
    if not args.no_checkpoint:
        state["asset_map"] = {str(k): v for k, v in asset_map.items()}
        save_checkpoint(state, checkpoint)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 4.5/10 — DIRETOR DE ARTE: mídia ↔ roteiro ↔ timing
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    art_mode = getattr(args, "art_director", "standard")
    if art_mode == "off":
        log("[Diretor de Arte] Desativado por --art-director off.")
    else:
        print("[4.5/10] Diretor de Arte: validação cruzada de assets e timing...")
        validation_results = {}
        art_report = {
            "version": 1,
            "mode": art_mode,
            "topic": locals().get("topic_for_eval", "documentario"),
            "scene_count": len(scenes),
            "validated_count": 0,
            "approved_count": 0,
            "rejected_count": 0,
            "timeline": [],
            "unresolved_issues": [],
            "narration_script_check": {
                "status": "not_checked",
                "reason": "Comparação indicativa disponível quando --subtitles está ativo."
            },
        }
        previous_end = None
        for scene in scenes:
            sid = scene.get("id")
            try:
                st = float(scene.get("start", 0) or 0)
                et = float(scene.get("end", 0) or 0)
                valid = et > st
                issue = None
                if not valid:
                    issue = "Duração de cena inválida (end <= start)"
                elif previous_end is not None and st < previous_end - 0.15:
                    issue = f"Sobreposição de timeline: início {st:.3f}s antes do fim anterior {previous_end:.3f}s"
                elif previous_end is not None and st > previous_end + 0.75:
                    issue = f"Lacuna de timeline de {st - previous_end:.3f}s"
                if issue:
                    art_report["unresolved_issues"].append({"scene_id": sid, "type": "timeline", "issue": issue})
                art_report["timeline"].append({
                    "scene_id": sid, "start": st, "end": et,
                    "duration": round(max(0.0, et - st), 3),
                    "ok": valid and issue is None, "issue": issue
                })
                if valid:
                    previous_end = et
            except (TypeError, ValueError) as exc:
                art_report["unresolved_issues"].append({
                    "scene_id": sid, "type": "timeline", "issue": f"Timecode inválido: {exc}"
                })

        try:
            if _IMAGE_VALIDATOR_AVAILABLE and _validate_assets:
                validation_results = _validate_assets(
                    cfg, project_dir, art_report["topic"], script_text, scenes,
                    asset_map, locals().get("mra"), log
                )
                art_report["validated_count"] = len(validation_results)
                art_report["approved_count"] = sum(1 for r in validation_results.values() if r.approved)
                art_report["rejected_count"] = sum(1 for r in validation_results.values() if not r.approved)
                for sid, result in validation_results.items():
                    if not result.approved:
                        art_report["unresolved_issues"].append({
                            "scene_id": sid, "type": "asset_validation",
                            "issue": result.reason, "score": result.score,
                            "asset_path": result.asset_path
                        })
                if not args.no_checkpoint:
                    state["asset_map"] = {str(k): val for k, val in asset_map.items()}
                    save_checkpoint(state, checkpoint)
                log(f"  {art_report['approved_count']}/{art_report['validated_count']} assets aprovados.")
            else:
                art_report["unresolved_issues"].append({
                    "type": "validator_unavailable",
                    "issue": "image_validator_agent indisponível"
                })
                log("  [WARN] ImageValidatorAgent indisponível; conteúdo visual não validado.", warn=True)
        except Exception as e:
            art_report["unresolved_issues"].append({
                "type": "validator_error", "issue": str(e)
            })
            log(f"  [WARN] Diretor de Arte falhou: {e}", warn=True)

        if srt_blocks:
            import unicodedata
            def _art_words(value):
                value = unicodedata.normalize("NFKD", str(value or "").lower())
                value = "".join(ch for ch in value if not unicodedata.combining(ch))
                return set(re.findall(r"\b[a-z0-9]{3,}\b", value))
            transcript = " ".join(str(b.get("text", "")) for b in srt_blocks)
            script_words = _art_words(script_text)
            transcript_words = _art_words(transcript)
            coverage = len(script_words & transcript_words) / max(1, len(script_words))
            art_report["narration_script_check"] = {
                "status": "indicative_only",
                "script_word_count": len(script_words),
                "transcript_word_count": len(transcript_words),
                "lexical_coverage": round(coverage, 4),
                "note": "Cobertura lexical indicativa; não substitui revisão semântica."
            }

        report_path = Path(project_dir) / "art_director_report.json"
        try:
            # O validator escreve os detalhes por cena no mesmo relatório; mescla-os
            # antes de gravar o resumo da timeline para não perder scores e razões.
            if report_path.is_file():
                try:
                    previous_report = json.loads(report_path.read_text(encoding="utf-8"))
                    if isinstance(previous_report, dict) and "results" in previous_report:
                        art_report["asset_results"] = previous_report["results"]
                except (OSError, ValueError, TypeError):
                    pass
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(art_report, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"  Relatório do Diretor de Arte: {report_path}")
        except Exception as e:
            log(f"  [WARN] Não foi possível salvar o relatório: {e}", warn=True)

        if art_mode == "strict" and art_report["unresolved_issues"]:
            log("  [BLOQUEIO] Diretor de Arte em modo strict encontrou problemas não resolvidos. Renderização cancelada.", warn=True)
            log("  Corrija os itens em art_director_report.json e execute novamente.")
            sys.exit(2)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 5/10 — Processamento Visual (Ken Burns + Normalização 1080p)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[5/10] Processamento visual (Efeitos profissionais + padronização 1080p)...")
    clips = process_all_scenes(
        scenes,
        asset_map,
        temp_clips,
        ffmpeg_path,
        cfg,
        asset_sequences=local_asset_sequences,
    )
    log(f"  {len(clips)} clipes processados na pasta temp_clips do projeto.")
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
    try:
        shutil.copy2(out_video, export_video)
        log(f"  Cópia sincronizada em saida/: {Path(export_video).name}")
    except Exception as e:
        log(f"  [WARN] Falha ao sincronizar em saida/: {e}", warn=True)
    print("  [OK]\n")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # PASSO 7/10 — Geração de Capas (ThumbnailAgent legacy + Novo Generator Gemini Nano Banana 2)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[7/10] Geração de capas (Gemini Nano Banana 2 + contraste visual)...")
    title_text   = project_slug.replace("_", " ").title()
    canal_active = getattr(args, "canal", None)

    # Tenta o novo gerador Gemini Nano Banana 2 primeiro
    thumb_path = None
    if _THUMB_GEN_AVAILABLE and _gen_thumb:
        try:
            thumb_path = _gen_thumb(
                cfg, project_dir, title_text,
                script_text=script_text,
                topic_keywords=None,
                channel_style=canal_active or "documentario",
                log_func=log
            )
            if thumb_path and os.path.exists(thumb_path):
                log(f"  [ThumbnailGenerator] ✓ Gerado via Gemini Nano Banana 2: {Path(thumb_path).name}")
            else:
                thumb_path = None
        except Exception as e:
            log(f"  [WARN] ThumbnailGenerator (Gemini) falhou: {e}", warn=True)
            thumb_path = None

    # Fallback: ThumbnailAgent legacy
    if not thumb_path and _THUMB_AGENT_AVAILABLE:
        try:
            thumb_agent = _THUMBA(
                ffmpeg_path, thumbs_dir,
                cfg["output"]["thumbnail_width"], cfg["output"]["thumbnail_height"]
            )
            out_thumb = thumb_agent.run(
                video_path=out_video, asset_map=asset_map,
                scenes=scenes, title=title_text, canal=canal_active
            )
            if out_thumb and os.path.exists(out_thumb):
                thumb_path = out_thumb
        except Exception as e:
            log(f"  [WARN] ThumbnailAgent legacy falhou ({e}). Usando gerador simples.", warn=True)
            thumb_path = None

    # Fallback final: gerador simples
    if not thumb_path:
        first_asset = asset_map.get(scenes[0]["id"], "") if scenes else ""
        generate_thumbnail(first_asset, out_thumb, title_text,
                           cfg["output"]["thumbnail_width"], cfg["output"]["thumbnail_height"])
        thumb_path = out_thumb

    if thumb_path and os.path.exists(thumb_path):
        try:
            shutil.copy2(thumb_path, saida_dir / f"{project_slug}_thumbnail.jpg")
        except Exception:
            pass

    print("  [OK]\n")

    # PASSO 8/10 — Controle de Qualidade Automatizado (QualityAgent)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    print("[8/10] Controle de qualidade final (QualityAgent)...")
    if _QUALITY_AVAILABLE:
        try:
            qa = _QA(ffmpeg_path, metadados_dir)
            passed = qa.run(
                video_path=out_video,
                audio_path=audio_path,
                srt_path=srt_path_file,
                asset_map=asset_map,
                scenes=scenes,
                expected_duration_s=audio_dur,
            )
            try:
                shutil.copy2(metadados_dir / "quality_report.json", saida_dir / f"{project_slug}_quality_report.json")
            except Exception:
                pass
            if not passed:
                print("\n" + "!" * 62, file=sys.stderr)
                print("  ERRO CRÍTICO: QualityAgent reprovou o vídeo final!", file=sys.stderr)
                print(f"  Consulte o relatório em: {metadados_dir / 'quality_report.json'}", file=sys.stderr)
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
            seo = _SEO(metadados_dir)
            seo.run(
                script_text=script_text,
                scenes=scenes,
                audio_duration_s=audio_dur,
                roteiro_name=project_slug,
                canal=canal_active
            )
            try:
                shutil.copy2(metadados_dir / "youtube_metadata.json", saida_dir / f"{project_slug}_metadata.json")
            except Exception:
                pass
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
                roteiro_name=project_slug,
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

    print("=" * 62)
    print("  VideoFactoryAI — PRODUÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 62)
    print(f"  Projeto        : {project_slug}")
    print(f"  Vídeo Master   : {out_video}")
    print(f"  Cópia Saída    : {export_video}")
    print(f"  Workspace      : {project_dir}")
    print(f"  Thumbnail      : {out_thumb}")
    print(f"  Qualidade      : {metadados_dir / 'quality_report.json'}")
    print(f"  SEO / YouTube  : {metadados_dir / 'youtube_metadata.json'}")
    print(f"  Histórico      : {AGENT_DIR / 'memory' / 'project_history.json'}")
    print(f"  Total de Cenas : {len(scenes)}")
    print(f"  Duração Real   : {audio_dur:.1f}s ({audio_dur/60:.2f} min)")
    print(f"  Tempo Total    : {elapsed:.1f}s ({elapsed/60:.2f} min)")
    print("=" * 62 + "\n")


# Ponto de entrada padrão da linguagem Python
if __name__ == "__main__":
    main()
