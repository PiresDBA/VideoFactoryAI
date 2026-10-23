"""
=============================================================================
GERADOR DOCUMENTARIO V2 — DEEP SEMANTIC MULTI-SOURCE SOURCING PIPELINE
=============================================================================
Combines:
  1. Wikimedia Commons API for 100% authentic historical archive imagery
     (1953 Coup, Mossadegh, Shah Pahlavi, Khomeini, 1979 Hostage Crisis, Majlis, Azadi Tower)
  2. Pixabay API for targeted 1080p modern geopolitical & military footage
  3. Cinematic Ken Burns zoompan motion on historical photographs
  4. 1080p@30fps yuv420p video normalization with looping and audio stripping
  5. Master timeline concatenation, audio binding, and stylized subtitle burn-in
=============================================================================
"""
import os
import re
import sys
import time
import shutil
import subprocess
import requests
from typing import Dict, Any, List

BASE_DIR = r"C:\Projeto_Ira_EUA"
PIXABAY_KEY = "58184749-b92df4cd039274d2c7a6aac7a"

VIDEOS_DIR = os.path.join(BASE_DIR, "videos")
IMAGENS_DIR = os.path.join(BASE_DIR, "imagens")
SAIDA_DIR = os.path.join(BASE_DIR, "saida")
TEMP_CLIPS_DIR = os.path.join(BASE_DIR, "temp_clips")

FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg.exe")
AUDIO_PATH = os.path.join(BASE_DIR, "narracao.mp3")
SRT_PATH = os.path.join(BASE_DIR, "narracao.srt")
OUTPUT_MASTER = os.path.join(SAIDA_DIR, "documentario_perfeito_v2.mp4")
MANIFEST_PATH = os.path.join(BASE_DIR, "concat_list.txt")

