"""
SeoAgent — Geração de metadados YouTube para VideoFactoryAI
===========================================================
Gera automaticamente:
  - Título otimizado
  - Descrição completa com timestamps
  - Hashtags e tags do YouTube
  - Capítulos do vídeo (baseados nas cenas)
  - Palavras-chave

Salva em: saida/youtube_metadata.json
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


class SeoAgent:
    """Gerador de metadados SEO para YouTube."""

    MAX_TITLE_LEN       = 100
    MAX_DESC_LEN        = 5000
    MAX_TAGS            = 500   # caracteres totais de tags
    MAX_HASHTAGS        = 15

    def __init__(self, saida_dir: Path):
        self.saida = Path(saida_dir)

    # ─────────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────────

    def run(
        self,
        script_text: str,
        scenes: List[Dict],
        audio_duration_s: float,
        roteiro_name: str,
        canal: Optional[str] = None,
    ) -> Dict:
        """
        Gera todos os metadados e salva youtube_metadata.json.
        Retorna o dicionário com os metadados.
        """
        print("[SeoAgent] Gerando metadados YouTube...")

        title       = self._generate_title(script_text, roteiro_name, canal)
        keywords    = self._extract_keywords(script_text)
        hashtags    = self._generate_hashtags(keywords, canal)
        tags        = self._generate_tags(keywords, canal)
        chapters    = self._generate_chapters(scenes, audio_duration_s)
        description = self._generate_description(
            script_text, chapters, hashtags, audio_duration_s, canal
        )

        metadata = {
            "generated_at":   datetime.now().isoformat(),
            "canal":          canal or "geral",
            "roteiro":        roteiro_name,
            "title":          title,
            "description":    description,
            "tags":           tags,
            "hashtags":       hashtags,
            "chapters":       chapters,
            "keywords":       keywords[:20],
            "duration_s":     audio_duration_s,
            "scene_count":    len(scenes),
            "char_counts": {
                "title":       len(title),
                "description": len(description),
                "tags_total":  len(", ".join(tags)),
            },
        }

        out_path = self.saida / "youtube_metadata.json"
        self.saida.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        print(f"  [SeoAgent] Titulo: {title[:70]}...")
        print(f"  [SeoAgent] Tags: {len(tags)} | Hashtags: {len(hashtags)} | Capitulos: {len(chapters)}")
        print(f"  [SeoAgent] Metadata salvo: {out_path}")
        return metadata

    # ─────────────────────────────────────────────────────────────────────────
    # Geração de título
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_title(self, text: str, roteiro_name: str, canal: Optional[str]) -> str:
        # Usa a primeira frase substantiva do roteiro
        sentences = re.split(r"[.!?]", text)
        candidates = [s.strip() for s in sentences if len(s.strip()) > 20]

        if candidates:
            title = candidates[0][:self.MAX_TITLE_LEN].strip()
            # Capitaliza corretamente
            if len(title) > 0:
                title = title[0].upper() + title[1:]
        else:
            title = roteiro_name.replace("_", " ").replace("-", " ").title()

        # Adiciona sufixo do canal se relevante
        canal_suffix = {
            "documentarios": "| Documentario",
            "geopolitica":   "| Analise Geopolitica",
            "historia":      "| Documentario Historico",
            "tecnologia":    "| Tecnologia",
        }
        suffix = canal_suffix.get((canal or "").lower(), "| Documentario")
        full = f"{title} {suffix}"
        return full[:self.MAX_TITLE_LEN]

    # ─────────────────────────────────────────────────────────────────────────
    # Extração de palavras-chave
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_keywords(self, text: str) -> List[str]:
        # Stop words em português
        stopwords = {
            "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
            "a", "o", "as", "os", "e", "é", "um", "uma", "uns", "umas",
            "que", "se", "por", "para", "com", "mais", "mas", "ou", "ao",
            "à", "seu", "sua", "seus", "suas", "este", "esta", "estes",
            "estas", "esse", "essa", "esses", "essas", "isso", "isto",
            "ele", "ela", "eles", "elas", "nós", "vós", "eu", "tu",
            "foram", "foi", "era", "são", "ser", "ter", "tem", "teve",
            "não", "já", "como", "quando", "onde", "pelo", "pela",
            "pelos", "pelas", "entre", "sobre", "após", "antes",
        }

        words = re.findall(r"\b[a-záéíóúâêîôûãõàèìòùç]{4,}\b", text.lower())
        freq: Dict[str, int] = {}
        for w in words:
            if w not in stopwords:
                freq[w] = freq.get(w, 0) + 1

        # Ordena por frequência
        sorted_kw = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [k for k, _ in sorted_kw[:30]]

    # ─────────────────────────────────────────────────────────────────────────
    # Hashtags
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_hashtags(self, keywords: List[str], canal: Optional[str]) -> List[str]:
        canal_tags = {
            "documentarios": ["#Documentario", "#Historia", "#Brasil"],
            "geopolitica":   ["#Geopolitica", "#RelacaoInternacional", "#Mundo"],
            "historia":      ["#Historia", "#HistoriaMundial", "#Documentario"],
            "tecnologia":    ["#Tecnologia", "#Inovacao", "#Tech", "#IA"],
        }
        base = canal_tags.get((canal or "").lower(),
                               ["#Documentario", "#Brasil", "#Informacao"])

        # Adiciona top keywords como hashtags
        kw_tags = [f"#{k.capitalize()}" for k in keywords[:8]
                   if len(k) > 4 and k.isalpha()]
        all_tags = base + kw_tags
        # Remove duplicatas, mantém ordem
        seen = set()
        unique = []
        for t in all_tags:
            if t.lower() not in seen:
                seen.add(t.lower())
                unique.append(t)
        return unique[:self.MAX_HASHTAGS]

    # ─────────────────────────────────────────────────────────────────────────
    # Tags YouTube
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_tags(self, keywords: List[str], canal: Optional[str]) -> List[str]:
        canal_base_tags = {
            "documentarios": ["documentario", "brasil", "historia", "educacao"],
            "geopolitica":   ["geopolitica", "relacoes internacionais", "politica",
                               "analise", "mundo"],
            "historia":      ["historia", "documentario historico", "passado",
                               "educacao", "fatos historicos"],
            "tecnologia":    ["tecnologia", "inovacao", "inteligencia artificial",
                               "ciencia", "futuro", "tech"],
        }
        base = canal_base_tags.get((canal or "").lower(),
                                    ["documentario", "informacao", "brasil"])
        all_tags = base + keywords[:15]
        # Limita por caracteres totais
        result = []
        total_chars = 0
        for t in all_tags:
            if total_chars + len(t) + 2 <= self.MAX_TAGS:
                result.append(t)
                total_chars += len(t) + 2
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Capítulos
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_chapters(self, scenes: List[Dict], total_dur: float) -> List[Dict]:
        """Gera capítulos do YouTube baseados nas cenas com timestamps."""
        if not scenes or total_dur <= 0:
            return []

        chapters = []
        current_time = 0.0
        dur_per_scene = total_dur / len(scenes)

        # Agrupa a cada ~3 cenas para não criar capítulos demais
        group_size = max(1, len(scenes) // 10)

        for i in range(0, len(scenes), group_size):
            group = scenes[i:i + group_size]
            # Texto representativo do grupo
            first_scene = group[0]
            label = first_scene.get("descricao", "") or first_scene.get("texto", "")
            label = label[:60].strip()
            if not label:
                label = f"Capitulo {len(chapters) + 1}"

            ts_s = int(current_time)
            mm, ss = divmod(ts_s, 60)
            chapters.append({
                "index":     len(chapters) + 1,
                "timestamp": f"{mm:02d}:{ss:02d}",
                "seconds":   ts_s,
                "label":     label,
            })
            current_time += dur_per_scene * len(group)

        return chapters

    # ─────────────────────────────────────────────────────────────────────────
    # Descrição
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_description(
        self,
        text: str,
        chapters: List[Dict],
        hashtags: List[str],
        duration_s: float,
        canal: Optional[str],
    ) -> str:
        dur_min = int(duration_s // 60)
        dur_sec = int(duration_s % 60)

        # Primeiro parágrafo: resumo do roteiro (primeiras ~300 chars)
        sentences = re.split(r"[.!?]", text)
        intro_sentences = []
        total = 0
        for s in sentences:
            s = s.strip()
            if s and total + len(s) < 350:
                intro_sentences.append(s)
                total += len(s)
            if total >= 250:
                break
        intro = ". ".join(intro_sentences) + "."

        # Capítulos formatados
        chap_lines = ""
        if chapters:
            chap_lines = "\n\n📌 CAPITULOS:\n"
            for c in chapters:
                chap_lines += f"{c['timestamp']} — {c['label']}\n"

        # Rodapé
        canal_name = (canal or "documentarios").capitalize()
        footer = (
            f"\n\n{'─'*40}\n"
            f"Duracao: {dur_min}min {dur_sec}s\n"
            f"Produzido com VideoFactoryAI — Pipeline automatico de documentarios\n"
            f"Canal: {canal_name}\n"
            f"{'─'*40}\n\n"
        )

        # Hashtags no final
        hashtag_line = " ".join(hashtags)

        full = intro + chap_lines + footer + hashtag_line
        return full[:self.MAX_DESC_LEN]
