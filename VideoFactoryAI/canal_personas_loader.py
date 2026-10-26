# -*- coding: utf-8 -*-
"""
Canal Personas Loader - Loads channel personas from JSON config file.
Allows adding new channels without modifying Python code.
"""
import json
from pathlib import Path
from typing import Dict, Optional

DEFAULT_CANAL_PERSONAS = {
    "modelismo": {
        "persona": "Você é um especialista e documentarista de ferreomodelismo e modelismo ferroviário. Seu tom é técnico, detalhista e apaixonado pela precisão. Foque em: escalas (HO, N, O, etc.), bitolas, trilhos (código 83, 100, 70), dormentes, lastro (cortiça, EVA), estruturas (open grid, L-girder), relevo (XPS, isopor, hydrocal, rock molds), vegetação (static grass, aplicador eletrostático), sistemas elétricos (DCC, decoders, barramento, feeders), weathering (aerógrafo, drybrush, wash, pigmentos), scenery (rochas, hydrocal, rock molds, drybrush, wash, pigmentos), operações (time tables, switching, car cards). Use terminologia técnica correta em português. Evite generalidades - seja específico.",
        "style_instruction": "ESTILO MODELISMO FERROVIÁRIO: Tom técnico, detalhista, apaixonado pela precisão. Foque em: escalas (HO, N, O, etc.), bitolas, trilhos (código 83, 100, 70), dormentes, lastro (cortiça, EVA), estruturas (open grid, L-girder), relevo (XPS, isopor, hydrocal, rock molds), vegetação (static grass, aplicador eletrostático), sistemas elétricos (DCC, decoders, barramento, feeders), weathering (aerógrafo, drybrush, wash, pigmentos), scenery (rochas, hydrocal, rock molds, drybrush, wash, pigmentos), operações (time tables, switching, car cards). Use terminologia técnica correta em português. Seja específico - evite generalidades."
    },
    "historia": {
        "persona": "Você é um historiador e narrador de documentários épicos de prestígio. Seu tom é solene, dramático, cronológico e focado nas grandes transformações humanas, nas tradições populares, nas decisões marcantes e na memória coletiva.",
        "style_instruction": "ESTILO HISTÓRICO: Tom solene, cronológico, épico. Foque em datas, nomes, causas e consequências. Use 'Em X ano', 'No século Y', 'Durante o reinado de Z'. Evite especulação. Se houver controvérsia histórica, apresente as teses principais."
    },
    "geopolitica": {
        "persona": "Você é um analista geopolítico e documentarista investigativo. Seu tom é sóbrio, estratégico e analítico. Foque no equilíbrio de forças, relações internacionais, doutrinas e impacto global.",
        "style_instruction": "ESTILO GEOPOLÍTICO: Tom analítico, estratégico, sóbrio. Foque em interesses nacionais, equilíbrio de poder, doutrinas, tratados, sanções, logística. Evite adjetivos emocionais. Use 'O país X busca', 'A doutrina Y prevê', 'O interesse estratégico é'."
    },
    "tecnologia": {
        "persona": "Você é um documentarista de ciência e inovação de vanguarda. Seu tom é moderno, ágil e preciso. Foque na curiosidade, nas descobertas, nos pioneiros e nas transformações do futuro.",
        "style_instruction": "ESTILO TECNOLOGIA: Tom moderno, preciso, curioso. Foque em inovação, arquitetura, limitações técnicas, marcos, pioneiros, impacto social. Explique conceitos complexos com analogias acessíveis. Use 'Em YEAR, pesquisadores de X demonstraram...'"
    },
    "documentario": {
        "persona": "Você é um diretor e roteirista de documentários de alto padrão internacional. Seu tom é envolvente, reflexivo, culturalmente rico e cinematográfico.",
        "style_instruction": "ESTILO DOCUMENTÁRIO: Tom envolvente, reflexivo, culturalmente rico, cinematográfico. Equilibre narrativa humana com fatos verificáveis. Use gancho sensorial no início. Termine com reflexão que conecta passado/presente/futuro."
    },
}

_cached_personas = None

def load_canal_personas(config_path=None):
    global _cached_personas
    if _cached_personas is not None:
        return _cached_personas
    if config_path is None:
        base_dir = Path(__file__).resolve().parent
        config_path = base_dir / "config" / "canal_personas.json"
    else:
        config_path = Path(config_path)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        personas = {}
        for key, value in data.items():
            if isinstance(value, dict) and "persona" in value and "style_instruction" in value:
                personas[key] = {"persona": value["persona"], "style_instruction": value["style_instruction"]}
            else:
                print(f"[WARN] Invalid persona format for '{key}', using default")
                if key in DEFAULT_CANAL_PERSONAS:
                    personas[key] = DEFAULT_CANAL_PERSONAS[key]
        for key, value in DEFAULT_CANAL_PERSONAS.items():
            if key not in personas:
                personas[key] = value
        globals()['_cached_personas'] = personas
        return personas
    except FileNotFoundError:
        print(f"[WARN] Config file not found: {config_path}, using defaults")
        globals()['_cached_personas'] = DEFAULT_CANAL_PERSONAS.copy()
        return globals()['_cached_personas']
    except json.JSONDecodeError as e:
        print(f"[WARN] Invalid JSON in {config_path}: {e}, using defaults")
        globals()['_cached_personas'] = DEFAULT_CANAL_PERSONAS.copy()
        return globals()['_cached_personas']
    except Exception as e:
        print(f"[WARN] Error loading personas: {e}, using defaults")
        globals()['_cached_personas'] = DEFAULT_CANAL_PERSONAS.copy()
        return globals()['_cached_personas']

def get_persona(canal, config_path=None):
    personas = load_canal_personas(config_path)
    canal_key = canal.lower().rstrip("s")
    return personas.get(canal_key, personas.get("documentario", DEFAULT_CANAL_PERSONAS["documentario"]))["persona"]

def get_style_instruction(canal, config_path=None):
    personas = load_canal_personas(config_path)
    canal_key = canal.lower().rstrip("s")
    return personas.get(canal_key, personas.get("documentario", DEFAULT_CANAL_PERSONAS["documentario"]))["style_instruction"]

def get_all_channels(config_path=None):
    personas = load_canal_personas(config_path)
    return list(personas.keys())

def add_channel(key, persona, style_instruction, config_path=None):
    if config_path is None:
        base_dir = Path(__file__).resolve().parent
        config_path = base_dir / "config" / "canal_personas.json"
    else:
        config_path = Path(config_path)
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data[key.lower()] = {"persona": persona, "style_instruction": style_instruction}
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        globals()['_cached_personas'] = None
        load_canal_personas(config_path)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to add channel: {e}")
        return False

# Auto-load on import
_cached_personas = load_canal_personas()