"""
StoryboardAgent — Semantic Scene Planner & Timeline Builder.

Responsabilities:
  • Parse subtitle blocks (if available) or split the raw script into scenes
  • Assign each scene: tipo (video/image), query (EN), query_pt, descricao
  • Flag scenes that need AI image generation (historical / no stock source)
  • Produce the complete ordered scene list in context.scenes
"""
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
from videofactory.core.base_agent import BaseAgent
from videofactory.core.context import VideoFactoryContext

# ─── Keywords that indicate archival / historical content → prefer image ──────
HISTORICAL_KEYWORDS = [
    "1953", "1979", "golpe", "Mossadegh", "Shah", "Pahlavi", "Khomeini",
    "reféns", "embaixada", "revolucionário", "revolução islâmica", "arquivo",
    "colonial", "guerra fria", "cold war",
]

# ─── Entities that should be sourced from Wikimedia Commons ──────────────────
WIKIMEDIA_ENTITIES = {
    "mossadegh": ("Mohammad Mossadegh 1953 trial iran premier", True),
    "shah": ("Mohammad Reza Pahlavi Shah portrait historical", True),
    "pahlavi": ("Mohammad Reza Pahlavi Shah portrait historical", True),
    "khomeini": ("Ruhollah Khomeini 1979 portrait revolutionary leader", True),
    "reféns": ("Iran hostage crisis Tehran 1979 US embassy siege", True),
    "revolução islâmica": ("Islamic revolution Iran 1979 crowd Khomeini", True),
    "golpe": ("1953 Iran coup d'état Mossadegh protest Tehran", True),
}

# ─── Query templates (PT → EN mapping for stock / AI) ────────────────────────
SEMANTIC_VIDEO_QUERIES = {
    "bandeiras": "usa iran flag waving bilateral relations",
    "sanções": "economic sanctions protest inflation market",
    "manchetes": "global news broadcast television studio",
    "geopolítica": "world map geopolitics strategy globe",
    "petróleo": "oil pump jack desert oilfield pipeline",
    "casa branca": "white house washington dc politics government",
    "oriente médio": "middle east aerial desert city skyline",
    "nuclear": "nuclear research laboratory facility reactor",
    "estreito": "oil tanker cargo ship hormuz sea ocean",
    "satélite": "satellite military surveillance technology",
    "ciberataque": "cyber attack digital data hacker dark room",
    "refugiados": "refugee camp humanitarian crisis displaced people",
    "xadrez": "chess board strategy game pieces global",
    "teerã": "modern tehran iran city skyline aerial",
    "diplomacia": "diplomats meeting negotiation table conference",
    "onu": "united nations flags international diplomacy",
    "inscreva": "youtube subscribe button bell notification",
    "militares": "military troops aircraft carrier ocean naval",
    "inflação": "gas station fuel price inflation economy",
    "guerra": "military smoke explosion war destruction",
    "aliança": "middle east military alliance handshake diplomacy",
    "bolsa": "stock market financial trading graph economy",
}

CTA_QUERIES = [
    ("youtube subscribe bell button", "video"),
    ("like button social media engagement", "video"),
]


def _classify_scene(text: str) -> Tuple[str, str, str, bool]:
    """
    Returns (tipo, query_en, descricao, needs_ai).
    tipo: 'video' or 'image'
    """
    text_lower = text.lower()

    # Check for Wikimedia-matched historical entities
    for keyword, (wm_query, _) in WIKIMEDIA_ENTITIES.items():
        if keyword in text_lower:
            return "image", wm_query, f"Arquivo histórico: {keyword}", False

    # Check for general historical keywords → image with AI fallback
    for kw in HISTORICAL_KEYWORDS:
        if kw.lower() in text_lower:
            ai_prompt = (
                f"Cinematic historical documentary photograph, 1970s film grain style, "
                f"realistic lighting, related to: {text[:120]}"
            )
            return "image", "", ai_prompt, True

    # Map semantic keywords → stock video query
    for pt_key, en_query in SEMANTIC_VIDEO_QUERIES.items():
        if pt_key in text_lower:
            return "video", en_query, text[:80], False

    # Generic fallback based on paragraph position (handled in caller)
    return "video", "geopolitics world news documentary footage", text[:80], False


