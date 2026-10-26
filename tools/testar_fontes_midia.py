# -*- coding: utf-8 -*-
"""
Teste real de fontes de mídia gratuita do VideoFactoryAI.

Para cada fonte:
  1. chama a função real usada pelo pipeline
  2. valida o arquivo baixado (PIL para imagem / ffprobe para vídeo)
  3. mede tempo e tamanho
  4. grava resultado em tools/relatorio_fontes.json

Uso:
    python tools/testar_fontes_midia.py
    python tools/testar_fontes_midia.py --apenas burst,pexels
    python tools/testar_fontes_midia.py --query "segunda guerra mundial"
"""
import argparse
import io
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VF_DIR = ROOT / "VideoFactoryAI"
sys.path.insert(0, str(VF_DIR))
sys.path.insert(0, str(ROOT))

# Silencia prints ruidosos das funções originais
import contextlib


def _valida_imagem(path: str) -> tuple[bool, str]:
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            w, h = im.size
            fmt = im.format
        if w < 400 or h < 300:
            return False, f"pequena {w}x{h}"
        if w * h < 250_000:
            return False, f"baixa resolucao {w}x{h}"
        return True, f"{fmt} {w}x{h}"
    except Exception as e:
        return False, f"invalida: {type(e).__name__}"


def _valida_video(path: str) -> tuple[bool, str]:
    """Valida MP4/MOV/WEBM usando o header dos boxes ISO-BMFF ou EBML."""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
        size = os.path.getsize(path)
        if b"ftyp" in head[:32]:
            return True, f"mp4 {size // 1024}KB"
        if head[:4] == b"\x1a\x45\xdf\xa3":
            return True, f"webm {size // 1024}KB"
        if head[:4] in (b"RIFF",):
            return True, f"riff/avi {size // 1024}KB"
        if size < 100_000:
            return False, f"pequeno {size // 1024}KB"
        return False, f"nao e video ({head[:8]!r})"
    except Exception as e:
        return False, f"erro: {e}"


def _executar(fn, query, dest, *args):
    buf = io.StringIO()
    t0 = time.time()
    try:
        with contextlib.redirect_stdout(buf):
            res = fn(query, dest, *args)
    except Exception as e:
        return None, time.time() - t0, f"EXC {type(e).__name__}: {e}", buf.getvalue()
    return res, time.time() - t0, "", buf.getvalue()


def testar_imagens(queries, apenas=None):
    import media_research_agent as mra

    fontes = mra.FREE_IMAGE_SOURCES
    if apenas:
        fontes = {k: v for k, v in fontes.items() if k in apenas}

    resultados = []
    tmp = tempfile.mkdtemp(prefix="vftest_")
    total = len(fontes)
    try:
        for idx, nome in enumerate(sorted(fontes), 1):
            print(f"[{idx}/{total}] imagem: {nome:<20}", end=" ", flush=True)
            ok_any = False
            detalhes = []
            for q in queries:
                dest = os.path.join(tmp, f"{nome}_{abs(hash(q)) % 9999}.jpg")
                res, dt, erro, _out = _executar(
                    mra._l2_free_image_source, q, dest, nome
                )
                if res:
                    url, lic = res
                    val, msg = _valida_imagem(dest)
                    detalhes.append({
                        "query": q, "url": url, "licenca": lic,
                        "valido": val, "detalhe": msg,
                        "segundos": round(dt, 1),
                        "bytes": os.path.getsize(dest) if os.path.exists(dest) else 0,
                    })
                    if val:
                        ok_any = True
                        break
                else:
                    saida = (erro or "").strip()
                    if not saida:
                        linhas = [l.strip() for l in _out.splitlines() if l.strip()]
                        saida = linhas[-1] if linhas else "sem resultado"
                    detalhes.append({
                        "query": q, "url": None, "licenca": None,
                        "valido": False, "detalhe": saida,
                        "segundos": round(dt, 1), "bytes": 0,
                    })
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                    except Exception:
                        pass

            status = "OK" if ok_any else "FALHOU"
            print(f"{status}  ({detalhes[0]['detalhe'][:40]})")
            resultados.append({
                "tipo": "imagem",
                "fonte": nome,
                "funciona": ok_any,
                "tentativas": detalhes,
            })
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return resultados


