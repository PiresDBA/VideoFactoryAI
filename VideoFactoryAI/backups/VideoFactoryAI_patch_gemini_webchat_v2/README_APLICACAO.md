PATCH CORRETIVO V2 — VideoFactoryAI / Gemini Webchat
====================================================

Objetivo
--------
Corrige o fluxo L4 de geração e avaliação visual com Gemini Web sem substituir
Pollinations/PIL por placeholders e preservando a pesquisa L1-L3, cache e a
versão do media_research_agent.py que contém a configuração explícita de FFmpeg/ffprobe.

O que este patch faz
--------------------
- Mantém o media_research_agent.py baseado na versão com caminhos de FFmpeg/ffprobe.
- Para imagens estáticas, usa avaliação visual Gemini por padrão; a imagem real é anexada.
- Não aceita imagem se a avaliação visual falhar, não retornar JSON válido ou ficar abaixo da nota mínima.
- L4 usa apenas geração real via Gemini; se falhar, a cena fica pendente.
- A auditoria de duplicatas tenta substituta via Gemini e avaliação visual; se falhar, marca pendente.
- Corrige captura de imagens do Gemini para ignorar URLs já presentes antes do pedido, reduzindo risco de reutilizar uma imagem antiga.
- Evita aceitar resposta JSON antiga como se fosse a resposta da avaliação atual.
- Saída normalizada para 1920x1080; modificadores de estilo só são enviados se VF_IMAGE_STYLE e/ou VF_IMAGE_STYLE_MODIFIERS estiverem definidos.
- Inclui instalador com backup automático e script de reversão.

Arquivos instalados na raiz do projeto
--------------------------------------
- media_research_agent.py
- gemini_webchat_image.py

Antes de instalar
-----------------
1. Feche o VideoFactoryAI e qualquer execução do pipeline.
2. Extraia esta pasta para dentro de C:\Fabrica-de-videos\VideoFactoryAI (ou indique a raiz com -ProjectRoot).
3. Execute o instalador a partir de um PowerShell. Ele cria backup datado e valida sintaxe.
4. Na primeira execução, o Gemini pode abrir uma janela para login manual. O perfil padrão é
   %USERPROFILE%\.videofactory_gemini_profile. Não compartilhe a pasta de perfil.
5. Teste com 1–2 cenas antes da produção completa.

Comando de instalação
--------------------
Set-Location "C:\Fabrica-de-videos\VideoFactoryAI\VideoFactoryAI_patch_gemini_webchat_v2"
.\instalar_patch.ps1

Configuração opcional
---------------------
VF_GEMINI_PROFILE_DIR       Pasta do perfil persistente dedicado
VF_GEMINI_URL               URL da interface Gemini
VF_GEMINI_TIMEOUT           Timeout em segundos (padrão 180)
VF_GEMINI_VISUAL_EVAL=0     Desliga avaliação visual Gemini e usa o avaliador legado
VF_IMAGE_EVAL_MIN_SCORE     Nota mínima de aprovação (padrão 65)
VF_IMAGE_STYLE              Estilo visual opcional
VF_IMAGE_STYLE_MODIFIERS    Modificadores técnicos opcionais

Limitações
----------
- A automação depende da interface web do Gemini, que pode mudar sem aviso.
- Login, disponibilidade de geração de imagens e limites da conta Google continuam necessários.
- O patch não foi testado numa sessão autenticada real do Gemini; o teste sintático é local.
- Vídeos continuam usando o avaliador legado; a avaliação visual Gemini deste patch é para imagens estáticas.
- Se a avaliação Gemini falhar, a imagem estática é rejeitada por segurança; isso pode deixar cenas pendentes.
