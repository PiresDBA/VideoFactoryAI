#!/usr/bin/env python
"""
VideoFactoryAI — Entry Point

Uso:
    python run.py roteiro.txt
    python run.py roteiro.txt --voice pt-BR-FranciscaNeural
    python run.py roteiro.txt --whisper medium --resume
    python run.py --help

Recebe um roteiro e gera automaticamente o vídeo completo.
"""
import argparse
import sys
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(
        prog="VideoFactoryAI",
        description="Agente autônomo que transforma um roteiro em vídeo documentário 1080p."
    )
    parser.add_argument(
        "roteiro",
        nargs="?",
        default=None,
        help="Caminho para o arquivo de roteiro .txt (ou texto na stdin)"
    )
    parser.add_argument(
        "--voice",
        default="pt-BR-AntonioNeural",
        help="Voz Edge-TTS a usar. Ex: pt-BR-FranciscaNeural, pt-BR-AntonioNeural"
    )
    parser.add_argument(
        "--tts-engine",
        choices=["edge-tts", "f5-tts", "openai"],
        default="edge-tts",
        help="Motor de narração TTS"
    )
    parser.add_argument(
        "--whisper-model",
        choices=["tiny", "base", "small", "medium", "large"],
        default="base",
        help="Modelo Whisper para geração de legendas"
    )
    parser.add_argument(
        "--title",
        default="",
        help="Título do documentário (detectado automaticamente se omitido)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Retomar pipeline a partir do último checkpoint"
    )
    parser.add_argument(
        "--pixabay-key",
        default=None,
        help="Pixabay API key (sobrescreve variável PIXABAY_API_KEY)"
    )
    parser.add_argument(
        "--openai-key",
        default=None,
        help="OpenAI API key para DALL-E 3 e TTS (sobrescreve OPENAI_API_KEY)"
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=20,
        help="CRF de compressão FFmpeg (0=lossless, 51=pior). Padrão: 20"
    )
    parser.add_argument(
        "--preset",
        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"],
        default="fast",
        help="Preset de encoding FFmpeg. Padrão: fast"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ── 1. Read Script ────────────────────────────────────────────────────────
    script_text = ""
    script_path = ""

    if args.roteiro:
        roteiro_file = Path(args.roteiro)
        if not roteiro_file.exists():
            print(f"❌ Erro: arquivo '{args.roteiro}' não encontrado.", file=sys.stderr)
            sys.exit(1)
        script_path = str(roteiro_file.resolve())
        script_text = roteiro_file.read_text(encoding="utf-8").strip()
    elif not sys.stdin.isatty():
        # Read from stdin pipe
        script_text = sys.stdin.read().strip()
    else:
        # No input — try default roteiro.txt in project root
        default = Path("roteiro.txt")
        if default.exists():
            script_path = str(default.resolve())
            script_text = default.read_text(encoding="utf-8").strip()
            print(f"ℹ️  Usando roteiro padrão: {default}")
        else:
            print("❌ Nenhum roteiro fornecido. Use: python run.py roteiro.txt", file=sys.stderr)
            sys.exit(1)

    if not script_text:
        print("❌ Roteiro está vazio.", file=sys.stderr)
        sys.exit(1)

    # ── 2. Configure Pipeline ─────────────────────────────────────────────────
    import os
    from videofactory.config import VideoFactoryConfig
    from videofactory.core.context import VideoFactoryContext
    from videofactory.agents.director_agent import DirectorAgent

    config = VideoFactoryConfig(
        tts_engine=args.tts_engine,
        tts_voice=args.voice,
        whisper_model=args.whisper_model,
        crf=args.crf,
        preset=args.preset,
    )

    if args.pixabay_key:
        config.pixabay_api_key = args.pixabay_key
    if args.openai_key:
        config.openai_api_key = args.openai_key

    # ── 3. Build Context ──────────────────────────────────────────────────────
    context = VideoFactoryContext(
        script_path=script_path,
        script_text=script_text,
        title=args.title or "Documentário Sem Título",
    )

    # ── 4. Run Director ───────────────────────────────────────────────────────
    director = DirectorAgent(config=config, resume_from_checkpoint=args.resume)

    try:
        final_context = director.run(context)
        print(f"\n[OK] Concluido!")
        print(f"   Video : {final_context.output_video_path}")
        print(f"   Thumb : {final_context.output_thumbnail_path}")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Pipeline falhou: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