# Master definition of the 27 documentary scenes with strict historical & semantic queries
SCENE_SPEC = [
    {
        "id": 1, "start": 0.00, "end": 10.70, "duration": 10.70,
        "type": "video", "source": "pixabay", "query": "american flag waving",
        "desc": "Alianças passadas e tensão inicial EUA-Irã"
    },
    {
        "id": 2, "start": 10.70, "end": 20.40, "duration": 9.70,
        "type": "video", "source": "pixabay", "query": "military warship naval ocean",
        "desc": "Sanções econômicas e ameaças militares contínuas"
    },
    {
        "id": 3, "start": 20.40, "end": 36.60, "duration": 16.20,
        "type": "video", "source": "pixabay", "query": "news broadcast studio television",
        "desc": "Além das manchetes diárias e geopolítica global"
    },
    {
        "id": 4, "start": 36.60, "end": 47.60, "duration": 11.00,
        "type": "video", "source": "pixabay", "query": "world map rotating globe",
        "desc": "Retrospectiva histórica e o tabuleiro geopolítico"
    },
    {
        "id": 5, "start": 47.60, "end": 56.80, "duration": 9.20,
        "type": "video", "source": "pixabay", "query": "oil pump",
        "desc": "Guerra Fria, fronteira soviética e petróleo vital"
    },
    {
        "id": 6, "start": 56.80, "end": 71.70, "duration": 14.90,
        "type": "image", "source": "wikimedia", "query": "Court officials in military trial of Mohammad Mosaddegh",
        "desc": "Golpe de 1953 e julgamento de Mohammad Mossadegh (Arquivo Histórico)"
    },
    {
        "id": 7, "start": 71.70, "end": 77.90, "duration": 6.20,
        "type": "image", "source": "wikimedia", "query": "Mohammad Reza Pahlavi Shah portrait",
        "desc": "Xá Mohammad Reza Pahlavi e polícia secreta (Arquivo Histórico)"
    },
    {
        "id": 8, "start": 77.90, "end": 89.90, "duration": 12.00,
        "type": "image", "source": "wikimedia", "query": "Portrait of Ruhollah Khomeini By Ali Kaveh",
        "desc": "Revolução Islâmica de 1979 e Aiatolá Khomeini (Arquivo Histórico)"
    },
    {
        "id": 9, "start": 89.90, "end": 110.20, "duration": 20.30,
        "type": "image", "source": "wikimedia", "query": "Iran hostage crisis - Iraninan students comes up U.S. embassy in Tehran.jpg",
        "desc": "Crise dos reféns na embaixada americana em Teerã 1979 (Arquivo Histórico)"
    },
    {
        "id": 10, "start": 110.20, "end": 123.20, "duration": 13.00,
        "type": "video", "source": "pixabay", "query": "white house washington dc",
        "desc": "Pilares da política externa de Washington"
    },
    {
        "id": 11, "start": 123.20, "end": 143.80, "duration": 20.60,
        "type": "video", "source": "pixabay", "query": "soldiers patrol military",
        "desc": "Alianças no Oriente Médio: Israel e monarquias do Golfo"
    },
    {
        "id": 12, "start": 143.80, "end": 158.10, "duration": 14.30,
        "type": "video", "source": "pixabay", "query": "nuclear power plant cooling towers",
        "desc": "Programa nuclear iraniano e risco de corrida armamentista"
    },
    {
        "id": 13, "start": 158.10, "end": 169.00, "duration": 10.90,
        "type": "video", "source": "pixabay", "query": "diplomats meeting table negotiation",
        "desc": "Pacto nuclear de 2015, desconfiança e acordos rompidos"
    },
    {
        "id": 14, "start": 169.00, "end": 186.30, "duration": 17.30,
        "type": "video", "source": "pixabay", "query": "oil tanker cargo ship sea",
        "desc": "Estreito de Ormuz e fluxo vital de energia global"
    },
    {
        "id": 15, "start": 186.30, "end": 200.20, "duration": 13.90,
        "type": "image", "source": "wikimedia", "query": "Azadi Tower at night III.jpg",
        "desc": "Perspectiva de Teerã, soberania e marco nacional Azadi (Arquivo Histórico)"
    },
    {
        "id": 16, "start": 200.20, "end": 214.80, "duration": 14.60,
        "type": "video", "source": "pixabay", "query": "aircraft carrier ocean military",
        "desc": "Presença militar dos EUA vista como intromissão regional"
    },
    {
        "id": 17, "start": 214.80, "end": 226.60, "duration": 11.80,
        "type": "video", "source": "pixabay", "query": "money counting cash inflation",
        "desc": "Sobrevivência do regime e resistência a sanções econômicas"
    },
    {
        "id": 18, "start": 226.60, "end": 242.10, "duration": 15.50,
        "type": "image", "source": "wikimedia", "query": "Old Building of Iranian Parliament",
        "desc": "Parlamento Iraniano Majlis e discurso nacionalista (Arquivo Histórico)"
    },
    {
        "id": 19, "start": 242.10, "end": 260.00, "duration": 17.90,
        "type": "video", "source": "pixabay", "query": "laboratory scientist microscope research",
        "desc": "Direito à tecnologia e fins pacíficos da energia nuclear"
    },
    {
        "id": 20, "start": 260.00, "end": 273.20, "duration": 13.20,
        "type": "video", "source": "pixabay", "query": "oil refinery industrial plant sunset",
        "desc": "Impacto econômico mundial no mercado de petróleo e gás"
    },
    {
        "id": 21, "start": 273.20, "end": 283.40, "duration": 10.20,
        "type": "video", "source": "pixabay", "query": "gas station fuel pump buttons",
        "desc": "Disparada no preço dos combustíveis e inflação nos postos"
    },
    {
        "id": 22, "start": 283.40, "end": 292.30, "duration": 8.90,
        "type": "video", "source": "pixabay", "query": "binary code matrix glitch",
        "desc": "Guerras por procuração e ciberconflitos digitais"
    },
    {
        "id": 23, "start": 292.30, "end": 306.80, "duration": 14.50,
        "type": "video", "source": "pixabay", "query": "refugee camp humanitarian crisis",
        "desc": "Tensão crônica, crises humanitárias e fluxo de refugiados"
    },
    {
        "id": 24, "start": 306.80, "end": 316.80, "duration": 10.00,
        "type": "video", "source": "pixabay", "query": "chess board strategy game",
        "desc": "Xadrez geopolítico cauteloso no Oriente Médio"
    },
    {
        "id": 25, "start": 316.80, "end": 340.70, "duration": 23.90,
        "type": "video", "source": "pixabay", "query": "military smoke explosion war",
        "desc": "Custos catastróficos de um confronto militar aberto"
    },
    {
        "id": 26, "start": 340.70, "end": 352.30, "duration": 11.60,
        "type": "video", "source": "pixabay", "query": "united nations flags international",
        "desc": "O dilema diplomático do século XXI: acordo ou impasse?"
    },
    {
        "id": 27, "start": 352.30, "end": 372.38, "duration": 20.08,
        "type": "video", "source": "pixabay", "query": "youtube subscribe bell button",
        "desc": "Interação com o espectador, comentários e inscrição"
    }
]

