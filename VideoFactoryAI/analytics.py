"""
Analytics — Registro de execuções do VideoFactoryAI
====================================================
Após cada execução, registra em memory/project_history.json:

  - data
  - tema (nome do roteiro)
  - duracao
  - numero de cenas
  - fontes utilizadas
  - quantidade de IA gerada
  - quantidade de midia real
  - canal
  - tempo de processamento
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any


class Analytics:
    """Registro persistente de execuções do pipeline."""

    HISTORY_FILE = "project_history.json"
    MAX_ENTRIES  = 200  # histórico máximo

    def __init__(self, memory_dir: Path):
        self.memory_dir   = Path(memory_dir)
        self.history_path = self.memory_dir / self.HISTORY_FILE
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        roteiro_name: str,
        scenes: List[Dict],
        asset_map: Dict,
        audio_duration_s: float,
        elapsed_s: float,
        canal: Optional[str],
        compliance: Optional[Dict] = None,
        output_video: str = "",
    ):
        """Registra uma execução no histórico."""
        entry = self._build_entry(
            roteiro_name, scenes, asset_map, audio_duration_s,
            elapsed_s, canal, compliance, output_video
        )

        history = self._load()
        history.append(entry)

        # Mantém limite
        if len(history) > self.MAX_ENTRIES:
            history = history[-self.MAX_ENTRIES:]

        self._save(history)
        self._update_preferences(entry)
        print(f"  [Analytics] Execucao registrada: {self.history_path}")
        return entry

    def summary(self) -> Dict:
        """Retorna resumo estatístico do histórico."""
        history = self._load()
        if not history:
            return {"total_runs": 0}

        durations   = [h["duracao_s"] for h in history if h.get("duracao_s")]
        ai_counts   = [h.get("midia_ia_gerada", 0) for h in history]
        real_counts = [h.get("midia_real", 0) for h in history]

        return {
            "total_runs":          len(history),
            "avg_duration_s":      round(sum(durations) / len(durations), 1) if durations else 0,
            "total_ia_generated":  sum(ai_counts),
            "total_real_media":    sum(real_counts),
            "canais_usados":       list({h.get("canal", "geral") for h in history}),
            "last_run":            history[-1].get("data") if history else None,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Internos
    # ─────────────────────────────────────────────────────────────────────────

    def _build_entry(
        self,
        roteiro_name: str,
        scenes: List[Dict],
        asset_map: Dict,
        audio_duration_s: float,
        elapsed_s: float,
        canal: Optional[str],
        compliance: Optional[Dict],
        output_video: str,
    ) -> Dict:
        # Conta fontes e IA vs real
        source_counts: Dict[str, int] = {}
        ia_count   = 0
        real_count = 0

        if compliance:
            by_level = compliance.get("by_level", {})
            ia_count   = by_level.get("L4_ia_generated", 0)
            real_count = by_level.get("L1_video", 0) + by_level.get("L2_image", 0)
            source_counts = by_level
        else:
            # Estimativa simples se não há compliance disponível
            total = len(asset_map)
            real_count = total
            ia_count   = 0

        tipos_cenas: Dict[str, int] = {}
        for s in scenes:
            t = s.get("tipo", "unknown")
            tipos_cenas[t] = tipos_cenas.get(t, 0) + 1

        return {
            "data":             datetime.now().isoformat(),
            "tema":             roteiro_name,
            "canal":            canal or "geral",
            "duracao_s":        round(audio_duration_s, 1),
            "duracao_min":      round(audio_duration_s / 60, 2),
            "num_cenas":        len(scenes),
            "tipos_cenas":      tipos_cenas,
            "assets_total":     len(asset_map),
            "midia_real":       real_count,
            "midia_ia_gerada":  ia_count,
            "fontes":           source_counts,
            "tempo_pipeline_s": round(elapsed_s, 1),
            "tempo_pipeline_min": round(elapsed_s / 60, 2),
            "output_video":     output_video,
        }

    def _load(self) -> List[Dict]:
        if self.history_path.exists():
            try:
                with open(self.history_path, encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, list) else []
            except Exception:
                pass
        return []

    def _save(self, history: List[Dict]):
        try:
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [Analytics] Falha ao salvar historico: {e}")

    def _update_preferences(self, entry: Dict):
        """Atualiza preferences.json com estatísticas da execução."""
        prefs_path = self.memory_dir / "preferences.json"
        prefs: Dict[str, Any] = {}
        if prefs_path.exists():
            try:
                with open(prefs_path, encoding="utf-8") as f:
                    prefs = json.load(f)
            except Exception:
                pass

        prefs["run_count"]    = prefs.get("run_count", 0) + 1
        prefs["last_updated"] = datetime.now().isoformat()

        # Atualiza duração média
        prev_avg = prefs.get("avg_video_duration_s", 0)
        runs     = prefs["run_count"]
        prefs["avg_video_duration_s"] = round(
            (prev_avg * (runs - 1) + entry.get("duracao_s", 0)) / runs, 1
        )

        # Atualiza stats de mídia acumuladas
        ms = prefs.setdefault("media_stats", {
            "l1_video_hits": 0, "l2_image_hits": 0,
            "l3_ai_public_hits": 0, "l4_ai_generated": 0
        })
        by_lvl = entry.get("fontes", {})
        ms["l1_video_hits"]    += by_lvl.get("L1_video", 0)
        ms["l2_image_hits"]    += by_lvl.get("L2_image", 0)
        ms["l3_ai_public_hits"] += by_lvl.get("L3_ai_public", 0)
        ms["l4_ai_generated"]  += entry.get("midia_ia_gerada", 0)

        try:
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
