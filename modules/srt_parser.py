"""
SRT Parser & Dynamic Timeline Segmenter
Module for parsing OpenAI Whisper SRT and segmenting into cinematic scenes.
"""
import os
import re
import subprocess
from typing import List, Dict, Any

def parse_time(time_str: str) -> float:
    """Convert SRT timestamp (00:01:23,456) to seconds (float)."""
    h, m, s = time_str.replace(',', '.').strip().split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)

def parse_srt(srt_path: str) -> List[Dict[str, Any]]:
    """Parse Whisper SRT file into structured blocks."""
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"SRT file not found: {srt_path}")
    
    with open(srt_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    pattern = re.compile(
        r'(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n([\s\S]*?)(?=\n\s*\d+\s*\n|\Z)'
    )
    matches = pattern.findall(content)
    
    blocks = []
    for m in matches:
        idx = int(m[0])
        st = parse_time(m[1])
        et = parse_time(m[2])
        text = re.sub(r'\s+', ' ', m[3]).strip()
        blocks.append({
            "id": idx,
            "start": round(st, 3),
            "end": round(et, 3),
            "duration": round(et - st, 3),
            "text": text
        })
    return blocks

def get_audio_duration(ffmpeg_path: str, audio_path: str) -> float:
    """Extract audio duration in seconds using ffmpeg."""
    cmd = [ffmpeg_path, "-i", audio_path]
    res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    m = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", res.stderr)
    if m:
        h, mn, s = m.groups()
        return int(h) * 3600 + int(mn) * 60 + float(s)
    return 372.38  # Default fallback if parsing fails

# Mapping 69 subtitle blocks into 27 cohesive documentary narrative scenes
SCENE_GROUPINGS = [
    {"id": 1,  "blocks": [1, 2],       "type": "video", "query": "iran usa flag tension politics", "desc": "Alianças e tensões EUA e Irã"},
    {"id": 2,  "blocks": [3],          "type": "video", "query": "economic sanctions protest military crisis", "desc": "Sanções econômicas e crises"},
    {"id": 3,  "blocks": [4, 5, 6],    "type": "video", "query": "global news television studio broadcast", "desc": "Manchetes e geopolítica"},
    {"id": 4,  "blocks": [7, 8, 9],    "type": "video", "query": "middle east world map geopolitics strategy", "desc": "História e tabuleiro geopolítico"},
    {"id": 5,  "blocks": [10],         "type": "video", "query": "cold war 1950s oil pipeline desert", "desc": "Guerra Fria e petróleo vital"},
    {"id": 6,  "blocks": [11, 12],     "type": "image", "query": "1953 historical archive protest tehran", "desc": "Golpe de 1953 e Mossadegh"},
    {"id": 7,  "blocks": [13],         "type": "image", "query": "iranian shah pahlavi historical archive", "desc": "Xá Reza Pahlavi e polícia secreta"},
    {"id": 8,  "blocks": [14, 15],     "type": "video", "query": "islamic revolution crowd 1979 protest", "desc": "Revolução Islâmica 1979"},
    {"id": 9,  "blocks": [16, 17, 18], "type": "image", "query": "us embassy hostage crisis tehran archive", "desc": "Crise dos reféns e ruptura"},
    {"id": 10, "blocks": [19, 20, 21], "type": "video", "query": "white house washington dc politics", "desc": "Pilares de Washington e aliados"},
    {"id": 11, "blocks": [22, 23, 24, 25], "type": "video", "query": "middle east military alliance diplomacy", "desc": "Aliança com Israel e Arábia Saudita"},
    {"id": 12, "blocks": [26, 27, 28], "type": "video", "query": "nuclear research laboratory facility uranium", "desc": "Programa nuclear iraniano"},
    {"id": 13, "blocks": [29, 30],     "type": "video", "query": "diplomats meeting table negotiation treaty", "desc": "Acordo nuclear e desconfiança"},
    {"id": 14, "blocks": [31, 32, 33], "type": "video", "query": "oil tanker cargo ship strait of hormuz", "desc": "Estreito de Ormuz e rotas de energia"},
    {"id": 15, "blocks": [34, 35, 36], "type": "video", "query": "modern tehran skyline iran city aerial", "desc": "Perspectiva de Teerã e soberania"},
    {"id": 16, "blocks": [37, 38, 39], "type": "video", "query": "middle east military troops war presence", "desc": "Presença militar dos EUA e reação"},
    {"id": 17, "blocks": [40, 41],     "type": "video", "query": "inflation economic sanctions cash money market", "desc": "Resistência a sanções econômicas"},
    {"id": 18, "blocks": [42, 43],     "type": "image", "query": "iran government official tehran assembly crowd", "desc": "Discurso oficial e nacionalismo"},
    {"id": 19, "blocks": [44, 45, 46], "type": "video", "query": "scientific laboratory technology medical research", "desc": "Tecnologia e energia nuclear civil"},
    {"id": 20, "blocks": [47, 48, 49], "type": "video", "query": "global energy oil refinery barrels industry", "desc": "Impacto no mercado global de energia"},
    {"id": 21, "blocks": [50, 51],     "type": "video", "query": "gas station fuel price inflation economy", "desc": "Preço do petróleo e inflação global"},
    {"id": 22, "blocks": [52, 53],     "type": "video", "query": "cyber attack data digital war military room", "desc": "Guerras por procuração e ciberataques"},
    {"id": 23, "blocks": [54, 55],     "type": "video", "query": "humanitarian crisis refugees middle east", "desc": "Tensão crônica e crise de refugiados"},
    {"id": 24, "blocks": [56, 57],     "type": "video", "query": "chess board strategy game competition pieces", "desc": "Xadrez geopolítico mundial"},
    {"id": 25, "blocks": [58, 59, 60, 61], "type": "video", "query": "war devastation smoke conflict explosion", "desc": "Custos de um confronto aberto"},
    {"id": 26, "blocks": [62, 63],     "type": "video", "query": "united nations flags diplomacy international", "desc": "Futuro da diplomacia no século XXI"},
    {"id": 27, "blocks": [64, 65, 66, 67, 68, 69], "type": "video", "query": "youtube subscribe bell like button animated", "desc": "Call to Action e Encerramento"}
]

def build_scene_timeline(srt_blocks: List[Dict[str, Any]], total_audio_duration: float) -> List[Dict[str, Any]]:
    """Build seamless scene timeline matching total audio duration without micro-gaps."""
    blocks_dict = {b["id"]: b for b in srt_blocks}
    scenes = []
    
    current_timeline_cursor = 0.0
    num_scenes = len(SCENE_GROUPINGS)
    
    for i, grp in enumerate(SCENE_GROUPINGS):
        scene_id = grp["id"]
        blk_ids = grp["blocks"]
        
        # Aggregate spoken text
        spoken_texts = [blocks_dict[bid]["text"] for bid in blk_ids if bid in blocks_dict]
        combined_text = " ".join(spoken_texts)
        
        # Calculate start and end
        first_blk = blocks_dict[blk_ids[0]]
        last_blk = blocks_dict[blk_ids[-1]]
        
        # Make timeline seamless: start exactly where previous scene ended
        scene_start = current_timeline_cursor
        
        if i == num_scenes - 1:
            # Last scene runs until total audio duration
            scene_end = round(total_audio_duration, 3)
        else:
            # Determine end based on next group's first block start or current last block end
            next_first_blk_id = SCENE_GROUPINGS[i + 1]["blocks"][0]
            scene_end = round(blocks_dict[next_first_blk_id]["start"], 3)
            
        scene_dur = round(scene_end - scene_start, 3)
        current_timeline_cursor = scene_end
        
        ext = ".mp4" if grp["type"] == "video" else ".jpg"
        filename = f"cena_{scene_id:02d}{ext}"
        
        scenes.append({
            "id": scene_id,
            "start": scene_start,
            "end": scene_end,
            "duration": scene_dur,
            "tipo": grp["type"],
            "arquivo": filename,
            "query": grp["query"],
            "descricao": grp["desc"],
            "texto": combined_text
        })
        
    return scenes
