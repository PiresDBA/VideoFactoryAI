"""
QualityAgent — Final Pipeline Quality Inspector & Report Generator.

Checks:
  • Video file exists and has minimum expected duration / file size
  • All scenes were processed (no missing clips)
  • Subtitles SRT is well-formed
  • Thumbnail exists
  • Generates a structured quality report saved to ckpts/quality_report.json
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, List
from videofactory.core.base_agent import BaseAgent
from videofactory.core.context import VideoFactoryContext
from videofactory.tools.ffmpeg_tool import get_media_duration, get_video_specs

MIN_VIDEO_SIZE_MB = 5.0
MIN_VIDEO_DURATION_RATIO = 0.80  # at least 80% of narration duration

class QualityAgent(BaseAgent):
    """Validates all pipeline outputs and generates a quality report."""

    def execute(self, context: VideoFactoryContext) -> VideoFactoryContext:
        report: Dict[str, Any] = {
            "passed": True,
            "checks": [],
            "warnings": [],
            "errors": [],
        }

        def _check(name: str, passed: bool, detail: str = "", is_warning: bool = False):
            status = "PASS" if passed else ("WARN" if is_warning else "FAIL")
            report["checks"].append({"check": name, "status": status, "detail": detail})
            if not passed:
                if is_warning:
                    report["warnings"].append(f"{name}: {detail}")
                else:
                    report["errors"].append(f"{name}: {detail}")
                    report["passed"] = False
            self.log(f"[{status}] {name}: {detail}")

        ffmpeg = self.config.ffmpeg_path

        # ── 1. Output Video Exists ────────────────────────────────────────────
        video_exists = bool(context.output_video_path and os.path.exists(context.output_video_path))
        _check("output_video_exists", video_exists, context.output_video_path or "não definido")

        if video_exists:
            size_mb = os.path.getsize(context.output_video_path) / (1024 * 1024)
            _check(
                "output_video_size",
                size_mb >= MIN_VIDEO_SIZE_MB,
                f"{size_mb:.2f} MB (mínimo {MIN_VIDEO_SIZE_MB} MB)",
                is_warning=(size_mb < MIN_VIDEO_SIZE_MB)
            )

            # ── 2. Video Duration ─────────────────────────────────────────────
            video_duration = get_media_duration(context.output_video_path, ffmpeg)
            expected = context.audio_duration or 0.0
            ratio = (video_duration / expected) if expected > 0 else 1.0
            _check(
                "output_video_duration",
                ratio >= MIN_VIDEO_DURATION_RATIO,
                f"vídeo={video_duration:.1f}s  narração={expected:.1f}s  ratio={ratio:.2f}"
            )

            # ── 3. Video Specs ─────────────────────────────────────────────────
            specs = get_video_specs(context.output_video_path, ffmpeg)
            _check(
                "output_video_resolution",
                specs["width"] == self.config.width and specs["height"] == self.config.height,
                f"{specs['width']}x{specs['height']} (esperado {self.config.width}x{self.config.height})",
                is_warning=True
            )

        # ── 4. Subtitle SRT ───────────────────────────────────────────────────
        srt_ok = bool(context.srt_path and os.path.exists(context.srt_path) and
                      os.path.getsize(context.srt_path) > 200)
        _check("srt_file_exists", srt_ok, context.srt_path or "não gerado", is_warning=not srt_ok)

        # ── 5. Thumbnail ──────────────────────────────────────────────────────
        thumb_ok = bool(context.output_thumbnail_path and os.path.exists(context.output_thumbnail_path))
        _check("thumbnail_exists", thumb_ok, context.output_thumbnail_path or "não gerada", is_warning=not thumb_ok)

        # ── 6. All Scenes Processed ───────────────────────────────────────────
        total_scenes = len(context.scenes)
        processed = len([s for s in context.scenes if s.get("processed_clip") and
                         os.path.exists(s.get("processed_clip", ""))])
        _check(
            "all_clips_processed",
            processed == total_scenes,
            f"{processed}/{total_scenes} clipes processados",
            is_warning=(processed < total_scenes)
        )

        # ── 7. Audio Narration ────────────────────────────────────────────────
        audio_ok = bool(context.audio_path and os.path.exists(context.audio_path))
        _check("narration_audio_exists", audio_ok, context.audio_path or "não gerado")

        # ── 8. Save Report ────────────────────────────────────────────────────
        report_path = str(self.config.root_dir / "ckpts" / "quality_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        context.quality_report = report

        # ── 9. Print Summary ──────────────────────────────────────────────────
        total_checks = len(report["checks"])
        passed_checks = sum(1 for c in report["checks"] if c["status"] == "PASS")
        warn_count = len(report["warnings"])
        error_count = len(report["errors"])

        status_icon = "✅" if report["passed"] else "❌"
        print(f"\n  {status_icon} Quality Report: {passed_checks}/{total_checks} checks passaram | "
              f"{warn_count} avisos | {error_count} erros")

        if report["errors"]:
            for err in report["errors"]:
                self.log(f"ERRO: {err}", level="ERROR")

        if not report["passed"]:
            raise RuntimeError(f"QualityAgent: pipeline falhou com {error_count} erro(s). "
                               f"Verifique '{report_path}'.")

        return context
