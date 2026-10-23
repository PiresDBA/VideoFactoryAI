"""
NarratorAgent — Text-to-Speech Audio Generator.

Responsabilities:
  • Generate narration audio from the full script text
  • Support Edge-TTS (default, zero cost), F5-TTS (voice clone), and OpenAI TTS
  • Skip generation if a valid audio file already exists (cache)
  • Store audio_path and estimated audio_duration on context
"""
import os
from pathlib import Path
from videofactory.core.base_agent import BaseAgent
from videofactory.core.context import VideoFactoryContext
from videofactory.tools.tts_tool import generate_narration_audio
from videofactory.tools.ffmpeg_tool import get_media_duration

class NarratorAgent(BaseAgent):
    """Converts the script text into a narration MP3 using TTS."""

    def execute(self, context: VideoFactoryContext) -> VideoFactoryContext:
        audio_path = str(self.config.root_dir / "narracao.mp3")

        # ── 1. Use existing audio if cache hit (file > 50 KB) ─────────────────
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 50_000:
            dur = get_media_duration(audio_path, self.config.ffmpeg_path)
            self.log(f"Narração já existente detectada ({dur:.2f}s). Pulando geração.")
            context.audio_path = audio_path
            context.audio_duration = dur
            return context

        # ── 2. Generate narration ─────────────────────────────────────────────
        success = generate_narration_audio(
            text=context.script_text,
            output_path=audio_path,
            engine=self.config.tts_engine,
            voice=self.config.tts_voice,
            rate=self.config.tts_rate,
            pitch=self.config.tts_pitch,
            api_key=self.config.openai_api_key,
        )

        if not success:
            raise RuntimeError("NarratorAgent: falha ao gerar áudio de narração.")

        dur = get_media_duration(audio_path, self.config.ffmpeg_path)
        self.log(f"Narração gerada: '{Path(audio_path).name}' ({dur:.2f}s)")

        context.audio_path = audio_path
        context.audio_duration = dur
        return context
