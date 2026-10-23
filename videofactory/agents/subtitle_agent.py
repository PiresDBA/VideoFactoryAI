"""
SubtitleAgent — Whisper Transcription & Timeline Synchronizer.

Responsabilities:
  • Run OpenAI Whisper on the generated narration audio
  • Parse and store subtitle_blocks on context
  • Update scene start/end/duration timestamps from real audio timing
  • Re-trigger StoryboardAgent if blocks are available (second pass)
"""
import os
import re
from pathlib import Path
from typing import List, Dict, Any
from videofactory.core.base_agent import BaseAgent
from videofactory.core.context import VideoFactoryContext
from videofactory.tools.whisper_tool import transcribe_audio_to_srt, parse_existing_srt

class SubtitleAgent(BaseAgent):
    """Generates accurate SRT subtitles via Whisper and re-syncs scene timeline."""

    def execute(self, context: VideoFactoryContext) -> VideoFactoryContext:
        if not context.audio_path or not os.path.exists(context.audio_path):
            raise FileNotFoundError("SubtitleAgent: áudio de narração não encontrado.")

        srt_path = str(self.config.root_dir / "narracao.srt")

        # ── 1. Reuse existing SRT if cache hit ────────────────────────────────
        if os.path.exists(srt_path) and os.path.getsize(srt_path) > 500:
            self.log("SRT existente encontrado. Fazendo parse sem re-transcrever...")
            blocks = parse_existing_srt(srt_path)
        else:
            # ── 2. Run Whisper ────────────────────────────────────────────────
            blocks = transcribe_audio_to_srt(
                audio_path=context.audio_path,
                output_srt_path=srt_path,
                model_name=self.config.whisper_model,
                device=self.config.whisper_device,
            )

        if not blocks:
            raise RuntimeError("SubtitleAgent: Whisper não gerou blocos de legenda.")

        context.srt_path = srt_path
        context.subtitle_blocks = blocks
        self.log(f"{len(blocks)} blocos de legenda sincronizados.")

        # ── 3. Re-sync scene timelines from real SRT if storyboard exists ─────
        if context.scenes:
            context.scenes = _resync_scenes_to_srt(
                context.scenes,
                blocks,
                context.audio_duration or 0.0
            )
            self.log("Timelines das cenas ressincronizadas com Whisper.")

        return context


def _resync_scenes_to_srt(
    scenes: List[Dict[str, Any]],
    blocks: List[Dict[str, Any]],
    total_duration: float
) -> List[Dict[str, Any]]:
    """
    Distribute SRT blocks across scenes proportionally, snapping to sentence
    boundaries, ensuring gapless timelines and exact total audio coverage.
    """
    if not scenes or not blocks:
        return scenes

    blocks_per_scene = max(1, len(blocks) // len(scenes))
    num_scenes = len(scenes)
    cursor = 0
    updated = []

    for i, scene in enumerate(scenes):
        is_last = (i == num_scenes - 1)
        end_block_idx = min(cursor + blocks_per_scene, len(blocks) - 1)

        # Find sentence boundary (period, ?, !) for cleaner cuts
        if not is_last:
            lookahead = min(end_block_idx + 3, len(blocks) - 1)
            for j in range(end_block_idx, lookahead + 1):
                if re.search(r'[.!?]$', blocks[j]["text"].strip()):
                    end_block_idx = j
                    break

        if is_last:
            end_block_idx = len(blocks) - 1

        start_t = blocks[cursor]["start"]
        end_t = blocks[end_block_idx]["end"] if not is_last else (total_duration or blocks[-1]["end"])

        updated.append({
            **scene,
            "start": round(start_t, 3),
            "end": round(end_t, 3),
            "duration": round(max(end_t - start_t, 1.0), 3),
        })
        cursor = end_block_idx + 1
        if cursor >= len(blocks):
            cursor = len(blocks) - 1

    return updated
