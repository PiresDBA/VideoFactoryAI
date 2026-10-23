import os
import json
import subprocess

base_dir = r"C:\Projeto_Ira_EUA"
audio_path = os.path.join(base_dir, "narracao.mp3")
videos_dir = os.path.join(base_dir, "videos")
imagens_dir = os.path.join(base_dir, "imagens")
output_dir = os.path.join(base_dir, "saida")
ffmpeg_path = os.path.join(base_dir, "ffmpeg.exe")
json_path = os.path.join(base_dir, "cenas.json")
srt_path = os.path.join(base_dir, "narracao.srt")

os.makedirs(output_dir, exist_ok=True)

if not os.path.exists(json_path):
    print("Erro: Arquivo cenas.json não encontrado.")
    exit()

with open(json_path, "r", encoding="utf-8-sig") as f:
    cenas = json.load(f)

print(f"Lendo {len(cenas)} cenas do roteiro...")

list_file_path = os.path.join(base_dir, "concat_list.txt")
processed_clips = []

for cena in cenas:
    c_id = cena["id"]
    c_tipo = cena["tipo"]
    c_arquivo = cena["arquivo"]
    c_duracao = cena["duracao"]
    
    if c_tipo == "video":
        file_path = os.path.join(videos_dir, c_arquivo)
    else:
        file_path = os.path.join(imagens_dir, c_arquivo)
        
    if not os.path.exists(file_path):
        fallback_v = [os.path.join(videos_dir, x) for x in os.listdir(videos_dir) if x.endswith(".mp4")]
        if fallback_v:
            file_path = fallback_v[0]
        else:
            continue

    temp_output = os.path.join(base_dir, f"temp_cena_{c_id:02d}.mp4")
    
    # Se o clipe temporário já foi gerado na rodada anterior, aproveita para economizar tempo
    if os.path.exists(temp_output):
        processed_clips.append(temp_output)
        continue

    vf_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p"

    cmd_cena = [
        ffmpeg_path, "-y",
        "-t", str(c_duracao),
        "-i", file_path,
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-an",
        temp_output
    ]
    
    print(f"Processando Cena {c_id:02d} / {len(cenas)}...")
    resultado_cena = subprocess.run(cmd_cena)
    if resultado_cena.returncode == 0 and os.path.exists(temp_output):
        processed_clips.append(temp_output)

if not processed_clips:
    print("Erro crítico: Nenhum clipe processado.")
    exit()

with open(list_file_path, "w", encoding="utf-8", newline="\n") as f:
    for clip in processed_clips:
        f.write(f"file '{clip.replace(chr(92), '/')}'\n")

print("\n--- JUNTANDO TUDO E APLICANDO LEGENDA ---")

# Tratamento correto do caminho do SRT para o filtro do FFmpeg no Windows (escapando C: como C\:)
srt_escaped = srt_path.replace('\\', '/').replace(':', '\\:')
video_filter_final = f"subtitles='{srt_escaped}':force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=1,Alignment=2'"

final_output = os.path.join(output_dir, "documentario_completo.final.mp4")

cmd_final = [
    ffmpeg_path, "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", list_file_path,
    "-i", audio_path,
    "-vf", video_filter_final,
    "-c:v", "libx264",
    "-preset", "ultrafast",
    "-c:a", "aac",
    "-b:a", "192k",
    "-shortest",
    final_output
]

print("Renderizando vídeo final com legendas...")
resultado_final = subprocess.run(cmd_final)

if resultado_final.returncode == 0:
    print(f"\nSUCESSO TOTAL! Documentário gerado em:")
    print(f"-> {final_output}")
else:
    print("\nErro na renderização final.")

for clip in processed_clips:
    if os.path.exists(clip):
        os.remove(clip)
if os.path.exists(list_file_path):
    os.remove(list_file_path)
