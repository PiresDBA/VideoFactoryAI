"""
Multi-Engine Text-to-Speech (TTS) Tool for VideoFactoryAI.
Supports Microsoft Edge-TTS (Zero Cost, Natural Neural Voices),
F5-TTS Voice Cloning, and OpenAI TTS.
"""
import os
import asyncio
from pathlib import Path
from typing import Optional

async def _synthesize_edge_tts(
    text: str,
    output_path: str,
    voice: str = "pt-BR-AntonioNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> bool:
    """Async generator for Microsoft Edge-TTS."""
    import edge_tts
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)
    return os.path.exists(output_path) and os.path.getsize(output_path) > 1000

def generate_edge_tts(
    text: str,
    output_path: str,
    voice: str = "pt-BR-AntonioNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> bool:
    """Synchronous interface for Edge-TTS."""
    return asyncio.run(_synthesize_edge_tts(text, output_path, voice, rate, pitch))

def generate_f5_tts(
    text: str,
    output_path: str,
    ref_audio: str = "voice/minhavoz_curta.wav",
    ref_text: str = "Olá, imagine duas nações que já foram aliadas."
) -> bool:
    """F5-TTS Voice Clone generation if installed and reference audio exists."""
    try:
        from f5_tts.api import F5TTS
        f5tts = F5TTS()
        f5tts.infer(
            ref_file=ref_audio,
            ref_text=ref_text,
            gen_text=text,
            file_wave=output_path
        )
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as e:
        print(f"  [TTS] F5-TTS fallback error: {e}")
        return False

def generate_openai_tts(
    text: str,
    output_path: str,
    api_key: Optional[str] = None,
    voice: str = "onyx"
) -> bool:
    """OpenAI TTS (tts-1-hd) generation."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        response = client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=text
        )
        response.stream_to_file(output_path)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as e:
        print(f"  [TTS] OpenAI TTS error: {e}")
        return False

def generate_narration_audio(
    text: str,
    output_path: str,
    engine: str = "edge-tts",
    voice: str = "pt-BR-AntonioNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
    api_key: Optional[str] = None
) -> bool:
    """Master TTS dispatcher."""
    print(f"  [TTS] Gerando narração com motor '{engine}' (Voz: {voice})...")
    
    if engine == "edge-tts":
        success = generate_edge_tts(text, output_path, voice=voice, rate=rate, pitch=pitch)
        if success:
            return True
        print("  [TTS] Edge-TTS falhou, tentando fallback...")

    elif engine == "f5-tts":
        success = generate_f5_tts(text, output_path)
        if success:
            return True
        print("  [TTS] F5-TTS falhou, revertendo para Edge-TTS...")
        return generate_edge_tts(text, output_path, voice=voice)

    elif engine == "openai":
        success = generate_openai_tts(text, output_path, api_key=api_key)
        if success:
            return True
        print("  [TTS] OpenAI TTS falhou, revertendo para Edge-TTS...")
        return generate_edge_tts(text, output_path, voice=voice)

    # Universal default
    return generate_edge_tts(text, output_path, voice=voice)
