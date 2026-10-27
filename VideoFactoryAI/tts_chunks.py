# -*- coding: utf-8 -*-
"""
Narração longa com XTTS: divide o texto em trechos abaixo do limite do modelo,
sintetiza cada trecho e junta os áudios com uma pausa curta entre eles.

O XTTS para português aceita cerca de 203 caracteres por chamada. Acima disso, o
áudio sai truncado. Aqui o limite padrão é 180 (margem de segurança).

Variáveis de ambiente:
  VF_XTTS_CHUNK_CHARS   limite de caracteres por trecho  (padrão: 180)
  VF_XTTS_PAUSA_MS      silêncio entre trechos, em ms     (padrão: 250)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Callable, List, Optional

LIMITE_PADRAO = 180
PAUSA_PADRAO_MS = 250


def _limite() -> int:
    try:
        return max(60, int(os.getenv("VF_XTTS_CHUNK_CHARS", str(LIMITE_PADRAO))))
    except ValueError:
        return LIMITE_PADRAO


def _pausa_ms() -> int:
    try:
        return max(0, int(os.getenv("VF_XTTS_PAUSA_MS", str(PAUSA_PADRAO_MS))))
    except ValueError:
        return PAUSA_PADRAO_MS


def _quebrar_longo(trecho: str, limite: int) -> List[str]:
    """Trecho sem pontuação forte que ainda passa do limite: quebra em vírgula, depois em espaço."""
    partes: List[str] = []
    atual = ""
    for pedaco in re.split(r"(?<=[,;:])\s+", trecho):
        if len(pedaco) > limite:
            # Último recurso: corta em espaço.
            for palavra in pedaco.split(" "):
                cand = f"{atual} {palavra}".strip()
                if len(cand) > limite and atual:
                    partes.append(atual)
                    atual = palavra
                else:
                    atual = cand
            continue
        cand = f"{atual} {pedaco}".strip()
        if len(cand) > limite and atual:
            partes.append(atual)
            atual = pedaco
        else:
            atual = cand
    if atual:
        partes.append(atual)
    return partes


def dividir_texto(texto: str, limite: Optional[int] = None) -> List[str]:
    """Divide em trechos <= limite, preferindo fronteiras de frase e nunca cortando palavras."""
    limite = limite or _limite()
    texto = re.sub(r"\s+", " ", texto.replace("\r", " ").replace("\n", " ")).strip()
    if not texto:
        return []
    frases = re.split(r"(?<=[.!?…])\s+", texto)
    trechos: List[str] = []
    atual = ""
    for frase in frases:
        if not frase:
            continue
        if len(frase) > limite:
            if atual:
                trechos.append(atual)
                atual = ""
            trechos.extend(_quebrar_longo(frase, limite))
            continue
        cand = f"{atual} {frase}".strip()
        if len(cand) > limite and atual:
            trechos.append(atual)
            atual = frase
        else:
            atual = cand
    if atual:
        trechos.append(atual)
    return trechos


def _concatenar_wav(partes: List[Path], destino: Path, pausa_ms: int) -> None:
    with wave.open(str(partes[0]), "rb") as ref:
        params = ref.getparams()
    frames_pausa = b""
    if pausa_ms > 0:
        n = int(params.framerate * pausa_ms / 1000) * params.nchannels
        frames_pausa = b"\x00" * (n * params.sampwidth)
    with wave.open(str(destino), "wb") as out:
        out.setparams(params)
        for i, p in enumerate(partes):
            with wave.open(str(p), "rb") as w:
                if w.getparams()[:3] != params[:3]:
                    raise RuntimeError(f"formato de áudio diferente em {p.name}; não dá para concatenar")
                out.writeframes(w.readframes(w.getnframes()))
            if frames_pausa and i < len(partes) - 1:
                out.writeframes(frames_pausa)


def _concatenar_ffmpeg(partes: List[Path], destino: Path, pausa_ms: int, ffmpeg: str) -> None:
    entradas: List[str] = []
    for p in partes:
        entradas += ["-i", str(p)]
    filtros: List[str] = []
    lista: List[str] = []
    for i in range(len(partes)):
        lista.append(f"[{i}:a]")
        if pausa_ms > 0 and i < len(partes) - 1:
            filtros.append(f"anullsrc=r=24000:cl=mono,atrim=0:{pausa_ms / 1000:.3f}[s{i}]")
            lista.append(f"[s{i}]")
    filtros.append("".join(lista) + f"concat=n={len(lista)}:v=0:a=1[out]")
    cmd = [ffmpeg, "-y", "-loglevel", "error", *entradas,
           "-filter_complex", ";".join(filtros), "-map", "[out]", str(destino)]
    subprocess.run(cmd, check=True)


def sintetizar_em_partes(
    texto: str,
    destino: str,
    sintetizar_trecho: Callable[[str, str], str],
    log=print,
    ffmpeg: Optional[str] = None,
) -> str:
    """
    Sintetiza `texto` em trechos e junta tudo em `destino`.

    sintetizar_trecho(texto_do_trecho, caminho_de_saida) -> caminho_gerado
    (é a função de síntese já existente, por exemplo xtts_engine.sintetizar).
    """
    trechos = dividir_texto(texto)
    if not trechos:
        raise RuntimeError("texto vazio para narração")
    destino_p = Path(destino)
    pasta = destino_p.parent / f"{destino_p.stem}_partes"
    pasta.mkdir(parents=True, exist_ok=True)
    limite = _limite()
    log(f"  [TTS] Texto de {len(texto)} caracteres dividido em {len(trechos)} trechos (limite {limite}).")

    gerados: List[Path] = []
    for i, trecho in enumerate(trechos, 1):
        alvo = pasta / f"parte_{i:03d}.wav"
        saida = Path(sintetizar_trecho(trecho, str(alvo)))
        if not saida.is_file() or saida.stat().st_size == 0:
            raise RuntimeError(f"trecho {i} não gerou áudio ({saida})")
        gerados.append(saida)
        log(f"  [TTS] trecho {i}/{len(trechos)} ok ({len(trecho)} caracteres)")

    pausa = _pausa_ms()
    if all(p.suffix.lower() == ".wav" for p in gerados):
        _concatenar_wav(gerados, destino_p.with_suffix(".wav"), pausa)
        resultado = destino_p.with_suffix(".wav")
    else:
        ff = ffmpeg or shutil.which("ffmpeg") or "ffmpeg"
        resultado = destino_p.with_suffix(".mp3")
        _concatenar_ffmpeg(gerados, resultado, pausa, ff)
    log(f"  [TTS] Narração concatenada: {resultado.name}")
    return str(resultado)
