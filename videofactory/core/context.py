"""
Pipeline Context Data Transfer Object (DTO) for VideoFactoryAI.
Holds the state, assets, and progress across all agents.
"""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional

@dataclass
class SceneData:
    id: int
    text: str
    tipo: str  # 'video' or 'image'
    query: str
    query_en: str
    descricao: str
    needs_ai_generation: bool = False
    ai_prompt: str = ""
    start: float = 0.0
    end: float = 0.0
    duration: float = 0.0
    source_asset: str = ""
    processed_clip: str = ""

@dataclass
class VideoFactoryContext:
    script_path: str = ""
    script_text: str = ""
    title: str = "Documentário Sem Título"
    
    # Storyboard & Scenes
    scenes: List[Dict[str, Any]] = field(default_factory=list)
    
    # Narration & Whisper
    audio_path: str = ""
    audio_duration: float = 0.0
    srt_path: str = ""
    subtitle_blocks: List[Dict[str, Any]] = field(default_factory=list)
    
    # Sourced Media & Processed Clips
    asset_map: Dict[int, str] = field(default_factory=dict)
    processed_clips: List[str] = field(default_factory=list)
    
    # Outputs
    manifest_path: str = ""
    output_video_path: str = ""
    output_thumbnail_path: str = ""
    
    # Quality & Execution Logs
    quality_report: Dict[str, Any] = field(default_factory=dict)
    execution_log: List[Dict[str, Any]] = field(default_factory=list)
    
    def log_event(self, agent_name: str, message: str, status: str = "INFO", data: Optional[Dict[str, Any]] = None):
        """Append an event to the context log."""
        entry = {
            "agent": agent_name,
            "status": status,
            "message": message,
            "data": data or {}
        }
        self.execution_log.append(entry)

    def save_checkpoint(self, checkpoint_file: str) -> None:
        """Serialize current pipeline state to disk."""
        data = asdict(self)
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load_checkpoint(cls, checkpoint_file: str) -> "VideoFactoryContext":
        """Deserialize context from disk."""
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)
