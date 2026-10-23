import os
import subprocess

print("Iniciando varredura do projeto...")

base_dir = r"C:\Projeto_Ira_EUA"
audio_path = os.path.join(base_dir, "narracao.mp3")
videos_dir = os.path.join(base_dir, "videos")
imagens_dir = os.path.join(base_dir, "imagens")
output_dir = os.path.join(base_dir, "saida")

if not os.path.exists(audio_path):
    print("Erro: Arquivo narracao.mp3 não encontrado!")
    exit()

print("Áudio principal localizado com sucesso.")
print("Próximo passo: Adicione seus vídeos (ex: cena_01.mp4, cena_02.mp4) na pasta 'videos' ou imagens na pasta 'imagens'.")
print("Tudo pronto para a automação da montagem.")
