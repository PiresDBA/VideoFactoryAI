#!/usr/bin/env python
"""
VideoFactoryAI — Script de Instalação e Verificação do Ambiente
==============================================================
Uso:
    python setup.py
    ou execute install.bat

Instala e verifica:
    - Python 3.10+
    - PyTorch + CUDA / GPU
    - OpenAI Whisper (legendas e transcrição)
    - Microsoft Edge-TTS (narração neural)
    - Pillow (processamento de imagem e thumbnails)
    - Requests e PyYAML
    - FFmpeg com NVEnc (binário local ou PATH)
    - Estrutura completa de diretórios e canais
"""

import os
import sys
import shutil
import platform
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
AGENT_DIR = ROOT_DIR / "VideoFactoryAI"

# Dependências Python essenciais
REQUIRED_PACKAGES = [
    ("requests", "requests>=2.31.0"),
    ("yaml", "pyyaml>=6.0"),
    ("PIL", "Pillow>=10.0.0"),
    ("edge_tts", "edge-tts>=6.1.0"),
    ("whisper", "openai-whisper>=20231117"),
]

DIRECTORIES_TO_CREATE = [
    ROOT_DIR / "saida",
    ROOT_DIR / "videos",
    ROOT_DIR / "imagens",
    ROOT_DIR / "temp_clips",
    ROOT_DIR / "ckpts",
    ROOT_DIR / "cache",
    ROOT_DIR / "roteiros",
    AGENT_DIR / "memory",
    AGENT_DIR / "channels",
]


def print_header(title: str):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def check_python_version() -> bool:
    v = sys.version_info
    print(f"[*] Python: {v.major}.{v.minor}.{v.micro} ({platform.system()} {platform.architecture()[0]})")
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        print("[ERRO] VideoFactoryAI requer Python 3.10 ou superior.", file=sys.stderr)
        return False
    print("    -> Versao compativel.")
    return True


def check_and_install_torch() -> bool:
    print("\n[*] Verificando PyTorch e aceleracao GPU...")
    try:
        import torch
        cuda_avail = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if cuda_avail else "Nenhuma (CPU apenas)"
        print(f"    PyTorch {torch.__version__} instalado.")
        print(f"    CUDA disponivel: {'SIM (' + gpu_name + ')' if cuda_avail else 'NAO'}")
        return True
    except ImportError:
        print("    PyTorch nao encontrado. Instalando versao compativel...")
        # Tenta detectar NVIDIA GPU via nvidia-smi
        has_nvidia = False
        try:
            r = subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
            has_nvidia = r.returncode == 0
        except Exception:
            pass

        if has_nvidia:
            print("    GPU NVIDIA detectada. Instalando PyTorch com suporte CUDA 12.1...")
            cmd = [sys.executable, "-m", "pip", "install", "torch", "torchaudio",
                   "--index-url", "https://download.pytorch.org/whl/cu121"]
        else:
            print("    Instalando PyTorch padrao (CPU)...")
            cmd = [sys.executable, "-m", "pip", "install", "torch", "torchaudio"]

        res = subprocess.run(cmd)
        return res.returncode == 0


def install_packages() -> bool:
    print("\n[*] Verificando e instalando dependencias Python...")
    all_ok = True
    for mod_name, pkg_spec in REQUIRED_PACKAGES:
        try:
            __import__(mod_name)
            print(f"    [OK] {pkg_spec.split('>=')[0]} ja instalado.")
        except ImportError:
            print(f"    [INSTALANDO] {pkg_spec}...")
            cmd = [sys.executable, "-m", "pip", "install", pkg_spec]
            res = subprocess.run(cmd)
            if res.returncode != 0:
                print(f"    [FALHA] Nao foi possivel instalar {pkg_spec}", file=sys.stderr)
                all_ok = False
            else:
                print(f"    [OK] {pkg_spec} instalado com sucesso.")
    return all_ok


def check_and_setup_ffmpeg() -> bool:
    print("\n[*] Verificando FFmpeg...")
    local_ffmpeg = ROOT_DIR / "ffmpeg.exe"
    system_ffmpeg = shutil.which("ffmpeg")

    if local_ffmpeg.exists():
        print(f"    [OK] FFmpeg local encontrado: {local_ffmpeg}")
        try:
            r = subprocess.run([str(local_ffmpeg), "-version"], capture_output=True, text=True, timeout=5)
            first_line = r.stdout.splitlines()[0] if r.stdout else ""
            print(f"    -> {first_line}")
        except Exception:
            pass
        return True

    if system_ffmpeg:
        print(f"    [OK] FFmpeg encontrado no PATH do sistema: {system_ffmpeg}")
        return True

    print("    [!] FFmpeg nao encontrado localmente nem no PATH.")
    print("    Deseja baixar o executavel oficial do FFmpeg agora? (s/n): ", end="")
    try:
        resp = input().strip().lower()
    except Exception:
        resp = "s"

    if resp in ("s", "sim", "y", "yes", ""):
        return download_ffmpeg()
    else:
        print("    [AVISO] FFmpeg precisara ser colocado em C:\\Projeto_Ira_EUA\\ffmpeg.exe manualmente.")
        return False