def _build_scenes_from_subtitle_blocks(
    blocks: List[Dict[str, Any]],
    target_duration: float = 12.0
) -> List[Dict[str, Any]]:
    """Group subtitle blocks into scenes of ~target_duration seconds."""
    if not blocks:
        return []

    scenes = []
    current_group: List[Dict[str, Any]] = []
    current_start = blocks[0]["start"]
    scene_id = 1

    for block in blocks:
        current_group.append(block)
        span = block["end"] - current_start

        # Commit scene when we reach the target or a natural sentence break
        is_sentence_end = block["text"].strip().endswith(('.', '!', '?'))
        if (span >= target_duration and is_sentence_end) or span >= target_duration * 1.5:
            combined_text = " ".join(b["text"] for b in current_group)
            tipo, query_en, descricao, needs_ai = _classify_scene(combined_text)

            scenes.append({
                "id": scene_id,
                "text": combined_text,
                "tipo": tipo,
                "query": query_en,
                "query_en": query_en,
                "descricao": descricao,
                "needs_ai_generation": needs_ai,
                "ai_prompt": descricao if needs_ai else "",
                "start": round(current_start, 3),
                "end": round(block["end"], 3),
                "duration": round(block["end"] - current_start, 3),
                "source_asset": "",
                "processed_clip": "",
                "arquivo": f"scene_{scene_id:02d}.{'mp4' if tipo == 'video' else 'jpg'}",
            })
            scene_id += 1
            current_group = []
            current_start = block["end"] if scene_id <= len(blocks) else block["end"]

    # Flush remaining group
    if current_group:
        combined_text = " ".join(b["text"] for b in current_group)
        tipo, query_en, descricao, needs_ai = _classify_scene(combined_text)
        scenes.append({
            "id": scene_id,
            "text": combined_text,
            "tipo": tipo,
            "query": query_en,
            "query_en": query_en,
            "descricao": descricao,
            "needs_ai_generation": needs_ai,
            "ai_prompt": descricao if needs_ai else "",
            "start": round(current_start, 3),
            "end": round(current_group[-1]["end"], 3),
            "duration": round(current_group[-1]["end"] - current_start, 3),
            "source_asset": "",
            "processed_clip": "",
            "arquivo": f"scene_{scene_id:02d}.{'mp4' if tipo == 'video' else 'jpg'}",
        })

    return scenes


def _build_scenes_from_script(
    script_text: str,
    target_duration: float = 12.0,
    words_per_second: float = 2.3  # ~138 wpm for PT-BR narration
) -> List[Dict[str, Any]]:
    """Build scenes directly from raw script text when no SRT is available yet."""
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', script_text.strip())

    scenes = []
    scene_id = 1
    current_sentences: List[str] = []
    current_word_count = 0

    target_words = int(target_duration * words_per_second)

    for sent in sentences:
        words = len(sent.split())
        current_sentences.append(sent)
        current_word_count += words

        if current_word_count >= target_words:
            combined_text = " ".join(current_sentences)
            est_dur = round(current_word_count / words_per_second, 2)
            tipo, query_en, descricao, needs_ai = _classify_scene(combined_text)

            scenes.append({
                "id": scene_id,
                "text": combined_text,
                "tipo": tipo,
                "query": query_en,
                "query_en": query_en,
                "descricao": descricao,
                "needs_ai_generation": needs_ai,
                "ai_prompt": descricao if needs_ai else "",
                "start": 0.0,  # Will be updated by SubtitleAgent
                "end": 0.0,
                "duration": est_dur,
                "source_asset": "",
                "processed_clip": "",
                "arquivo": f"scene_{scene_id:02d}.{'mp4' if tipo == 'video' else 'jpg'}",
            })
            scene_id += 1
            current_sentences = []
            current_word_count = 0

    # Flush remainder
    if current_sentences:
        combined_text = " ".join(current_sentences)
        est_dur = round(max(current_word_count / words_per_second, 3.0), 2)
        tipo, query_en, descricao, needs_ai = _classify_scene(combined_text)
        scenes.append({
            "id": scene_id,
            "text": combined_text,
            "tipo": tipo,
            "query": query_en,
            "query_en": query_en,
            "descricao": descricao,
            "needs_ai_generation": needs_ai,
            "ai_prompt": descricao if needs_ai else "",
            "start": 0.0,
            "end": 0.0,
            "duration": est_dur,
            "source_asset": "",
            "processed_clip": "",
            "arquivo": f"scene_{scene_id:02d}.{'mp4' if tipo == 'video' else 'jpg'}",
        })

    return scenes


class StoryboardAgent(BaseAgent):
    """Plans scenes from script text or existing Whisper subtitle blocks."""

    def execute(self, context: VideoFactoryContext) -> VideoFactoryContext:
        target_dur = self.config.target_scene_duration

        # ── 1. Use SRT blocks if available (post-NarratorAgent + SubtitleAgent) ─
        # Note: in the pipeline NarratorAgent & SubtitleAgent run first,
        # so on second-pass (resume) SRT blocks are already present.
        if context.subtitle_blocks:
            self.log(f"Construindo storyboard a partir de {len(context.subtitle_blocks)} blocos de legenda Whisper...")
            scenes = _build_scenes_from_subtitle_blocks(
                context.subtitle_blocks,
                target_duration=target_dur
            )
        else:
            # ── 2. Build from raw script (first run, before TTS is generated) ──
            self.log("Construindo storyboard a partir do texto bruto do roteiro...")
            scenes = _build_scenes_from_script(
                context.script_text,
                target_duration=target_dur
            )

        context.scenes = scenes

        # ── 3. Summary ────────────────────────────────────────────────────────
        n_video = sum(1 for s in scenes if s["tipo"] == "video")
        n_image = sum(1 for s in scenes if s["tipo"] == "image")
        n_ai = sum(1 for s in scenes if s.get("needs_ai_generation"))

        self.log(f"Storyboard: {len(scenes)} cenas | {n_video} vídeo | {n_image} imagem | {n_ai} precisam de IA")

        # ── 4. Save storyboard JSON ───────────────────────────────────────────
        storyboard_path = str(self.config.root_dir / "ckpts" / "storyboard.json")
        import json
        with open(storyboard_path, "w", encoding="utf-8") as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
        self.log(f"Storyboard salvo em '{storyboard_path}'")

        return context
