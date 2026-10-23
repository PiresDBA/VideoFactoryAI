import os
import requests

API_KEY = "58184749-b92df4cd039274d2c7a6aac7a"
base_dir = r"C:\Projeto_Ira_EUA"
videos_dir = os.path.join(base_dir, "videos")
os.makedirs(videos_dir, exist_ok=True)

# Mapeamento de termos de busca em inglês (a API do Pixabay funciona melhor em inglês) para cada cena
buscas_cenas = {
    1: "usa and iran flags political tension",
    2: "global news headlines television studio",
    3: "geopolitics world map diplomacy",
    4: "middle east city skyline tehran",
    5: "cold war historical archive 1950s",
    6: "oil pipeline desert energy industry",
    7: "historical vintage archival footage 1950s",
    8: "iranian shah pahlavi historical portrait",
    9: "protest crowd street riot",
    10: "islamic revolution crowd 1979",
    11: "us embassy hostage crisis archive",
    12: "white house washington dc politics",
    13: "middle east military alliance israel",
    14: "nuclear laboratory science research",
    15: "oil tanker cargo ship ocean aerial",
    16: "modern tehran city traffic",
    17: "government official speech podium",
    18: "economic sanctions inflation money",
    19: "scientific laboratory technology",
    20: "gas station fuel price inflation",
    21: "stock market financial crash global",
    22: "military map strategy war room",
    23: "humanitarian crisis refugees walking",
    24: "diplomats meeting table negotiation",
    25: "news anchor reporting studio",
    26: "youtube subscribe bell button animation",
    27: "youtube end screen subscribe channel"
}

print("Iniciando download automático de vídeos reais via Pixabay...")

for cena_id, query in buscas_cenas.items():
    nome_arquivo = f"cena_{cena_id:02d}.mp4"
    dest_path = os.path.join(videos_dir, nome_arquivo)
    
    # Se o vídeo já existir, pula para economizar tempo
    if os.path.exists(dest_path):
        print(f"[{cena_id}/27] {nome_arquivo} já existe. Pulando...")
        continue

    print(f"[{cena_id}/27] Buscando '{query}' para {nome_arquivo}...")
    url = f"https://pixabay.com/api/videos/?key={API_KEY}&q={requests.utils.quote(query)}&per_page=3"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get("hits"):
                # Pega a versão 'large' ou 'medium' do primeiro vídeo encontrado
                video_url = data["hits"][0]["videos"]["medium"]["url"]
                video_data = requests.get(video_url).content
                with open(dest_path, "wb") as f:
                    f.write(video_data)
                print(f"  -> Sucesso! Salvo como {nome_arquivo}")
            else:
                print(f"  -> Nenhum vídeo encontrado para '{query}'. Usando fallback genérico.")
                # Fallback para um termo genérico de política
                fallback_url = f"https://pixabay.com/api/videos/?key={API_KEY}&q=politics&per_page=3"
                fb_resp = requests.get(fallback_url).get("hits", [])
                if fb_resp:
                    video_url = fb_resp[0]["videos"]["medium"]["url"]
                    with open(dest_path, "wb") as f:
                        f.write(requests.get(video_url).content)
                    print(f"  -> Fallback salvo como {nome_arquivo}")
        else:
            print(f"  -> Erro na API do Pixabay (Status: {response.status_code})")
    except Exception as e:
        print(f"  -> Erro de conexão na cena {cena_id}: {e}")

print("\nDownload de todas as cenas concluído com sucesso!")
