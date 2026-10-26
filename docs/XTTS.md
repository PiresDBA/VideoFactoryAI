# XTTS-v2 — Narração com voz clonada (GPU)

O VideoFactoryAI usa o **XTTS-v2** para narrar os documentários com a sua própria voz.
A síntese roda em um ambiente conda separado (`xtts`), porque o modelo exige
Python 3.10 + torch 2.3.1+cu118 + transformers 4.41.2 — versões que conflitam
com o ambiente principal do projeto.

## Como funciona

```
agent.py  (Python 3.12, ambiente principal)
   └── generate_voice(engine="xtts")
         └── VideoFactoryAI/xtts_engine.py
               └── subprocess: C:\Users\Pires\miniconda3\envs\xtts\python.exe
                     └── voice/xtts/xtts_worker.py
                           └── XTTS-v2 (carrega 1x) → WAV
               └── ffmpeg → narracao.mp3
```

- O modelo é carregado **uma única vez** por narração (não por trecho).
- O roteiro é dividido em trechos curtos (padrão: 240 caracteres), respeitando fim de frase.
- Os trechos são concatenados com 220 ms de pausa e normalizados em pico (0.95).
- Se o XTTS falhar, o pipeline cai automaticamente para **edge-tts** (a menos que
  `VF_XTTS_SEM_FALLBACK=1`).

## Como ativar

No `VideoFactoryAI/config.yaml`:

```yaml
tts:
  engine: xtts
  xtts_python: C:\Users\Pires\miniconda3\envs\xtts\python.exe
  xtts_speaker_wav: voice/xtts/ale.wav
  xtts_use_cuda: true
```

Ou por linha de comando:

```powershell
python VideoFactoryAI/agent.py --topic "Segunda Guerra Mundial" --duration 15 `
  --channel historia --tts-engine xtts
```

## Teste rápido

```powershell
python VideoFactoryAI/xtts_engine.py
```

Saída esperada: `voice/xtts/teste_pipeline.wav` (~5 s de áudio).

## Requisitos da amostra de voz

| Item | Recomendação |
|------|--------------|
| Duração | 10 a 30 segundos |
| Conteúdo | fala contínua, sem música nem ruído |
| Formato | WAV mono, 24 kHz ou superior |
| Tom | o mesmo que você quer na narração (calmo, documental) |

A amostra atual é `voice/xtts/ale.wav`.

## Variáveis de ambiente

| Variável | Efeito |
|----------|--------|
| `VF_XTTS_PYTHON` | Caminho do python do ambiente conda `xtts` |
| `VF_XTTS_SPEAKER` | WAV de referência da voz |
| `VF_XTTS_LANGUAGE` | Idioma (`pt`) |
| `VF_XTTS_USE_CUDA` | `1` / `0` para forçar GPU ou CPU |
| `VF_XTTS_WORKER` | Caminho alternativo do `xtts_worker.py` |
| `VF_XTTS_TIMEOUT` | Limite de segurança em segundos (padrão: 7200) |

## Desempenho medido (GTX 1060 6 GB)

| Etapa | Tempo |
|-------|-------|
| Carregar modelo | ~33 s |
| 5,3 s de áudio | ~8,5 s (RTF ≈ 1,46) |

Estimativa: **~1,5× o tempo do áudio**. Uma narração de 15 minutos leva cerca de
22 minutos de síntese. Rode com a GPU livre (feche jogos/navegadores pesados).

## Solução de problemas

| Sintoma | Causa provável | Correção |
|---------|----------------|----------|
| `python do ambiente conda 'xtts' não encontrado` | caminho errado | ajuste `tts.xtts_python` |
| `CUDA indisponível — caindo para CPU` | driver/GPU ocupada | verifique `nvidia-smi` |
| `worker XTTS retornou código 6` | erro no trecho | veja a mensagem acima no log |
| Áudio sai como WAV | ffmpeg não encontrado | instale/aponte o ffmpeg do projeto |

## Teste de integridade do ambiente

```powershell
C:\Users\Pires\miniconda3\envs\xtts\python.exe -c "import torch, TTS; print(torch.__version__, torch.cuda.is_available())"
```

Esperado: `2.3.1+cu118 True`