def download_ffmpeg() -> bool:
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    dest_zip = ROOT_DIR / "ffmpeg_temp.zip"
    print(f"    Baixando FFmpeg essentials de {url}...")
    try:
        def reporthook(count, block_size, total_size):
            if total_size > 0:
                pct = int(count * block_size * 100 / total_size)
                sys.stdout.write(f"\r    Progresso: {pct}%")
                sys.stdout.flush()

        urllib.request.urlretrieve(url, str(dest_zip), reporthook)
        print("\n    Extraindo ffmpeg.exe...")
        with zipfile.ZipFile(dest_zip, 'r') as z:
            for item in z.namelist():
                if item.endswith("bin/ffmpeg.exe"):
                    with z.open(item) as src, open(ROOT_DIR / "ffmpeg.exe", "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    print(f"    [OK] ffmpeg.exe extraido com sucesso para {ROOT_DIR / 'ffmpeg.exe'}")
                    break
        if dest_zip.exists():
            dest_zip.unlink()
        return True
    except Exception as e:
        print(f"    [ERRO] Falha ao baixar FFmpeg: {e}")
        print("    Baixe manualmente de https://www.gyan.dev/ffmpeg/builds/ e coloque ffmpeg.exe na raiz.")
        return False


def create_directories():
    print("\n[*] Verificando e criando estrutura de pastas...")
    for d in DIRECTORIES_TO_CREATE:
        d.mkdir(parents=True, exist_ok=True)
        print(f"    [OK] {d.relative_to(ROOT_DIR)}/")


def verify_videofactoryai():
    print("\n[*] Validando módulos internos do VideoFactoryAI...")
    sys.path.insert(0, str(AGENT_DIR))
    sys.path.insert(0, str(ROOT_DIR))

    modules_to_test = [
        ("modules.media_engine", "media_engine"),
        ("modules.visual_processor", "visual_processor"),
        ("modules.composer", "composer"),
        ("quality_agent", "QualityAgent"),
        ("seo_agent", "SeoAgent"),
        ("thumbnail_agent", "ThumbnailAgent"),
        ("asset_cache", "AssetCache"),
        ("analytics", "Analytics"),
        ("voice_memory", "VoiceMemory"),
        ("media_research_agent", "MediaResearchAgent"),
    ]

    errors = 0
    for mod_path, label in modules_to_test:
        try:
            __import__(mod_path)
            print(f"    [OK] {label}")
        except Exception as e:
            print(f"    [FALHA] {label}: {e}")
            errors += 1

    return errors == 0


def main():
    print_header("VideoFactoryAI — Instalador e Validador do Ambiente")

    ok_py = check_python_version()
    if not ok_py:
        sys.exit(1)

    ok_torch = check_and_install_torch()
    ok_pkgs  = install_packages()
    ok_ff    = check_and_setup_ffmpeg()
    create_directories()
    ok_mods  = verify_videofactoryai()

    print_header("RESUMO DA INSTALACAO")
    status = lambda b: "[OK] Pronto" if b else "[AVISO] Requer Atencao"
    print(f"  Python 3.10+       : {status(ok_py)}")
    print(f"  PyTorch / CUDA     : {status(ok_torch)}")
    print(f"  Pacotes essenciais : {status(ok_pkgs)}")
    print(f"  FFmpeg local       : {status(ok_ff)}")
    print(f"  Modulos do Agente  : {status(ok_mods)}")
    print("=" * 65)

    if ok_py and ok_torch and ok_pkgs and ok_ff and ok_mods:
        print("\n  >>> O VideoFactoryAI esta 100% pronto para uso! <<<")
        print("  Comando para gerar documentario a partir de um roteiro:")
        print("    python VideoFactoryAI/agent.py roteiro.txt\n")
        print("  Comando no modo Produtor Automatico (cria e produz sem roteiro):")
        print("    python VideoFactoryAI/agent.py --topic \"A Guerra Fria\" --duration 8\n")
    else:
        print("\n  Instalacao concluida com alguns avisos. Revise os itens acima.")


if __name__ == "__main__":
    main()
