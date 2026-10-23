import torchaudio
from f5_tts.api import F5TTS

print("Carregando o modelo F5-TTS...")
f5tts = F5TTS()

# 1. Use o áudio curto que você recortou
audio_ref = "voice/minhavoz_curta.wav"

# 2. Use APENAS a primeira frase exata correspondente ao início do áudio
texto_ref = "Olá, imagine duas nações que já foram aliadas."

# 3. Mande um texto curto e direto para teste (depois o seu harness faz isso em loop para o roteiro todo)
texto_para_gerar = "Fala pessoal, bem-vindos a mais um vídeo aqui no canal do YouTube. Testando a clonagem de voz com o F5 TTS."

arquivo_saida = "resultado_limpo.wav"

print("Gerando áudio com estabilidade...")

# Executa a inferência com parâmetros ajustados
f5tts.infer(
    ref_file=audio_ref,
    ref_text=texto_ref,
    gen_text=texto_para_gerar,
    file_wave=arquivo_saida
)

print(f"Sucesso! Verifique o arquivo: {arquivo_saida}")