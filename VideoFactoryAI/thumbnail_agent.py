"""
ThumbnailAgent — Geração de múltiplas thumbnails para VideoFactoryAI
=====================================================================
Gera 3 versões de thumbnail e classifica pelo maior contraste visual.

Saídas:
  saida/thumbnail_v1.jpg  — Frame real do vídeo + título
  saida/thumbnail_v2.jpg  — Frame alternativo + fundo colorido de canal
  saida/thumbnail_v3.jpg  — Card procedural com alta legibilidade
  saida/thumbnail.jpg     — Melhor versão (por contraste)
  saida/thumbnail_report.json — Pontuações de contraste

Estratégia de contraste:
  Contraste = stddev dos pixels (desvio padrão da luminância).
  Maior stddev → maior variação visual → thumbnail mais impactante.
"""

import os
import json
import subprocess
import tempfile
import statistics
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple


class ThumbnailAgent:
    """Agente de geração e seleção de thumbnails por contraste."""

    DEFAULT_W = 1280
    DEFAULT_H = 720

    CANAL_COLORS = {
        "documentarios": ((15, 23, 42),   (220, 180, 80)),   # azul escuro + ouro
        "geopolitica":   ((20, 0, 0),     (200, 30, 30)),    # preto + vermelho
        "historia":      ((30, 20, 5),    (200, 160, 80)),   # marrom + dourado
        "tecnologia":    ((0, 10, 30),    (0, 200, 255)),    # preto azulado + ciano
        "geral":         ((15, 23, 42),   (255, 255, 255)),  # azul + branco
    }

    def __init__(self, ffmpeg_path: str, saida_dir: Path, w: int = 1280, h: int = 720):
        self.ffmpeg = ffmpeg_path
        self.saida  = Path(saida_dir)
        self.w      = w
        self.h      = h

    # ─────────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────────

    def run(
        self,
        video_path: str,
        asset_map: Dict,
        scenes: List[Dict],
        title: str,
        canal: Optional[str] = None,
    ) -> str:
        """
        Gera as 3 versões e retorna o caminho da melhor thumbnail.
        """
        print("[ThumbnailAgent] Gerando thumbnails (3 versoes)...")
        self.saida.mkdir(parents=True, exist_ok=True)

        canal_key = (canal or "geral").lower()
        bg_color, accent = self.CANAL_COLORS.get(canal_key, self.CANAL_COLORS["geral"])

        versions: List[Dict] = []

        # V1: Frame real do início do vídeo
        v1_path = str(self.saida / "thumbnail_v1.jpg")
        ok_v1 = self._extract_frame(video_path, v1_path, seek_pct=0.05)
        if ok_v1:
            ok_v1 = self._overlay_title(v1_path, v1_path, title, accent, bg_color)
        if not ok_v1:
            self._procedural_card(v1_path, title, bg_color, accent)
        versions.append({"version": "v1", "path": v1_path,
                         "strategy": "frame_inicio"})

        # V2: Frame do meio do vídeo
        v2_path = str(self.saida / "thumbnail_v2.jpg")
        ok_v2 = self._extract_frame(video_path, v2_path, seek_pct=0.40)
        if ok_v2:
            ok_v2 = self._overlay_title(v2_path, v2_path, title, accent, bg_color)
        if not ok_v2:
            self._procedural_card(v2_path, title, (30, 10, 10), (255, 80, 80))
        versions.append({"version": "v2", "path": v2_path,
                         "strategy": "frame_meio"})

        # V3: Card procedural de alta legibilidade
        v3_path = str(self.saida / "thumbnail_v3.jpg")
        self._high_contrast_card(v3_path, title, bg_color, accent)
        versions.append({"version": "v3", "path": v3_path,
                         "strategy": "card_procedural"})

        # Pontua contraste de cada versão
        for v in versions:
            v["contrast_score"] = self._measure_contrast(v["path"])

        # Elege melhor versão
        best = max(versions, key=lambda x: x["contrast_score"])
        best_path = str(self.saida / "thumbnail.jpg")
        import shutil as _sh
        _sh.copy2(best["path"], best_path)

        # Salva relatório
        report = {
            "generated_at": datetime.now().isoformat(),
            "title":        title,
            "canal":        canal_key,
            "best_version": best["version"],
            "best_path":    best_path,
            "versions":     versions,
        }
        with open(self.saida / "thumbnail_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"  [ThumbnailAgent] Melhor versao: {best['version']} "
              f"(contraste={best['contrast_score']:.1f})")
        print(f"  [ThumbnailAgent] Thumbnail final: {best_path}")
        return best_path

    # ─────────────────────────────────────────────────────────────────────────
    # Extração de frame via FFmpeg
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_frame(self, video_path: str, out_path: str, seek_pct: float = 0.1) -> bool:
        """Extrai um frame do vídeo em seek_pct% da duração."""
        if not Path(video_path).exists():
            return False
        try:
            # Duração
            ffprobe = str(Path(self.ffmpeg).parent / "ffprobe.exe")
            if not Path(ffprobe).exists():
                ffprobe = "ffprobe"
            cmd_probe = [
                ffprobe, "-v", "quiet", "-print_format", "json",
                "-show_format", video_path
            ]
            import json as _json
            result = subprocess.run(cmd_probe, capture_output=True,
                                    text=True, timeout=15)
            dur = float(_json.loads(result.stdout or "{}").get(
                "format", {}).get("duration", 60))
            seek_s = max(1, dur * seek_pct)

            cmd = [
                self.ffmpeg, "-ss", str(seek_s), "-i", video_path,
                "-frames:v", "1",
                "-vf", f"scale={self.w}:{self.h}:force_original_aspect_ratio=decrease,"
                       f"pad={self.w}:{self.h}:(ow-iw)/2:(oh-ih)/2",
                "-q:v", "2", out_path, "-y"
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=30)
            return r.returncode == 0 and Path(out_path).exists()
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Overlay de título
    # ─────────────────────────────────────────────────────────────────────────

    def _overlay_title(self, in_path: str, out_path: str,
                        title: str, text_color: Tuple, shadow_color: Tuple) -> bool:
        """Adiciona título ao frame usando FFmpeg drawtext."""
        try:
            from PIL import Image, ImageDraw
            img = Image.open(in_path).convert("RGB")
            img = img.resize((self.w, self.h))
            draw = ImageDraw.Draw(img)

            # Faixa escura na base
            overlay_h = int(self.h * 0.30)
            for y in range(self.h - overlay_h, self.h):
                alpha = int(200 * (y - (self.h - overlay_h)) / overlay_h)
                for x in range(self.w):
                    orig = img.getpixel((x, y))
                    blended = tuple(
                        int(orig[c] * (1 - alpha/255) + shadow_color[c] * (alpha/255))
                        for c in range(3)
                    )
                    img.putpixel((x, y), blended)

            # Texto
            text = title[:60]
            font_size = 52
            x = 40
            y = self.h - overlay_h + 20

            # Sombra
            draw.text((x+2, y+2), text, fill=(0, 0, 0))
            # Texto principal
            draw.text((x, y), text, fill=text_color)

            img.save(out_path, "JPEG", quality=92)
            return True
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Cards procedurais
    # ─────────────────────────────────────────────────────────────────────────

    def _procedural_card(self, out_path: str, title: str,
                          bg: Tuple, accent: Tuple):
        """Card básico com fundo sólido e título."""
        try:
            from PIL import Image, ImageDraw
            img  = Image.new("RGB", (self.w, self.h), bg)
            draw = ImageDraw.Draw(img)

            # Faixa de destaque lateral esquerda
            for x in range(12):
                for y in range(self.h):
                    img.putpixel((x, y), accent)

            # Título
            lines = self._wrap_text(title, 40)
            y = self.h // 2 - len(lines) * 35
            for line in lines:
                draw.text((50, y), line, fill=accent)
                y += 70

            img.save(out_path, "JPEG", quality=92)
        except Exception:
            pass

    def _high_contrast_card(self, out_path: str, title: str,
                              bg: Tuple, accent: Tuple):
        """Card de alto contraste: fundo escuro, texto grande e brilhante."""
        try:
            from PIL import Image, ImageDraw
            img  = Image.new("RGB", (self.w, self.h), bg)
            draw = ImageDraw.Draw(img)

            # Gradiente horizontal simulado (faixas)
            for i in range(20):
                x = int(self.w * i / 20)
                brightness = int(30 * (i / 20))
                color = tuple(min(255, c + brightness) for c in bg)
                draw.rectangle([x, 0, x + self.w // 20, self.h], fill=color)

            # Linha de destaque horizontal
            y_line = int(self.h * 0.55)
            draw.rectangle([40, y_line, self.w - 40, y_line + 6], fill=accent)

            # Título grande acima da linha
            lines = self._wrap_text(title.upper(), 28)
            y = y_line - len(lines) * 75 - 20
            for line in lines:
                # Sombra
                draw.text((44, y + 4), line, fill=(0, 0, 0))
                # Texto
                draw.text((40, y), line, fill=accent)
                y += 80

            # Subtítulo "DOCUMENTARIO" abaixo da linha
            draw.text((40, y_line + 20), "DOCUMENTARIO", fill=(180, 180, 180))

            img.save(out_path, "JPEG", quality=95)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # Medição de contraste
    # ─────────────────────────────────────────────────────────────────────────

    def _measure_contrast(self, img_path: str) -> float:
        """
        Calcula contraste como desvio padrão da luminância dos pixels.
        Maior valor = maior variação visual = thumbnail mais impactante.
        """
        try:
            from PIL import Image
            img  = Image.open(img_path).convert("L")  # escala de cinza
            # Amostra 1% dos pixels para velocidade
            pixels = list(img.getdata())
            step   = max(1, len(pixels) // 500)
            sample = pixels[::step]
            if len(sample) < 10:
                return 0.0
            return statistics.stdev(sample)
        except Exception:
            return 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Utilitários
    # ─────────────────────────────────────────────────────────────────────────

    def _wrap_text(self, text: str, max_chars: int) -> List[str]:
        """Quebra texto em linhas de no máximo max_chars caracteres."""
        words  = text.split()
        lines  = []
        current = ""
        for w in words:
            if len(current) + len(w) + 1 <= max_chars:
                current = (current + " " + w).strip()
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        return lines[:4]  # máx 4 linhas
