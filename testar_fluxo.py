import os
import json

base_dir = r"C:\Projeto_Ira_EUA"
json_path = os.path.join(base_dir, "cenas.json")
videos_dir = os.path.join(base_dir, "videos")

with open(json_path, "r", encoding="utf-8-sig") as f:
    cenas = json.load(f)

print(f"Total de cenas no JSON: {len(cenas)}")

arquivos_videos = os.listdir(videos_dir)
print(f"Arquivos encontrados na pasta videos/: {arquivos_videos}")

for cena in cenas:
    c_id = cena["id"]
    c_tipo = cena["tipo"]
    c_arquivo = cena["arquivo"]
    
    if c_tipo == "video":
        fp = os.path.join(videos_dir, c_arquivo)
        existe = os.path.exists(fp)
        print(f"Cena {c_id:02d} -> Arquivo esperado: {c_arquivo} | Existe? {existe}")
