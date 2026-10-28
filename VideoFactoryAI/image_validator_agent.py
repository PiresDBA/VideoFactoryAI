# -*- coding: utf-8 -*-
"""
ImageValidatorAgent — Validação rigorosa de imagem ↔ roteiro + timing.

Funcionalidades:
1. Compara cada cena do roteiro com a imagem/vídeo baixado
2. Verifica se o conteúdo visual corresponde ao texto narrado
3. Valida timing: duração da cena vs duração do áudio correspondente
4. Se falhar: deleta asset e solicita regeneração com query corrigida
5. Usa LLM (Gemini) para análise visual + heurísticas rápidas
"""
import os
import json
import time
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from modules.media_engine import get_media_info  # type: ignore


@dataclass
class ValidationResult:
    scene_id: int
    approved: bool
    score: float  # 0-100
    reason: str
    suggestions: List[str]
    timing_ok: bool
    content_ok: bool
    asset_path: str
    asset_type: str  # "image" | "video"
    query_used: str
    regenerate: bool = False
    corrected_query: Optional[str] = None


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as asset_file:
        for chunk in iter(lambda: asset_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ImageValidatorAgent:
    def __init__(
        self,
        cfg: Dict,
        project_dir: Path,
        topic: str,
        script_text: str,
        scenes: List[Dict],
        asset_map: Dict[int, str],
        log_func=print
    ):
        self.cfg = cfg
        self.project_dir = Path(project_dir)
        self.topic = topic
        self.script_text = script_text
        self.scenes = scenes
        self.asset_map = asset_map
        self.log = log_func
        
        # Config
        self.min_score = cfg.get("media", {}).get("image_validator_min_score", 65)
        self.max_retries = cfg.get("media", {}).get("image_validator_max_retries", 3)
        self.use_llm = cfg.get("media", {}).get("image_validator_use_llm", True)
        self._last_content_validation_was_gemini = False
        pipeline_cfg = cfg.get("pipeline", {})
        media_cfg = cfg.get("media", {})
        self.resume_mode = bool(pipeline_cfg.get("resume_mode", False))
        self.reuse_approved_images = bool(media_cfg.get("reuse_approved_images", True))
        self.revalidate_images = bool(media_cfg.get("revalidate_images", False))
        self.force_regeneration = bool(media_cfg.get("force_regeneration", False))
        self.validated_assets_path = self.project_dir / "memory" / "validated_assets.json"
        self.validated_assets = self._load_validated_assets()
        
        # LLM client
        self.llm_client = None
        if self.use_llm and GENAI_AVAILABLE:
            api_key = os.getenv("GEMINI_API_KEY") or cfg.get("media", {}).get("gemini_api_key")
            if api_key:
                try:
                    self.llm_client = genai.Client(api_key=api_key)
                    self.log(f"[ImageValidator] LLM ativado (Gemini)")
                except Exception as e:
                    self.log(f"[ImageValidator] Falha ao inicializar LLM: {e}", warn=True)
        
        # Extrai segmentos de texto por cena para comparação
        self.scene_texts = self._extract_scene_texts()

    def _load_validated_assets(self) -> Dict[str, Dict[str, Any]]:
        if not self.resume_mode or self.revalidate_images or self.force_regeneration:
            return {}
        if not self.validated_assets_path.is_file():
            return {}
        try:
            cache = json.loads(self.validated_assets_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.log(f"[ImageValidator] Não foi possível ler cache de assets aprovados: {exc}", warn=True)
            return {}
        if not isinstance(cache, dict):
            self.log("[ImageValidator] Cache de assets aprovados inválido; será ignorado.", warn=True)
            return {}
        return {
            str(scene_id): item
            for scene_id, item in cache.items()
            if isinstance(item, dict)
        }

    def _save_validated_assets(self) -> None:
        self.validated_assets_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.validated_assets_path.with_suffix(".json.tmp")
        try:
            temp_path.write_text(
                json.dumps(self.validated_assets, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp_path, self.validated_assets_path)
        except OSError as exc:
            self.log(f"[ImageValidator] Não foi possível salvar cache de assets aprovados: {exc}", warn=True)
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _cached_approval(self, scene_id: int, asset_path: str) -> Optional[ValidationResult]:
        cached = self.validated_assets.get(str(scene_id))
        if not cached or cached.get("approved") is not True or not os.path.isfile(asset_path):
            return None
        try:
            current_hash = _sha256_file(asset_path)
        except OSError as exc:
            self.log(f"[ImageValidator] Não foi possível verificar hash do asset {scene_id}: {exc}", warn=True)
            return None
        cached_asset = str(cached.get("asset", ""))
        if cached_asset != asset_path or cached.get("hash") != current_hash:
            return None
        scene = next((item for item in self.scenes if item.get("id") == scene_id), {})
        return ValidationResult(
            scene_id=scene_id,
            approved=True,
            score=100,
            reason="Aprovação reutilizada do cache (hash do asset inalterado)",
            suggestions=[],
            timing_ok=True,
            content_ok=True,
            asset_path=asset_path,
            asset_type=str(scene.get("tipo", "image")),
            query_used=str(scene.get("query", "") or scene.get("wikimedia_q", "")),
        )

    def _resumed_asset_approval(
        self, scene_id: int, asset_path: str, media_agent
    ) -> Optional[ValidationResult]:
        resumed_scene_ids = getattr(media_agent, "resumed_scene_ids", set())
        if (
            not self.resume_mode
            or not self.reuse_approved_images
            or self.revalidate_images
            or self.force_regeneration
            or scene_id not in resumed_scene_ids
            or not os.path.isfile(asset_path)
        ):
            return None
        scene = next((item for item in self.scenes if item.get("id") == scene_id), {})
        return ValidationResult(
            scene_id=scene_id,
            approved=True,
            score=100,
            reason="Asset reutilizado do checkpoint; revalidação desativada",
            suggestions=[],
            timing_ok=True,
            content_ok=True,
            asset_path=asset_path,
            asset_type=str(scene.get("tipo", "image")),
            query_used=str(scene.get("query", "") or scene.get("wikimedia_q", "")),
        )

    def _gemini_auto_approval(
        self, scene_id: int, asset_path: str, media_agent
    ) -> Optional[ValidationResult]:
        scene = next((item for item in self.scenes if item.get("id") == scene_id), {})
        if str(scene.get("tipo", "image")).lower() == "video":
            return None
        approval = getattr(media_agent, "gemini_approved_assets", {}).get(scene_id)
        if not isinstance(approval, dict) or approval.get("approved") is not True:
            return None
        try:
            score = float(approval.get("score", 0))
        except (TypeError, ValueError):
            return None
        if score <= 85 or not os.path.isfile(asset_path):
            return None
        if os.path.normcase(os.path.abspath(str(approval.get("asset", "")))) != os.path.normcase(os.path.abspath(asset_path)):
            return None
        try:
            current_hash = _sha256_file(asset_path)
        except OSError as exc:
            self.log(f"[ImageValidator] Não foi possível verificar o asset aprovado pelo Gemini {scene_id}: {exc}", warn=True)
            return None
        if approval.get("sha256") != current_hash:
            return None
        file_ok, _ = self._validate_file(asset_path, "image")
        if not file_ok:
            return None
        return ValidationResult(
            scene_id=scene_id,
            approved=True,
            score=score,
            reason=f"Gemini aprovou com score {score:g} (>85); validação do Diretor de Arte ignorada",
            suggestions=[],
            timing_ok=True,
            content_ok=True,
            asset_path=asset_path,
            asset_type="image",
            query_used=str(scene.get("query", "") or scene.get("wikimedia_q", "")),
        )
    
    def _extract_scene_texts(self) -> Dict[int, str]:
        """Mapeia scene_id -> texto narrado daquela cena."""
        # O script_text já está sincronizado com as cenas via resync_scenes
        # Cada cena tem 'texto' (o trecho narrado) e 'start'/'end' (timing)
        return {s["id"]: s.get("texto", "") for s in self.scenes}
    
    def validate_all(
        self,
        media_agent,  # MediaResearchAgent instance para regenerar
        max_total_retries: int = 5
    ) -> Dict[int, ValidationResult]:
        """Valida todas as cenas, regenerando as que falharem."""
        results = {}
        total_retries = 0
        
        for scene in self.scenes:
            sid = scene["id"]
            asset_path = self.asset_map.get(sid)
            if not asset_path or not os.path.exists(asset_path):
                self.log(f"[ImageValidator] Cena {sid:02d}: asset não encontrado")
                results[sid] = ValidationResult(
                    scene_id=sid, approved=False, score=0,
                    reason="Asset ausente; cena não pode ser aprovada",
                    suggestions=["Buscar mídia novamente", "Verificar o mapa de assets"],
                    timing_ok=False, content_ok=False,
                    asset_path=str(asset_path or ""), asset_type=str(scene.get("tipo", "image")),
                    query_used=str(scene.get("query", "") or scene.get("wikimedia_q", "")),
                    regenerate=True
                )
                continue

            resumed_result = self._resumed_asset_approval(sid, asset_path, media_agent)
            if resumed_result:
                results[sid] = resumed_result
                self.log(f"[ImageValidator] [RESUME] Cena {sid:02d}: asset do checkpoint reutilizado; validação ignorada.")
                continue

            gemini_result = self._gemini_auto_approval(sid, asset_path, media_agent)
            if gemini_result:
                results[sid] = gemini_result
                self.validated_assets[str(sid)] = {
                    "asset": asset_path,
                    "approved": True,
                    "hash": _sha256_file(asset_path),
                }
                self._save_validated_assets()
                self.log(f"[ImageValidator] [Gemini] Cena {sid:02d}: score {gemini_result.score:g} (>85); aceita automaticamente.")
                continue
            
            retry = 0
            while retry <= self.max_retries:
                if retry == 0:
                    cached_result = self._cached_approval(sid, asset_path)
                    if cached_result:
                        results[sid] = cached_result
                        self.log(f"[ImageValidator] [RESUME] Cena {sid:02d}: aprovação visual reutilizada.")
                        break
                result = self._validate_scene(scene, asset_path)
                results[sid] = result
                
                if result.approved:
                    try:
                        asset_hash = _sha256_file(asset_path)
                    except OSError as exc:
                        self.log(f"[ImageValidator] Não foi possível calcular hash do asset {sid}: {exc}", warn=True)
                    else:
                        self.validated_assets[str(sid)] = {
                            "asset": asset_path,
                            "approved": True,
                            "hash": asset_hash,
                        }
                        self._save_validated_assets()
                    self.log(f"[ImageValidator] ✓ Cena {sid:02d} APROVADA (score={result.score:.0f})")
                    break
                
                if retry >= self.max_retries:
                    self.log(f"[ImageValidator] ✗ Cena {sid:02d} REJEITADA após {retry} tentativas: {result.reason}")
                    result.regenerate = False  # Para não loop infinito
                    break
                
                self.log(f"[ImageValidator] ⚠ Cena {sid:02d} REJEITADA (tentativa {retry+1}/{self.max_retries}): {result.reason}")
                
                # Regenera com query corrigida
                if result.corrected_query and media_agent:
                    try:
                        # Preserve o asset atual até existir uma substituição válida.
                        old_asset_path = asset_path
                        # Solicita regeneração
                        scene_copy = dict(scene)
                        if result.corrected_query:
                            scene_copy["query"] = result.corrected_query
                            scene_copy["wikimedia_q"] = result.corrected_query
                        new_asset = media_agent.regenerate_scene(
                            scene_copy,
                            topic=self.topic
                        )
                        if new_asset and os.path.exists(new_asset):
                            asset_path = new_asset
                            self.asset_map[sid] = new_asset
                            self.log(f"[ImageValidator]   Substituição disponível: {Path(new_asset).name}")
                        else:
                            asset_path = old_asset_path
                            self.log(f"[ImageValidator]   Falha ao regenerar; asset anterior preservado", warn=True)
                            result.regenerate = False
                            break
                    except Exception as e:
                        self.log(f"[ImageValidator]   Erro na regeneração: {e}", warn=True)
                        result.regenerate = False
                        break
                
                retry += 1
                total_retries += 1
                if total_retries >= max_total_retries:
                    self.log(f"[ImageValidator] Limite global de retries atingido", warn=True)
                    break
        
        return results
    
    def _validate_scene(self, scene: Dict, asset_path: str) -> ValidationResult:
        """Valida uma única cena: conteúdo + timing."""
        sid = scene["id"]
        scene_text = self.scene_texts.get(sid, "")
        asset_type = "video" if scene["tipo"] == "video" else "image"
        query_used = scene.get("query", "") or scene.get("wikimedia_q", "") or scene.get("ai_prompt", "")
        
        # 1. Validação de arquivo básico
        file_ok, file_reason = self._validate_file(asset_path, asset_type)
        if not file_ok:
            return ValidationResult(
                scene_id=sid, approved=False, score=0,
                reason=f"Arquivo inválido: {file_reason}",
                suggestions=["Verificar download", "Tentar fonte alternativa"],
                timing_ok=False, content_ok=False,
                asset_path=asset_path, asset_type=asset_type,
                query_used=query_used, regenerate=True
            )
        
        # 2. Validação de timing
        timing_ok, timing_reason = self._validate_timing(scene, asset_path, asset_type)
        
        # 3. Validação de conteúdo (LLM + heurísticas)
        if self.llm_client and self.use_llm:
            content_ok, content_score, content_reason, suggestions, corrected_query = \
                self._validate_content_llm(scene_text, asset_path, asset_type, query_used, self.topic)
        else:
            content_ok, content_score, content_reason, suggestions, corrected_query = \
                self._validate_content_heuristic(scene_text, query_used, asset_type)
        
        gemini_high_score = (
            self._last_content_validation_was_gemini
            and self.use_llm
            and asset_type == "image"
            and content_score > 80
        )
        if gemini_high_score:
            final_score = content_score
            approved = timing_ok
            reason = (
                f"Gemini aprovou com score {content_score:g} (>80); "
                "validação do Diretor de Arte ignorada"
                if approved else timing_reason
            )
            corrected_query = None
        else:
            final_score = content_score * 0.7 + (100 if timing_ok else 30) * 0.3
            approved = (final_score >= self.min_score) and content_ok and timing_ok
            reason = content_reason if not content_ok else (timing_reason if not timing_ok else "OK")
        
        return ValidationResult(
            scene_id=sid,
            approved=approved,
            score=round(final_score, 1),
            reason=reason,
            suggestions=suggestions,
            timing_ok=timing_ok,
            content_ok=content_ok,
            asset_path=asset_path,
            asset_type=asset_type,
            query_used=query_used,
            regenerate=not approved,
            corrected_query=corrected_query if not approved else None
        )
    
    def _validate_file(self, path: str, asset_type: str) -> Tuple[bool, str]:
        """Validação básica de arquivo."""
        if not os.path.exists(path):
            return False, "Arquivo não existe"
        
        size = os.path.getsize(path)
        if asset_type == "video":
            if size < 50_000:  # 50KB mínimo
                return False, f"Vídeo muito pequeno ({size} bytes)"
            # Verifica se é vídeo válido via ffprobe
            try:
                info = get_media_info(path)
                if info.get("duration", 0) < 1.0:
                    return False, "Vídeo muito curto (<1s)"
            except Exception:
                return False, "Não foi possível ler metadados do vídeo"
        else:
            if size < 15_000:  # 15KB mínimo
                return False, f"Imagem muito pequena ({size} bytes)"
            # Valida com PIL
            try:
                from PIL import Image
                with Image.open(path) as im:
                    im.verify()
                with Image.open(path) as im:
                    w, h = im.size
                    if w < 800 or h < 450:
                        return False, f"Resolução baixa: {w}x{h}"
            except Exception as e:
                return False, f"Imagem corrompida: {e}"
        
        return True, "OK"
    
    def _validate_timing(self, scene: Dict, asset_path: str, asset_type: str) -> Tuple[bool, str]:
        """Valida se duração do asset bate com duração da cena."""
        scene_dur = scene.get("duration", 0)
        if scene_dur <= 0:
            return True, "Sem duração definida na cena"
        
        if asset_type == "video":
            try:
                info = get_media_info(asset_path)
                asset_dur = info.get("duration", 0)
                if asset_dur <= 0:
                    return False, "Duração de vídeo inválida"
                # Tolerância: asset pode ser mais longo (loop) mas não muito mais curto
                ratio = asset_dur / scene_dur
                if ratio < 0.8:
                    return False, f"Vídeo curto demais: {asset_dur:.1f}s vs cena {scene_dur:.1f}s (ratio={ratio:.2f})"
                if ratio > 5.0:
                    return False, f"Vídeo longo demais: {asset_dur:.1f}s vs cena {scene_dur:.1f}s"
            except Exception:
                return False, "Erro ao ler duração do vídeo"
        else:
            # Imagem: duração é controlada pelo Ken Burns no visual_processor
            pass
        
        return True, "Timing OK"
    
    def _validate_content_llm(
        self, scene_text: str, asset_path: str, asset_type: str,
        query_used: str, topic: str
    ) -> Tuple[bool, float, str, List[str], Optional[str]]:
        """Valida imagem ou amostras temporais de vídeo usando Gemini."""
        self._last_content_validation_was_gemini = False
        frame_paths: List[str] = []
        try:
            if asset_type == "video":
                frame_paths = self._extract_sample_frames(asset_path)
                if not frame_paths:
                    return self._validate_content_heuristic(scene_text, query_used, asset_type)
            else:
                frame_paths = [asset_path]

            uploaded_items = [self.llm_client.files.upload(file=path) for path in frame_paths]
            media_label = "imagem" if asset_type == "image" else f"{len(uploaded_items)} frames amostrados do vídeo"
            prompt = f"""Você é o Diretor de Arte de um documentário sobre "{topic}".

TEXTO NARRADO DA CENA:
"{scene_text}"

CONSULTA USADA PARA BUSCAR A MÍDIA:
"{query_used}"

MÍDIA AVALIADA: {media_label}.
Para vídeos, os frames são amostras em momentos diferentes; considere se o conteúdo se mantém relevante ao longo do trecho.

Avalie de 0 a 100:
- Correspondência entre elementos visuais e o texto narrado.
- Contexto histórico, geográfico e temático correto; não confunda pessoas, lugares ou épocas.
- Se a mídia ilustra a afirmação narrada, em vez de apenas compartilhar o tema geral.
- Qualidade documental e legibilidade; penalize imagens irrelevantes, memes, conteúdo enganoso ou marcas d'água intrusivas.
- Para vídeo, consistência visual entre os frames amostrados.

Não invente fatos que não possam ser inferidos visualmente. Se não for possível confirmar a correspondência, explique a incerteza e não aprove automaticamente.

Responda APENAS em JSON:
{{
  "score": 0-100,
  "approved": true/false,
  "reason": "explicação breve",
  "suggestions": ["sugestão 1", "sugestão 2"],
  "corrected_query": "consulta mais específica se a mídia não corresponder"
}}"""
            response = self.llm_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt, *uploaded_items],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1
                )
            )
            result = json.loads(response.text)
            score = float(result.get("score", 0))
            if not 0 <= score <= 100:
                raise ValueError("Gemini retornou score fora da faixa 0–100")
            self._last_content_validation_was_gemini = True
            return (
                bool(result.get("approved", False)),
                score,
                str(result.get("reason", "LLM evaluation")),
                result.get("suggestions", []) if isinstance(result.get("suggestions", []), list) else [],
                result.get("corrected_query") if not result.get("approved", False) else None
            )
        except Exception as e:
            self.log(f"[ImageValidator] LLM falhou: {e}, usando heurística", warn=True)
            return self._validate_content_heuristic(scene_text, query_used, asset_type)
        finally:
            # Frames são temporários; nunca remover a mídia original.
            for frame_path in frame_paths:
                if frame_path != asset_path:
                    try:
                        if os.path.exists(frame_path):
                            os.remove(frame_path)
                    except OSError:
                        pass

    def _extract_sample_frames(self, video_path: str) -> List[str]:
        """Extrai até três frames distribuídos no vídeo, não apenas o frame central."""
        frame_paths: List[str] = []
        try:
            info = get_media_info(video_path)
            duration = float(info.get("duration", 0) or 0)
            if duration <= 0:
                return []
            ffmpeg = self.cfg.get("ffmpeg_path", "ffmpeg")
            # Em vídeos curtos, pontos distintos ainda evitam amostrar exatamente o fim.
            points = sorted(set([max(0.05, duration * ratio) for ratio in (0.2, 0.5, 0.8)]))
            for index, timestamp in enumerate(points, start=1):
                out_path = str(Path(video_path).with_name(
                    f"{Path(video_path).stem}.art_director_{index}.jpg"
                ))
                cmd = [
                    ffmpeg, "-y", "-ss", f"{timestamp:.3f}", "-i", video_path,
                    "-frames:v", "1", "-q:v", "3", out_path
                ]
                proc = subprocess.run(cmd, capture_output=True, timeout=30)
                if proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                    frame_paths.append(out_path)
                else:
                    try:
                        if os.path.exists(out_path):
                            os.remove(out_path)
                    except OSError:
                        pass
        except Exception as exc:
            self.log(f"[ImageValidator] Não foi possível amostrar frames do vídeo: {exc}", warn=True)
        return frame_paths

    def _validate_content_heuristic(
        self, scene_text: str, query_used: str, asset_type: str
    ) -> Tuple[bool, float, str, List[str], Optional[str]]:
        """Validação heurística rápida quando LLM não disponível."""
        # Extrai palavras-chave do texto narrado
        keywords = self._extract_keywords(scene_text)
        query_words = set(query_used.lower().split())
        
        # Overlap entre keywords do texto e query usada
        overlap = len(keywords & query_words) / max(len(keywords), 1)
        
        # Penaliza queries genéricas
        generic_penalty = 0
        generic_terms = ["nature", "city", "people", "background", "abstract", "technology", "business"]
        if any(t in query_used.lower() for t in generic_terms):
            generic_penalty = 15
        
        score = max(0, min(100, overlap * 100 - generic_penalty))
        approved = score >= 35 or (0 < len(query_words) <= 3)
        
        if not approved:
            # Sugere query mais específica baseada no texto
            corrected = self._suggest_corrected_query(scene_text, query_used)
            return False, score, f"Baixo overlap texto-query ({overlap:.0%})", \
                ["Query muito genérica", "Adicionar termos específicos do texto"], corrected
        
        return True, score, "Heurística: overlap texto-query adequado", [], None
    
    def _extract_keywords(self, text: str) -> set:
        """Extrai palavras-chave relevantes do texto."""
        import re
        stopwords = {
            "a", "o", "e", "de", "da", "do", "em", "para", "com", "por", "que",
            "um", "uma", "os", "as", "se", "na", "no", "as", "ao", "aos",
            "é", "foi", "era", "são", "eram", "tem", "tinha", "há", "havia",
            "mais", "menos", "muito", "pouco", "todo", "toda", "todos", "todas",
            "este", "esta", "esse", "essa", "aquele", "aquela", "isto", "aquilo",
            "seu", "sua", "seus", "suas", "meu", "minha", "nosso", "nossa",
            "ele", "ela", "eles", "elas", "você", "vocês", "nós", "eu"
        }
        words = re.findall(r'\b[À-ÿa-z]{4,}\b', text.lower())
        return {w for w in words if w not in stopwords and len(w) > 3}
    
    def _suggest_corrected_query(self, scene_text: str, old_query: str) -> str:
        """Sugere query corrigida baseada no texto da cena."""
        keywords = self._extract_keywords(scene_text)
        # Pega top 3 keywords mais longas/específicas
        top_kw = sorted(keywords, key=len, reverse=True)[:3]
        base = " ".join(top_kw)
        return f"{base} documentary historical footage archival".strip()


def validate_scene_assets(
    cfg: Dict,
    project_dir: Path,
    topic: str,
    script_text: str,
    scenes: List[Dict],
    asset_map: Dict[int, str],
    media_agent,
    log_func=print
) -> Dict[int, ValidationResult]:
    """Função de conveniência para validar todos os assets."""
    validator = ImageValidatorAgent(cfg, project_dir, topic, script_text, scenes, asset_map, log_func)
    results = validator.validate_all(media_agent)
    report = {
        "version": 1,
        "topic": topic,
        "scene_count": len(scenes),
        "validated_count": len(results),
        "approved_count": sum(1 for r in results.values() if r.approved),
        "rejected_count": sum(1 for r in results.values() if not r.approved),
        "results": {str(sid): asdict(result) for sid, result in results.items()},
    }
    try:
        report_path = Path(project_dir) / "art_director_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log_func(f"[ImageValidator] Relatório salvo: {report_path}")
    except Exception as exc:
        log_func(f"[ImageValidator] Não foi possível salvar relatório: {exc}", warn=True)
    return results