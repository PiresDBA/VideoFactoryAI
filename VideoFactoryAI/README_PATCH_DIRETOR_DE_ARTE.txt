# Patch do Diretor de Arte — VideoFactoryAI

## Conteúdo
- `agent.py`: adiciona `--art-director off|standard|strict`, auditoria de timeline e relatório consolidado.
- `image_validator_agent.py`: registra cenas sem asset como reprovadas, preserva a mídia anterior quando uma substituição falha, gera relatório detalhado e avalia três amostras temporais de vídeos quando Gemini está configurado.
- `AGENT.md`: documentação de uso e limites.

## Instalação segura (Windows)
1. Feche qualquer execução do VideoFactoryAI.
2. Faça uma cópia de segurança dos arquivos atuais `agent.py`, `image_validator_agent.py` e `AGENT.md`.
3. Copie os três arquivos deste pacote para a pasta do projeto, substituindo os existentes.
4. Primeiro teste em modo padrão com um roteiro curto:
   `python agent.py roteiro_teste.txt --art-director standard`
5. Confira `art_director_report.json` dentro da pasta do projeto gerado.
6. Só depois experimente `--art-director strict`; esse modo interrompe antes do render quando encontra problemas não resolvidos.

## Modos
- `standard` (padrão): audita e registra; não bloqueia o render.
- `strict`: bloqueia o render se houver falha de validação, problema de timeline ou validador indisponível.
- `off`: desliga o Diretor de Arte explicitamente.

## Limitações importantes
- O ZIP original fornecido não contém a pasta `modules/` nem todo o ambiente/dependências. Portanto, foi possível verificar a sintaxe dos dois arquivos alterados, mas não executar um documentário completo nem confirmar integração end-to-end.
- A avaliação visual semântica depende de `google-genai` e de `GEMINI_API_KEY` (ou configuração equivalente já existente). Sem isso, o código recorre à heurística baseada na consulta de busca, que é mais fraca e não consegue confirmar com segurança o conteúdo visual.
- A checagem roteiro/transcrição usa cobertura lexical indicativa quando `--subtitles` está ativo; não é uma prova semântica de que a narração inteira corresponde ao roteiro.
- O Diretor de Arte não garante que sempre encontrará uma mídia correta: problemas sem solução são registrados e, em modo `strict`, impedem a renderização.
