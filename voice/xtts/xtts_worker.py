# -*- coding: utf-8 -*-
"""
XTTS-v2 worker — executa DENTRO do ambiente conda 'xtts'.

Recebe um arquivo JSON de job e gera um WAV único com a narração completa,
carregando o modelo UMA única vez (o gargalo do XTTS é o carregamento).

Job JSON:
{
  "text": "...",                 # narração completa
  "out_wav": "C:/.../narracao.wav",
  "speaker_wav": "C:/.../ale.wav",
  "language": "pt",
  "use_cuda": true,
  "chunk_chars": 240,
  "gap_ms": 220,
  "model_name": "tts_models/multilingual/multi-dataset/xtts_v2"
}

Uso:
    python xtts_worker.py job.json
"""
import json
import os
import re
import sys
import time
import tempfile
import traceback


def log(msg: str) -> None:
    print(f"[XTTS] {msg}", flush=True)


def dividir_texto(texto: str, limite: int = 240) -> list[str]:
    """Divide a narração em trechos curtos respeitando fim de frase."""
    texto = re.sub(r"\s+", " ", texto or "").strip()
    if not texto:
        return []

    # 1) separa por sentenças
    sentencas = re.split(r"(?<=[\.\!\?\:\;])\s+", texto)
    partes, atual = [], ""
    for s in sentencas:
        s = s.strip()
        if not s:
            continue
        if len(s) > limite:
            # sentença gigante: quebra por vírgula
            pedacos = re.split(r"(?<=,)\s+", s)
            for p in pedacos:
                p = p.strip()
                if not p:
                    continue
                if len(atual) + len(p) + 1 <= limite:
                    atual = f"{atual} {p}".strip()
                else:
                    if atual:
                        partes.append(atual)
                    while len(p) > limite:
                        corte = p.rfind(" ", 0, limite)
                        corte = corte if corte > 40 else limite
                        partes.append(p[:corte].strip())
                        p = p[corte:].strip()
                    atual = p
            continue

        if len(atual) + len(s) + 1 <= limite:
            atual = f"{atual} {s}".strip()
        else:
            if atual:
                partes.append(atual)
            atual = s

    if atual:
        partes.append(atual)
    return [p for p in partes if p.strip()]


def main() -> int:
    if len(sys.argv) < 2:
        log("ERRO: informe o caminho do job.json")
        return 2

    job_path = sys.argv[1]
    with open(job_path, "r", encoding="utf-8") as f:
        job = json.load(f)

    texto = job.get("text", "")
    out_wav = job["out_wav"]
    speaker = job["speaker_wav"]
    language = job.get("language", "pt")
    use_cuda = bool(job.get("use_cuda", True))
    chunk_chars = int(job.get("chunk_chars", 240))
    gap_ms = int(job.get("gap_ms", 220))
    model_name = job.get("model_name", "tts_models/multilingual/multi-dataset/xtts_v2")

    if not os.path.isfile(speaker):
        log(f"ERRO: amostra de voz não encontrada: {speaker}")
        return 3

    partes = dividir_texto(texto, chunk_chars)
    if not partes:
        log("ERRO: texto vazio")
        return 4

    log(f"Trechos: {len(partes)} | CUDA: {use_cuda} | idioma: {language}")
    log(f"Amostra de voz: {speaker}")

    try:
        import numpy as np
        import soundfile as sf
        import torch
        from TTS.api import TTS
    except Exception as e:
        log(f"ERRO ao importar dependências: {e}")
        traceback.print_exc()
        return 5

    if use_cuda and not torch.cuda.is_available():
        log("AVISO: CUDA indisponível — caindo para CPU (será MUITO mais lento)")
        use_cuda = False
    elif use_cuda:
        log(f"GPU: {torch.cuda.get_device_name(0)}")

    t0 = time.time()
    log("Carregando modelo XTTS-v2 (uma vez)...")
    try:
        tts = TTS(model_name=model_name, progress_bar=False, gpu=use_cuda)
    except TypeError:
        tts = TTS(model_name=model_name, progress_bar=False)
    log(f"Modelo carregado em {time.time() - t0:.1f}s")

    tmpdir = tempfile.mkdtemp(prefix="xtts_chunks_")
    arquivos = []
    sr_final = None
    total = len(partes)

    for i, parte in enumerate(partes, 1):
        destino = os.path.join(tmpdir, f"chunk_{i:04d}.wav")
        t1 = time.time()
        try:
            tts.tts_to_file(
                text=parte,
                speaker_wav=speaker,
                language=language,
                file_path=destino,
                split_sentences=False,
            )
        except Exception as e:
            log(f"ERRO no trecho {i}/{total}: {e}")
            traceback.print_exc()
            return 6

        if not os.path.exists(destino) or os.path.getsize(destino) < 1000:
            log(f"ERRO: trecho {i} gerou áudio inválido")
            return 7

        info = sf.info(destino)
        sr_final = sr_final or info.samplerate
        arquivos.append(destino)
        log(f"Trecho {i}/{total} OK — {info.duration:.1f}s de áudio ({time.time() - t1:.1f}s)")

    # Concatena com pequeno silêncio entre trechos
    log("Concatenando trechos...")
    gap = np.zeros(int(sr_final * gap_ms / 1000.0), dtype="float32")
    blocos = []
    for idx, caminho in enumerate(arquivos):
        dados, sr = sf.read(caminho, dtype="float32", always_2d=False)
        if dados.ndim > 1:
            dados = dados.mean(axis=1)
        blocos.append(dados)
        if idx < len(arquivos) - 1 and gap_ms > 0:
            blocos.append(gap)

    audio = np.concatenate(blocos) if blocos else np.zeros(1, dtype="float32")

    # Normalização de pico (evita clipping e volume baixo)
    pico = float(np.max(np.abs(audio))) if audio.size else 0.0
    if pico > 1e-6:
        audio = audio * (0.95 / pico)

    os.makedirs(os.path.dirname(os.path.abspath(out_wav)), exist_ok=True)
    sf.write(out_wav, audio, sr_final, subtype="PCM_16")

    dur = len(audio) / float(sr_final)
    log(f"WAV final: {out_wav} ({dur:.1f}s, {sr_final} Hz, {os.path.getsize(out_wav) // 1024} KB)")
    log(f"Tempo total: {time.time() - t0:.1f}s")

    # Limpeza
    for caminho in arquivos:
        try:
            os.remove(caminho)
        except Exception:
            pass
    try:
        os.rmdir(tmpdir)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
