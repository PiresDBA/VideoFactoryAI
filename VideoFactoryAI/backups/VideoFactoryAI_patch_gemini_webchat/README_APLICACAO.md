# Patch conservador — geração e avaliação visual via Gemini Webchat

## O que altera
- Usa a interface web do Gemini para pedir imagens reais e recuperar os bytes do arquivo.
- Anexa o arquivo de imagem ao Gemini na avaliação visual; não envia apenas o caminho local.
- Salva imagens geradas em 1920×1080, sem desenhar texto ou cartões artificiais.
- Remove Pollinations/PIL como fallback da geração L4 neste fluxo. Se o Gemini falhar, a cena fica pendente e não recebe uma imagem falsa.
- Estilos extras passam a ser opcionais via `VF_IMAGE_STYLE` e `VF_IMAGE_STYLE_MODIFIERS`.
- Mantém a pesquisa de vídeos/imagens reais e os caminhos de cache existentes.

## Conteúdo
- `media_research_agent.py`: versão modificada baseada no arquivo atual fornecido.
- `gemini_webchat_image.py`: integração Playwright independente com a interface web do Gemini para geração e avaliação. Ela não altera a API textual de `webchat_bridge.py`; usa perfil de navegador dedicado para evitar quebrar o bridge existente.
- `README_APLICACAO.md`: estas instruções.

## Instalação segura
1. Feche o VideoFactoryAI.
2. Faça backup de `media_research_agent.py` e de qualquer `gemini_webchat_image.py` existente.
3. Copie os dois arquivos do ZIP para a pasta raiz `C:\Fabrica-de-videos\VideoFactoryAI`.
4. Confirme que o ambiente tem `playwright` e `Pillow` instalados. Se necessário, instale no venv correto:
   `C:\Docling\venv\Scripts\python.exe -m pip install playwright Pillow`
5. Se o Chromium do Playwright não estiver instalado:
   `C:\Docling\venv\Scripts\python.exe -m playwright install chromium`
6. Na primeira execução, o patch abrirá uma janela do Gemini. Faça login manualmente na conta Google. O perfil persistente fica em `%USERPROFILE%\.videofactory_gemini_profile` por padrão.
7. Rode um teste com 1–2 cenas antes da produção completa.

## Configuração opcional
- `VF_GEMINI_PROFILE_DIR`: perfil de navegador persistente dedicado.
- `VF_GEMINI_TIMEOUT`: tempo máximo de espera, em segundos (padrão 180).
- `VF_GEMINI_VISUAL_EVAL=0`: desliga explicitamente a avaliação visual Gemini e volta ao avaliador legado. O padrão é `1`.
- `VF_IMAGE_EVAL_MIN_SCORE`: nota mínima para aprovar (padrão 65).
- `VF_IMAGE_STYLE`: modificador visual opcional.
- `VF_IMAGE_STYLE_MODIFIERS`: modificadores técnicos opcionais.

## Limitações e honestidade dos testes
- Foram verificados a sintaxe Python dos arquivos e os pontos de integração estáticos.
- Não foi possível testar uma sessão autenticada real do Gemini nesta execução. A UI do Gemini pode mudar; a integração falha explicitamente se não conseguir recuperar uma imagem real ou anexar bytes para avaliação.
- A avaliação visual é aplicada a imagens estáticas. Vídeos continuam usando o avaliador legado nesta versão.
- A janela do Gemini é aberta em navegador visível; não use o mesmo diretório de perfil em duas instâncias simultâneas.
- Nenhuma imagem sintética é criada para substituir uma geração que falhou.
