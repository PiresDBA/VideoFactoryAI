# VideoFactoryAI — Patch corretivo do avaliador Gemini v4

## O que corrige
- Remove o exemplo de JSON inválido `true|false` e o exemplo de nota zero, que podia induzir respostas inconsistentes.
- Define escala explícita de 0–100 e exige coerência entre nota e justificativa.
- Extrai objetos JSON com `JSONDecoder`, incluindo respostas envolvidas em Markdown ou texto extra, escolhendo o último objeto válido.
- Registra resposta bruta, campos normalizados e erros em `logs/gemini_eval_debug.jsonl` para diagnosticar casos como `score=10` com justificativa dizendo “perfeitamente”.
- Mantém a regra de segurança: `approved=true` não passa se a nota ficar abaixo de `VF_IMAGE_EVAL_MIN_SCORE` (padrão 65).
- Não altera `media_research_agent.py`, L1–L3, nem o fluxo L4 de até três tentativas.
- Não aprova automaticamente por palavras positivas; a avaliação visual continua necessária.

## Instalação
1. Faça backup manual do projeto se possível.
2. Extraia a pasta `VideoFactoryAI_patch_gemini_eval_v4` diretamente dentro de `C:\Fabrica-de-videos\VideoFactoryAI`, de modo que fique ao lado de `media_research_agent.py`.
3. Abra PowerShell e execute:
   ```powershell
   Set-Location "C:\Fabrica-de-videos\VideoFactoryAI\VideoFactoryAI_patch_gemini_eval_v4"
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\instalar_patch.ps1
   ```
4. O instalador cria backup e verifica sintaxe com `C:\Doclingenv\Scripts\python.exe`.

## Após testar
Se a avaliação voltar a dar nota incompatível com a justificativa, envie as últimas linhas de `logs\gemini_eval_debug.jsonl`. O arquivo contém o texto da resposta do Gemini e metadados da avaliação.

## Reversão
Execute `reverter_patch.ps1` e cole o caminho da pasta `_backup_gemini_eval_v4_...` mostrada pelo instalador.

## Limitações
O patch foi verificado por compilação sintática local do módulo. Não foi possível executar o navegador Gemini autenticado nesta máquina de empacotamento; a geração real deve ser validada no ambiente Windows do projeto.
