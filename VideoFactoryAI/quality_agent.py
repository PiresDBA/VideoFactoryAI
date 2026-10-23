"""
QualityAgent — Verificação pós-renderização do VideoFactoryAI
=============================================================
Verifica o vídeo final e gera saida/quality_report.json.

Verificações:
  - Duração final (vs. áudio esperado)
  - Frames pretos (via FFmpeg blackdetect)
  - Cenas repetidas (hashing de frames-chave)
  - Ausência de mídia (asset_map incompleto)
  - Erros de legenda (SRT malformado ou vazio)
  - Resolução/aspect-ratio final
  - Sincronização de áudio (stream de áudio presente)

Resultado:
  - saida/quality_report.json  (sempre gerado)
  - Retorna True se aprovado, False se erros críticos
"""

import os
import json
import subprocess
import hashlib
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


class QualityAgent:
    """Agente de controle de qualidade pós-renderização."""

    # Tolerâncias
    DURATION_TOLERANCE_S = 3.0   # diferença máxima aceitável entre vídeo e áudio
    BLACK_THRESHOLD_S    = 0.5   # frames pretos contínuos acima disso = erro
    MIN_RESOLUTION_W     = 1280  # resolução mínima aceitável
    MIN_RESOLUTION_H     = 720

    # Criticidade dos erros
    CRITICAL = "CRITICAL"
    WARNING  = "WARNING"
    INFO     = "INFO"

    def __init__(self, ffmpeg_path: str, saida_dir: Path):
        self.ffmpeg   = ffmpeg_path
        self.saida    = Path(saida_dir)
        self.errors: List[Dict] = []
        self.warnings: List[Dict] = []
        self.infos: List[Dict] = []

    # ─────────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────────

    def run(
        self,
        video_path: str,
        audio_path: str,
        srt_path: str,
        asset_map: Dict,
        scenes: List[Dict],
        expected_duration_s: float,
    ) -> bool:
        """
        Executa todas as verificações e grava quality_report.json.
        Retorna True se não há erros críticos.
        """
        print("[QualityAgent] Iniciando verificacoes de qualidade...")

        # 1. Existência do arquivo
        self._check_file_exists(video_path)

        if Path(video_path).exists():
            # 2. Resolução e streams
            meta = self._probe(video_path)
            self._check_resolution(meta)
            self._check_audio_stream(meta)

            # 3. Duração
            actual_dur = self._get_duration(meta)
            self._check_duration(actual_dur, expected_duration_s)

            # 4. Frames pretos
            self._check_black_frames(video_path)

            # 5. Frames repetidos (hash de 5 keyframes)
            self._check_repeated_frames(video_path)

        # 6. Asset map completo
        self._check_asset_coverage(asset_map, scenes)

        # 7. Legendas
        self._check_subtitles(srt_path)

        # Grava relatório
        report = self._build_report(video_path, expected_duration_s)
        report_path = self.saida / "quality_report.json"
        self.saida.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Exibe resumo
        n_crit = len(self.errors)
        n_warn = len(self.warnings)
        status = "REPROVADO" if n_crit > 0 else "APROVADO"
        print(f"  [QualityAgent] Status: {status} | Erros criticos: {n_crit} | Avisos: {n_warn}")
        print(f"  [QualityAgent] Relatorio: {report_path}")

        if n_crit > 0:
            print("  [QualityAgent] ERROS CRITICOS:")
            for e in self.errors:
                print(f"    - [{e['check']}] {e['message']}")

        return n_crit == 0

    # ─────────────────────────────────────────────────────────────────────────
    # Verificações individuais
    # ─────────────────────────────────────────────────────────────────────────

    def _check_file_exists(self, video_path: str):
        if not Path(video_path).exists():
            self._add(self.CRITICAL, "file_exists",
                      f"Arquivo de video nao encontrado: {video_path}")
        else:
            size_mb = Path(video_path).stat().st_size / (1024 * 1024)
            self._add(self.INFO, "file_exists",
                      f"Video encontrado: {Path(video_path).name} ({size_mb:.1f} MB)")

    def _check_resolution(self, meta: Dict):
        w = meta.get("width", 0)
        h = meta.get("height", 0)
        if w < self.MIN_RESOLUTION_W or h < self.MIN_RESOLUTION_H:
            self._add(self.CRITICAL, "resolution",
                      f"Resolucao abaixo do minimo: {w}x{h} (minimo {self.MIN_RESOLUTION_W}x{self.MIN_RESOLUTION_H})")
        else:
            self._add(self.INFO, "resolution", f"Resolucao OK: {w}x{h}")

    def _check_audio_stream(self, meta: Dict):
        if not meta.get("has_audio"):
            self._add(self.CRITICAL, "audio_stream",
                      "Stream de audio ausente no video final")
        else:
            self._add(self.INFO, "audio_stream", "Stream de audio presente")

    def _check_duration(self, actual: float, expected: float):
        diff = abs(actual - expected)
        if actual <= 0:
            self._add(self.CRITICAL, "duration",
                      "Duracao do video e zero ou invalida")
        elif diff > self.DURATION_TOLERANCE_S:
            level = self.WARNING if diff < 10 else self.CRITICAL
            self._add(level, "duration",
                      f"Duracao divergente: video={actual:.1f}s, audio={expected:.1f}s, diff={diff:.1f}s")
        else:
            self._add(self.INFO, "duration",
                      f"Duracao OK: {actual:.1f}s (esperado ~{expected:.1f}s)")

    def _check_black_frames(self, video_path: str):
        """Detecta segmentos de frames pretos usando FFmpeg blackdetect."""
        try:
            cmd = [
                self.ffmpeg, "-i", video_path,
                "-vf", f"blackdetect=d={self.BLACK_THRESHOLD_S}:pix_th=0.10",
                "-an", "-f", "null", "-",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                errors="replace"
            )
            output = result.stderr
            black_segments = re.findall(
                r"black_start:([\d.]+).*?black_end:([\d.]+).*?black_duration:([\d.]+)",
                output
            )
            if black_segments:
                total_black = sum(float(d) for _, _, d in black_segments)
                self._add(self.WARNING, "black_frames",
                          f"{len(black_segments)} segmento(s) preto(s) detectado(s), total={total_black:.1f}s")
            else:
                self._add(self.INFO, "black_frames", "Nenhum frame preto detectado")
        except subprocess.TimeoutExpired:
            self._add(self.WARNING, "black_frames", "Timeout na verificacao de frames pretos")
        except Exception as e:
            self._add(self.WARNING, "black_frames", f"Verificacao de frames pretos falhou: {e}")

    def _check_repeated_frames(self, video_path: str):
        """
        Extrai 8 frames distribuídos pelo vídeo e verifica duplicatas via hash MD5.
        Frames idênticos indicam cenas repetidas.
        """
        import tempfile
        try:
            # Obtém duração
            dur = self._get_duration(self._probe(video_path))
            if dur <= 0:
                return

            hashes = []
            with tempfile.TemporaryDirectory() as tmpdir:
                for i in range(8):
                    t = dur * (i + 0.5) / 8
                    out_frame = os.path.join(tmpdir, f"frame_{i}.jpg")
                    cmd = [
                        self.ffmpeg, "-ss", str(t), "-i", video_path,
                        "-frames:v", "1", "-q:v", "5", out_frame, "-y"
                    ]
                    subprocess.run(cmd, capture_output=True, timeout=30)
                    if os.path.exists(out_frame):
                        with open(out_frame, "rb") as f:
                            hashes.append(hashlib.md5(f.read()).hexdigest())

            unique = len(set(hashes))
            total  = len(hashes)
            if total > 0 and unique < total * 0.6:
                self._add(self.WARNING, "repeated_frames",
                          f"Possivel conteudo repetido: {unique}/{total} frames unicos")
            else:
                self._add(self.INFO, "repeated_frames",
                          f"Frames variados: {unique}/{total} frames unicos")
        except Exception as e:
            self._add(self.WARNING, "repeated_frames", f"Verificacao de frames falhou: {e}")

    def _check_asset_coverage(self, asset_map: Dict, scenes: List[Dict]):
        missing = []
        for s in scenes:
            sid = s.get("id")
            if sid not in asset_map and str(sid) not in asset_map:
                missing.append(sid)
        if missing:
            self._add(self.WARNING, "asset_coverage",
                      f"Cenas sem midia: {missing}")
        else:
            self._add(self.INFO, "asset_coverage",
                      f"Todas as {len(scenes)} cenas possuem midia")

    def _check_subtitles(self, srt_path: str):
        if not Path(srt_path).exists():
            self._add(self.WARNING, "subtitles", "Arquivo SRT nao encontrado")
            return
        try:
            content = Path(srt_path).read_text(encoding="utf-8", errors="replace").strip()
            if not content:
                self._add(self.WARNING, "subtitles", "Arquivo SRT vazio")
                return
            # Conta blocos válidos
            blocks = re.split(r"\n\n+", content)
            valid = 0
            for b in blocks:
                lines = b.strip().splitlines()
                if len(lines) >= 3 and "-->" in lines[1]:
                    valid += 1
            if valid == 0:
                self._add(self.CRITICAL, "subtitles",
                          "Nenhum bloco SRT valido encontrado")
            else:
                self._add(self.INFO, "subtitles",
                          f"SRT OK: {valid} blocos de legenda")
        except Exception as e:
            self._add(self.WARNING, "subtitles", f"Leitura do SRT falhou: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Utilitários FFprobe
    # ─────────────────────────────────────────────────────────────────────────

    def _probe(self, video_path: str) -> Dict:
        """Retorna metadados usando ffprobe ou ffmpeg diretamente."""
        import shutil

        # 1. Tenta ffprobe se disponível
        ffprobe = str(Path(self.ffmpeg).parent / "ffprobe.exe")
        if not Path(ffprobe).exists():
            ffprobe = shutil.which("ffprobe")

        if ffprobe:
            try:
                cmd = [
                    ffprobe, "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams", "-show_format",
                    video_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True,
                                        timeout=30, errors="replace")
                data = json.loads(result.stdout or "{}")
                if data.get("streams"):
                    meta: Dict[str, Any] = {}
                    for stream in data.get("streams", []):
                        if stream.get("codec_type") == "video" and "width" not in meta:
                            meta["width"]       = stream.get("width", 0)
                            meta["height"]      = stream.get("height", 0)
                            meta["video_codec"]  = stream.get("codec_name", "")
                            dur = stream.get("duration")
                            if dur:
                                meta["duration_s"] = float(dur)
                        if stream.get("codec_type") == "audio":
                            meta["has_audio"]   = True
                            meta["audio_codec"] = stream.get("codec_name", "")

                    fmt_dur = data.get("format", {}).get("duration")
                    if fmt_dur:
                        meta["duration_s"] = float(fmt_dur)

                    meta.setdefault("has_audio", False)
                    if meta.get("width", 0) > 0:
                        return meta
            except Exception:
                pass

        # 2. Fallback universal usando ffmpeg -i (funciona sempre com o ffmpeg.exe local)
        try:
            cmd = [self.ffmpeg, "-i", video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20, errors="replace")
            output = result.stderr or ""
            meta: Dict[str, Any] = {"has_audio": False, "width": 0, "height": 0, "duration_s": 0.0}

            # Resolução (ex: 1920x1080)
            res_m = re.search(r",\s*(\d{3,4})x(\d{3,4})", output)
            if res_m:
                meta["width"]  = int(res_m.group(1))
                meta["height"] = int(res_m.group(2))

            # Duração (Duration: HH:MM:SS.ss)
            dur_m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", output)
            if dur_m:
                hh, mm, ss = dur_m.groups()
                meta["duration_s"] = int(hh) * 3600 + int(mm) * 60 + float(ss)

            # Presença de áudio
            if re.search(r"Stream #.*?: Audio:", output):
                meta["has_audio"] = True

            return meta
        except Exception as e:
            return {"error": str(e), "has_audio": False, "width": 0, "height": 0, "duration_s": 0.0}

    def _get_duration(self, meta: Dict) -> float:
        return float(meta.get("duration_s", 0))

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers internos
    # ─────────────────────────────────────────────────────────────────────────

    def _add(self, level: str, check: str, message: str):
        entry = {"level": level, "check": check, "message": message}
        if level == self.CRITICAL:
            self.errors.append(entry)
        elif level == self.WARNING:
            self.warnings.append(entry)
        else:
            self.infos.append(entry)

    def _build_report(self, video_path: str, expected_dur: float) -> Dict:
        passed = len(self.errors) == 0
        return {
            "timestamp":        datetime.now().isoformat(),
            "video_path":       str(video_path),
            "expected_duration": expected_dur,
            "status":           "APROVADO" if passed else "REPROVADO",
            "critical_count":   len(self.errors),
            "warning_count":    len(self.warnings),
            "checks": {
                "critical": self.errors,
                "warnings": self.warnings,
                "info":     self.infos,
            },
        }
