"""
Master FFmpeg Assembly & Subtitle Burn-in Composer
Assembles normalized scene clips, synchronizes master narration audio, and burns stylized subtitles.
"""
import os
import subprocess
import tempfile
from typing import List, Optional, Sequence

def _ffprobe_for(ffmpeg_path: str) -> str:
    """ffprobe fica na mesma pasta do ffmpeg configurado."""
    name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    return os.path.join(os.path.dirname(ffmpeg_path), name) if os.path.dirname(ffmpeg_path) else name


def probe_duration(media_path: str, ffprobe_path: str) -> float:
    """Duração do vídeo (stream) em segundos; cai para a duração do container se não houver."""
    result = subprocess.run(
        [ffprobe_path, "-v", "error", "-show_entries",
         "stream=codec_type,duration:format=duration", "-of", "json", media_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe falhou em {media_path}: {result.stderr[-300:]}")
    import json
    data = json.loads(result.stdout or "{}")
    video = next((st for st in data.get("streams", []) if st.get("codec_type") == "video"), {})
    for value in (video.get("duration"), data.get("format", {}).get("duration")):
        try:
            if value not in (None, "", "N/A"):
                return float(value)
        except (TypeError, ValueError):
            continue
    raise RuntimeError(f"ffprobe não informou a duração de {media_path}")


def create_concat_manifest(clips: List[str], manifest_path: str) -> None:
    """Generate concat demuxer manifest in strict UTF-8 without BOM with LF newlines."""
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        for clip in clips:
            safe_clip = os.path.abspath(clip).replace("\\", "/")
            f.write(f"file '{safe_clip}'\n")

def escape_windows_path_for_ffmpeg(path_str: str) -> str:
    """Escape Windows drive letter and path for FFmpeg filtergraph."""
    clean_path = os.path.abspath(path_str).replace("\\", "/")
    # Escape colon after drive letter: C:/ -> C\:/
    if len(clean_path) >= 2 and clean_path[1] == ":":
        clean_path = clean_path[0] + "\\:" + clean_path[2:]
    return clean_path


TRANSITIONS_DEFAULT = ("fade",)


def build_transition_graph(durations: Sequence[float], transition_s: float,
                           transitions: Sequence[str] = TRANSITIONS_DEFAULT,
                           subtitle_filter: Optional[str] = None) -> str:
    """Monta o filter_complex. Entradas: [0:v] ... [N-1:v]. Saída: [vout]."""
    n = len(durations)
    if n == 0:
        raise ValueError("nenhum plano informado")
    if n == 1:
        base = f"[0:v]{_normalize_chain()}"
        return f"{base}{',' + subtitle_filter if subtitle_filter else ''}[vout]"
    half = transition_s / 2.0
    too_short = [i for i, d in enumerate(durations) if d <= transition_s]
    if too_short:
        raise ValueError(f"planos mais curtos que a transição ({transition_s}s): {too_short}")

    parts = []
    for i in range(n):
        head = half if i > 0 else 0.0
        tail = half if i < n - 1 else 0.0
        pad = []
        if head:
            pad.append(f"start_mode=clone:start_duration={head:.4f}")
        if tail:
            pad.append(f"stop_mode=clone:stop_duration={tail:.4f}")
        chain = f"[{i}:v]{_normalize_chain()}"
        if pad:
            chain += f",tpad={':'.join(pad)}"
        parts.append(f"{chain},setpts=PTS-STARTPTS[s{i}]")

    cur = "s0"
    boundary = 0.0
    for k in range(1, n):
        boundary += durations[k - 1]
        offset = boundary - half
        name = transitions[(k - 1) % len(transitions)]
        out = f"x{k}" if k < n - 1 else "xout"
        parts.append(
            f"[{cur}][s{k}]xfade=transition={name}:duration={transition_s:.4f}:offset={offset:.4f}[{out}]"
        )
        cur = out
    final = f"[{cur}]"
    if subtitle_filter:
        parts.append(f"{final}{subtitle_filter}[vout]")
    else:
        parts.append(f"{final}format=yuv420p[vout]")
    return ";".join(parts)


def _normalize_chain() -> str:
    return ("scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=yuv420p")


def assemble_with_transitions(
    clips: List[str],
    audio_path: str,
    srt_path: str,
    output_path: str,
    ffmpeg_path: str,
    transition_s: float = 0.6,
    transitions: tuple = TRANSITIONS_DEFAULT,
) -> bool:
    """Monta o master com crossfade entre todos os planos, sincronizado com a narração.

    Cada transição fica centrada na fronteira do plano. A duração total é a soma das
    durações dos planos, que precisa bater com a narração (mesma verificação de antes).
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if not clips:
        print("[FFmpeg Error] No scene clips were provided for master assembly.")
        return False
    ffprobe_path = _ffprobe_for(ffmpeg_path)
    # Cada plano pode arredondar até 1/60 s (quadros a 30 fps); a tolerância acompanha o total.
    tolerance = max(float(os.getenv("VF_DURATION_TOLERANCE", "0.5") or 0.5), len(clips) / 60.0)
    durations = [probe_duration(clip, ffprobe_path) for clip in clips]
    audio_seconds = probe_duration(audio_path, ffprobe_path)
    video_seconds = sum(durations)  # as transições são sobrepostas dentro dos planos, sem perder tempo
    print(f"  [Transições] {len(clips)} planos | transição={transition_s:.2f}s | "
          f"vídeo={video_seconds:.2f}s | narração={audio_seconds:.2f}s | "
          f"diferença={video_seconds - audio_seconds:+.2f}s")
    if abs(video_seconds - audio_seconds) > tolerance:
        shortest = sorted(zip(clips, durations), key=lambda item: item[1])[:5]
        print(f"[FFmpeg Error] Planos e narração divergem em {video_seconds - audio_seconds:+.2f}s "
              f"(tolerância {tolerance}s). Renderização cancelada para não cortar a narração.")
        for clip, seconds in shortest:
            print(f"    plano curto: {os.path.basename(clip)} = {seconds:.2f}s")
        return False

    subtitle_filter = None
    if srt_path and os.path.exists(srt_path):
        escaped_srt = escape_windows_path_for_ffmpeg(srt_path)
        subtitle_filter = (
            f"subtitles='{escaped_srt}':"
            f"force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            f"BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=35'"
        )
    graph = build_transition_graph(durations, transition_s, transitions, subtitle_filter)

    cmd = [ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error"]
    for clip in clips:
        cmd.extend(["-i", clip])
    cmd.extend(["-i", audio_path])
    cmd.extend([
        "-filter_complex", graph,
        "-map", "[vout]",
        "-map", f"{len(clips)}:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ])
    print("\n--- MASTER RENDERING IN PROGRESS (transições) ---")
    print(f"  Target: {output_path}\n")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print(f"[FFmpeg Error] Render com transições falhou: {result.stderr[-1000:]}")
        return False
    return os.path.exists(output_path) and os.path.getsize(output_path) > 1000000


def assemble_master_documentary(
    clips: List[str],
    audio_path: str,
    srt_path: str,
    output_path: str,
    ffmpeg_path: str,
    manifest_path: str
) -> bool:
    """
    Concatenate video clips, bind narration audio, optionally burn stylized subtitles,
    and render the master documentary MP4.
    If srt_path is None or doesn't exist, skips subtitle burning.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if not clips:
        print("[FFmpeg Error] No scene clips were provided for master assembly.")
        return False

    transition_s = float(os.getenv("VF_TRANSICAO_S", "0.6") or 0)
    if transition_s > 0:
        return assemble_with_transitions(clips, audio_path, srt_path, output_path, ffmpeg_path, transition_s)

    create_concat_manifest(clips, manifest_path)

    with tempfile.TemporaryDirectory(prefix="videofactory-normalized-") as normalized_dir:
        normalized_clips = []
        normalize_filter = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,"
            "setsar=1,fps=30,format=yuv420p,setpts=PTS-STARTPTS"
        )
        for index, clip in enumerate(clips, 1):
            normalized_clip = os.path.join(normalized_dir, f"clip_{index:02d}.mp4")
            normalize_command = [
                ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                clip,
                "-vf",
                normalize_filter,
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-an",
                normalized_clip,
            ]
            print(f"  [Normalize] Clip {index:02d}/{len(clips):02d}")
            result = subprocess.run(
                normalize_command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
            if (
                result.returncode != 0
                or not os.path.isfile(normalized_clip)
                or os.path.getsize(normalized_clip) < 1000
            ):
                print(
                    f"[FFmpeg Error] Failed to normalize clip {clip}: "
                    f"{result.stderr[-1000:]}"
                )
                return False
            normalized_clips.append(normalized_clip)

        # Verifica durações antes de renderizar: o -shortest abaixo corta a narração
        # em silêncio se o vídeo for mais curto. Aqui a falha aparece com o clipe culpado.
        tolerance = float(os.getenv("VF_DURATION_TOLERANCE", "0.5") or 0.5)
        ffprobe_path = _ffprobe_for(ffmpeg_path)
        audio_seconds = probe_duration(audio_path, ffprobe_path)
        rows = []
        for source, normalized in zip(clips, normalized_clips):
            rows.append((os.path.basename(source), probe_duration(source, ffprobe_path),
                         probe_duration(normalized, ffprobe_path)))
        video_seconds = sum(norm for _, _, norm in rows)
        drift = [(name, src, norm) for name, src, norm in rows if abs(norm - src) > 0.1]
        print(f"  [Duração] vídeo={video_seconds:.2f}s | narração={audio_seconds:.2f}s | "
              f"diferença={video_seconds - audio_seconds:+.2f}s")
        for name, src, norm in drift:
            print(f"  [Duração] {name}: original={src:.2f}s, normalizado={norm:.2f}s")
        if abs(video_seconds - audio_seconds) > tolerance:
            shortest = sorted(rows, key=lambda r: r[2])[:5]  # clipes mais curtos do conjunto
            print(f"[FFmpeg Error] Vídeo e narração divergem em {video_seconds - audio_seconds:+.2f}s "
                  f"(tolerância {tolerance}s). Renderização cancelada para não cortar a narração.")
            for name, src, norm in shortest:
                print(f"    clipe curto: {name} original={src:.2f}s normalizado={norm:.2f}s")
            return False

        normalized_manifest = os.path.join(normalized_dir, "concat.txt")
        create_concat_manifest(normalized_clips, normalized_manifest)
        cmd = [
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            normalized_manifest,
            "-i",
            audio_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]

        if srt_path and os.path.exists(srt_path):
            escaped_srt = escape_windows_path_for_ffmpeg(srt_path)
            subtitle_filter = (
                f"subtitles='{escaped_srt}':"
                f"force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                f"BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=35',format=yuv420p"
            )
            cmd.extend(["-vf", subtitle_filter, "-c:v", "libx264", "-preset", "fast", "-crf", "20"])
        else:
            cmd.extend(["-c:v", "copy"])

        cmd.extend([
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            output_path,
        ])

        print("\n--- MASTER RENDERING IN PROGRESS ---")
        print(f"  Target: {output_path}")
        print(f"  Encoding preset: fast | CRF: 20 | Audio: AAC 192k\n")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace"
        )

        for line in iter(process.stdout.readline, ""):
            line_s = line.strip()
            if "frame=" in line_s or "time=" in line_s or "fps=" in line_s:
                print(f"  [Render Progress] {line_s}", end="\r")
            elif "Error" in line_s or "fatal" in line_s:
                print(f"\n  [FFmpeg Warning/Error] {line_s}")

        process.stdout.close()
        returncode = process.wait()
        print("\n")

        if returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000000:
            return True
        return False