def testar_videos(queries):
    """Testa as fontes de vídeo que o pipeline realmente usa (L1)."""
    import media_research_agent as mra

    # Chaves opcionais: sem chave a fonte é pulada (não é falha de código).
    pixabay_key = os.getenv("PIXABAY_API_KEY", "").strip()
    pexels_key = os.getenv("PEXELS_API_KEY", "").strip()

    fontes = [
        ("wikimedia_video", mra._l1_wikimedia_video, ()),
        ("internet_archive_video", mra._l1_internet_archive_video, ()),
    ]
    if pixabay_key:
        fontes.append(("pixabay_video", mra._l1_pixabay_video, (pixabay_key,)))
    if pexels_key:
        fontes.append(("pexels_video", mra._l1_pexels_video, (pexels_key,)))
    resultados = []
    tmp = tempfile.mkdtemp(prefix="vftest_v_")
    try:
        for idx, (nome, fn, extras) in enumerate(fontes, 1):
            print(f"[{idx}/{len(fontes)}] video:  {nome:<20}", end=" ", flush=True)
            ok_any = False
            detalhes = []
            for q in queries:
                dest = os.path.join(tmp, f"{nome}.mp4")
                res, dt, erro, _out = _executar(fn, q, dest, *extras)
                if res:
                    url, lic = res
                    val, msg = _valida_video(dest)
                    detalhes.append({
                        "query": q, "url": url, "licenca": lic,
                        "valido": val, "detalhe": msg,
                        "segundos": round(dt, 1),
                        "bytes": os.path.getsize(dest) if os.path.exists(dest) else 0,
                    })
                    if val:
                        ok_any = True
                        break
                else:
                    detalhes.append({
                        "query": q, "url": None, "licenca": None,
                        "valido": False, "detalhe": erro or "sem resultado",
                        "segundos": round(dt, 1), "bytes": 0,
                    })
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                    except Exception:
                        pass

            print(f"{'OK' if ok_any else 'FALHOU'}  ({detalhes[0]['detalhe'][:40]})")
            resultados.append({
                "tipo": "video",
                "fonte": nome,
                "funciona": ok_any,
                "tentativas": detalhes,
            })
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return resultados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", action="append", default=None)
    ap.add_argument("--apenas", default=None, help="lista separada por virgula")
    ap.add_argument("--sem-video", action="store_true")
    ap.add_argument("--saida", default=str(ROOT / "tools" / "relatorio_fontes.json"))
    args = ap.parse_args()

    queries = args.query or ["war", "nature", "city"]
    apenas = {s.strip() for s in args.apenas.split(",")} if args.apenas else None

    print("=" * 78)
    print("TESTE REAL DE FONTES DE MIDIA — VideoFactoryAI")
    print(f"Queries: {queries}")
    print("=" * 78)

    resultados = []
    if not apenas or any(k for k in (apenas or []) if k.endswith("_video")):
        somente_video = apenas and all(k.endswith("_video") for k in apenas)
        nomes_video = {k for k in (apenas or []) if k.endswith("_video")}
        if not somente_video:
            resultados += testar_imagens(queries, {k for k in apenas} if apenas else None)
            print()
        if not args.sem_video:
            resultados += testar_videos(queries)
    else:
        resultados += testar_imagens(queries, apenas)
        if not args.sem_video:
            print()
            resultados += testar_videos(queries)

    ok = [r["fonte"] for r in resultados if r["funciona"]]
    falhou = [r["fonte"] for r in resultados if not r["funciona"]]

    print()
    print("=" * 78)
    print(f"FUNCIONAM ({len(ok)}): {', '.join(ok) if ok else '-'}")
    print(f"FALHARAM  ({len(falhou)}): {', '.join(falhou) if falhou else '-'}")
    print("=" * 78)

    Path(args.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.saida).write_text(
        json.dumps({"queries": queries, "resultados": resultados}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Relatorio: {args.saida}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
