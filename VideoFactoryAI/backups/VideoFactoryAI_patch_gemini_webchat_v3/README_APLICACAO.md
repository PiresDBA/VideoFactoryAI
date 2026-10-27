# VideoFactoryAI — Gemini Recovery Patch v3

## O que este patch muda
- Substitui `gemini_webchat_image.py` por uma versão que prioriza o download explícito da imagem recém-gerada, valida assinatura/tamanho e normaliza para 1920x1080.
- Melhora o envio da imagem para avaliação visual, validando o arquivo e aguardando o preview do anexo.
- Atualiza somente o bloco L4 em `media_research_agent.py`: até 3 tentativas de geração; após reprovação, usa o motivo retornado pelo Gemini como feedback para a próxima tentativa.
- Preserva L1-L3, cache, deduplicação, relatório e pesquisa de vídeos já existentes.

## Limites importantes
- O patch não garante que o Gemini Web mantenha os mesmos seletores de interface para sempre.
- A tentativa adaptativa em L4 regenera imagens no Gemini. Ela ainda não reexecuta automaticamente as buscas L1-L3 com a justificativa visual; isso deve ser uma etapa separada depois de validar este patch.
- A busca de vídeos L1 já existe no projeto (Pixabay, Pexels, Wikimedia, Internet Archive e YouTube conforme configuração). Este patch não altera licenças nem baixa vídeos de fontes adicionais.
- Não execute novamente as 46 cenas para o primeiro teste.

## Instalação
1. Faça backup do projeto inteiro.
2. Extraia esta pasta `VideoFactoryAI_patch_gemini_webchat_v3` diretamente dentro de `C:\Fabrica-de-videos\VideoFactoryAI`, ao lado de `media_research_agent.py`.
3. Abra PowerShell nessa pasta extraída.
4. Se necessário, execute:
   `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
5. Execute:
   `.\instalar_patch.ps1`

O instalador cria backup dos dois arquivos antes de editar e roda `py_compile` com `C:\Docling\venv\Scripts\python.exe`. Se a sintaxe falhar, restaura os arquivos automaticamente.

## Primeiro teste
- Não rode o roteiro inteiro.
- Faça um teste isolado de geração/avaliação ou execute um roteiro curto de 1–2 cenas, se o projeto tiver esse mecanismo.
- Confira que uma imagem gerada é baixada, abre como JPEG 1920x1080 e que uma reprovação dispara uma nova tentativa com o motivo no log.
- Para limitar tentativas: ` $env:VF_GEMINI_RETRIES = "2" ` antes de iniciar.
- Para mudar timeout: ` $env:VF_GEMINI_TIMEOUT = "180" `.

## Reversão
Execute `.everter_patch.ps1` e informe o caminho da pasta `_backup_gemini_patch_...` criado pelo instalador.
