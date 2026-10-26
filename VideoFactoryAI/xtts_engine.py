# -*- coding: utf-8 -*-
"""
XTTS-v2 engine — clonagem de voz local em GPU.

Este módulo roda no ambiente PRINCIPAL do VideoFactoryAI (Python 3.12) e
delega a síntese para o ambiente conda 'xtts' (Python 3.10 + torch cu118),
que é onde o XTTS-v2 funciona.

Por que subprocesso?
  - O XTTS exige torch 2.3.1+cu118, transformers 4.41.2 e Python 3.10.
  - O pipeline principal roda em outro Python. Isolar evita conflito de versões
    e mantém o XTTS opcional: se falhar, o pipeline cai para edge-tts.

Configuração (config.yaml, seção tts):
  xtts_python:      C:\\Users\\Pires\\miniconda3\\envs\\xtts\\python.exe
  xtts_speaker_wav: voice/xtts/ale.wav
  xtts_language:    pt
  xtts_use_cuda:    true
  xtts_worker:      voice/xtts/xtts_worker.py
  xtts_timeout_s:   7200

Variáveis de ambiente equivalentes:
  VF_XTTS_PYTHON, VF_XTTS_SPEAKER, VF_XTTS_LANGUAGE,
  VF_XTTS_USE_CUDA, VF_XTTS_WORKER, VF_XTTS_TIMEOUT
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

VF_DIR = Path(__file__).resolve().parent
ROOT_DIR = VF_DIR.parent


class XTTSError(RuntimeError):
    """Falha na síntese XTTS."""


def _cfg(cfg: dict, chave: str, padrao=None):
    return (cfg or {}).get("tts", {}).get(chave, padrao)


def localizar_python(cfg: Optional[dict] = None) -> Optional[str]:
    """Descobre o python do ambiente conda que tem o XTTS instalado."""
    candidatos = [
        os.getenv("VF_XTTS_PYTHON", "").strip(),
        str(_cfg(cfg, "xtts_python", "") or "").strip(),
        str(Path.home() / "miniconda3" / "envs" / "xtts" / "python.exe"),
        str(Path.home() / "anaconda3" / "envs" / "xtts" / "python.exe"),
        r"C:\Users\Pires\miniconda3\envs\xtts\python.exe",
    ]
    for c in candidatos:
        if c and os.path.isfile(c):
            return c
    return None


def localizar_worker(cfg: Optional[dict] = None) -> Optional[str]:
    candidatos = [
        os.getenv("VF_XTTS_WORKER", "").strip(),
        str(_cfg(cfg, "xtts_worker", "") or "").strip(),
        str(ROOT_DIR / "voice" / "xtts" / "xtts_worker.py"),
        str(VF_DIR / "xtts_worker.py"),
    ]
    for c in candidatos:
        if not c:
            continue
        p = Path(c)
        if not p.is_absolute():
            p = ROOT_DIR / c
        if p.is_file():
            return str(p)
    return None


def localizar_referencia(cfg: Optional[dict] = None) -> Optional[str]:
    """Amostra de voz usada para clonar (WAV de 6-30s, voz limpa)."""
    candidatos = [
        os.getenv("VF_XTTS_SPEAKER", "").strip(),
        str(_cfg(cfg, "xtts_speaker_wav", "") or "").strip(),
        str(ROOT_DIR / "voice" / "xtts" / "ale.wav"),
        str(ROOT_DIR / "voice" / "minhavoz_curta.wav"),
    ]
    for c in candidatos:
        if not c:
            continue
        p = Path(c)
        if not p.is_absolute():
            p = ROOT_DIR / c
        if p.is_file():
            return str(p)
    return None


def localizar_ffmpeg() -> Optional[str]:
    candidatos = [
        str(ROOT_DIR / "ffmpeg" / "bin" / "ffmpeg.exe"),
        str(ROOT_DIR / "ffmpeg.exe"),
        shutil.which("ffmpeg") or "",
    ]
    for c in candidatos:
        if c and os.path.isfile(c):
            return c
    return None


def disponivel(cfg: Optional[dict] = None) -> tuple[bool, str]:
    """Verifica se o XTTS pode ser usado, sem carregar o modelo."""
    py = localizar_python(cfg)
    if not py:
        return False, "python do ambiente conda 'xtts' não encontrado (defina tts.xtts_python)"
    worker = localizar_worker(cfg)
    if not worker:
        return False, "xtts_worker.py não encontrado"
    ref = localizar_referencia(cfg)
    if not ref:
        return False, "amostra de voz (speaker_wav) não encontrada"
    return True, f"python={py} | voz={Path(ref).name}"


def sintetizar(
    texto: str,
    out_path: str,
    cfg: Optional[dict] = None,
    log=print,
    timeout_s: Optional[int] = None,
) -> str:
    """
    Gera a narração com a voz clonada e grava em `out_path` (.mp3 ou .wav).

    Levanta XTTSError em qualquer falha — o chamador decide se cai para edge-tts.
    """
    if not texto or not texto.strip():
        raise XTTSError("texto vazio para síntese")

    ok, motivo = disponivel(cfg)
    if not ok:
        raise XTTSError(motivo)

    py = localizar_python(cfg)
    worker = localizar_worker(cfg)
    ref = localizar_referencia(cfg)

    use_cuda = _cfg(cfg, "xtts_use_cuda", True)
    env_cuda = os.getenv("VF_XTTS_USE_CUDA", "").strip().lower()
    if env_cuda in ("0", "false", "nao", "não", "no"):
        use_cuda = False
    elif env_cuda in ("1", "true", "sim", "yes"):
        use_cuda = True

    language = os.getenv("VF_XTTS_LANGUAGE", "").strip() or _cfg(cfg, "xtts_language", "pt")
    model_name = _cfg(cfg, "xtts_model", "tts_models/multilingual/multi-dataset/xtts_v2")
    chunk_chars = int(_cfg(cfg, "xtts_chunk_chars", 240) or 240)
    gap_ms = int(_cfg(cfg, "xtts_gap_ms", 220) or 220)

    if timeout_s is None:
        timeout_s = int(os.getenv("VF_XTTS_TIMEOUT", "0") or 0) or int(_cfg(cfg, "xtts_timeout_s", 7200) or 7200)

    out_path = str(out_path)
    destino_wav = out_path
    converter_mp3 = False
    if out_path.lower().endswith(".mp3"):
        destino_wav = str(Path(tempfile.gettempdir()) / f"xtts_{int(time.time())}.wav")
        converter_mp3 = True

    job = {
        "text": texto,
        "out_wav": destino_wav,
        "speaker_wav": ref,
        "language": language,
        "use_cuda": bool(use_cuda),
        "chunk_chars": chunk_chars,
        "gap_ms": gap_ms,
        "model_name": model_name,
    }

    fd, job_path = tempfile.mkstemp(prefix="xtts_job_", suffix=".json")
    os.close(fd)
    with open(job_path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.setdefault("OMP_NUM_THREADS", "4")

    log(f"  [XTTS] Sintetizando {len(texto.split())} palavras com voz clonada "
        f"({'GPU' if use_cuda else 'CPU'}) — pode levar vários minutos...")

    t0 = time.time()
    try:
        proc = subprocess.Popen(
            [py, worker, job_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(Path(worker).parent),
            bufsize=1,
        )
        try:
            assert proc.stdout is not None
            for linha in proc.stdout:
                linha = linha.rstrip()
                if linha:
                    log(f"  {linha}")
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise XTTSError(f"tempo esgotado após {timeout_s}s na síntese XTTS")

        if proc.returncode != 0:
            raise XTTSError(f"worker XTTS retornou código {proc.returncode}")
    except FileNotFoundError as e:
        raise XTTSError(f"não foi possível executar o python do XTTS: {e}")
    finally:
        try:
            os.remove(job_path)
        except Exception:
            pass

    if not os.path.exists(destino_wav) or os.path.getsize(destino_wav) < 10_000:
        raise XTTSError("XTTS não gerou áudio válido")

    if converter_mp3:
        ffmpeg = localizar_ffmpeg()
        if not ffmpeg:
            # Sem ffmpeg: mantém WAV e devolve o caminho real
            destino_final = str(Path(out_path).with_suffix(".wav"))
            shutil.move(destino_wav, destino_final)
            log(f"  [XTTS] FFmpeg ausente — áudio salvo em WAV: {Path(destino_final).name}")
            log(f"  [XTTS] Concluído em {time.time() - t0:.1f}s")
            return destino_final

        log("  [XTTS] Convertendo para MP3...")
        cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", destino_wav,
               "-ar", "44100", "-ac", "1", "-b:a", "192k", out_path]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        try:
            os.remove(destino_wav)
        except Exception:
            pass
        if r.returncode != 0 or not os.path.exists(out_path):
            raise XTTSError(f"falha ao converter para MP3: {(r.stderr or '')[:200]}")

    if not os.path.exists(out_path):
        raise XTTSError("arquivo final de áudio não foi criado")

    kb = os.path.getsize(out_path) / 1024
    log(f"  [XTTS] Concluído em {time.time() - t0:.1f}s — {Path(out_path).name} ({kb:.0f} KB)")
    return out_path


def testar(cfg: Optional[dict] = None, log=print) -> int:
    """Teste rápido de fumaça: gera uma frase curta."""
    ok, motivo = disponivel(cfg)
    print(f"[XTTS] disponivel={ok} | {motivo}")
    if not ok:
        return 1
    saida = Path(ROOT_DIR) / "voice" / "xtts" / "teste_pipeline.wav"
    try:
        sintetizar(
            "Olá. Este é um teste da clonagem de voz do VideoFactoryAI.",
            str(saida), cfg, log=log,
        )
    except XTTSError as e:
        print(f"[XTTS] FALHOU: {e}")
        return 1
    print(f"[XTTS] OK -> {saida}")
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(VF_DIR))
    try:
        import yaml
        with open(VF_DIR / "config.yaml", encoding="utf-8") as f:
            _c = yaml.safe_load(f) or {}
    except Exception:
        _c = {}
    raise SystemExit(testar(_c))
