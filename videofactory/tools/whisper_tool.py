"""
Whisper Speech-to-Text & Subtitle Synchronization Tool.
Wraps OpenAI Whisper to generate structured subtitle blocks and accurate SRT files.
"""
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

def format_timestamp(seconds: float) -> str:
    """Format seconds into SRT timestamp (HH:MM:SS,mmm)."""
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = int(round(seconds * 1000))
    hours = milliseconds // 3600000
    milliseconds %= 3600000
    minutes = milliseconds // 60000
    milliseconds %= 60000
    secs = milliseconds // 1000
    milliseconds %= 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

def transcribe_audio_to_srt(
    audio_path: str,
    output_srt_path: str,
    model_name: str = "base",
    device: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Transcribe audio with Whisper and export standard SRT.
    Returns structured subtitle blocks.
    """
    import whisper
    import torch

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"  [Whisper] Carregando modelo '{model_name}' em '{device}'...")
    model = whisper.load_model(model_name, device=device)

    print(f"  [Whisper] Transcrevendo áudio '{Path(audio_path).name}'...")
    result = model.transcribe(
        audio_path,
        language="pt",
        verbose=False,
        word_timestamps=True
    )

    segments = result.get("segments", [])
    blocks: List[Dict[str, Any]] = []

    os.makedirs(os.path.dirname(os.path.abspath(output_srt_path)), exist_ok=True)
    with open(output_srt_path, "w", encoding="utf-8") as srt_file:
        for idx, seg in enumerate(segments, 1):
            st = round(float(seg["start"]), 3)
            et = round(float(seg["end"]), 3)
            txt = seg["text"].strip()
            
            # Write to SRT
            srt_file.write(f"{idx}\n")
            srt_file.write(f"{format_timestamp(st)} --> {format_timestamp(et)}\n")
            srt_file.write(f"{txt}\n\n")

            blocks.append({
                "id": idx,
                "start": st,
                "end": et,
                "duration": round(et - st, 3),
                "text": txt
            })

    print(f"  [Whisper] Transcrição concluída: {len(blocks)} blocos de legenda gerados.")
    return blocks

def parse_existing_srt(srt_path: str) -> List[Dict[str, Any]]:
    """Parse existing SRT file if already transcribed."""
    if not os.path.exists(srt_path):
        return []

    with open(srt_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    pattern = re.compile(
        r'(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n([\s\S]*?)(?=\n\s*\d+\s*\n|\Z)'
    )
    matches = pattern.findall(content)

    def parse_t(time_str: str) -> float:
        h, m, s = time_str.replace(',', '.').strip().split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)

    blocks = []
    for m in matches:
        idx = int(m[0])
        st = parse_t(m[1])
        et = parse_t(m[2])
        text = re.sub(r'\s+', ' ', m[3]).strip()
        blocks.append({
            "id": idx,
            "start": round(st, 3),
            "end": round(et, 3),
            "duration": round(et - st, 3),
            "text": text
        })
    return blocks
