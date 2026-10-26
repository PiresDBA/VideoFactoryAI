# -*- coding: utf-8 -*-
"""
ThumbnailGenerator — Gera thumbnails YouTube de alta qualidade usando Gemini Nano Banana 2.

Características:
- Usa Gemini 2.5 Flash Image Generation (Nano Banana 2)
- Prompt otimizado para CTR alto: cores vibrantes, texto legível, composição rule-of-thirds
- Gera 3 variações e seleciona a melhor por análise de contraste/saturação
- Fallback local se API falhar
"""
import os
import json
import time
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

try:
    from PIL import Image, ImageStat, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@dataclass
class ThumbnailCandidate:
    path: str
    score: float
    metrics: Dict[str, float]
    prompt_used: str


class ThumbnailGenerator:
    def __init__(self, cfg: Dict, project_dir: Path, log_func=print):
        self.cfg = cfg
        self.project_dir = Path(project_dir)
        self.log = log_func
        
        # Config
        self.width = cfg.get("output", {}).get("thumbnail_width", 1280)
        self.height = cfg.get("output", {}).get("thumbnail_height", 720)
        self.api_key = os.getenv("GEMINI_API_KEY") or cfg.get("media", {}).get("gemini_api_key")
        
        self.thumbs_dir = self.project_dir / "thumbnails"
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        
        # Client
        self.client = None
        if GENAI_AVAILABLE and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                self.log("[ThumbnailGenerator] Gemini API disponível")
            except Exception as e:
                self.log(f"[ThumbnailGenerator] Falha ao inicializar Gemini: {e}", warn=True)
    
    def generate(
        self,
        topic: str,
        script_text: str = "",
        topic_keywords: Optional[List[str]] = None,
        channel_style: str = "documentario",
        num_variations: int = 3
    ) -> Optional[str]:
        """
        Gera thumbnail final.
        Retorna caminho do arquivo final ou None se falhar.
        """
        self.log(f"[ThumbnailGenerator] Gerando {num_variations} variações para: {topic}")
        
        # Prepara prompts baseados no tema e estilo
        prompts = self._build_prompts(topic, script_text, topic_keywords, channel_style, num_variations)
        
        candidates = []
        
        for i, prompt in enumerate(prompts):
            self.log(f"[ThumbnailGenerator] Variação {i+1}/{len(prompts)}...")
            candidate = self._generate_variation(prompt, i, topic)
            if candidate:
                candidates.append(candidate)
                self.log(f"[ThumbnailGenerator]   Score: {candidate.score:.1f}")
        
        if not candidates:
            self.log("[ThumbnailGenerator] Todas as variações falharam, tentando fallback local...", warn=True)
            return self._fallback_thumbnail(topic)
        
        # Seleciona a melhor
        best = max(candidates, key=lambda c: c.score)
        final_path = self.thumbs_dir / "thumbnail.jpg"
        
        # Copia a melhor para o local final
        try:
            import shutil
            shutil.copy2(best.path, final_path)
            # Otimiza para YouTube (JPEG qualidade 90, sRGB)
            self._optimize_for_youtube(final_path)
            self.log(f"[ThumbnailGenerator] ✓ Thumbnail final: {final_path} (score={best.score:.1f})")
            return str(final_path)
        except Exception as e:
            self.log(f"[ThumbnailGenerator] Erro ao salvar final: {e}", warn=True)
            return best.path if os.path.exists(best.path) else None
    
    def _build_prompts(
        self, topic: str, script_text: str, keywords: Optional[List[str]], 
        channel_style: str, num_variations: int
    ) -> List[str]:
        """Constrói prompts otimizados para YouTube thumbnails."""
        
        # Extrai palavras-chave do roteiro se não fornecidas
        if not keywords:
            keywords = self._extract_keywords(script_text or topic)
        
        # Palavras-chave principais (top 3)
        main_kw = " ".join(keywords[:3])
        
        # Estilos por canal
        style_guides = {
            "historia": "sepia tones, vintage photograph style, historical documentary, archival footage aesthetic, dramatic lighting, cinematic",
            "geopolitica": "modern clean design, world map background, geometric shapes, professional, authoritative, blue/red accent colors",
            "tecnologia": "futuristic, neon accents, circuit patterns, holographic elements, high-tech, vibrant cyan/magenta",
            "documentario": "cinematic documentary style, rule of thirds, dramatic lighting, depth of field, professional photography",
            "infantil": "bright colorful, friendly cartoon style, happy characters, simple shapes, high contrast, playful",
            "modelismo": "macro photography, detailed scale model, workshop lighting, precision tools, craftsmanship, realistic textures"
        }
        
        style = style_guides.get(channel_style.lower(), style_guides["documentario"])
        
        base_prompt = (
            f"YouTube thumbnail for documentary about '{topic}', "
            f"main subject: {main_kw}, "
            f"{style}, "
            "high contrast, vibrant colors, text-safe areas (top/bottom thirds), "
            "1280x720, 16:9, eye-catching, high CTR design, "
            "professional YouTube thumbnail style, no text overlay (text added later)"
        )
        
        # Variações
        variations = [
            base_prompt + ", close-up hero shot, emotional impact, dramatic shadows",
            base_prompt + ", wide cinematic shot, epic scale, golden hour lighting, atmospheric",
            base_prompt + ", split composition, before/after or cause/effect, dynamic diagonal lines",
            base_prompt + ", centered iconic object, minimal background, bold silhouette, high recognition",
            base_prompt + ", action moment frozen, motion blur, energy, movement, decisive moment"
        ]
        
        return variations[:num_variations]
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extrai palavras-chave relevantes do texto."""
        import re
        stopwords = {
            "a", "o", "e", "de", "da", "do", "em", "para", "com", "por", "que",
            "um", "uma", "os", "as", "se", "na", "no", "as", "ao", "aos",
            "é", "foi", "era", "são", "eram", "tem", "tinha", "há", "havia",
            "mais", "menos", "muito", "pouco", "todo", "toda", "todos", "todas",
            "este", "esta", "esse", "essa", "aquele", "aquela", "isto", "aquilo",
            "seu", "sua", "seus", "suas", "meu", "minha", "nosso", "nossa",
            "ele", "ela", "eles", "elas", "você", "vocês", "nós", "eu",
            "sobre", "como", "quando", "onde", "porque", "então", "depois",
            "antes", "durante", "entre", "contra", "desde", "até", "sem"
        }
        words = re.findall(r'\b[À-ÿa-z]{4,}\b', text.lower())
        freq = {}
        for w in words:
            if w not in stopwords and len(w) > 3:
                freq[w] = freq.get(w, 0) + 1
        return sorted(freq.keys(), key=lambda k: freq[k], reverse=True)[:8]
    
    def _generate_variation(self, prompt: str, idx: int, topic: str) -> Optional[ThumbnailCandidate]:
        """Gera uma variação via Gemini Nano Banana 2."""
        if not self.client:
            return None
        
        try:
            # Gera imagem via Gemini 2.5 Flash Image Generation
            response = self.client.models.generate_content(
                model="gemini-2.5-flash-image-generation",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    candidate_count=1
                )
            )
            
            # Extrai imagem da resposta
            img_data = None
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    img_data = part.inline_data.data
                    break
            
            if not img_data:
                self.log(f"[ThumbnailGenerator] Variação {idx+1}: sem imagem na resposta", warn=True)
                return None
            
            # Salva
            out_path = self.thumbs_dir / f"thumb_var_{idx}_{hashlib.md5(prompt.encode()).hexdigest()[:8]}.jpg"
            with open(out_path, "wb") as f:
                f.write(img_data)
            
            # Verifica e avalia
            if not os.path.exists(out_path) or os.path.getsize(out_path) < 10000:
                return None
            
            metrics = self._analyze_image(out_path)
            score = self._score_thumbnail(metrics)
            
            return ThumbnailCandidate(
                path=str(out_path),
                score=score,
                metrics=metrics,
                prompt_used=prompt
            )
            
        except Exception as e:
            self.log(f"[ThumbnailGenerator] Erro na variação {idx+1}: {e}", warn=True)
            return None
    
    def _analyze_image(self, path: str) -> Dict[str, float]:
        """Analisa métricas da imagem para scoring."""
        if not PIL_AVAILABLE:
            return {"contrast": 50, "saturation": 50, "brightness": 50, "sharpness": 50}
        
        try:
            with Image.open(path) as im:
                im = im.convert("RGB")
                stat = ImageStat.Stat(im)
                
                # Contraste (desvio padrão da luminância)
                luminance = im.convert("L")
                lum_stat = ImageStat.Stat(luminance)
                contrast = min(100, lum_stat.stddev[0] * 2)
                
                # Saturação (média da saturação HSV)
                hsv = im.convert("HSV")
                hsv_stat = ImageStat.Stat(hsv)
                saturation = min(100, hsv_stat.mean[1] * 100 / 255)
                
                # Brilho
                brightness = min(100, stat.mean[0] * 100 / 255)
                
                # Nitidez (Laplaciano variance)
                gray = im.convert("L")
                import numpy as np
                laplacian = np.array(gray.filter(ImageFilter.Kernel(
                    (3, 3), [0, -1, 0, -1, 4, -1, 0, -1, 0]
                )))
                sharpness = min(100, np.var(laplacian) / 100)
                
                return {
                    "contrast": round(contrast, 1),
                    "saturation": round(saturation, 1),
                    "brightness": round(brightness, 1),
                    "sharpness": round(sharpness, 1)
                }
        except Exception:
            return {"contrast": 50, "saturation": 50, "brightness": 50, "sharpness": 50}
    
    def _score_thumbnail(self, metrics: Dict[str, float]) -> float:
        """Calcula score composto para thumbnail (0-100)."""
        # Pesos para YouTube: contraste > saturação > nitidez > brilho
        weights = {
            "contrast": 0.35,
            "saturation": 0.25,
            "sharpness": 0.25,
            "brightness": 0.15
        }
        
        # Normaliza cada métrica (ideal: contraste 60-80, saturação 50-70, nitidez >40, brilho 40-70)
        def norm(val, ideal_min, ideal_max):
            if ideal_min <= val <= ideal_max:
                return 100
            elif val < ideal_min:
                return max(0, 100 * val / ideal_min)
            else:
                return max(0, 100 - (val - ideal_max) * 2)
        
        score = (
            weights["contrast"] * norm(metrics.get("contrast", 50), 60, 80) +
            weights["saturation"] * norm(metrics.get("saturation", 50), 50, 70) +
            weights["sharpness"] * norm(metrics.get("sharpness", 50), 40, 100) +
            weights["brightness"] * norm(metrics.get("brightness", 50), 40, 70)
        )
        
        return round(score, 1)
    
    def _optimize_for_youtube(self, path: Path) -> None:
        """Otimiza JPEG para YouTube: qualidade 90, sRGB, sem metadados desnecessários."""
        if not PIL_AVAILABLE:
            return
        try:
            with Image.open(path) as im:
                im = im.convert("RGB")
                # Garante 1280x720
                if im.size != (1280, 720):
                    im = im.resize((1280, 720), Image.LANCZOS)
                # Salva otimizado
                im.save(path, "JPEG", quality=90, optimize=True, progressive=True, icc_profile=im.info.get("icc_profile"))
        except Exception:
            pass
    
    def _fallback_thumbnail(self, topic: str) -> Optional[str]:
        """Gera thumbnail simples local como fallback."""
        if not PIL_AVAILABLE:
            return None
        
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            img = Image.new("RGB", (1280, 720), color=(20, 30, 50))
            draw = ImageDraw.Draw(img)
            
            # Gradiente simples
            for y in range(720):
                r = int(20 + (y / 720) * 40)
                g = int(30 + (y / 720) * 20)
                b = int(50 + (y / 720) * 30)
                draw.line([(0, y), (1280, y)], fill=(r, g, b))
            
            # Texto do tema
            try:
                font = ImageFont.truetype("arial.ttf", 72)
            except:
                font = ImageFont.load_default()
            
            # Quebra texto em linhas
            words = topic.split()
            lines = []
            current = ""
            for w in words:
                test = current + " " + w if current else w
                bbox = draw.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] > 1100:
                    lines.append(current)
                    current = w
                else:
                    current = test
            if current:
                lines.append(current)
            
            # Desenha texto centralizado
            y = 200
            for line in lines[:3]:
                bbox = draw.textbbox((0, 0), line, font=font)
                w = bbox[2] - bbox[0]
                x = (1280 - w) // 2
                # Sombra
                draw.text((x+3, y+3), line, font=font, fill=(0, 0, 0, 180))
                # Texto principal
                draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
                y += 100
            
            out_path = self.thumbs_dir / "thumbnail.jpg"
            img.save(out_path, "JPEG", quality=90)
            return str(out_path)
        except Exception as e:
            self.log(f"[ThumbnailGenerator] Fallback falhou: {e}", warn=True)
            return None


def generate_thumbnail(
    cfg: Dict,
    project_dir: Path,
    topic: str,
    script_text: str = "",
    topic_keywords: Optional[List[str]] = None,
    channel_style: str = "documentario",
    log_func=print
) -> Optional[str]:
    """Função de conveniência."""
    gen = ThumbnailGenerator(cfg, project_dir, log_func)
    return gen.generate(topic, script_text, topic_keywords, channel_style)