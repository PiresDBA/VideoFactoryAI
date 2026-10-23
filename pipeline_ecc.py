"""
=============================================================================
DOCUMENTARY AUTOMATION PIPELINE (ECC ARCHITECTURE)
Historical Documentary: The US-Iran Conflict (6-10 min full documentary)
=============================================================================
Orchestrates:
  1. Timestamp-Aligned Whisper SRT Parsing & Dynamic Scene Segmentation
  2. Semantic Pixabay Media Sourcing (Videos & Archival Images)
  3. Cinematic Ken Burns & 1080p Video Normalization
  4. Master FFmpeg Concat, Audio Binding & Stylized Subtitle Burn-in
=============================================================================
"""
import os
import sys
import time
import json

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from modules.srt_parser import parse_srt, get_audio_duration, build_scene_timeline
from modules.media_engine import ensure_media_for_scenes
from modules.visual_processor import process_all_scenes
from modules.composer import assemble_master_documentary

def audit_workspace():
    """Verify core inputs and binaries exist."""
    print("=" * 70)
    print("  PHASE 0: WORKSPACE AUDIT & ENVIRONMENT INITIALIZATION")
    print("=" * 70)
    
    paths = {
        "ffmpeg": os.path.join(BASE_DIR, "ffmpeg.exe"),
        "audio": os.path.join(BASE_DIR, "narracao.mp3"),
        "srt": os.path.join(BASE_DIR, "narracao.srt")
    }
    
    for key, path in paths.items():
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing essential file: {key} ({path})")
        size_mb = os.path.getsize(path) / (1024 * 1024)
        print(f"  [OK] {key.upper():<8}: {os.path.basename(path)} ({size_mb:.2f} MB)")
        
    videos_dir = os.path.join(BASE_DIR, "videos")
    imagens_dir = os.path.join(BASE_DIR, "imagens")
    output_dir = os.path.join(BASE_DIR, "saida")
    temp_clips_dir = os.path.join(BASE_DIR, "temp_clips")
    
    for d in [videos_dir, imagens_dir, output_dir, temp_clips_dir]:
        os.makedirs(d, exist_ok=True)
        
    print(f"  [OK] Working directories verified: videos/, imagens/, saida/, temp_clips/\n")
    return paths

def main():
    start_total_time = time.time()
    
    print("\n" + "#" * 70)
    print("  PRODUCTION-GRADE HISTORICAL DOCUMENTARY PIPELINE - ECC FRAMEWORK")
    print("#" * 70 + "\n")
    
    # 0. Audit Workspace
    paths = audit_workspace()
    ffmpeg_path = paths["ffmpeg"]
    audio_path = paths["audio"]
    srt_path = paths["srt"]
    
    videos_dir = os.path.join(BASE_DIR, "videos")
    imagens_dir = os.path.join(BASE_DIR, "imagens")
    output_dir = os.path.join(BASE_DIR, "saida")
    temp_clips_dir = os.path.join(BASE_DIR, "temp_clips")
    manifest_path = os.path.join(BASE_DIR, "concat_list.txt")
    final_output_path = os.path.join(output_dir, "documentario_completo_ecc.mp4")
    
    # 1. SRT Parsing & Dynamic Scene Segmentation
    print("=" * 70)
    print("  PHASE 1: TIMESTAMP-ALIGNED SRT PARSER & SCENE SEGMENTATION")
    print("=" * 70)
    audio_duration = get_audio_duration(ffmpeg_path, audio_path)
    print(f"  Narration Audio Duration: {audio_duration:.2f}s ({audio_duration/60:.2f} minutes)")
    
    srt_blocks = parse_srt(srt_path)
    print(f"  Parsed Whisper SRT Subtitle Blocks: {len(srt_blocks)}")
    
    scenes = build_scene_timeline(srt_blocks, audio_duration)
    total_timeline = sum(s["duration"] for s in scenes)
    print(f"  Generated Dynamic Scene Timeline: {len(scenes)} scenes")
    print(f"  Total Scene Duration: {total_timeline:.2f}s (Synchronized: {abs(total_timeline - audio_duration) < 0.05})")
    
    # Save planned scenes to JSON for auditability
    plan_path = os.path.join(BASE_DIR, "cenas_planejadas.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(scenes, f, indent=2, ensure_ascii=False)
    print(f"  Saved planned timeline to {os.path.basename(plan_path)}\n")
    
    # 2. Intelligent Semantic Media Sourcing
    print("=" * 70)
    print("  PHASE 2: INTELLIGENT SEMANTIC MEDIA SOURCING (PIXABAY ENGINE)")
    print("=" * 70)
    asset_map = ensure_media_for_scenes(scenes, videos_dir, imagens_dir)
    print(f"  All {len(asset_map)} scene assets verified and ready in videos/ and imagens/.\n")
    
    # 3. Advanced Visual Processing & Motion Engineering
    print("=" * 70)
    print("  PHASE 3: ADVANCED VISUAL PROCESSING & KEN BURNS MOTION")
    print("=" * 70)
    processed_clips = process_all_scenes(scenes, asset_map, temp_clips_dir, ffmpeg_path)
    print(f"  Normalized and motion-processed {len(processed_clips)} clips (1080p @ 30fps yuv420p).\n")
    
    # 4. Master FFmpeg Assembly & Subtitle Burn-in
    print("=" * 70)
    print("  PHASE 4: MASTER FFMPEG ASSEMBLY & SUBTITLE BURN-IN")
    print("=" * 70)
    success = assemble_master_documentary(
        processed_clips,
        audio_path,
        srt_path,
        final_output_path,
        ffmpeg_path,
        manifest_path
    )
    
    if not success:
        print("\n  [CRITICAL ERROR] Master rendering failed.")
        sys.exit(1)
        
    elapsed = time.time() - start_total_time
    file_size_mb = os.path.getsize(final_output_path) / (1024 * 1024)
    
    print("=" * 70)
    print("  DOCUMENTARY PIPELINE EXECUTION SUCCESSFUL!")
    print("=" * 70)
    print(f"  Master File:     {final_output_path}")
    print(f"  File Size:       {file_size_mb:.2f} MB")
    print(f"  Total Duration:  {audio_duration:.2f} seconds ({audio_duration/60:.2f} min)")
    print(f"  Total Time:      {elapsed:.1f} seconds ({elapsed/60:.2f} min)")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
