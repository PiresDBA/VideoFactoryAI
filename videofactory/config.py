"""
Central Configuration for VideoFactoryAI.
Configures file directories, binary paths, default voices, media engines and styling.
"""
import os
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Base Project Root Directory
ROOT_DIR = Path(__file__).resolve().parent.parent

def find_ffmpeg_binary() -> str:
    """Locate local ffmpeg.exe or fallback to system path."""
    local_ffmpeg = ROOT_DIR / "ffmpeg.exe"
    if local_ffmpeg.exists():
        return str(local_ffmpeg)
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    return str(local_ffmpeg)

@dataclass
class VideoFactoryConfig:
    # Directories
    root_dir: Path = ROOT_DIR
    videos_dir: Path = field(default_factory=lambda: ROOT_DIR / "videos")
    imagens_dir: Path = field(default_factory=lambda: ROOT_DIR / "imagens")
    temp_clips_dir: Path = field(default_factory=lambda: ROOT_DIR / "temp_clips")
    saida_dir: Path = field(default_factory=lambda: ROOT_DIR / "saida")
    voice_dir: Path = field(default_factory=lambda: ROOT_DIR / "voice")
    
    # Binaries
    ffmpeg_path: str = field(default_factory=find_ffmpeg_binary)
    
    # Video Specifications
    width: int = 1920
    height: int = 1080
    fps: int = 30
    pixel_format: str = "yuv420p"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    crf: int = 20
    preset: str = "fast"
    
    # Motion & Ken Burns
    ken_burns_zoom_speed: float = 0.0008
    ken_burns_max_zoom: float = 1.25
    
    # Narration / TTS
    tts_engine: str = "edge-tts"  # 'edge-tts', 'f5-tts', 'openai'
    tts_voice: str = "pt-BR-AntonioNeural"  # 'pt-BR-AntonioNeural', 'pt-BR-FranciscaNeural', 'pt-BR-ThalitaNeural'
    tts_rate: str = "+0%"
    tts_pitch: str = "+0Hz"
    
    # Subtitles (Whisper)
    whisper_model: str = "base"  # 'tiny', 'base', 'small', 'medium'
    whisper_device: Optional[str] = None  # None -> auto-detect CUDA/CPU
    subtitle_font_size: int = 24
    subtitle_primary_color: str = "&H00FFFFFF"  # Pure White
    subtitle_outline_color: str = "&H00000000"  # Black Outline
    subtitle_outline_width: int = 2
    subtitle_shadow_depth: int = 1
    subtitle_margin_v: int = 35
    
    # Media APIs
    pixabay_api_key: str = field(
        default_factory=lambda: os.getenv("PIXABAY_API_KEY", "58184749-b92df4cd039274d2c7a6aac7a")
    )
    openai_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY")
    )
    ai_image_provider: str = "pollinations"  # 'pollinations', 'dalle3'
    
    # Scene Pacing Defaults
    min_scene_duration: float = 5.0
    target_scene_duration: float = 12.0
    max_scene_duration: float = 20.0
    
    def ensure_directories(self) -> None:
        """Create necessary working directories if they don't exist."""
        for d in [self.videos_dir, self.imagens_dir, self.temp_clips_dir, self.saida_dir, self.voice_dir]:
            d.mkdir(parents=True, exist_ok=True)

# Default Global Instance
DEFAULT_CONFIG = VideoFactoryConfig()
