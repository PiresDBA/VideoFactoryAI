# 📌 Instruções do Projeto — VideoFactoryAI

## ⚠️ REGRA DE OURO 1: Leia o manual ANTES de qualquer alteração

**Antes de escrever/editar QUALQUER arquivo no projeto, leia o arquivo [`manual.md`](manual.md) na raiz.**

O `manual.md` contém:
- A arquitetura completa do sistema
- O pipeline de produção (11 passos)
- As regras de ouro do projeto
- O que já está implementado e o que está incompleto
- As dependências e configurações

**Não pule essa leitura.** Mesmo que você ache que já sabe, o manual pode ter informações atualizadas que você não tem.

---

## ⚠️ REGRA DE OURO 2: Atualize o manual após cada alteração

Após **QUALQUER** alteração no sistema (código, config, dependência, pipeline, fontes, etc.), você **DEVE** atualizar o `manual.md` refletindo a mudança.

Para cada tipo de mudança, atualize a seção correspondente do manual (ver [REGRA DE MANUTENÇÃO DO MANUAL](manual.md#-regra-de-manutenção-do-manual)).

---

## ⚠️ REGRA DE OURO 3: Adicione uma linha no histórico de versões

Sempre que alterar o sistema, **adicione uma nova linha** na tabela de histórico de versões no final do `manual.md` com:
- Versão (incrementar)
- Data
- O que mudou
- Arquivos afetados
- Autor

---

## Resumo das regras inegociáveis

1. **Não invente dados** — só fatos verificáveis das fontes
2. **Não repita imagens** — cada cena usa mídia diferente
3. **Fontes livres de direitos** — só as 4 aprovadas (reshot, negativespace, freestocks, newoldstock)
4. **WebChat é exclusivo** — sem fallback local silencioso
5. **Legendas são opcionais** — padrão é sem legendas
6. **Manual atualizado** — sempre, após cada mudança

---

**Antes de começar qualquer tarefa neste projeto, leia o `manual.md`.**
