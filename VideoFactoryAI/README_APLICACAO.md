# Busca e geração de imagens no VideoFactoryAI

## Fluxo atual

- As consultas das cenas priorizam o assunto do roteiro. Para roteiros de ferromodelismo, o tema ferroviário em escala HO acompanha as cenas mesmo quando a narração usa uma metáfora ou menciona outro objeto incidentalmente.
- L1–L3 buscam primeiro vídeos/imagens com verificações de licença; as fontes de imagem aplicam filtros locais por metadados. O modo YouTube `cc` verifica metadados completos e baixa somente vídeos com licença reutilizável explícita.
- L4 tenta Gemini até o limite configurado. Se a sessão falhar, a imagem não for recuperada ou for reprovada, tenta CapCut Dreamina e depois Copilot.
- Cada imagem gerada precisa ser baixada como arquivo novo e passar pelas verificações do Gemini. Imagens estáticas com score acima de 85 são aceitas automaticamente e não passam por uma segunda avaliação do Diretor de Arte; abaixo desse limite, o fluxo de validação normal continua. Copilot reutiliza o perfil persistente do webchat; Gemini e Dreamina mantêm perfis próprios.
- A GUI inclui botões para calibrar os campos de prompt do Gemini, Dreamina e Copilot. Calibração confere acesso e seletor; não gera imagem nem consome cota.

## Arquivos de legenda

O Whisper transcreve a narração em português brasileiro e salva `narracao.srt` dentro da pasta do projeto. Na GUI, escolha entre:

- **Gerar SRT e incluir no vídeo**: mantém o comportamento de queimar as legendas no vídeo final.
- **Gerar somente SRT da narração existente**: exige o roteiro original e uma narração já criada para esse projeto. Regenera apenas a legenda PT-BR; não gera voz, pesquisa imagens nem renderiza o vídeo.
- **Não gerar legendas**: não cria nem inclui SRT.

Para enviar uma faixa ao YouTube, use o arquivo `.srt` como legenda separada no YouTube Studio; ela não precisa estar gravada nos pixels do vídeo. O YouTube não exige que o criador forneça três idiomas. Inglês e espanhol podem ser adicionados como faixas traduzidas no futuro; por enquanto, a GUI gera apenas PT-BR.

O botão para escolher roteiro abre primeiro a pasta `ROOT_DIR/roteiros`.

## YouTube e direitos de uso

`--youtube-mode cc` pesquisa mais resultados, usa runtime JavaScript do yt-dlp quando disponível e relata quantos candidatos não tinham licença explícita, metadados ou relevância. A rotina só baixa conteúdo com licença reutilizável declarada. `authorized`/`both` aceitam um arquivo local apenas após confirmação do usuário.

A busca Google Imagens existe como função auxiliar, mas não participa automaticamente do pipeline: o filtro Creative Commons da página de busca não comprova a licença da imagem original para uso comercial.

## Verificação e limites

Verificações offline incluem o planejamento das 46 cenas do roteiro HO, filtros de metadados, pesquisa YouTube simulada, exclusão de imagens antigas e compilação de sintaxe. Elas não confirmam login ou geração em tempo real. Use os botões de calibração na GUI e faça uma produção curta para confirmar que as contas têm acesso e que cada site ainda expõe os controles esperados. O avaliador continua rejeitando imagens sem confirmação visual.
