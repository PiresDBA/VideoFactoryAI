---
name: projeto-ira-eua-patterns
description: "Use when developing, extending, or maintaining the automated documentary video pipeline in Projeto_Ira_EUA, especially before modifying SRT parsing, sourcing historical/geopolitical media, applying FFmpeg Ken Burns motion effects, or assembling burned-in subtitle timelines"
metadata:
  version: "1.0.0"
  source: local-repo-analysis
  analyzed_components: "video-pipeline-v2"
---

# Projeto Ira EUA — Documentary Video Automation Patterns

This skill encodes the architectural conventions, file-handling rules, and media-processing patterns for the automated historical documentary video pipeline in `Projeto_Ira_EUA`.

## Code Architecture & Modular Division

The repository follows a clean, single-responsibility modular structure:

- **`modules/srt_parser.py`**:
  - Parses OpenAI Whisper SRT files into structured subtitle blocks.
  - Measures total audio duration using `ffmpeg -i`.
  - Builds dynamic, gapless scene timelines (`start`, `end`, `duration`) that map subtitle blocks into cohesive narrative scenes (averaging 10–18 seconds).
  - Eliminates mid-sentence visual cuts by snapping cuts to natural speech boundaries.

- **`modules/media_engine.py`**:
  - Implements multi-source semantic media sourcing.
  - Routes archival historical requests (1953 Coup, Mossadegh, Shah Pahlavi, Khomeini, 1979 Hostage Crisis) to **Wikimedia Commons API**.
  - Routes modern geopolitical footage (naval warships, White House, nuclear facilities, oil tankers, refineries, gas stations, UN flags) to **Pixabay API**.
  - Enforces zero-hallucination fallbacks and integrity checks (>15 KB per asset).

- **`modules/visual_processor.py`**:
  - Standardizes all media to **1920x1080 @ 30fps (`yuv420p`)**.
  - Applies cinematic **Ken Burns zoompan** (`scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='min(zoom+0.0008,1.25)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30,format=yuv420p`) on static historical images.
  - Normalizes video clips: strips audio (`-an`), letterboxes/pads without distortion, and loops seamlessly (`-stream_loop -1`) to match the scene's exact duration.

- **`modules/composer.py`**:
  - Generates `concat_list.txt` in pure UTF-8 without BOM with LF newlines (`\n`).
  - Escapes Windows paths for FFmpeg filtergraphs (`C\:/...`).
  - Integrates `narracao.mp3` with burned-in stylized subtitles (`narracao.srt`).

- **`gerador_documentario_v2.py` & `pipeline_ecc.py`**:
  - Master pipeline orchestrators.

## Critical File Conventions & Formats

1. **Deterministic File I/O for External Binaries**:
   - Always open text files read by FFmpeg (like `concat_list.txt`) with `encoding="utf-8"` and `newline="\n"` (no BOM).
   - Use forward slashes in file paths inside concat manifests: `file 'C:/Projeto_Ira_EUA/temp_clips/clip_01.mp4'`.

2. **Windows Path Escaping for FFmpeg Filters**:
   - In FFmpeg filtergraphs (such as `-vf subtitles='...'`), escape the drive letter colon and use forward slashes:
     `subtitles='C\:/Projeto_Ira_EUA/narracao.srt':force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=35'`

3. **Media Directory Roles**:
   - `videos/`: Sequentially named stock video clips (`scene_01.mp4`, etc.).
   - `imagens/`: Sequentially named high-resolution archival photographs (`scene_06.jpg`, etc.).
   - `temp_clips/`: Normalized, 1080p@30fps intermediate clips ready for concatenation (`clip_01.mp4`, etc.).
   - `saida/`: Master documentary video renders (`documentario_perfeito_v2.mp4`).

## Multi-Source Sourcing Guidelines

- **Never use generic filler videos**: Avoid stock footage that does not directly match the spoken entity.
- **Historical Milestones**: For events prior to the 1990s, prefer verified public-domain historical photographs from Wikimedia Commons over AI-generated or unrelated modern footage.
- **Modern Geopolitical Context**: Use Pixabay video searches with narrow, context-specific English terms (`american flag waving`, `military warship naval`, `white house washington dc`, `nuclear power plant cooling towers`, `oil tanker cargo ship sea`).
