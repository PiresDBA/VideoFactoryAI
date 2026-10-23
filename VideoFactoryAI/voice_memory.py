"""
VoiceMemory — Persistência de configurações de voz para VideoFactoryAI
======================================================================
Salva e recupera automaticamente:
  - voz escolhida (ex: pt-BR-AntonioNeural)
  - velocidade (rate)
  - pitch
  - engine utilizada (edge-tts, f5-tts, openai)

Arquivo: memory/preferences.json  (seção "voice")
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional


class VoiceMemory:
    """Gerencia persistência de preferências de voz."""

    DEFAULTS = {
        "voice":  "pt-BR-AntonioNeural",
        "rate":   "+0%",
        "pitch":  "+0Hz",
        "engine": "edge-tts",
    }

    def __init__(self, memory_dir: Path):
        self.memory_dir  = Path(memory_dir)
        self.prefs_path  = self.memory_dir / "preferences.json"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────────

    def load(self) -> Dict[str, str]:
        """
        Carrega preferências de voz salvas.
        Retorna defaults se não houver histórico.
        """
        prefs = self._load_prefs()
        voice_cfg = prefs.get("voice_settings", {})
        result = dict(self.DEFAULTS)
        result.update({k: v for k, v in voice_cfg.items() if v})
        return result

    def save(self, voice: str, rate: str, pitch: str, engine: str):
        """Persiste configurações de voz após execução."""
        prefs = self._load_prefs()
        prefs["voice_settings"] = {
            "voice":       voice,
            "rate":        rate,
            "pitch":       pitch,
            "engine":      engine,
            "saved_at":    datetime.now().isoformat(),
        }
        # Também atualiza campo legado preferred_voice para compatibilidade
        prefs["preferred_voice"] = voice
        self._save_prefs(prefs)

    def apply_to_cfg(self, cfg: Dict, cli_voice: Optional[str] = None,
                     cli_engine: Optional[str] = None) -> Dict:
        """
        Aplica preferências de voz ao cfg dict.
        CLI overrides têm prioridade sobre memória salva.
        Retorna cfg modificado.
        """
        saved = self.load()

        tts = cfg.setdefault("tts", {})

        # Aplica memória apenas se não há override de CLI
        if not cli_voice:
            tts.setdefault("voice", saved["voice"])
        if not cli_engine:
            tts.setdefault("engine", saved["engine"])

        tts.setdefault("rate",  saved["rate"])
        tts.setdefault("pitch", saved["pitch"])

        return cfg

    def log_summary(self) -> str:
        """Retorna string legível com as preferências atuais."""
        s = self.load()
        return (f"Voz: {s['voice']} | Engine: {s['engine']} | "
                f"Rate: {s['rate']} | Pitch: {s['pitch']}")

    # ─────────────────────────────────────────────────────────────────────────
    # Internos
    # ─────────────────────────────────────────────────────────────────────────

    def _load_prefs(self) -> Dict:
        if self.prefs_path.exists():
            try:
                with open(self.prefs_path, encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
            except Exception:
                pass
        return {}

    def _save_prefs(self, prefs: Dict):
        try:
            with open(self.prefs_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [VoiceMemory] Falha ao salvar preferencias: {e}")
