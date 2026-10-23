##ffmpeg -i minhavoz.mp4 -vn -acodec pcm_s16le -ar 22050 -ac 1 minhavoz.wav


from TTS.api import TTS
import torch

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Usando dispositivo: {device}")

# Carrega o modelo
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

# Texto de teste curto com gírias ou pontuações que você costuma usar
texto_teste = "Fala pessoal, beleza? Testando a clonagem de voz para o canal do YouTube. Vamos ver se ficou idêntico."

# Executa a geração
tts.tts_to_file(
    text=texto_teste,
    speaker_wav="voices/minha_voz.wav",
    language="pt",
    file_path="teste_output.wav"
)
print("Áudio de teste gerado com sucesso! Verifique o arquivo teste_output.wav")