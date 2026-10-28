# -*- coding: utf-8 -*-
"""Assunto visual em inglês por cena, validado antes da busca de mídia.

Para cada cena, nesta ordem:
  1. Entrada manual (subject_en preenchido por você, com source diferente de "model")
     é usada como está.
  2. Cache: se o texto da cena não mudou (hash) e a entrada está "ok", reaproveita.
  3. Senão, pede ao modelo local (Ollama), valida a resposta e, se rejeitada, tenta de
     novo informando o motivo da rejeição.
  4. Se nada passar, a cena vira "review".

Arquivo de assuntos: <roteiro>.subjects.json, ao lado do .txt. Fica fora da pasta do
projeto, então sobrevive a "Excluir projeto" na GUI.

Regras, exemplos, palavras proibidas e glossário: subject_rules.yaml (dados, não código).
Configuração: bloco "subjects" do config.yaml.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

import yaml

MODULE_DIR = Path(__file__).resolve().parent
SIDECAR_VERSION = 1
REQUIREMENTS = ("manual", "glossary")


def _norm_plain(text: str) -> str:
    """Minúsculas, sem acentos, espaços colapsados. Usado para comparar termos."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


# ---------------------------------------------------------------------------
# Regras (subject_rules.yaml)
# ---------------------------------------------------------------------------
def load_rules(rules_file: str) -> dict[str, Any]:
    path = Path(rules_file).expanduser()
    if not path.is_absolute():
        path = MODULE_DIR / path
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo de regras não encontrado: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    required_keys = ("system_prompt", "examples", "forbidden_pt_words", "glossary", "min_words", "max_words")
    missing = [key for key in required_keys if key not in data]
    if missing:
        raise ValueError(f"{path.name} sem as chaves: {', '.join(missing)}")
    if int(data["min_words"]) > int(data["max_words"]):
        raise ValueError(f"{path.name}: min_words é maior que max_words")
    data["min_words"] = int(data["min_words"])
    data["max_words"] = int(data["max_words"])
    data["forbidden_pt_words"] = {_norm_plain(word) for word in (data["forbidden_pt_words"] or [])}
    data["glossary"] = {_norm_plain(k): str(v) for k, v in (data["glossary"] or {}).items()}
    data["examples"] = list(data["examples"] or [])
    return data


