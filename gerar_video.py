import os
import subprocess

base_dir = r"C:\Projeto_Ira_EUA"
audio_path = os.path.join(base_dir, "narracao.mp3")
videos_dir = os.path.join(base_dir, "videos")
output_dir = os.path.join(base_dir, "saida")
ffmpeg_path = os.path.join(base_dir, "ffmpeg.exe")

os.makedirs(output_dir, exist_ok=True)

videos = sorted([os.path.join(videos_dir, f) for f in os.listdir(videos_dir) if f.endswith(".mp4")])

if not videos:
    print("Erro: Nenhum vídeo encontrado na pasta 'videos'.")
    exit()

print(f"Encontrados {len(videos)} clipes de vídeo. Criando arquivo de lista para o FFmpeg...")

lista_txt = os.path.join(base_dir, "lista_videos.txt")
with open(lista_txt, "w", encoding="utf-8") as f:
    for v in videos:
        f.write(f"file '{v.replace(chr(92), '/')}'\n")

print("Processando montagem com FFmpeg local...")
cmd = [
    ffmpeg_path, "-y",
    "-f", "concat",
    "-safe", "0",
    "-i", lista_txt,
    "-i", audio_path,
    "-c:v", "libx264",
    "-preset", "ultrafast",
    "-c:a", "aac",
    "-shortest",
    os.path.join(output_dir, "video_final.mp4")
]

resultado = subprocess.run(cmd)

if resultado.returncode == 0:
    print("\nSUCESSO! Vídeo gerado em:")
    print(f"-> {os.path.join(output_dir, 'video_final.mp4')}")
else:
    print("\nOcorreu um erro durante a renderização.")
