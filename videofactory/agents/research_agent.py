"""
ResearchAgent — Script Analyst & Title / Metadata Extractor.

Responsabilities:
  • Parse the raw script text into paragraphs / semantic sections
  • Extract or generate the documentary title
  • Identify the language, tone and key entities (persons, places, events)
  • Write enriched metadata to the context for use by downstream agents
"""
import re
from typing import List, Dict, Any
from videofactory.core.base_agent import BaseAgent
from videofactory.core.context import VideoFactoryContext

# ── Simple keyword-based entity detection (no external API required) ──────────
HISTORICAL_ENTITY_PATTERNS = [
    r"\b(Mossadegh|Shah|Pahlavi|Khomeini|Khamenei)\b",
    r"\b(1953|1979|2015|2018)\b",
    r"\b(embargo|sanção|golpe|revolução|reféns|crise)\b",
    r"\b(JCPOA|IAEA|CIA|MI6|OPEP|OTAN)\b",
]

def _detect_historical_entities(text: str) -> List[str]:
    found = []
    for pattern in HISTORICAL_ENTITY_PATTERNS:
        for m in re.findall(pattern, text, flags=re.IGNORECASE):
            if m not in found:
                found.append(m)
    return found


def _split_into_paragraphs(text: str) -> List[str]:
    """Split script on blank lines or sentence groups of ~3 sentences."""
    raw_paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(raw_paragraphs) >= 3:
        return raw_paragraphs

    # Fallback: split on sentence boundaries in groups of ~3
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks, group = [], []
    for s in sentences:
        group.append(s)
        if len(group) >= 3:
            chunks.append(" ".join(group))
            group = []
    if group:
        chunks.append(" ".join(group))
    return chunks


def _generate_title_from_script(text: str) -> str:
    """Heuristically extract a title from the first question or bold statement."""
    # Look for first sentence containing 'Por que', 'Como', 'O que', 'Quem'
    m = re.search(r'(Por que|Como|O que|Quem)[^.!?]{10,80}[.!?]', text, re.IGNORECASE)
    if m:
        candidate = m.group(0).strip().rstrip('.!?')
        if len(candidate) <= 80:
            return candidate

    # Fallback: use first sentence (truncated at 80 chars)
    first_sentence = re.split(r'[.!?]', text)[0].strip()
    if first_sentence:
        return first_sentence[:80]

    return "Documentário Sem Título"


class ResearchAgent(BaseAgent):
    """Analyzes the script and enriches context with metadata."""

    def execute(self, context: VideoFactoryContext) -> VideoFactoryContext:
        text = context.script_text

        # ── 1. Title ──────────────────────────────────────────────────────────
        if context.title in ("Documentário Sem Título", ""):
            context.title = _generate_title_from_script(text)
        self.log(f"Título detectado: '{context.title}'")

        # ── 2. Paragraphs / Sections ─────────────────────────────────────────
        paragraphs = _split_into_paragraphs(text)
        self.log(f"{len(paragraphs)} seção(ões) semântica(s) identificada(s) no roteiro")

        # ── 3. Entity Detection ───────────────────────────────────────────────
        entities = _detect_historical_entities(text)
        if entities:
            self.log(f"Entidades históricas detectadas: {', '.join(entities[:10])}")

        # ── 4. Script Statistics ──────────────────────────────────────────────
        word_count = len(text.split())
        char_count  = len(text)
        est_duration_min = round(word_count / 140, 1)  # ~140 wpm for PT-BR narration
        self.log(f"Roteiro: {word_count} palavras / {char_count} chars / ~{est_duration_min} min estimados")

        # ── 5. Store Research Data in Context ─────────────────────────────────
        context.log_event(
            "ResearchAgent",
            "Análise do roteiro concluída",
            data={
                "title": context.title,
                "word_count": word_count,
                "paragraphs": len(paragraphs),
                "entities": entities,
                "estimated_duration_min": est_duration_min,
            }
        )
        return context