def _system_prompt(rules: dict) -> str:
    lines = [str(rules["system_prompt"]).strip(), "", "Examples:"]
    for example in rules["examples"]:
        lines.append(f"Text: {example['text']} -> {example['answer']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Arquivo de assuntos (ao lado do roteiro)
# ---------------------------------------------------------------------------
def sidecar_path(script_path) -> Path:
    script = Path(script_path)
    return script.with_name(script.stem + ".subjects.json")


def load_sidecar(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": SIDECAR_VERSION, "scenes": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), dict):
        raise ValueError(f"Arquivo de assuntos inválido (esperado objeto com 'scenes'): {path}")
    return data


def save_sidecar(path: Path, data: dict[str, Any]) -> None:
    """Escrita atômica: nunca deixa o arquivo meio gravado."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Cena
# ---------------------------------------------------------------------------
def scene_key(scene: dict) -> str:
    return str(scene.get("id", scene.get("idx", "?")))


def scene_text(scene: dict) -> str:
    return str(scene.get("texto") or scene.get("text") or "").strip()


def text_hash(text: str) -> str:
    canon = re.sub(r"\s+", " ", text.lower()).strip()
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Termos obrigatórios. Cada item é um grupo: "bulldog|dog" = basta um dos dois.
# ---------------------------------------------------------------------------
def required_from_glossary(text: str, rules: dict) -> list[str]:
    plain = f" {_norm_plain(text)} "
    groups: list[str] = []
    for pt_term, en_group in rules["glossary"].items():
        if pt_term and re.search(rf"\b{re.escape(pt_term)}\b", plain) and en_group not in groups:
            groups.append(en_group)
    return groups


def _required_for(requirement: str, entry: dict, text: str, rules: dict) -> list[str]:
    if requirement == "glossary":
        return required_from_glossary(text, rules)
    return [str(group) for group in (entry.get("required") or [])]


def _has_term_group(answer: str, group: str) -> bool:
    plain = _norm_plain(answer)
    for alternative in group.split("|"):
        alt = _norm_plain(alternative)
        if alt and re.search(rf"\b{re.escape(alt)}(s|es)?\b", plain):  # aceita plural
            return True
    return False


# ---------------------------------------------------------------------------
# Resposta do modelo
# ---------------------------------------------------------------------------
def clean_answer(raw: str) -> str:
    first = next((line.strip() for line in str(raw or "").splitlines() if line.strip()), "")
    first = first.strip().strip("\"'`“”‘’").strip()
    return re.sub(r"[.!?;:]+$", "", first).strip()


def validate_answer(answer: str, required_groups: list[str], rules: dict) -> tuple[bool, str]:
    if not answer:
        return False, "resposta vazia"
    if re.search(r"[^A-Za-z\s-]", answer):
        return False, "contém caractere fora do inglês (acento, pontuação ou símbolo)"
    words = answer.split()
    if not rules["min_words"] <= len(words) <= rules["max_words"]:
        return False, f"{len(words)} palavras (permitido de {rules['min_words']} a {rules['max_words']})"
    pt_words = [w for w in words if _norm_plain(w) in rules["forbidden_pt_words"]]
    if pt_words:
        return False, "palavra em português: " + ", ".join(pt_words)
    missing = [group for group in required_groups if not _has_term_group(answer, group)]
    if missing:
        return False, "falta termo obrigatório: " + " / ".join(missing)
    return True, ""


def _ask_ollama(system: str, user: str, scfg: dict) -> str:
    body = {
        "model": scfg["model"],
        "stream": False,
        "keep_alive": scfg.get("keep_alive", "30m"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": 0, "num_predict": int(scfg.get("max_tokens", 16))},
    }
    url = str(scfg["ollama_url"]).rstrip("/") + "/api/chat"
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=float(scfg.get("timeout_s", 60))) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str((data.get("message") or {}).get("content", ""))


def resolve_subject(text: str, required_groups: list[str], scfg: dict, rules: dict) -> tuple[str | None, str]:
    """Pede ao modelo, valida e repete com o motivo da rejeição. Retorna (assunto, motivo)."""
    system = _system_prompt(rules)
    attempts = max(1, int(scfg.get("max_attempts", 2)))
    reason = ""
    for _ in range(attempts):
        user = f"Text: {text}"
        if reason:
            user += f"\nYour previous answer was rejected: {reason}. Answer again, following all rules."
        try:
            raw = _ask_ollama(system, user, scfg)
        except Exception as exc:  # Ollama fora do ar, timeout, modelo ausente
            return None, f"modelo indisponível: {exc}"
        answer = clean_answer(raw)
        ok, why = validate_answer(answer, required_groups, rules)
        if ok:
            return answer, ""
        reason = why
    return None, reason


# ---------------------------------------------------------------------------
# Ponto de entrada usado pelo agent.py
# ---------------------------------------------------------------------------
def enrich_scene_subjects(scenes: list[dict], script_path, cfg: dict) -> dict[str, Any]:
    scfg = cfg.get("subjects") or {}
    requirement = str(scfg.get("requirement", "manual")).strip().lower()
    if requirement not in REQUIREMENTS:
        raise ValueError(f"subjects.requirement deve ser um de {REQUIREMENTS}, veio '{requirement}'")
    rules = load_rules(scfg.get("rules_file", "subject_rules.yaml"))

    side_path = sidecar_path(script_path)
    data = load_sidecar(side_path)
    entries: dict[str, dict] = data["scenes"]

    counts = {"ok": 0, "manual": 0, "cache": 0, "review": 0}
    review: list[str] = []
    changed = not side_path.is_file()

    for scene in scenes:
        key = scene_key(scene)
        text = scene_text(scene)
        digest = text_hash(text)
        entry = entries.get(key, {})

        if entry.get("subject_en") and entry.get("source") != "model":
            subject, status = str(entry["subject_en"]).strip(), "manual"
            if entry.get("hash") and entry["hash"] != digest:
                print(f"[Assuntos] Cena {key}: o texto mudou desde a entrada manual; conferir.")
        elif entry.get("status") == "ok" and entry.get("hash") == digest and entry.get("subject_en"):
            subject, status = str(entry["subject_en"]), "cache"
        else:
            required = _required_for(requirement, entry, text, rules)
            if not text:
                subject, reason = None, "texto da cena vazio"
            elif requirement == "glossary" and not required:
                subject, reason = None, "nenhum termo do glossário encontrado no texto"
            else:
                subject, reason = resolve_subject(text, required, scfg, rules)
            status = "ok" if subject else "review"
            entries[key] = {
                "hash": digest,
                "source": "model",
                "subject_en": subject or "",
                "status": status,
                "required": required,
                "reason": "" if subject else reason,
                "text_preview": text[:120],
            }
            changed = True

        scene["subject_en"] = subject or ""
        scene["subject_status"] = status
        counts[status] += 1
        if status == "review":
            review.append(key)

    if changed:
        save_sidecar(side_path, data)

    summary = {**counts, "review_ids": review, "sidecar": str(side_path)}
    if review and scfg.get("block_on_review", True):
        details = "; ".join(f"cena {k}: {entries[k].get('reason', '')}" for k in review)
        raise RuntimeError(
            f"{len(review)} cena(s) sem assunto validado ({details}). "
            f"Edite {side_path} (campos subject_en e required) e rode de novo."
        )
    return summary
