"""
DirectorAgent — Orchestrator of the VideoFactoryAI Multi-Agent Pipeline.

Responsabilities:
  1. Load and validate the script (roteiro)
  2. Run each specialized agent in sequence
  3. Manage a checkpoint file for resumable runs
  4. Produce the final execution summary
"""
import json
import time
from pathlib import Path
from typing import Optional, List, Type

from videofactory.core.base_agent import BaseAgent
from videofactory.core.context import VideoFactoryContext
from videofactory.config import VideoFactoryConfig, DEFAULT_CONFIG

class DirectorAgent(BaseAgent):
    """Master orchestrator that runs all downstream agents in order."""

    CHECKPOINT_FILE = "ckpts/pipeline_state.json"

    def __init__(
        self,
        config: Optional[VideoFactoryConfig] = None,
        resume_from_checkpoint: bool = False
    ):
        super().__init__("DirectorAgent", config)
        self.resume = resume_from_checkpoint
        self._agents: List[BaseAgent] = []

    def _build_pipeline(self) -> List[BaseAgent]:
        """Lazy-import agents to keep startup fast."""
        from videofactory.agents.research_agent import ResearchAgent
        from videofactory.agents.storyboard_agent import StoryboardAgent
        from videofactory.agents.narrator_agent import NarratorAgent
        from videofactory.agents.subtitle_agent import SubtitleAgent
        from videofactory.agents.media_agent import MediaAgent
        from videofactory.agents.video_editor_agent import VideoEditorAgent
        from videofactory.agents.quality_agent import QualityAgent

        return [
            ResearchAgent(self.config),
            StoryboardAgent(self.config),
            NarratorAgent(self.config),
            SubtitleAgent(self.config),
            MediaAgent(self.config),
            VideoEditorAgent(self.config),
            QualityAgent(self.config),
        ]

    def execute(self, context: VideoFactoryContext) -> VideoFactoryContext:
        # ── 1. Validate Script Input ─────────────────────────────────────────
        if not context.script_text and not context.script_path:
            raise ValueError("DirectorAgent: nenhum roteiro fornecido. Defina script_text ou script_path.")

        if not context.script_text and context.script_path:
            script_file = Path(context.script_path)
            if not script_file.exists():
                raise FileNotFoundError(f"Roteiro não encontrado: {script_file}")
            context.script_text = script_file.read_text(encoding="utf-8").strip()
            self.log(f"Roteiro carregado de '{script_file.name}' ({len(context.script_text)} caracteres)")

        if not context.script_text:
            raise ValueError("DirectorAgent: roteiro está vazio.")

        # ── 2. Ensure Directories ─────────────────────────────────────────────
        self.config.ensure_directories()
        (self.config.root_dir / "ckpts").mkdir(exist_ok=True)

        # ── 3. Optionally Load Checkpoint ────────────────────────────────────
        checkpoint_path = str(self.config.root_dir / self.CHECKPOINT_FILE)
        if self.resume and Path(checkpoint_path).exists():
            self.log("Retomando estado salvo do checkpoint...")
            context = VideoFactoryContext.load_checkpoint(checkpoint_path)

        # ── 4. Run Pipeline ──────────────────────────────────────────────────
        pipeline = self._build_pipeline()
        total = len(pipeline)
        pipeline_start = time.time()

        print(f"\n{'='*60}")
        print(f"  VideoFactoryAI -- Pipeline de {total} Agentes Iniciado")
        print(f"  Titulo: {context.title}")
        print(f"{'='*60}")

        for step, agent in enumerate(pipeline, 1):
            print(f"\n[Passo {step}/{total}]", end="")
            context = agent.run(context)
            context.save_checkpoint(checkpoint_path)

        # ── 5. Final Summary ─────────────────────────────────────────────────
        total_time = time.time() - pipeline_start
        minutes, seconds = divmod(int(total_time), 60)

        print(f"\n{'='*60}")
        print(f"  [OK] Pipeline concluido em {minutes}m {seconds}s")
        print(f"  Video final: {context.output_video_path}")
        print(f"  Thumbnail  : {context.output_thumbnail_path}")
        print(f"{'='*60}\n")

        context.log_event(
            "DirectorAgent",
            f"Pipeline completo em {minutes}m {seconds}s",
            status="COMPLETE",
            data={
                "output_video": context.output_video_path,
                "thumbnail": context.output_thumbnail_path,
                "total_scenes": len(context.scenes),
            }
        )
        return context
