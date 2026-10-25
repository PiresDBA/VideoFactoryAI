# -*- coding: utf-8 -*-
"""
ImageEvaluatorAgent — Validação de compatibilidade Imagem ↔ Roteiro
====================================================================
Para cada cena, avalia se a imagem/vídeo candidato corresponde ao texto do roteiro.
Usa modelos de visão (via webchat bridge ou API) para "olhar" a imagem e julgar.

Fluxo:
1. Recebe: texto da cena, caminho da imagem/vídeo, query usada para buscar
2. Extrai frame-chave (se vídeo) ou usa a imagem diretamente
3. Envia para avaliador visual com prompt: "Esta imagem ilustra bem o texto: '...'?"
4. Retorna: score 0-100, aprovado/reprovado, motivo
5. Se reprovado: MediaResearchAgent busca outra opção (loop até aprovar ou esgotar tentativas)

Integração:
- Chamado pelo MediaResearchAgent APÓS baixar/gerar cada asset
- Antes de salvar no asset_map final
- Configurável: VF_IMAGE_EVAL=1 para ativar
"""
import os
import json
import base64
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

try:
    import requests
except ImportError:
    requests = None


@dataclass
class EvaluationResult:
    approved: bool
    score: int          # 0-100
    reason: str         # Explicação curta
    suggestions: List[str]  # Como melhorar a query se reprovado


