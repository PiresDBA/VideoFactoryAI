# Correções para Revisão de Mídia Local

## Problema
A interface gráfica de seleção de imagens locais não estava abrindo quando o modo `--review-local-media` era ativado.

## Causa
A função `_request_local_media_review` foi alterada para retornar uma lista (para suportar seleção múltipla), mas a GUI espera que retorne um booleano (`True`/`False`).

## Correções Aplicadas

### 1. `agent.py` - `_request_local_media_review`

**Antes:**
```python
def _request_local_media_review(scene: dict, candidate: dict) -> list:
    choices = []
    while True:
        choice = input().strip().lower()
        if choice in {"fim", "finish", "end", "terminar"}:
            break
        elif choice in {"aprovar", "a"}:
            choices.append(candidate["path"])
        # ...
    return choices
```

**Depois:**
```python
def _request_local_media_review(scene: dict, candidate: dict):
    review = {
        "scene_id": scene.get("id"),
        "scene_text": str(scene.get("texto") or scene.get("descricao") or ""),
        "image_path": str(candidate["path"]),
        "image_title": str(candidate.get("title") or Path(candidate["path"]).name),
        "score": float(candidate["score"]),
    }
    if os.environ.get("VF_LOCAL_MEDIA_REVIEW_GUI") == "1":
        print(LOCAL_MEDIA_REVIEW_MARKER + json.dumps(review), flush=True)
    else:
        print("Digite 'aprovar' ou 'rejeitar': ", end="", flush=True)
    answer = sys.stdin.readline().strip().casefold()
    if answer in {"approve", "aprovar", "a", "yes", "y"}:
        return True
    if answer in {"reject", "rejeitar", "r", "no", "n"}:
        return False
    raise RuntimeError("Resposta inválida")
```

### 2. `media_research_agent.py` - `_try_local_image`

**Antes:**
```python
chosen_paths = review_callback(scene, match)
if chosen_paths is None or isinstance(chosen_paths, bool):
    return None
if isinstance(chosen_paths, (str, Path)):
    chosen_paths = [str(chosen_paths)]
primary_path = Path(chosen_paths[0])
```

**Depois:**
```python
result = review_callback(scene, match)

# Se retornou booleano (modo GUI antigo): True = aprovado, False = rejeitado
if isinstance(result, bool):
    if not result:
        return None
    chosen_paths = [str(match["path"])]
# Se retornou None ou lista vazia
elif result is None:
    return None
else:
    chosen_paths = result

# Se por acaso retornar apenas uma string (caminho único), converte para lista
if isinstance(chosen_paths, (str, Path)):
    chosen_paths = [str(chosen_paths)]

primary_path = Path(chosen_paths[0])
```

## Como Testar

### 1. Testar com GUI (interface gráfica)

```bash
cd C:\Fabrica-de-videos\VideoFactoryAI
C:\Docling\venv\Scripts\python.exe videofactory_gui.py
```

Configurações na GUI:
- Script: `roteiros\makete_ho.txt`
- ✅ Marcar "Review local media"
- Fonte: "Local Only"
- Pasta: `projetos\makete_ho\imagens`
- Clicar em Executar

### 2. Testar com terminal

```bash
C:\Docling\venv\Scripts\python.exe C:\Fabrica-de-videos\VideoFactoryAI\agent.py C:\Fabrica-de-videos\roteiros\makete_ho.txt --media-source-mode local_only --local-media-folder "C:\Fabrica-de-videos\projetos\makete_ho\imagens" --review-local-media --skip-ollama
```

No terminal, você verá prompts como:
```
[REVISÃO LOCAL] Cena 1:
  Imagem: locomotiva_maquete.jpg
  Score: 0.85
  Caminho: C:\...\locomotiva_maquete.jpg
  Trecho: A locomotiva cruza a ponte...
  Digite 'aprovar' ou 'rejeitar':
```

Digite:
- `aprovar` ou `a` para aprovar a imagem
- `rejeitar` ou `r` para rejeitar

### 3. Testar código diretamente

```bash
C:\Docling\venv\Scripts\python.exe C:\Fabrica-de-videos\VideoFactoryAI\test_e2e_flow.py
```

Este teste verifica:
- Callback retornando `True` (aprovação via GUI)
- Callback retornando lista (terminal)
- Callback retornando `False` (rejeição)

## Fluxo de Comunicação GUI ↔ Agent

1. **Agent** inicia cena e chama `_request_local_media_review`
2. **Agent** imprime: `__LOCAL_MEDIA_REVIEW__{"scene_id": 1, "image_path": "...", ...}`
3. **GUI** lê stdout do agente e detecta o marker `__LOCAL_MEDIA_REVIEW__`
4. **GUI** parseia o JSON e mostra a imagem ao usuário
5. **Usuário** clica em "Aprovar" ou "Rejeitar"
6. **GUI** envia `"aprovar\n"` ou `"rejeitar\n"` via stdin do agente
7. **Agent** lê a resposta e retorna `True` ou `False`
8. **Agent** processa a imagem conforme decisão

## Verificações Automatizadas

Execute os testes unitários para verificar se tudo funciona:

```bash
cd C:\Fabrica-de-videos\VideoFactoryAI
C:\Docling\venv\Scripts\python.exe -m unittest tests.test_local_media_review -v
```

Testes esperados como PASS:
- `test_review_callback_emits_gui_event_and_reads_approval`
- `test_gui_sends_review_decision_to_pipeline`
- `test_cli_exposes_local_media_review_flag`
- `test_media_source_modes_allow_only_the_selected_source_families`

## Solução de Problemas

### GUI não abre
- Verifique se o Tkinter está instalado: `C:\Docling\venv\Scripts\python.exe -c "import tkinter; print('OK')"`
- Verifique se há erros de importação no terminal

### Imagem não aparece na GUI
- Verifique se o caminho da imagem é válido
- Verifique se o arquivo existe

### Agente não recebe resposta da GUI
- Verifique se a GUI está rodando antes de executar o agente
- Verifique se o stdout/stderr estão sendo capturados corretamente

### Timeout no terminal
- O agente está esperando input mas você não digitou nada
- Digite `aprovar` ou `rejeitar` e pressione Enter

## Notas Técnicas

- **GUI usa**: `LOCAL_MEDIA_REVIEW_MARKER + JSON` para comunicação
- **GUI retorna**: `True` (aprovar) ou `False` (rejeitar)
- **Terminal retorna**: `True` (aprovar) ou `False` (rejeitar)
- **Ambos funcionam**: O código lida com ambos os formatos

Para suportar seleção múltipla no futuro, seria necessário:
1. Modificar a GUI para permitir seleção múltipla
2. Retornar lista de paths em vez de bool
3. Atualizar `_try_local_image` para lidar com múltiplos paths