def fetch_wikimedia_image(query: str, dest_path: str) -> bool:
    """Download an authentic archival photograph from Wikimedia Commons."""
    url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": 5,
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "format": "json"
    }
    headers = {"User-Agent": "HistoricalDocumentaryV2/1.0 (contact: agent@antigravity.dev)"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=12)
        if resp.status_code == 200:
            pages = resp.json().get("query", {}).get("pages", {})
            for pid, p in pages.items():
                imageinfo = p.get("imageinfo", [{}])[0]
                img_url = imageinfo.get("url")
                mime = imageinfo.get("mime", "")
                if img_url and mime in ["image/jpeg", "image/png"]:
                    # Download image
                    r_img = requests.get(img_url, headers=headers, timeout=20)
                    if r_img.status_code == 200 and len(r_img.content) > 10000:
                        with open(dest_path, "wb") as f:
                            f.write(r_img.content)
                        return True
    except Exception as e:
        print(f"    [Wikimedia Error] '{query}': {e}")
    return False

def fetch_pixabay_video(query: str, dest_path: str) -> bool:
    """Download targeted 1080p video clip from Pixabay API."""
    url = "https://pixabay.com/api/videos/"
    params = {
        "key": PIXABAY_KEY,
        "q": query,
        "per_page": 5,
        "safesearch": "true"
    }
    try:
        resp = requests.get(url, params=params, timeout=12)
        if resp.status_code == 200:
            hits = resp.json().get("hits", [])
            if hits:
                vids = hits[0].get("videos", {})
                for quality in ["large", "medium", "small"]:
                    if quality in vids and vids[quality].get("url"):
                        video_url = vids[quality]["url"]
                        r_vid = requests.get(video_url, stream=True, timeout=25)
                        if r_vid.status_code == 200:
                            with open(dest_path, "wb") as f:
                                for chunk in r_vid.iter_content(chunk_size=1024 * 1024):
                                    if chunk:
                                        f.write(chunk)
                            return os.path.exists(dest_path) and os.path.getsize(dest_path) > 50000
    except Exception as e:
        print(f"    [Pixabay Error] '{query}': {e}")
    return False

def source_all_media() -> Dict[int, str]:
    """Source all 27 scene assets from scratch with zero old media reuse."""
    print("=" * 70)
    print("  PHASE 1: DEEP SEMANTIC MULTI-SOURCE MEDIA SOURCING")
    print("=" * 70)
    
    asset_map = {}
    
    for scene in SCENE_SPEC:
        s_id = scene["id"]
        s_type = scene["type"]
        s_source = scene["source"]
        s_query = scene["query"]
        s_desc = scene["desc"]
        
        filename = f"scene_{s_id:02d}.jpg" if s_type == "image" else f"scene_{s_id:02d}.mp4"
        dest_dir = IMAGENS_DIR if s_type == "image" else VIDEOS_DIR
        dest_path = os.path.join(dest_dir, filename)
        
        print(f"  [Scene {s_id:02d}] {s_type.upper()} ({s_source.upper()}): '{s_query}'")
        print(f"     Context: {s_desc}")
        
        success = False
        if s_source == "wikimedia":
            success = fetch_wikimedia_image(s_query, dest_path)
            # If primary query fails, try broader fallback
            if not success:
                fallback_q = s_query.split()[0] + " Iran history"
                print(f"     -> Retrying Wikimedia fallback: '{fallback_q}'")
                success = fetch_wikimedia_image(fallback_q, dest_path)
        else:
            success = fetch_pixabay_video(s_query, dest_path)
            if not success:
                # Broad fallback
                fallback_q = s_query.split()[0]
                print(f"     -> Retrying Pixabay fallback: '{fallback_q}'")
                success = fetch_pixabay_video(fallback_q, dest_path)
                
        if success and os.path.exists(dest_path):
            size_mb = os.path.getsize(dest_path) / (1024 * 1024)
            print(f"     -> Successfully Saved: {filename} ({size_mb:.2f} MB)")
            asset_map[s_id] = dest_path
        else:
            raise RuntimeError(f"Critical failure: Unable to source valid asset for Scene {s_id:02d} ({s_query})")
            
    print("\n  [SUCCESS] All 27 scenes freshly sourced and verified!\n")
    return asset_map

