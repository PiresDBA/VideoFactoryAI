"""
AssetCache — Cache de mídia reutilizável para VideoFactoryAI
============================================================
Evita downloads duplicados ao reutilizar assets já baixados.

Estrutura do cache:
  cache/
    index.json          ← índice: {query_hash → {path, source, downloaded_at, hits}}
    assets/             ← cópias dos arquivos em cache

Política:
  - Cache key = MD5(query + tipo)
  - Validade: 30 dias (configurável)
  - Tamanho máximo: 500 arquivos (limpa os mais antigos)
"""

import os
import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict


class AssetCache:
    """Cache de assets de mídia com TTL e limite de tamanho."""

    TTL_DAYS    = 30
    MAX_ENTRIES = 500
    INDEX_FILE  = "index.json"

    def __init__(self, cache_dir: Path):
        self.cache_dir   = Path(cache_dir)
        self.assets_dir  = self.cache_dir / "assets"
        self.index_path  = self.cache_dir / self.INDEX_FILE
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self._index: Dict = self._load_index()

    # ─────────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────────

    def get(self, query: str, tipo: str) -> Optional[str]:
        """
        Retorna caminho do asset em cache ou None se não encontrado / expirado.
        """
        key = self._key(query, tipo)
        entry = self._index.get(key)
        if not entry:
            return None

        # Verifica expiração
        downloaded_at = datetime.fromisoformat(entry.get("downloaded_at", "2000-01-01"))
        if datetime.now() - downloaded_at > timedelta(days=self.TTL_DAYS):
            self._evict(key)
            return None

        cached_path = entry.get("path", "")
        if not cached_path or not Path(cached_path).exists():
            self._evict(key)
            return None

        # Registra hit
        entry["hits"] = entry.get("hits", 0) + 1
        entry["last_used"] = datetime.now().isoformat()
        self._save_index()
        return cached_path

    def put(self, query: str, tipo: str, source_path: str,
             source_name: str = "unknown") -> str:
        """
        Copia o arquivo para o cache e registra no índice.
        Retorna o caminho no cache.
        """
        key  = self._key(query, tipo)
        ext  = Path(source_path).suffix or ".jpg"
        dest = self.assets_dir / f"{key}{ext}"

        try:
            shutil.copy2(source_path, dest)
        except Exception as e:
            return source_path  # falha silenciosa, retorna original

        self._index[key] = {
            "query":         query,
            "tipo":          tipo,
            "path":          str(dest),
            "source":        source_name,
            "downloaded_at": datetime.now().isoformat(),
            "last_used":     datetime.now().isoformat(),
            "hits":          0,
        }

        # Limpa entradas antigas se exceder limite
        if len(self._index) > self.MAX_ENTRIES:
            self._evict_oldest()

        self._save_index()
        return str(dest)

    def stats(self) -> Dict:
        """Retorna estatísticas do cache."""
        total_size = sum(
            Path(e["path"]).stat().st_size
            for e in self._index.values()
            if Path(e.get("path", "")).exists()
        )
        return {
            "entries":    len(self._index),
            "total_mb":   round(total_size / (1024 * 1024), 2),
            "max_entries": self.MAX_ENTRIES,
            "ttl_days":   self.TTL_DAYS,
        }

    def clear_expired(self) -> int:
        """Remove entradas expiradas. Retorna quantidade removida."""
        expired = [
            k for k, v in self._index.items()
            if datetime.now() - datetime.fromisoformat(
                v.get("downloaded_at", "2000-01-01")) > timedelta(days=self.TTL_DAYS)
        ]
        for k in expired:
            self._evict(k)
        if expired:
            self._save_index()
        return len(expired)

    # ─────────────────────────────────────────────────────────────────────────
    # Internos
    # ─────────────────────────────────────────────────────────────────────────

    def _key(self, query: str, tipo: str) -> str:
        raw = f"{query.lower().strip()}|{tipo.lower().strip()}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def _load_index(self) -> Dict:
        if self.index_path.exists():
            try:
                with open(self.index_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_index(self):
        try:
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _evict(self, key: str):
        entry = self._index.pop(key, None)
        if entry:
            p = Path(entry.get("path", ""))
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

    def _evict_oldest(self):
        """Remove as 50 entradas com last_used mais antigo."""
        sorted_keys = sorted(
            self._index.keys(),
            key=lambda k: self._index[k].get("last_used", "2000-01-01")
        )
        for k in sorted_keys[:50]:
            self._evict(k)
