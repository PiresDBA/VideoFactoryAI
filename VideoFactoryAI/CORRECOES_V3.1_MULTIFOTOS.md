# Correções para Sistema de Revisão de Mídia Local

## Versão 3.1 - Suporte a Múltiplas Fotos + Queries em Português

### Data: 27 de Outubro de 2026

---

## 🐛 Bugs Corrigidos

### 1. **Bug do min_local_images (CRÍTICO)**
**Problema**: Após processar todas as cenas, o sistema continuava pedindo mais fotos até atingir o mínimo configurado (ex: 150 imagens).

**Causa**: A configuração `min_local_images` forçava o sistema a solicitar imagens adicionais mesmo após o usuário já ter revisado todas as cenas.

**Solução**: 
- Quando a revisão manual está ativa, `min_local_images` é ignorado
- O usuário tem controle total sobre quantas fotos selecionar por cena
- Adicionada mensagem informativa quando o mínimo é ignorado

**Local da correção**: `media_research_agent.py` → `source_all()` (linha ~2790)

---

### 2. **Suporte a Múltiplas Fotos por Cena**
**Problema**: O sistema só permitia selecionar UMA foto por cena.

**Solução**: 
- A GUI agora retorna uma **lista de caminhos** (JSON array) em vez de "aprovar"/"rejeitar"
- O agente processa todas as fotos selecionadas e salva cada uma
- Todas as fotos são armazenadas em `local_assets_by_scene[scene_id]`
- Cada foto recebe um nome sequencial: `cena_01.jpg`, `cena_01_photo2.jpg`, etc.

**Alterações**:
- `agent.py` → `_request_local_media_review()`: Agora aceita JSON array
- `videofactory_gui.py` → `_handle_local_media_review_event()`: Envia JSON array
- `media_research_agent.py` → `_try_local_image()`: Processa múltiplos paths

---

### 3. **Processamento de Múltiplas Imagens no Vídeo**
**Problema**: Mesmo que múltiplas fotos fossem selecionadas, apenas a primeira era usada no vídeo.

**Solução**:
- Adicionada função `_process_multi_image_scene()` no `visual_processor.py`
- Divide a duração da cena igualmente entre todas as fotos
- Aplica efeitos Ken Burns diferentes em cada foto
- Concatena todos os clipes em um único vídeo da cena
- Fallback automático para imagem única se falhar

**Local da correção**: `modules/visual_processor.py`

---

### 4. **Queries em Inglês Dificultam Busca Local**
**Problema**: As queries estavam todas em inglês (ex: "model railroad HO scale layout"), dificultando o Ollama a encontrar imagens com nomes em português.

**Solução**:
- Criada função `_translate_query_to_portuguese()` com dicionário de termos visuais
- Modificado `_try_local_image()` para **priorizar texto em português** (campo `texto`)
- Tradução automática de termos comuns:
  - "model railroad" → "ferromodelismo"
  - "locomotive" → "locomotiva"
  - "track" → "trilho"
  - "benchwork" → "bancada construção"
  - "wood" → "madeira"
  - "plywood" → "compensado"
  - E mais 50+ termos

**Local da correção**: `media_research_agent.py`

---

## ✅ Fluxo Corrigido

### Antes (com bugs):
1. Usuário seleciona fotos para 46 cenas
2. Sistema volta para Cena 1 e pede MAIS fotos
3. Continua até atingir 150 fotos (min_local_images)
4. Queries em inglês dificultam busca
5. Apenas 1 foto é usada por cena

### Depois (corrigido):
1. Usuário seleciona fotos para 46 cenas (múltiplas por cena)
2. Sistema processa todas as fotos selecionadas
3. **IGNORA** min_local_images quando revisão manual está ativa
4. Queries traduzidas para português
5. **TODAS** as fotos selecionadas são usadas no vídeo
6. Avança automaticamente para próxima cena

---

## 🔧 Como Usar

### Configuração na GUI:
1. Marcar: **"Review local media"**
2. Selecionar: **"Local Only"** como fonte
3. Pasta: `projetos\makete_ho\imagens`
4. **IMPORTANTE**: Deixar `Min Local Images` como `0` (ou qualquer valor, será ignorado)
5. Marcar: **"Skip Ollama"** (opcional - para pular busca automática)

### Selecionando Múltiplas Fotos:
1. Para cada cena, a GUI mostra todas as imagens da pasta
2. Navegue com "Foto Anterior" / "Próxima Foto"
3. Clique em **"➕ Adicionar esta foto à cena"** para cada foto desejada
4. Clique em **"❌ Remover esta foto"** para remover
5. Clique em **"Concluir e Usar Selecionadas ➔"** quando terminar

### Resultado:
- Todas as fotos selecionadas serão processadas com efeitos Ken Burns
- As fotos serão concatenadas em um clipe único para a cena
- Duração dividida igualmente entre todas as fotos

---

## 📊 Testes Realizados

### Teste 1: Múltiplas Fotos ✅
- Callback retornando lista com 3 fotos
- Todas as 3 fotos foram salvas
- `local_assets_by_scene[1]` contém 3 paths

### Teste 2: Processamento Multi-Imagem ✅
- 3 imagens de teste processadas
- Duração: 6 segundos (2s por imagem)
- Clipe final: 6.00s ✓

### Teste 3: Tradução de Queries ✅
- "model railroad HO scale layout" → "ferromodelismo escala HO maquete"
- "locomotives cinematic documentary" → "locomotivas cinematográfico documentário"
- "wood cinematic footage" → "madeira cinematográfico filmagem"

---

## 📝 Notas Técnicas

### Protocolo de Comunicação GUI ↔ Agente:

**Antes**:
```
GUI → Agente: "aprovar\n" ou "rejeitar\n"
```

**Agora**:
```
GUI → Agente: '["C:\\path\\foto1.jpg", "C:\\path\\foto2.jpg"]\n'
```

### Prioridade de Query para Busca Local:
1. **texto** (português - texto original do roteiro)
2. **query traduzida** (tradução automática do inglês)
3. **descricao/wikimedia_q/ai_prompt** (fallback)

### Estrutura de Armazenamento:
```python
local_assets_by_scene = {
    1: ["cena_01.jpg", "cena_01_photo2.jpg", "cena_01_photo3.jpg"],
    2: ["cena_02.jpg"],
    # ...
}
```

---

## 🚀 Próximos Passos

1. **Testar fluxo completo** com GUI
2. **Verificar** se Ollama não é executado com skip_ollama
3. **Confirmar** que múltiplas fotos aparecem no vídeo final
4. **Ajustar** dicionário de tradução conforme necessário

---

## ⚠️ Importante

- **Backup criado**: branch `backup-before-filter`
- **Histórico reescrito**: chaves de API removidas via `git filter-branch`
- **Force push necessário**: `git push --force origin feature/revisao-manual-midia-local`
- **Rotacionar chaves**: OpenRouter e Groq keys expostas anteriormente

---

## 📚 Arquivos Modificados

1. `VideoFactoryAI/agent.py`
2. `VideoFactoryAI/media_research_agent.py`
3. `VideoFactoryAI/videofactory_gui.py`
4. `VideoFactoryAI/modules/visual_processor.py`
5. `VideoFactoryAI/CORRECOES_REVISAO_LOCAL.md` (este documento)
