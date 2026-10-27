"""Ollama vision search over a user-provided local image library."""

import base64
import io
import json
import math
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image


class LocalMediaAgent:
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    STOP_WORDS = {
        "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
        "e", "em", "entre", "era", "essa", "esse", "esta", "este", "foi", "há",
        "na", "nas", "no", "nos", "o", "os", "ou", "para", "pela", "pelo",
        "por", "que", "se", "sem", "sua", "suas", "seu", "seus", "um", "uma",
        "umas", "uns",
    }

    def __init__(
        self,
        folder: Path,
        threshold: float = 0.80,
        model: str = "llava-phi3",
        base_url: str = "http://127.0.0.1:11434",
        candidate_count: int = 4,
        timeout: float = 180,
    ):
        self.folder = Path(folder)
        self.threshold = float(threshold)
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("local similarity threshold must be between 0 and 1")

        self.model = str(model).strip()
        if not self.model:
            raise ValueError("local Ollama model name cannot be empty")
        normalized_url = str(base_url).strip()
        parsed_url = urlparse(normalized_url)
        if parsed_url.scheme != "http" or parsed_url.hostname not in {
            "localhost", "127.0.0.1", "::1",
        } or parsed_url.username or parsed_url.password or parsed_url.query or parsed_url.fragment:
            raise ValueError("local Ollama URL must point to localhost over HTTP")
        if parsed_url.path not in {"", "/"}:
            raise ValueError("local Ollama URL must be a server base URL without a path")
        self.base_url = normalized_url.rstrip("/")

        self.candidate_count = int(candidate_count)
        if self.candidate_count < 1:
            raise ValueError("local candidate count must be at least 1")
        self.timeout = float(timeout)
        if self.timeout <= 0:
            raise ValueError("local Ollama timeout must be greater than 0")

        self.index = [
            {
                "path": str(path.resolve()),
                "title": self._title(path),
                "tokens": self._tokens(self._title(path)),
            }
            for path in self._image_paths()
        ]

    def _image_paths(self):
        if not self.folder.is_dir():
            return []
        return sorted(
            path for path in self.folder.rglob("*")
            if path.is_file() and path.suffix.lower() in self.IMAGE_EXTENSIONS
        )

    @staticmethod
    def _title(path: Path) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", path.stem)).strip()

    @classmethod
    def _tokens(cls, text: str):
        normalized = unicodedata.normalize("NFKD", text.lower())
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        return {
            token for token in re.findall(r"[a-z0-9]+", normalized)
            if len(token) > 1 and token not in cls.STOP_WORDS
        }

    def _rank_candidates(self, text: str, exclude_paths=None):
        query_tokens = self._tokens(text)
        excluded = {str(Path(path).resolve()) for path in (exclude_paths or ())}
        available = [item for item in self.index if item["path"] not in excluded]
        if not available:
            return []

        document_frequency = {}
        for item in available:
            for token in item["tokens"]:
                document_frequency[token] = document_frequency.get(token, 0) + 1

        total_documents = len(available)

        def score(item):
            overlap = item["tokens"] & query_tokens
            return sum(
                math.log1p(total_documents / document_frequency[token])
                for token in overlap
            )

        return sorted(
            available,
            key=lambda item: (-score(item), item["title"].casefold(), item["path"]),
        )[:self.candidate_count]

    @staticmethod
    def _encode_image(path: Path) -> str:
        try:
            with Image.open(path) as image:
                image.thumbnail((768, 768), Image.Resampling.LANCZOS)
                if image.mode != "RGB":
                    image = image.convert("RGB")
                output = io.BytesIO()
                image.save(output, format="JPEG", quality=82, optimize=True)
        except (OSError, ValueError) as exc:
            raise ValueError(f"could not read local image {path}: {exc}") from exc
        return base64.b64encode(output.getvalue()).decode("ascii")

    @staticmethod
    def _parse_result(response_data, candidate_count: int):
        if not isinstance(response_data, dict):
            raise RuntimeError("Ollama returned an invalid response object")
        response_text = response_data.get("response")
        try:
            result = response_text if isinstance(response_text, dict) else json.loads(response_text)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Ollama returned an invalid JSON image assessment") from exc
        if not isinstance(result, dict):
            raise RuntimeError("Ollama image assessment must be a JSON object")

        selected = result.get("selected")
        confidence = result.get("confidence")
        if isinstance(selected, str):
            selected_text = selected.strip().upper()
            if selected_text.isdigit():
                selected = int(selected_text)
            elif len(selected_text) == 1 and "A" <= selected_text <= "Z":
                selected = ord(selected_text) - ord("A") + 1
        if isinstance(selected, bool) or not isinstance(selected, int):
            raise RuntimeError("Ollama image assessment has no valid selected image index")
        if not 1 <= selected <= candidate_count:
            raise RuntimeError("Ollama selected an image outside the candidate list")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise RuntimeError("Ollama image assessment has no numeric confidence")
        confidence = float(confidence)
        if 0.0 <= confidence <= 10.0:
            confidence /= 10.0
        elif 10.0 < confidence <= 100.0:
            confidence /= 100.0
        if not 0.0 <= confidence <= 1.0:
            raise RuntimeError("Ollama image confidence must be between 0 and 100")
        return selected - 1, confidence

    def find_best(self, text: str, exclude_paths=None):
        if not self.index or not str(text or "").strip():
            return None

        candidates = self._rank_candidates(text, exclude_paths=exclude_paths)
        images = []
        valid_candidates = []
        for candidate in candidates:
            try:
                encoded = self._encode_image(Path(candidate["path"]))
            except ValueError as exc:
                print(f"  [LOCAL] Candidata ignorada: {exc}")
                continue
            valid_candidates.append(candidate)
            images.append(encoded)

        if not images:
            return None

        candidate_titles = "\n".join(
            f"{index}. {candidate['title']}"
            for index, candidate in enumerate(valid_candidates, start=1)
        )
        response_schema = {
            "type": "object",
            "properties": {
                "selected": {
                    "type": "integer",
                    "enum": list(range(1, len(valid_candidates) + 1)),
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 10,
                },
            },
            "required": ["selected", "confidence"],
            "additionalProperties": False,
        }
        prompt = (
            "Escolha a imagem visualmente mais adequada à cena entre as imagens "
            "anexadas, na mesma ordem dos títulos. Não escolha apenas por palavras "
            "parecidas. Retorne somente o JSON exigido: selected é o índice "
            "começando em 1; confidence é uma nota de 0 a 10. Use nota abaixo de "
            "8 se nenhuma imagem for adequada.\n"
            f"Cena: {str(text).strip()[:800]}\n"
            f"Títulos das candidatas:\n{candidate_titles}"
        )
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": images,
                    "format": response_schema,
                    "stream": False,
                    "options": {
                        "temperature": 0,
                        "num_predict": 64,
                        "repeat_penalty": 1.1,
                    },
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            response_data = response.json()
        except requests.RequestException as exc:
            response_text = getattr(exc.response, "text", "") if exc.response else ""
            if response_text:
                response_text = f": {response_text[:500]}"
            raise RuntimeError(
                f"Falha ao consultar Ollama local em {self.base_url}: {exc}{response_text}"
            ) from exc
        except ValueError as exc:
            raise RuntimeError("Ollama returned an invalid HTTP response") from exc

        selected_index, confidence = self._parse_result(
            response_data,
            candidate_count=len(valid_candidates),
        )
        selected = valid_candidates[selected_index]
        return {
            "path": selected["path"],
            "title": selected["title"],
            "score": confidence,
            "accepted": confidence >= self.threshold,
        }