def process_scenes_to_clips(asset_map: Dict[int, str]) -> List[str]:
    """Process all assets to standardized 1920x1080@30fps yuv420p clips."""
    print("=" * 70)
    print("  PHASE 2: CINEMATIC PROCESSING & KEN BURNS MOTION")
    print("=" * 70)
    
    os.makedirs(TEMP_CLIPS_DIR, exist_ok=True)
    processed_clips = []
    
    total = len(SCENE_SPEC)
    for idx, scene in enumerate(SCENE_SPEC, 1):
        s_id = scene["id"]
        s_type = scene["type"]
        s_dur = scene["duration"]
        src_path = asset_map[s_id]
        
        clip_name = f"clip_{s_id:02d}.mp4"
        out_clip_path = os.path.join(TEMP_CLIPS_DIR, clip_name)
        frames = max(1, int(round(s_dur * 30)))
        
        print(f"  [{idx:02d}/{total:02d}] Rendering Clip {s_id:02d} ({s_type.upper()}, {s_dur:.2f}s)...")
        
        if s_type == "image":
            # Cinematic Ken Burns zoompan filter with high-res pre-scale
            zoom_speed = 0.0008
            vf = (
                f"scale=1920:1080:force_original_aspect_ratio=increase,"
                f"crop=1920:1080,"
                f"zoompan=z='min(zoom+{zoom_speed},1.25)':d={frames}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"s=1920x1080:fps=30,format=yuv420p"
            )
            cmd = [
                FFMPEG_PATH, "-y",
                "-loop", "1",
                "-i", src_path,
                "-vf", vf,
                "-t", str(s_dur),
                "-c:v", "libx264",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-an",
                out_clip_path
            ]
        else:
            # Video normalization: strip audio, pad & scale to 1080p, loop seamlessly
            vf = (
                "scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
                "fps=30,format=yuv420p"
            )
            cmd = [
                FFMPEG_PATH, "-y",
                "-stream_loop", "-1",
                "-i", src_path,
                "-t", str(s_dur),
                "-vf", vf,
                "-c:v", "libx264",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-an",
                out_clip_path
            ]
            
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            print(f"    [FFmpeg Error]: {res.stderr[-300:]}")
            raise RuntimeError(f"Failed to render clip for Scene {s_id}")
            
        processed_clips.append(out_clip_path)
        
    print(f"\n  [SUCCESS] All 27 standardized clips rendered in {TEMP_CLIPS_DIR}.\n")
    return processed_clips

def render_master_documentary(clips: List[str]):
    """Concatenate clips, merge narration audio, and burn stylized Whisper subtitles."""
    print("=" * 70)
    print("  PHASE 3: MASTER TIMELINE ASSEMBLY & SUBTITLE BURN-IN")
    print("=" * 70)
    
    # 1. Generate concat manifest in pure UTF-8 without BOM
    with open(MANIFEST_PATH, "w", encoding="utf-8", newline="\n") as f:
        for clip in clips:
            safe_clip = os.path.abspath(clip).replace("\\", "/")
            f.write(f"file '{safe_clip}'\n")
            
    # 2. Escape subtitle path for Windows FFmpeg
    escaped_srt = os.path.abspath(SRT_PATH).replace("\\", "/")
    if len(escaped_srt) >= 2 and escaped_srt[1] == ":":
        escaped_srt = escaped_srt[0] + "\\:" + escaped_srt[2:]
        
    subtitle_filter = (
        f"subtitles='{escaped_srt}':"
        f"force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        f"BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=35'"
    )
    
    cmd = [
        FFMPEG_PATH, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", MANIFEST_PATH,
        "-i", AUDIO_PATH,
        "-vf", subtitle_filter,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        OUTPUT_MASTER
    ]
    
    print(f"  Rendering Master Output: {OUTPUT_MASTER}")
    print(f"  Preset: fast | CRF: 20 | Subtitle Font: 24 (White, Outline=2, Shadow=1)")
    
    start_render = time.time()
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"  [FFmpeg Master Error]: {res.stderr[-400:]}")
        raise RuntimeError("Master documentary rendering failed.")
        
    render_time = time.time() - start_render
    size_mb = os.path.getsize(OUTPUT_MASTER) / (1024 * 1024)
    
    print("\n" + "=" * 70)
    print("  MASTER HISTORICAL DOCUMENTARY V2 COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print(f"  Output Path:   {OUTPUT_MASTER}")
    print(f"  Output Size:   {size_mb:.2f} MB")
    print(f"  Render Time:   {render_time:.1f}s ({render_time/60:.2f} min)")
    print("=" * 70 + "\n")

def main():
    start_all = time.time()
    
    # 1. Source all media
    asset_map = source_all_media()
    
    # 2. Process all clips with Ken Burns and video normalization
    clips = process_scenes_to_clips(asset_map)
    
    # 3. Assemble and burn subtitles
    render_master_documentary(clips)
    
    total_time = time.time() - start_all
    print(f"Total Pipeline Runtime: {total_time:.1f}s ({total_time/60:.2f} min)")

if __name__ == "__main__":
    main()