class ImageEvaluatorAgent:
    """
    Avaliador de compatibilidade imagem-roteiro.
    """
    
    def __init__(self, cfg: dict, root: Path, ffmpeg_path: str):
        self.cfg = cfg
        self.root = Path(root)
        self.ffmpeg = ffmpeg_path
        self.enabled = os.getenv("VF_IMAGE_EVAL", "1").strip() not in ("0", "false", "no")
        self.min_score = int(os.getenv("VF_IMAGE_MIN_SCORE", "65"))
        self.max_retries = int(os.getenv("VF_IMAGE_MAX_RETRIES", "3"))
        
        # Cache de avaliações para não reavaliar mesma imagem
        self._cache: Dict[str, EvaluationResult] = {}
        
        # Tenta carregar webchat bridge para avaliação via LLMs multimodais
        self._webchat_available = False
        webchat_dir = os.getenv("VF_WEBCHAT_DIR", "").strip()
        if webchat_dir:
            import sys
            if webchat_dir not in sys.path:
                sys.path.insert(0, webchat_dir)
            try:
                from webchat_bridge import ask_web
                self._ask_web = ask_web
                self._webchat_available = True
            except Exception:
                pass
    
    def evaluate(self, scene_text: str, media_path: str, query_used: str, 
                 scene_id: int, topic: str) -> EvaluationResult:
        """
        Avalia se a mídia em media_path ilustra bem o scene_text.
        Retorna EvaluationResult.
        """
        if not self.enabled:
            return EvaluationResult(True, 100, "Avaliação desativada (VF_IMAGE_EVAL=0)", [])
        
        if not Path(media_path).exists():
            return EvaluationResult(False, 0, "Arquivo não encontrado", ["Arquivo inexistente"])
        
        # Cache key = hash do arquivo + hash do texto
        import hashlib
        file_hash = self._file_hash(media_path)
        text_hash = hashlib.md5(scene_text.encode()).hexdigest()[:8]
        cache_key = f"{file_hash}_{text_hash}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Extrai frame se for vídeo
        img_path = media_path
        is_video = media_path.lower().endswith((".mp4", ".mov", ".webm", ".mkv"))
        temp_frame = None
        
        if is_video:
            temp_frame = self._extract_middle_frame(media_path)
            if temp_frame:
                img_path = temp_frame
            else:
                return EvaluationResult(False, 0, "Falha ao extrair frame do vídeo", ["Vídeo corrompido ou muito curto"])
        
        # Avalia via webchat (Gemini/Claude/GPT-4V) se disponível
        if self._webchat_available:
            result = self._evaluate_via_webchat(scene_text, img_path, query_used, topic)
        else:
            # Fallback: avaliação heurística baseada em query/texto
            result = self._evaluate_heuristic(scene_text, query_used, topic)
        
        # Limpa frame temporário
        if temp_frame and Path(temp_frame).exists():
            try:
                Path(temp_frame).unlink()
            except Exception:
                pass
        
        self._cache[cache_key] = result
        return result
    
    def _extract_middle_frame(self, video_path: str) -> Optional[str]:
        """Extrai frame do meio do vídeo para análise."""
        try:
            # Obtém duração
            cmd_probe = [self.ffmpeg, "-i", video_path]
            result = subprocess.run(cmd_probe, capture_output=True, text=True, timeout=15, errors="replace")
            import re
            m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr or "")
            if not m:
                return None
            hh, mm, ss = m.groups()
            duration = int(hh) * 3600 + int(mm) * 60 + float(ss)
            
            seek = max(1.0, duration / 2)
            tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            tmp_path = tmp.name
            tmp.close()
            
            cmd = [
                self.ffmpeg, "-y", "-ss", str(seek), "-i", video_path,
                "-frames:v", "1", "-q:v", "2", tmp_path
            ]
            subprocess.run(cmd, capture_output=True, timeout=30)
            
            if Path(tmp_path).exists() and Path(tmp_path).stat().st_size > 5000:
                return tmp_path
        except Exception:
            pass
        return None
    
    def _file_hash(self, filepath: str) -> str:
        import hashlib
        h = hashlib.md5()
        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            return h.hexdigest()[:16]
        except Exception:
            return "unknown"
    
    def _evaluate_via_webchat(self, scene_text: str, img_path: str, query_used: str, topic: str) -> EvaluationResult:
        """Usa LLM multimodal (Gemini, GPT-4V, Claude) via webchat_bridge para avaliar."""
        try:
            # Converte imagem para base64
            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            
            # Prompt para avaliação visual
            prompt = f"""Você é um editor visual de documentários. Avalie se a imagem anexa ilustra bem o texto do roteiro abaixo.

TEMA DO DOCUMENTÁRIO: {topic}
TEXTO DA CENA (o que o narrador fala):
\"\"\"{scene_text[:800]}\"\"\"

QUERY USADA PARA BUSCAR ESTA IMAGEM: {query_used}

CRITÉRIOS DE AVALIAÇÃO (0-100):
- 90-100: Perfeita — imagem mostra exatamente o que o texto descreve, enquadramento cinematográfico
- 75-89: Boa — ilustra o conceito central, pode ter detalhes genéricos mas não contradiz
- 60-74: Aceitável — ilustra parcialmente, serve mas não é ideal
- 40-59: Fraca — imagem genérica demais, só tangencialmente relacionada
- 0-39: Inadequada — não ilustra o texto, contradiz, ou é completamente irrelevante

PENALIDADES AUTOMÁTICAS (-20 cada):
- Imagem com marca d'água visível, texto sobreposto, UI de site
- Pessoa olhando para câmera (estilo stock photo posado) em cena histórica/documental
- Estilo "cartoon/ilustração" em documentário sério (exceto se texto pede animação)
- Qualidade técnica ruim (borrada, pixelada, proporção errada)

RESPONDA APENAS EM JSON:
{{
  "score": <inteiro 0-100>,
  "approved": <true/false>,
  "reason": "<uma frase explicando a nota>",
  "suggestions": ["<sugestão 1 para query melhor>", "<sugestão 2>"]
}}"""

            sites = [s.strip() for s in os.getenv("VF_WEBCHAT_SITES", "gemini,copilot,chatgpt").split(",") if s.strip()]
            # Filtra só sites com suporte a visão
            vision_sites = [s for s in sites if s in ("gemini", "chatgpt", "copilot", "claude")]
            if not vision_sites:
                vision_sites = ["gemini", "chatgpt", "copilot"]
            
            # Chama ask_web SEM image_b64 (o bridge não suporta ainda)
            # O bridge abre o navegador e o usuário cola a imagem manualmente se necessário
            resultado = self._ask_web(
                prompt + "\n\n[IMAGEM: " + img_path + " - avalie visualmente]", 
                order=vision_sites, 
                interactive=True, 
                fallback_local=False,
                validar=None
            )
            
            # Parseia resposta JSON
            texto = resultado.get("answer", "")
            import re
            json_match = re.search(r"\{.*\}", texto, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return EvaluationResult(
                    approved=data.get("approved", False),
                    score=int(data.get("score", 0)),
                    reason=data.get("reason", "Sem justificativa"),
                    suggestions=data.get("suggestions", [])
                )
        except Exception as e:
            print(f"  [ImageEval] Erro na avaliação via webchat: {e}")
        
        # Fallback heurístico
        return self._evaluate_heuristic(scene_text, query_used, topic)
    
    def _evaluate_heuristic(self, scene_text: str, query_used: str, topic: str) -> EvaluationResult:
        """Avaliação heurística baseada em overlap de palavras-chave (fallback sem visão)."""
        scene_lower = scene_text.lower()
        query_lower = query_used.lower()
        topic_lower = topic.lower()
        
        # Palavras-chave do texto da cena (substantivos, verbos principais)
        import re
        scene_words = set(re.findall(r"\b[a-záéíóúâêôãõç]{4,}\b", scene_lower))
        query_words = set(re.findall(r"\b[a-záéíóúâêôãõç]{4,}\b", query_lower))
        topic_words = set(re.findall(r"\b[a-záéíóúâêôãõç]{4,}\b", topic_lower))
        
        # Stopwords
        stop = {"sobre", "como", "para", "onde", "quando", "muito", "mais", "menos", 
                "esta", "este", "esse", "essa", "aquele", "aquela", "entre", "depois"}
        scene_words -= stop
        query_words -= stop
        topic_words -= stop
        
        # Overlap
        overlap_scene_query = len(scene_words & query_words)
        overlap_topic_query = len(topic_words & query_words)
        total_scene_kw = max(1, len(scene_words))
        
        # Score baseado em overlap
        score = min(100, int(50 + (overlap_scene_query / total_scene_kw) * 40 + overlap_topic_query * 5))
        
        # Penalidades heurísticas
        if any(bad in query_lower for bad in ["stock", "generic", "abstract", "concept", "background"]):
            score -= 15
        if "person" in query_lower and "historical" not in query_lower and "documentary" not in query_lower:
            score -= 10
        
        approved = score >= self.min_score
        
        return EvaluationResult(
            approved=approved,
            score=max(0, score),
            reason=f"Heurístico: overlap cena-query={overlap_scene_query}, tema-query={overlap_topic_query}",
            suggestions=[f"Adicionar termos específicos: {', '.join(list(scene_words)[:3])}"]
        )


def create_evaluator(cfg: dict, root: Path, ffmpeg_path: str) -> ImageEvaluatorAgent:
    """Factory function."""
    return ImageEvaluatorAgent(cfg, root, ffmpeg_path)